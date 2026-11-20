"""Contrôle technique d'une liste de paramètres extraits.

Aucune interprétation médicale : uniquement présence des champs, cohérence,
position arithmétique et calcul transparent du score de confiance technique.
"""
from __future__ import annotations

from app.identification.catalog import ACCEPTED_UNITS

from .reference import check_parameter, classify, plausible

REASONS = {
    "missing_unit": "unité absente du document",
    "unexpected_unit": "unité non reconnue",
    "missing_value": "valeur illisible",
    "invalid_reference": "fourchette incohérente",
    "implausible": "lecture incertaine (valeur très éloignée de la fourchette)",
}


def compute_parameter_confidence(param: dict, method: str) -> float:
    """Calcule un indice de confiance technique dans [0.0, 1.0]."""
    if method == "ocr":
        ocr_score = param.get("source_ocr_confidence")
        base = float(ocr_score) if ocr_score is not None else 0.70
    else:
        base = 0.95

    status = param.get("status")
    reason_code = param.get("reason_code")

    if status == "not_analyzed":
        if reason_code in ("missing_value", "implausible", "invalid_reference"):
            base = min(base, 0.35)
        else:
            base = min(base, 0.55)
    elif param.get("reference_min") is None and param.get("reference_max") is None:
        base = max(0.0, base - 0.10)

    return round(max(0.0, min(1.0, base)), 2)


def analyze_parameters(
    params: list[dict],
    method: str = "pdf_text",
    compute_confidence: bool = False,
) -> list[dict]:
    """Retourne une copie des paramètres enrichie de `status`, `reason_code`, `reason`."""
    known = [dict(p) for p in params if p["code"] in ACCEPTED_UNITS]

    blocked: dict[str, str] = {}
    for p in known:
        for issue in check_parameter(p, ACCEPTED_UNITS[p["code"]]):
            if issue["blocking"]:
                blocked.setdefault(p["code"], issue["issue"])

    if method == "ocr":
        for p in known:
            if p["code"] not in blocked and not plausible(p):
                blocked[p["code"]] = "implausible"

    for p in known:
        code = p["code"]
        if code in blocked:
            p["status"] = "not_analyzed"
            p["reason_code"] = blocked[code]
            p["reason"] = REASONS[blocked[code]]
        else:
            p["status"] = classify(p["value"], p["reference_min"], p["reference_max"])
            p["reason_code"] = None
            p["reason"] = None

        if compute_confidence or "page" in p or "source_ocr_confidence" in p:
            p["confidence"] = compute_parameter_confidence(p, method=method)

    return known