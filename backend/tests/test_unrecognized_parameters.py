"""Tests unitaires pour les paramètres non reconnus lors de l'extraction OCR/PDF."""
from __future__ import annotations

from app.agent.tools import _build_uncertainties
from app.generation.fallback import InsufficientSourcesGenerator
from app.generation.interface import GenerationRequest
from app.identification.parser import identify_parameters, identify_parameters_from_pages, normalize_unit
from app.schemas import parameter_from_dict
from app.validation.analysis import analyze_parameters


def test_unrecognized_parameters_are_extracted_and_kept_in_results():
    raw_ocr = """
    Compte rendu fictif n° 1 - Patient : TEST ANONYME
    Hémoglobine ................ 13,5 g/dL           ( 12,0 - 16,0 )
    Protéine C-réactive (CRP) .. 12,4 mg/L           ( < 5,0 )
    TSH ultra-sensible ......... 2,15 mUI/L          ( 0,40 - 4,00 )
    Vitamine D (25-OH) ......... 24,5 ng/mL          ( 30 - 100 )
    Sodium ..................... 140 mmol/L          ( 136 - 145 )
    """
    identified = identify_parameters(raw_ocr)
    analyzed = analyze_parameters(identified, method="ocr", compute_confidence=True)
    by_name = {item["name_printed"]: item for item in analyzed}

    assert "Hémoglobine" in by_name
    assert "Protéine C-réactive (CRP)" in by_name
    assert "TSH ultra-sensible" in by_name
    assert "Vitamine D (25-OH)" in by_name
    assert "Sodium" in by_name

    # Vérifie que les métadonnées d'en-tête restent ignorées
    assert not any("Patient" in name or "Compte rendu" in name for name in by_name)

    crp = by_name["Protéine C-réactive (CRP)"]
    assert crp["code"].startswith("RAW_")
    assert crp["value"] == 12.4
    assert crp["unit"] == "mg/L"
    assert crp["reference_max"] == 5.0
    assert crp["status"] == "above_reference"

    tsh = by_name["TSH ultra-sensible"]
    assert tsh["value"] == 2.15
    assert tsh["unit"] == "mUI/L"
    assert tsh["status"] == "within_reference"

    vit_d = by_name["Vitamine D (25-OH)"]
    assert vit_d["value"] == 24.5
    assert vit_d["unit"] == "ng/mL"
    assert vit_d["status"] == "below_reference"


def test_unrecognized_parameter_never_triggers_blocking_question_or_explanation():
    raw_ocr = """
    Hémoglobine ................ 13,5 g/dL   ( 12,0 - 16,0 )
    Marqueur inconnu XYZ ....... 42,0 U/mL   ( 10,0 - 50,0 )
    Paramètre sans unité ....... 18,0        ( 10,0 - 20,0 )
    """
    pages = [{"page": 1, "text": raw_ocr, "table_rows": [], "ocr_confidence": 0.88}]
    identified = identify_parameters_from_pages(pages)
    analyzed = analyze_parameters(identified, method="ocr", compute_confidence=True)

    # Aucune question bloquante posée pour les paramètres non reconnus
    assert _build_uncertainties(analyzed) == []

    params = [parameter_from_dict(item) for item in analyzed]
    assert len(params) == 3

    gen = InsufficientSourcesGenerator()
    result = gen.generate(GenerationRequest(parameters=params, passages=[], lifestyle_passages=[]))
    explained_codes = {exp.code for exp in result.parameter_explanations}
    assert "HGB" in explained_codes
    assert all(not code.startswith("RAW_") for code in explained_codes)


def test_normalize_unit_preserves_unrecognized_units():
    assert normalize_unit("mUI/L") == "mUI/L"
    assert normalize_unit("pg/mL") == "pg/mL"
    assert normalize_unit("mEq/L") == "mEq/L"
