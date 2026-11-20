"""Contrôles techniques sur les données extraites.

- classify : comparaison ARITHMÉTIQUE valeur / fourchette fournie par le laboratoire.
  Ce n'est pas une interprétation médicale.
- check_parameter : présence et cohérence des champs.
- plausible : détecte une lecture OCR douteuse (virgule perdue, par exemple).
"""
from __future__ import annotations


def classify(value, ref_min, ref_max) -> str:
    if value is None:
        return "value_unavailable"
    if ref_min is None and ref_max is None:
        return "reference_unavailable"
    if ref_min is not None and value < ref_min:
        return "below_reference"
    if ref_max is not None and value > ref_max:
        return "above_reference"
    return "within_reference"


def check_parameter(p: dict, accepted_units: list[str] | None) -> list[dict]:
    issues = []
    if p.get("value") is None:
        issues.append({"code": p["code"], "issue": "missing_value", "blocking": True})
    if not p.get("unit"):
        issues.append({"code": p["code"], "issue": "missing_unit", "blocking": True})
    elif accepted_units and p["unit"] not in accepted_units:
        issues.append(
            {
                "code": p["code"],
                "issue": "unexpected_unit",
                "blocking": True,
                "detail": p["unit"],
            }
        )
    lo, hi = p.get("reference_min"), p.get("reference_max")
    if lo is None and hi is None:
        issues.append({"code": p["code"], "issue": "missing_reference", "blocking": False})
    elif lo is not None and hi is not None and lo >= hi:
        issues.append({"code": p["code"], "issue": "invalid_reference", "blocking": True})
    return issues


def plausible(p: dict) -> bool:
    lo, hi, v = p["reference_min"], p["reference_max"], p["value"]
    if v is None:
        return True
    if lo is not None and lo > 0 and v < lo / 10:
        return False
    if hi is not None and hi > 0 and v > hi * 10:
        return False
    return True