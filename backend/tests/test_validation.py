from app.identification.catalog import ACCEPTED_UNITS
from app.validation.reference import check_parameter, classify, plausible


def test_classify():
    assert classify(60, 70, 100) == "below_reference"
    assert classify(95, 70, 100) == "within_reference"
    assert classify(100, 70, 100) == "within_reference"
    assert classify(120, 70, 100) == "above_reference"
    assert classify(95, None, None) == "reference_unavailable"
    assert classify(None, 70, 100) == "value_unavailable"


def _p(**kw):
    base = {"code": "GLY", "value": 1.0, "unit": "g/L", "reference_min": 0.7, "reference_max": 1.1}
    base.update(kw)
    return base


def test_parametre_valide():
    assert check_parameter(_p(), ACCEPTED_UNITS["GLY"]) == []


def test_unite_manquante_bloquante():
    issues = check_parameter(_p(unit=None), ACCEPTED_UNITS["GLY"])
    assert issues[0]["issue"] == "missing_unit" and issues[0]["blocking"]


def test_unite_inattendue():
    issues = check_parameter(_p(unit="%"), ACCEPTED_UNITS["GLY"])
    assert issues[0]["issue"] == "unexpected_unit"


def test_reference_absente_non_bloquante():
    issues = check_parameter(_p(reference_min=None, reference_max=None), ACCEPTED_UNITS["GLY"])
    assert issues[0]["issue"] == "missing_reference" and not issues[0]["blocking"]


def test_reference_incoherente():
    issues = check_parameter(_p(reference_min=2.0, reference_max=1.0), ACCEPTED_UNITS["GLY"])
    assert issues[0]["issue"] == "invalid_reference"


def test_plausibilite_virgule_perdue():
    assert plausible(_p(value=1.28)) is True
    assert plausible(_p(value=128)) is False