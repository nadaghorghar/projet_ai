from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate

from app.agent import AgentOrchestrator, AgentState
from app.extraction.extractor import extract_document
from app.identification.parser import identify_parameters_from_pages
from app.schemas import ParameterStatus, TaskStatus
from app.validation.analysis import analyze_parameters
from tests.helpers import render_pdf


def test_multipage_pdf_preserves_real_page_numbers_and_confidence(tmp_path):
    pdf = tmp_path / "multipage.pdf"
    st = getSampleStyleSheet()
    elements = [
        Paragraph("<b>Laboratoire Page 1</b>", st["Title"]),
        Paragraph("Hémoglobine : 13,8 g/dL (réf. : 12,0 - 16,0)", st["Normal"]),
        PageBreak(),
        Paragraph("<b>Laboratoire Page 2</b>", st["Title"]),
        Paragraph("Créatinine : 9,4 mg/L (réf. : 7,0 - 13,0)", st["Normal"]),
    ]
    SimpleDocTemplate(str(pdf), pagesize=A4).build(elements)

    extracted = extract_document(pdf)
    assert extracted["method"] == "pdf_text"
    assert len(extracted["pages"]) == 2

    state = AgentState(task_id="task-mp", file_path=str(pdf), filename=pdf.name)
    final_state = AgentOrchestrator().run(state)

    assert final_state.status == TaskStatus.done
    by_code = {p.code: p for p in final_state.validated_parameters}
    assert by_code["HGB"].evidence.page == 1
    assert by_code["CREAT"].evidence.page == 2
    assert by_code["HGB"].confidence == 0.95
    assert by_code["CREAT"].confidence == 0.95


def test_table_pdf_extracts_without_duplicates_and_computes_lower_confidence_on_missing_ref(tmp_path):
    pdf = tmp_path / "table_no_ref.pdf"
    render_pdf(
        pdf,
        "table1",
        True,
        [
            {
                "name_printed": "Plaquettes",
                "value": 240.0,
                "unit": "10^3/µL",
                "reference_min": None,
                "reference_max": None,
            }
        ],
    )

    state = AgentState(task_id="task-tab", file_path=str(pdf), filename=pdf.name)
    final_state = AgentOrchestrator().run(state)

    assert len(final_state.validated_parameters) == 1
    plt = final_state.validated_parameters[0]
    assert plt.status == ParameterStatus.reference_unavailable
    assert plt.evidence.page == 1
    assert plt.confidence == 0.85


def test_ocr_confidence_propagated_and_capped_when_not_analyzed():
    pages = [
        {
            "page": 2,
            "text": "Hémoglobine : 13,2 g/dL (12,0 - 16,0)\nHématocrite : 42,0 (37,0 - 47,0)",
            "table_rows": [],
            "ocr_confidence": 0.78,
        }
    ]
    identified = identify_parameters_from_pages(pages)
    analyzed = analyze_parameters(identified, method="ocr", compute_confidence=True)
    by_code = {p["code"]: p for p in analyzed}

    assert by_code["HGB"]["page"] == 2
    assert by_code["HGB"]["confidence"] == 0.78
    assert by_code["HCT"]["status"] == "not_analyzed"
    assert by_code["HCT"]["confidence"] == 0.55