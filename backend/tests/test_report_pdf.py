import pymupdf

from app.generation.interface import (
    ExplanationStatus,
    GenerationResult,
    ParameterExplanation,
)
from app.report import build_labmind_report_pdf
from app.schemas import (
    DISCLAIMER,
    DocumentInfo,
    Evidence,
    ExtractionMethod,
    ParameterResult,
    ParameterStatus,
    Reference,
    Source,
    Task,
    TaskStatus,
)


def _extract_pdf_text(pdf_bytes: bytes) -> tuple[str, int]:
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        page_count = doc.page_count
        raw_text = "\n".join(page.get_text("text") for page in doc)
    normalized = " ".join(raw_text.split())
    return normalized, page_count


def test_build_report_contains_results_citations_accents_and_single_disclaimer():
    src = Source(
        source_id="ameli-prise-sang-2026",
        title="Lire les résultats d'une prise de sang",
        organisme="Assurance Maladie",
        url="https://www.ameli.fr/assure/sante/examen/analyse/lire-resultats-prise-sang",
        date="2026-01-08",
    )
    gen_result = GenerationResult(
        summary="Explications pédagogiques produites à partir des sources vérifiées.",
        parameter_explanations=[
            ParameterExplanation(
                code="GLY",
                status=ExplanationStatus.grounded,
                text="La glycémie mesure le taux de sucre dans le sang.",
                source_ids=["ameli-prise-sang-2026"],
            ),
            ParameterExplanation(
                code="HCT",
                status=ExplanationStatus.not_analyzed,
                text="Information non disponible : paramètre non analysé.",
                source_ids=[],
            ),
        ],
        sources=[src],
    )
    task = Task(
        task_id="task-pdf-001",
        status=TaskStatus.done,
        document=DocumentInfo(filename="bilan.pdf", extraction_method=ExtractionMethod.pdf_text),
        detected_categories=["Bilan glycémique", "Bilan lipidique", "NFS"],
        parameters=[
            ParameterResult(
                code="GLY",
                name_printed="Glycémie",
                value=0.95,
                unit="g/L",
                reference=Reference(min=0.70, max=1.10, origin="document_laboratoire"),
                status=ParameterStatus.within_reference,
                confidence=0.95,
                evidence=Evidence(raw_text="Glycémie : 0,95 g/L (0,70 - 1,10)", page=1),
            ),
            ParameterResult(
                code="LDL",
                name_printed="Cholestérol LDL",
                value=1.72,
                unit="g/L",
                reference=Reference(min=None, max=1.60, origin="document_laboratoire"),
                status=ParameterStatus.above_reference,
                confidence=0.95,
                evidence=Evidence(raw_text="Cholestérol LDL : 1,72 g/L (< 1,60)", page=1),
            ),
            ParameterResult(
                code="HCT",
                name_printed="Hématocrite",
                value=42.0,
                unit=None,
                reference=Reference(min=37.0, max=47.0, origin="document_laboratoire"),
                status=ParameterStatus.not_analyzed,
                reason="unité absente du document",
                confidence=0.55,
                evidence=Evidence(raw_text="Hématocrite : 42,0 (37,0 - 47,0)", page=2),
            ),
        ],
        report_id="r-pdf001",
        explanations=gen_result.to_task_explanations(),
        sources=[src],
        disclaimer=DISCLAIMER,
    )

    pdf_bytes = build_labmind_report_pdf(task)
    assert pdf_bytes.startswith(b"%PDF")

    text, _ = _extract_pdf_text(pdf_bytes)
    assert "Glycémie" in text
    assert "Cholestérol LDL" in text
    assert "< 1.6" in text
    assert "La glycémie mesure le taux de sucre dans le sang." in text
    assert "Sources médicales" not in text
    assert "ameli-prise-sang-2026" not in text
    assert "unité absente du document" in text
    # Pas de section hygiène de vie sans source dédiée
    assert "hygiène de vie" not in text
    # Précaution affichée exactement une fois
    assert text.count(DISCLAIMER) == 1


def test_long_table_paginates_cleanly_and_includes_lifestyle_only_when_sourced():
    lifestyle_src = Source(
        source_id="anses-nutrition-2025",
        title="Repères nutritionnels généraux",
        organisme="ANSES",
        url="https://www.anses.fr/",
        date="2025-01-01",
    )
    params = [
        ParameterResult(
            code=f"P{i:02d}",
            name_printed=f"Paramètre biologique test numéro {i}",
            value=10.0 + i,
            unit="g/L",
            reference=Reference(min=5.0, max=40.0, origin="document_laboratoire"),
            status=ParameterStatus.within_reference,
            confidence=0.95,
            evidence=Evidence(raw_text=f"Param {i}", page=1),
        )
        for i in range(1, 26)
    ]
    task = Task(
        task_id="task-long-001",
        status=TaskStatus.done,
        document=DocumentInfo(filename="complet.pdf", extraction_method=ExtractionMethod.pdf_text),
        detected_categories=["NFS", "Bilan hépatique", "Bilan rénal"],
        parameters=params,
        report_id="r-long001",
        sources=[lifestyle_src],
        disclaimer=DISCLAIMER,
    )

    pdf_bytes = build_labmind_report_pdf(task)
    text, page_count = _extract_pdf_text(pdf_bytes)
    assert page_count >= 2
    assert "hygiène de vie" in text
    assert "Sources médicales" not in text
    assert text.count(DISCLAIMER) == 1