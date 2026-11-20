import json
from pathlib import Path

import pytest

from app.agent import (
    AgentOrchestrator,
    AgentState,
    InvalidAnswerError,
    InvalidQuestionStateError,
    LLMAgentPlanner,
    ToolName,
)
from app.generation import ExplanationStatus
from app.schemas import AnswerIn, ExtractionMethod, ParameterStatus, TaskStatus
from tests.helpers import render_pdf


def _state_for(path: Path, max_iterations: int = 12) -> AgentState:
    return AgentState(
        task_id="3f2b8c1e-6a52-4d7e-9a0c-1b2d3e4f5a6b",
        file_path=str(path),
        filename=path.name,
        max_iterations=max_iterations,
    )


def test_agent_nominal_native_pdf_flow(tmp_path):
    pdf = tmp_path / "nominal.pdf"
    render_pdf(
        pdf,
        "table1",
        True,
        [
            {
                "name_printed": "Hémoglobine",
                "value": 13.5,
                "unit": "g/dL",
                "reference_min": 12.0,
                "reference_max": 16.0,
            }
        ],
    )

    orchestrator = AgentOrchestrator()
    final_state = orchestrator.run(_state_for(pdf))

    assert final_state.status == TaskStatus.done
    assert final_state.extraction_method == ExtractionMethod.pdf_text
    assert [s.tool for s in final_state.steps] == [
        ToolName.extract_pdf_text,
        ToolName.identify_and_validate,
        ToolName.retrieve_knowledge,
        ToolName.generate_explanations,
        ToolName.finish,
    ]

    task = final_state.to_task(report_id="r-3f2b8c1e")
    assert task.status == TaskStatus.done
    assert task.report_id == "r-3f2b8c1e"
    assert task.explanations["parameter_explanations"][0]["status"] == "insufficient_sources"


def test_agent_adapts_from_empty_pdf_to_ocr(tmp_path):
    pdf = tmp_path / "scan_vide.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake-scanned")

    orchestrator = AgentOrchestrator(
        pdf_reader=lambda _: "",
        ocr_reader=lambda _: {
            "text": "Glycémie : 0,92 g/L (réf. : 0,70 - 1,10)",
            "method": "ocr",
        },
    )
    final_state = orchestrator.run(_state_for(pdf))

    assert final_state.status == TaskStatus.done
    assert final_state.extraction_method == ExtractionMethod.ocr
    assert final_state.steps[0].tool == ToolName.extract_pdf_text
    assert final_state.steps[0].success is False
    assert final_state.steps[1].tool == ToolName.extract_ocr
    assert final_state.steps[1].success is True


def test_agent_pauses_waiting_for_user_and_resumes_with_valid_unit(tmp_path):
    pdf = tmp_path / "unite_absente.pdf"
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
            }
        ],
    )

    orchestrator = AgentOrchestrator()
    paused = orchestrator.run(_state_for(pdf))

    assert paused.status == TaskStatus.waiting_for_user
    assert paused.pending_question is not None
    assert paused.pending_question.question_id == "q-001"
    assert paused.pending_question.code == "HCT"

    resumed = orchestrator.resume(paused, AnswerIn(question_id="q-001", answer="%"))

    assert resumed.status == TaskStatus.done
    assert resumed.pending_question is None
    assert resumed.validated_parameters[0].unit == "%"
    assert resumed.validated_parameters[0].status == ParameterStatus.within_reference


def test_agent_keeps_not_analyzed_when_user_answers_je_ne_sais_pas(tmp_path):
    pdf = tmp_path / "unite_absente_skip.pdf"
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
            }
        ],
    )

    orchestrator = AgentOrchestrator()
    paused = orchestrator.run(_state_for(pdf))
    resumed = orchestrator.resume(
        paused,
        AnswerIn(question_id="q-001", answer="je ne sais pas"),
    )

    assert resumed.status == TaskStatus.done
    assert resumed.validated_parameters[0].status == ParameterStatus.not_analyzed
    assert resumed.generation_result is not None
    assert (
        resumed.generation_result.parameter_explanations[0].status
        == ExplanationStatus.not_analyzed
    )


def test_agent_rejects_invalid_question_id_and_invalid_answer(tmp_path):
    pdf = tmp_path / "errors.pdf"
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
            }
        ],
    )
    orchestrator = AgentOrchestrator()
    paused = orchestrator.run(_state_for(pdf))

    with pytest.raises(InvalidQuestionStateError):
        orchestrator.resume(paused, AnswerIn(question_id="q-999", answer="%"))

    with pytest.raises(InvalidAnswerError):
        orchestrator.resume(paused, AnswerIn(question_id="q-001", answer="litres"))

    # La question reste intacte en attente après une réponse invalide (422)
    assert paused.status == TaskStatus.waiting_for_user
    assert paused.pending_question is not None


def test_agent_fails_cleanly_on_unreadable_document_and_respects_max_iterations(tmp_path):
    img = tmp_path / "vide.png"
    img.write_bytes(b"empty")

    orchestrator = AgentOrchestrator(ocr_reader=lambda _: {"text": "", "method": "ocr"})
    failed = orchestrator.run(_state_for(img))

    assert failed.status == TaskStatus.error
    assert failed.error is not None
    assert failed.error.code == "unreadable_document"

    # Vérifie la borne max_iterations
    pdf = tmp_path / "trop_court.pdf"
    render_pdf(
        pdf,
        "table1",
        True,
        [
            {
                "name_printed": "Hémoglobine",
                "value": 13.5,
                "unit": "g/dL",
                "reference_min": 12.0,
                "reference_max": 16.0,
            }
        ],
    )
    limited = orchestrator.run(_state_for(pdf, max_iterations=2))
    assert limited.status == TaskStatus.error
    assert limited.error.code == "internal_error"


def test_llm_planner_selects_tool_and_guards_against_invalid_output(tmp_path):
    class _StubPlannerLLM:
        def __init__(self):
            self.calls = 0

        def generate(self, system_prompt: str, user_prompt: str) -> str:
            self.calls += 1
            if self.calls == 1:
                return json.dumps(
                    {
                        "tool": "extract_pdf_text",
                        "reason": "Le fichier est un PDF, je tente le texte natif d'abord.",
                    }
                )
            return "outil_invalide_non_json"

    pdf = tmp_path / "llm_plan.pdf"
    render_pdf(
        pdf,
        "table1",
        True,
        [
            {
                "name_printed": "Glycémie",
                "value": 0.90,
                "unit": "g/L",
                "reference_min": 0.70,
                "reference_max": 1.10,
            }
        ],
    )
    llm = _StubPlannerLLM()
    orchestrator = AgentOrchestrator(planner=LLMAgentPlanner(llm))
    final_state = orchestrator.run(_state_for(pdf))

    assert final_state.status == TaskStatus.done
    assert final_state.steps[0].tool == ToolName.extract_pdf_text
    assert "texte natif d'abord" in final_state.steps[0].reason