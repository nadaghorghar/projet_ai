"""Orchestrateur de la boucle agentique et gestion de reprise utilisateur."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Callable

from app.generation import ExplanationGenerator
from app.identification.catalog import ACCEPTED_UNITS
from app.knowledge.retriever import FaissKnowledgeIndex
from app.schemas import (
    AnswerIn,
    ErrorInfo,
    ExtractionMethod,
    TaskStatus,
    parameter_from_dict,
)
from app.validation.analysis import analyze_parameters

from .planner import AgentPlanner, ObservationStatePlanner
from .state import AgentState, ToolName
from .tools import (
    SKIP_ANSWER_LABEL,
    ToolExecutionResult,
    run_extract_ocr,
    run_extract_pdf_text,
    run_generate_explanations,
    run_identify_and_validate,
    run_request_user_confirmation,
    run_retrieve_knowledge,
)


class InvalidQuestionStateError(Exception):
    """Levée lorsque la tâche n'attend pas cette question (futur HTTP 409)."""


class InvalidAnswerError(Exception):
    """Levée lorsque la réponse utilisateur est invalide (futur HTTP 422)."""


def _match_accepted_unit(code: str, raw_answer: str) -> str | None:
    cleaned = raw_answer.strip()
    accepted = ACCEPTED_UNITS.get(code, ())
    for candidate in accepted:
        if cleaned.lower() == candidate.lower():
            return candidate
    return None


def apply_user_answer(state: AgentState, answer_in: AnswerIn) -> AgentState:
    """Valide une réponse utilisateur et met à jour l'état sans jamais deviner."""
    if state.status != TaskStatus.waiting_for_user or state.pending_question is None:
        raise InvalidQuestionStateError(
            "Aucune question n'est actuellement en attente pour cette tâche."
        )

    question = state.pending_question
    if answer_in.question_id != question.question_id:
        raise InvalidQuestionStateError(
            f"question_id invalide ou périmé : '{answer_in.question_id}'."
        )

    raw_answer = answer_in.answer.strip()
    if not raw_answer:
        raise InvalidAnswerError("La réponse ne peut pas être vide.")

    target_uncertainty = next(
        (u for u in state.uncertainties if not u.resolved and u.code == question.code),
        None,
    )
    if target_uncertainty is None:
        raise InvalidQuestionStateError("Incertitude associée introuvable.")

    target_param = next(
        (p for p in state.raw_parameters if p.get("code") == question.code),
        None,
    )
    if target_param is None:
        raise InvalidQuestionStateError("Paramètre associé introuvable.")

    if raw_answer.lower() == SKIP_ANSWER_LABEL:
        target_uncertainty.resolved = True
        target_uncertainty.user_answer = SKIP_ANSWER_LABEL
        state.pending_question = None
        state.status = TaskStatus.processing
        state.record_step(
            tool=ToolName.request_user_confirmation,
            reason="Réponse utilisateur reçue.",
            success=True,
            summary=f"Utilisateur a répondu 'je ne sais pas' pour {question.code} : conservé en not_analyzed.",
        )
        return state

    if question.field == "unit":
        if raw_answer.lower() == "autre":
            target_uncertainty.resolved = True
            target_uncertainty.user_answer = "autre"
            target_param["reason"] = "unité non prise en charge (autre)"
            state.validated_parameters = [
                parameter_from_dict(item) for item in state.raw_parameters
            ]
            state.pending_question = None
            state.status = TaskStatus.processing
            state.record_step(
                tool=ToolName.request_user_confirmation,
                reason="Réponse utilisateur reçue.",
                success=True,
                summary=f"Unité signalée comme 'autre' pour {question.code} : conservé en not_analyzed.",
            )
            return state

        matched_unit = _match_accepted_unit(question.code, raw_answer)
        if matched_unit is None:
            raise InvalidAnswerError(
                f"Unité non reconnue pour {question.code}. Options attendues : {', '.join(question.options)}."
            )
        target_param["unit"] = matched_unit

    elif question.field in ("value", "reference_min", "reference_max"):
        numeric_str = raw_answer.replace(",", ".")
        try:
            numeric_val = float(numeric_str)
        except ValueError as exc:
            raise InvalidAnswerError(
                "Valeur numérique invalide : veuillez saisir un nombre."
            ) from exc

        if not math.isfinite(numeric_val) or numeric_val < 0:
            raise InvalidAnswerError(
                "La valeur numérique doit être un nombre positif fini."
            )
        target_param[question.field] = numeric_val

    method_value = (
        state.extraction_method.value
        if state.extraction_method is not None
        else ExtractionMethod.pdf_text.value
    )
    reanalyzed = analyze_parameters(
        state.raw_parameters,
        method=method_value,
        compute_confidence=True,
    )
    state.raw_parameters = reanalyzed
    state.validated_parameters = [parameter_from_dict(item) for item in reanalyzed]

    target_uncertainty.resolved = True
    target_uncertainty.user_answer = raw_answer
    state.pending_question = None
    state.status = TaskStatus.processing

    state.record_step(
        tool=ToolName.request_user_confirmation,
        reason="Confirmation utilisateur intégrée.",
        success=True,
        summary=f"Champ '{question.field}' confirmé pour {question.code} : paramètres ré-analysés.",
    )
    return state


class AgentOrchestrator:
    """Exécute la boucle observation -> décision -> outil -> adaptation."""

    def __init__(
        self,
        planner: AgentPlanner | None = None,
        knowledge_index: FaissKnowledgeIndex | None = None,
        generator: ExplanationGenerator | None = None,
        pdf_reader: Callable[[Path], str] | None = None,
        ocr_reader: Callable[[Path], dict] | None = None,
    ) -> None:
        self.planner: AgentPlanner = planner or ObservationStatePlanner()
        self.knowledge_index = knowledge_index
        self.generator = generator
        self.pdf_reader = pdf_reader
        self.ocr_reader = ocr_reader

    def _execute_tool(self, tool: ToolName, state: AgentState) -> ToolExecutionResult:
        if tool == ToolName.extract_pdf_text:
            return run_extract_pdf_text(state, pdf_reader=self.pdf_reader)
        if tool == ToolName.extract_ocr:
            return run_extract_ocr(state, ocr_reader=self.ocr_reader)
        if tool == ToolName.identify_and_validate:
            return run_identify_and_validate(state)
        if tool == ToolName.request_user_confirmation:
            return run_request_user_confirmation(state)
        if tool == ToolName.retrieve_knowledge:
            return run_retrieve_knowledge(state, knowledge_index=self.knowledge_index)
        if tool == ToolName.generate_explanations:
            return run_generate_explanations(state, generator=self.generator)
        if tool == ToolName.finish:
            state.status = TaskStatus.done
            return ToolExecutionResult(
                success=True,
                summary="Traitement terminé avec succès.",
            )

        ocr_failure_reason = ""
        for prev_step in reversed(state.steps):
            if prev_step.tool == ToolName.extract_ocr and not prev_step.success and prev_step.summary:
                ocr_failure_reason = prev_step.summary
                break
        if ocr_failure_reason and not state.raw_text.strip():
            error_msg = (
                f"Aucun paramètre biologique exploitable n'a pu être extrait du document ({ocr_failure_reason}). "
                "Sous Windows, vérifiez que Tesseract OCR (avec langue 'fra') est installé."
            )
        else:
            error_msg = "Aucun paramètre biologique exploitable n'a pu être extrait du document."
        state.status = TaskStatus.error
        state.error = ErrorInfo(
            code="unreadable_document",
            message=error_msg,
        )
        return ToolExecutionResult(
            success=False,
            summary=ocr_failure_reason or "Traitement interrompu : document illisible ou vide.",
        )

    def run(self, state: AgentState) -> AgentState:
        if state.status in (TaskStatus.done, TaskStatus.error):
            return state

        if state.status in (TaskStatus.received, TaskStatus.waiting_for_user):
            state.status = TaskStatus.processing

        while state.iterations < state.max_iterations:
            state.iterations += 1
            decision = self.planner.decide(state)
            result = self._execute_tool(decision.tool, state)
            state.record_step(
                tool=decision.tool,
                reason=decision.reason,
                success=result.success,
                summary=result.summary,
            )

            if state.status in (
                TaskStatus.waiting_for_user,
                TaskStatus.done,
                TaskStatus.error,
            ):
                return state

        state.status = TaskStatus.error
        state.error = ErrorInfo(
            code="internal_error",
            message="Nombre maximal d'itérations de l'agent atteint.",
        )
        return state

    def resume(self, state: AgentState, answer_in: AnswerIn) -> AgentState:
        """Applique une réponse utilisateur puis reprend l'exécution de l'agent."""
        apply_user_answer(state, answer_in)
        return self.run(state)