import pytest

from app.identification.parser import identify_parameters, normalize_unit

# Cas et résultats repris de la cellule #6 du notebook
CAS = [
    ("Hb 12,4 g/dL 12,0 - 16,0", "HGB", 12.4, "g/dL", 12.0, 16.0),
    ("Glycémie 0,7 - 1,1 0,85 g/L", "GLY", 0.85, "g/L", 0.7, 1.1),
    ("Cholestérol LDL : 122.0 mg/dL (réf. : 60.0 - 130.0)", "LDL", 122.0, "mg/dL", 60.0, 130.0),
    ("Hématocrite 46.0 12.0 - 47.0", "HCT", 46.0, None, 12.0, 47.0),
    ("Plaquettes 128.0 10^3/µL", "PLT", 128.0, "10^3/µL", None, None),
]


@pytest.mark.parametrize("ligne,code,valeur,unite,lo,hi", CAS)
def test_lignes_du_notebook(ligne, code, valeur, unite, lo, hi):
    res = identify_parameters(ligne)
    assert len(res) == 1
    p = res[0]
    assert (p["code"], p["value"], p["unit"], p["reference_min"], p["reference_max"]) == (code, valeur, unite, lo, hi)


def test_ligne_inconnue_ignoree():
    assert identify_parameters("Compte rendu fictif n° 1 - Patient : TEST ANONYME") == []


def test_normalisation_unite_ocr():
    assert normalize_unit("10%3/uL") == "10^3/µL"
    assert normalize_unit("G/DL") == "g/dL"
    assert normalize_unit("") is None