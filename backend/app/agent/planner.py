"""Planificateurs de décision pour la boucle de l'agent LabMind."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from app.generation.llm_client import LocalLLMClient, LocalLLMError
from app.schemas import TaskStatus

from .state import AgentState, ToolName

PLANNER_SYSTEM_PROMPT = (
    "Tu es l'orchestrateur d'outils de LabMind.\n"
    "Observe l'état courant et choisis EXACTEMENT un outil parmi la liste autorisée.\n"
    'Réponds uniquement en JSON valide : {"tool": "<nom_outil>", "reason": "<courte justification>"}.'
)


class AgentDecision(BaseModel):
    """Décision produite à chaque itération avant exécution d'un outil."""

    tool: ToolName
    reason: str


@runtime_checkable
class AgentPlanner(Protocol):
    """Interface de décision : observe `AgentState` et choisit le prochain outil."""

    def decide(self, state: AgentState) -> AgentDecision:
        ...


def _has_identified_after_last_extraction(state: AgentState) -> bool:
    """Vérifie si l'identification a déjà été lancée sur le texte extrait courant."""
    last_extract_idx = -1
    last_identify_idx = -1
    for idx, step in enumerate(state.steps):
        if step.tool in (ToolName.extract_pdf_text, ToolName.extract_ocr) and step.success:
            last_extract_idx = idx
        elif step.tool == ToolName.identify_and_validate and step.success:
            last_identify_idx = idx
    return last_identify_idx > last_extract_idx and last_extract_idx != -1


def available_tools(state: AgentState) -> list[ToolName]:
    """Détermine les outils techniquement éligibles selon l'état observé."""
    if state.status in (TaskStatus.done, TaskStatus.error, TaskStatus.waiting_for_user):
        return []

    # 1. Aucun texte exploitable encore extrait
    if not state.raw_text.strip():
        candidates: list[ToolName] = []
        if not state.tried_pdf_text and Path(state.file_path).suffix.lower() == ".pdf":
            candidates.append(ToolName.extract_pdf_text)
        if not state.tried_ocr:
            candidates.append(ToolName.extract_ocr)
        return candidates or [ToolName.fail]

    # 2. Texte extrait mais identification/validation non encore effectuée sur ce texte
    if not _has_identified_after_last_extraction(state):
        return [ToolName.identify_and_validate]

    # 3. Aucun paramètre trouvé : tenter OCR en secours si seul pdf_text a été tenté
    if not state.validated_parameters:
        if not state.tried_ocr:
            return [ToolName.extract_ocr, ToolName.fail]
        return [ToolName.fail]

    # 4. Incertitudes en attente de confirmation utilisateur
    if state.unresolved_uncertainties():
        return [ToolName.request_user_confirmation]

    # 5. Recherche documentaire RAG
    if not state.knowledge_searched:
        return [ToolName.retrieve_knowledge]

    # 6. Génération d'explications sourcées (ou repli neutre)
    if state.generation_result is None:
        return [ToolName.generate_explanations]

    # 7. Fin du traitement
    return [ToolName.finish]


class ObservationStatePlanner:
    """Planificateur déterministe guidé par l'observation de l'état."""

    def decide(self, state: AgentState) -> AgentDecision:
        candidates = available_tools(state)
        if not candidates:
            return AgentDecision(
                tool=ToolName.finish,
                reason="Aucune action supplémentaire requise dans l'état courant.",
            )

        chosen = candidates[0]
        reasons = {
            ToolName.extract_pdf_text: "Document PDF reçu : tentative d'extraction du texte natif.",
            ToolName.extract_ocr: "Texte natif absent, image ou aucun paramètre détecté : bascule vers l'OCR.",
            ToolName.identify_and_validate: "Texte extrait disponible : identification et validation technique des paramètres.",
            ToolName.request_user_confirmation: "Incertitude détectée : demande de confirmation à l'utilisateur.",
            ToolName.retrieve_knowledge: "Paramètres validés : recherche des passages documentaires pertinents.",
            ToolName.generate_explanations: "Contexte documentaire prêt : génération des explications sourcées.",
            ToolName.finish: "Explications prêtes : clôture de la tâche.",
            ToolName.fail: "Impossible d'extraire un paramètre exploitable après les tentatives autorisées.",
        }
        return AgentDecision(tool=chosen, reason=reasons[chosen])


class LLMAgentPlanner:
    """Planificateur piloté par un LLM local, encadré par `available_tools`."""

    def __init__(self, llm_client: LocalLLMClient) -> None:
        self.llm_client = llm_client
        self._guard = ObservationStatePlanner()

    def _build_observation_prompt(
        self,
        state: AgentState,
        allowed: list[ToolName],
    ) -> str:
        last_steps = [
            f"{s.step_number}. {s.tool.value} (ok={s.success}) : {s.summary}"
            for s in state.steps[-4:]
        ]
        observation = {
            "filename": state.filename,
            "tried_pdf_text": state.tried_pdf_text,
            "tried_ocr": state.tried_ocr,
            "has_raw_text": bool(state.raw_text.strip()),
            "validated_parameters_count": len(state.validated_parameters),
            "unresolved_uncertainties_count": len(state.unresolved_uncertainties()),
            "knowledge_searched": state.knowledge_searched,
            "retrieved_passages_count": len(state.retrieved_passages),
            "has_generation_result": state.generation_result is not None,
            "recent_steps": last_steps,
            "allowed_tools": [tool.value for tool in allowed],
        }
        return json.dumps(observation, ensure_ascii=False, indent=2)

    def decide(self, state: AgentState) -> AgentDecision:
        allowed = available_tools(state)
        if len(allowed) <= 1:
            return self._guard.decide(state)

        prompt = self._build_observation_prompt(state, allowed)
        try:
            raw = self.llm_client.generate(PLANNER_SYSTEM_PROMPT, prompt)
        except LocalLLMError:
            return self._guard.decide(state)

        cleaned = raw.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, flags=re.DOTALL)
        if fenced:
            cleaned = fenced.group(1)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return self._guard.decide(state)

        tool_name = data.get("tool")
        reason = data.get("reason")
        allowed_values = {t.value for t in allowed}

        if tool_name not in allowed_values:
            return self._guard.decide(state)

        return AgentDecision(
            tool=ToolName(tool_name),
            reason=str(reason).strip() if reason else f"Choix LLM : {tool_name}.",
        )