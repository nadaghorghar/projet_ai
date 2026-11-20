import json
from pathlib import Path

import numpy as np

from app.agent import AgentOrchestrator, AgentState, ToolName
from app.generation import ExplanationStatus, RagExplanationGenerator
from app.knowledge import (
    FaissKnowledgeIndex,
    build_passages_from_registry,
    load_sources_registry,
)
from app.schemas import AnswerIn, ExtractionMethod, ParameterStatus, TaskStatus
from tests.helpers import render_pdf

REPO_ROOT = Path(__file__).resolve().parents[2]


class _CorpusKeywordEmbedder:
    """Encodeur hors-ligne rapide pour tester le flux complet sur le corpus réel."""

    TERMS = ("glycémie", "glucose", "cholestérol", "ldl", "hémoglobine", "créatinine")

    def _vec(self, text: str) -> np.ndarray:
        low = text.lower()
        return np.array([1.0 if t in low else 0.0 for t in self.TERMS], dtype=np.float32)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.vstack([self._vec(t) for t in texts])

    def embed_query(self, query: str) -> np.ndarray:
        return self._vec(query)


def test_agent_switches_to_ocr_when_native_pdf_has_only_header_text(tmp_path):
    pdf = tmp_path / "entete_seule.pdf"
    pdf.write_bytes(b"%PDF-1.4 scanned-body")

    # Texte natif > 30 caractères (en-tête uniquement, 0 paramètre détectable)
    orchestrator = AgentOrchestrator(
        pdf_reader=lambda _: "Laboratoire Central d'Analyses Médicales - Compte rendu",
        ocr_reader=lambda _: {
            "text": "Glycémie : 0,95 g/L (réf. : 0,70 - 1,10)",
            "method": "ocr",
        },
    )
    state = AgentState(
        task_id="task-adaptive-ocr",
        file_path=str(pdf),
        filename=pdf.name,
    )

    final_state = orchestrator.run(state)

    assert final_state.status == TaskStatus.done
    assert final_state.extraction_method == ExtractionMethod.ocr
    assert [s.tool for s in final_state.steps] == [
        ToolName.extract_pdf_text,
        ToolName.identify_and_validate,
        ToolName.extract_ocr,
        ToolName.identify_and_validate,
        ToolName.retrieve_knowledge,
        ToolName.generate_explanations,
        ToolName.finish,
    ]


def test_agent_handles_two_sequential_confirmations_and_real_corpus_rag(tmp_path):
    pdf = tmp_path / "deux_incertitudes.pdf"
    render_pdf(
        pdf,
        "table1",
        True,
        [
            {
                "name_printed": "Hématocrite",
                "value": 42.0,
                "unit": None,
                "reference_min": 37.0,
                "reference_max": 47.0,
            },
            {
                "name_printed": "Glycémie",
                "value": 0.90,
                "unit": None,
                "reference_min": 0.70,
                "reference_max": 1.10,
            },
        ],
    )

    registry = load_sources_registry(
        REPO_ROOT / "knowledge_corpus" / "metadata" / "sources_registry.json"
    )
    passages = build_passages_from_registry(
        registry,
        REPO_ROOT / "knowledge_corpus" / "sources",
    )
    index = FaissKnowledgeIndex.build(passages, _CorpusKeywordEmbedder())

    class _FaithfulLLM:
        def generate(self, system_prompt: str, user_prompt: str) -> str:
            if "GLY" in user_prompt:
                return json.dumps(
                    {
                        "status": "grounded",
                        "text": (
                            "La glycémie est l'évaluation de la concentration de "
                            "glucose dans le sang."
                        ),
                        "source_ids": ["ameli-prise-sang-2026"],
                    }
                )
            return json.dumps(
                {
                    "status": "insufficient_sources",
                    "text": "",
                    "source_ids": [],
                }
            )

    orchestrator = AgentOrchestrator(
        knowledge_index=index,
        generator=RagExplanationGenerator(_FaithfulLLM()),
    )

    # 1. Premier arrêt sur q-001 (HCT)
    state = orchestrator.run(
        AgentState(task_id="task-multi-q", file_path=str(pdf), filename=pdf.name)
    )
    assert state.status == TaskStatus.waiting_for_user
    assert state.pending_question is not None
    assert state.pending_question.question_id == "q-001"
    assert state.pending_question.code == "HCT"

    # 2. Réponse à q-001 -> deuxième arrêt immédiat sur q-002 (GLY)
    state = orchestrator.resume(state, AnswerIn(question_id="q-001", answer="%"))
    assert state.status == TaskStatus.waiting_for_user
    assert state.pending_question is not None
    assert state.pending_question.question_id == "q-002"
    assert state.pending_question.code == "GLY"

    # 3. Réponse à q-002 -> fin du traitement avec explication sourcée sur GLY
    final_state = orchestrator.resume(state, AnswerIn(question_id="q-002", answer="g/L"))
    assert final_state.status == TaskStatus.done
    assert final_state.pending_question is None

    by_code = {p.code: p for p in final_state.validated_parameters}
    assert by_code["HCT"].status == ParameterStatus.within_reference
    assert by_code["GLY"].status == ParameterStatus.within_reference

    exp_by_code = {
        e.code: e for e in final_state.generation_result.parameter_explanations
    }
    assert exp_by_code["GLY"].status == ExplanationStatus.grounded
    assert exp_by_code["GLY"].source_ids == ["ameli-prise-sang-2026"]

    task = final_state.to_task(report_id="r-demo")
    assert task.sources[0].source_id == "ameli-prise-sang-2026"