from pathlib import Path

from app.agent import (
    AgentState,
    ToolName,
    run_extract_ocr,
    run_extract_pdf_text,
    run_generate_explanations,
    run_identify_and_validate,
    run_request_user_confirmation,
    run_retrieve_knowledge,
)
from app.generation import ExplanationStatus
from app.schemas import ExtractionMethod, ParameterStatus, TaskStatus
from tests.helpers import render_pdf


def _make_state(file_path: Path) -> AgentState:
    return AgentState(
        task_id="3f2b8c1e-6a52-4d7e-9a0c-1b2d3e4f5a6b",
        file_path=str(file_path),
        filename=file_path.name,
    )


def test_extract_pdf_text_reads_native_pdf_and_fails_on_empty_scan(tmp_path):
    pdf = tmp_path / "bilan.pdf"
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
    state = _make_state(pdf)
    res_ok = run_extract_pdf_text(state)

    assert res_ok.success is True
    assert state.extraction_method == ExtractionMethod.pdf_text
    assert "Hémoglobine" in state.raw_text

    # Cas simulation d'un PDF scanné sans couche texte : ne bascule PAS tout seul vers OCR
    scan_state = _make_state(pdf)
    res_empty = run_extract_pdf_text(scan_state, pdf_reader=lambda _: "")
    assert res_empty.success is False
    assert scan_state.tried_pdf_text is True
    assert scan_state.tried_ocr is False
    assert scan_state.raw_text == ""


def test_extract_pdf_text_rejects_image_and_ocr_recovers(tmp_path):
    img = tmp_path / "scan.png"
    img.write_bytes(b"fake-image-bytes")

    state = _make_state(img)
    res_pdf = run_extract_pdf_text(state)
    assert res_pdf.success is False
    assert state.tried_pdf_text is True

    res_ocr = run_extract_ocr(
        state,
        ocr_reader=lambda _: {
            "text": "Hémoglobine : 13,5 g/dL (réf. : 12,0 - 16,0)",
            "method": "ocr",
        },
    )
    assert res_ocr.success is True
    assert state.extraction_method == ExtractionMethod.ocr
    assert state.tried_ocr is True


def test_identify_and_request_confirmation_on_missing_unit(tmp_path):
    pdf = tmp_path / "unite_absente.pdf"
    render_pdf(
        pdf,
        "table1",
        True,
        [
            {
                "name_printed": "Hématocrite",
                "value": 46.0,
                "unit": None,
                "reference_min": 37.0,
                "reference_max": 47.0,
            }
        ],
    )
    state = _make_state(pdf)
    assert run_extract_pdf_text(state).success is True

    val_res = run_identify_and_validate(state)
    assert val_res.success is True
    assert state.validated_parameters[0].status == ParameterStatus.not_analyzed
    assert len(state.uncertainties) == 1
    assert state.uncertainties[0].field == "unit"

    q_res = run_request_user_confirmation(state)
    assert q_res.success is True
    assert state.status == TaskStatus.waiting_for_user
    assert state.pending_question is not None
    assert state.pending_question.question_id == "q-001"
    assert state.pending_question.options[-1] == "je ne sais pas"

    task = state.to_task()
    assert task.status == TaskStatus.waiting_for_user
    assert task.pending_question.code == "HCT"


def test_retrieve_and_generate_fallback_when_no_index(tmp_path):
    pdf = tmp_path / "gly.pdf"
    render_pdf(
        pdf,
        "lines",
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
    state = _make_state(pdf)
    run_extract_pdf_text(state)
    run_identify_and_validate(state)

    ret_res = run_retrieve_knowledge(state, knowledge_index=None)
    assert ret_res.success is True
    assert state.knowledge_searched is True
    assert state.retrieved_passages == []

    gen_res = run_generate_explanations(state, generator=None)
    assert gen_res.success is True
    assert state.generation_result is not None
    assert (
        state.generation_result.parameter_explanations[0].status
        == ExplanationStatus.insufficient_sources
    )

    state.record_step(ToolName.generate_explanations, "Fin de génération", True, gen_res.summary)
    assert len(state.steps) == 1