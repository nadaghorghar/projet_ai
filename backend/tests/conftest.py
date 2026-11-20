import pytest
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


@pytest.fixture
def pdf_lignes(tmp_path):
    """PDF numérique fictif, mise en page « lignes » (comme le notebook)."""
    path = tmp_path / "bilan.pdf"
    st = getSampleStyleSheet()
    lignes = [
        "Hémoglobine : 12,4 g/dL (réf. : 12,0 - 16,0)",
        "Glycémie : 0,85 g/L (réf. : 0,70 - 1,10)",
        "Triglycérides : 1,97 g/L (réf. : 0,40 - 1,50)",
    ]
    els = [Paragraph("Laboratoire Test", st["Title"]), Spacer(1, 20)]
    els += [Paragraph(l, st["Normal"]) for l in lignes]
    SimpleDocTemplate(str(path), pagesize=A4).build(els)
    return path