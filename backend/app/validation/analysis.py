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
    kept = [
        dict(p)
        for p in params
        if p["code"] in ACCEPTED_UNITS or str(p["code"]).startswith("RAW_")
    ]

    blocked: dict[str, str] = {}
    for p in kept:
        code = p["code"]
        if str(code).startswith("RAW_"):
            if p.get("value") is None:
                blocked.setdefault(code, "missing_value")
            lo, hi = p.get("reference_min"), p.get("reference_max")
            if lo is not None and hi is not None and lo >= hi:
                blocked.setdefault(code, "invalid_reference")
            continue
        for issue in check_parameter(p, ACCEPTED_UNITS[code]):
            if issue["blocking"]:
                blocked.setdefault(code, issue["issue"])

    if method == "ocr":
        for p in kept:
            if not str(p["code"]).startswith("RAW_") and p["code"] not in blocked and not plausible(p):
                blocked[p["code"]] = "implausible"

    for p in kept:
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
        p["marked_deviation"] = _is_marked_deviation(p)
        prior_cmp = _build_prior_comparison(p)
        if prior_cmp is not None:
            p["prior"] = prior_cmp

    return kept

def _build_prior_comparison(param: dict) -> dict | None:
    """Compare arithmétiquement une valeur antérieure extraite si les unités sont compatibles."""
    prior_val = param.get("prior_value")
    if prior_val is None:
        return None
    prior_unit = param.get("prior_unit")
    prior_date = param.get("prior_date")
    cur_val = param.get("value")
    cur_unit = param.get("unit")
    if (
        cur_val is None
        or not cur_unit
        or param.get("status") == "not_analyzed"
        or (prior_unit is not None and prior_unit != cur_unit)
    ):
        return {
            "prior_value": prior_val,
            "prior_unit": prior_unit,
            "prior_date": prior_date,
            "comparable": False,
            "delta": None,
            "trend": "not_comparable",
            "note": "Unités ou conditions potentiellement différentes : comparaison directe non effectuée.",
        }
    delta = round(float(cur_val) - float(prior_val), 4)
    if delta > 1e-4:
        trend = "increased"
        sign = "+"
    elif delta < -1e-4:
        trend = "decreased"
        sign = ""
    else:
        trend = "stable"
        sign = ""
    delta_str = f"{sign}{delta:g}".replace(".", ",")
    date_part = f" depuis le {prior_date}" if prior_date else ""
    note = (
        f"Stable ({prior_val:g} {cur_unit}{date_part})"
        if trend == "stable"
        else f"Évolution de {delta_str} {cur_unit} (précédent : {prior_val:g} {cur_unit}{date_part})"
    )
    return {
        "prior_value": prior_val,
        "prior_unit": prior_unit or cur_unit,
        "prior_date": prior_date,
        "comparable": True,
        "delta": delta,
        "trend": trend,
        "note": note,
    }


def _is_marked_deviation(param: dict) -> bool:
    """Écart arithmétique marqué par rapport aux bornes du laboratoire (non diagnostique)."""
    status = param.get("status")
    val = param.get("value")
    lo = param.get("reference_min")
    hi = param.get("reference_max")
    if val is None or status not in ("below_reference", "above_reference"):
        return False
    if status == "below_reference" and lo is not None and lo > 0 and val < lo * 0.7:
        return True
    if status == "above_reference" and hi is not None and hi > 0 and val > hi * 1.5:
        return True
    return False
