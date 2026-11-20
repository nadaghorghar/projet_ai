import pytest
from pydantic import ValidationError

from app.schemas import ParameterResult, ParameterStatus, TaskStatus, parameter_from_dict
from app.validation.analysis import analyze_parameters

BASE = {"code": "HGB", "name_printed": "Hémoglobine", "value": 10.5, "unit": "g/dL",
        "reference_min": 12.0, "reference_max": 16.0, "raw_line": "Hémoglobine 10,5 g/dL 12,0 - 16,0"}


def test_conversion_complete():
    p = analyze_parameters([BASE])[0]
    r = parameter_from_dict(p)
    assert r.status == ParameterStatus.below_reference
    assert r.reference.origin == "document_laboratoire"
    assert r.evidence.raw_text == BASE["raw_line"]
    assert r.confidence is None and r.evidence.page is None


def test_reference_absente_sans_origine():
    p = analyze_parameters([{**BASE, "reference_min": None, "reference_max": None}])[0]
    r = parameter_from_dict(p)
    assert r.status == ParameterStatus.reference_unavailable
    assert r.reference.origin is None


def test_not_analyzed_porte_la_raison():
    p = analyze_parameters([{**BASE, "unit": None}])[0]
    r = parameter_from_dict(p)
    assert r.status == ParameterStatus.not_analyzed
    assert r.reason == "unité absente du document"


def test_statut_invalide_refuse():
    with pytest.raises(ValidationError):
        parameter_from_dict({**BASE, "status": "diagnostic_anemie"})


def test_json_serialisable():
    r = parameter_from_dict(analyze_parameters([BASE])[0])
    assert '"status":"below_reference"' in r.model_dump_json()


def test_etats_de_tache():
    assert {s.value for s in TaskStatus} == {
        "received", "processing", "waiting_for_user", "done", "error"}