import pytest

from app.extraction.extractor import extract_document
from app.identification.parser import identify_parameters
from app.validation.analysis import analyze_parameters
from tests.helpers import render_pdf

# (code, nom imprimé, valeur, unité, ref_min, ref_max, statut attendu)
CASES = {
    "table1_virgule": ("table1", True, [
        ("HGB", "Hémoglobine", 10.5, "g/dL", 12.0, 16.0, "below_reference"),
        ("GLY", "Glycémie", 0.85, "g/L", 0.7, 1.1, "within_reference"),
        ("TG", "Triglycérides", 1.97, "g/L", 0.4, 1.5, "above_reference"),
    ]),
    "table2_point": ("table2", False, [
        ("WBC", "Globules blancs", 6.5, "10^3/µL", 4.0, 10.0, "within_reference"),
        ("PLT", "Plaquettes", 128.0, "10^3/µL", 150, 400, "below_reference"),
        ("HCT", "Hématocrite", 46.0, "%", 37, 47, "within_reference"),
    ]),
    "lines_mgdl": ("lines", True, [
        ("GLY", "Glucose", 126.0, "mg/dL", 70.0, 110.0, "above_reference"),
        ("LDL", "Cholestérol LDL", 99.0, "mg/dL", 60.0, 130.0, "within_reference"),
        ("HDL", "HDL", 35.0, "mg/dL", 40.0, 60.0, "below_reference"),
    ]),
    "unite_manquante": ("table1", True, [
        ("HGB", "Hémoglobine", 14.0, "g/dL", 12.0, 16.0, "within_reference"),
        ("HCT", "Hématocrite", 46.0, None, 37.0, 47.0, "not_analyzed"),
    ]),
    "reference_absente": ("lines", False, [
        ("PLT", "Plaquettes", 128.0, "10^3/µL", None, None, "reference_unavailable"),
        ("GLY", "Glycémie", 0.9, "g/L", 0.7, 1.1, "within_reference"),
    ]),
}


def _run(path):
    ex = extract_document(path)
    return analyze_parameters(identify_parameters(ex["text"]), ex["method"])


@pytest.mark.parametrize("nom", CASES)
def test_chaine_complete(nom, tmp_path):
    layout, comma, rows = CASES[nom]
    params = [dict(name_printed=n, value=v, unit=u, reference_min=lo, reference_max=hi)
              for (_, n, v, u, lo, hi, _) in rows]
    pdf = tmp_path / f"{nom}.pdf"
    render_pdf(pdf, layout, comma, params)

    res = {p["code"]: p for p in _run(pdf)}
    assert set(res) == {r[0] for r in rows}
    for code, _, valeur, unite, lo, hi, statut in rows:
        p = res[code]
        assert p["value"] == pytest.approx(valeur)
        assert p["unit"] == unite
        assert p["reference_min"] == lo and p["reference_max"] == hi
        assert p["status"] == statut


def test_unite_manquante_jamais_devinee(tmp_path):
    layout, comma, rows = CASES["unite_manquante"]
    params = [dict(name_printed=n, value=v, unit=u, reference_min=lo, reference_max=hi)
              for (_, n, v, u, lo, hi, _) in rows]
    pdf = tmp_path / "x.pdf"
    render_pdf(pdf, layout, comma, params)
    hct = next(p for p in _run(pdf) if p["code"] == "HCT")
    assert hct["status"] == "not_analyzed"
    assert hct["reason_code"] == "missing_unit"


def test_unite_inattendue_bloquee():
    p = [{"code": "HGB", "name_printed": "Hb", "value": 12.4, "unit": "mg/dL",
          "reference_min": 12.0, "reference_max": 16.0}]
    r = analyze_parameters(p)[0]
    assert r["status"] == "not_analyzed" and r["reason_code"] == "unexpected_unit"


def test_garde_fou_ocr_seulement_pour_ocr():
    p = [{"code": "GLY", "name_printed": "Glycémie", "value": 128.0, "unit": "g/L",
          "reference_min": 0.7, "reference_max": 1.1}]
    assert analyze_parameters(p, "ocr")[0]["reason_code"] == "implausible"
    assert analyze_parameters(p, "pdf_text")[0]["status"] == "above_reference"


def test_code_inconnu_ignore():
    p = [{"code": "XYZ", "name_printed": "?", "value": 1.0, "unit": "g/L",
          "reference_min": 0.0, "reference_max": 2.0}]
    assert analyze_parameters(p) == []