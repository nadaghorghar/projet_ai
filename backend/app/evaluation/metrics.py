"""Calcul de précision, rappel et exactitude séparée (nom, valeur, unité, référence)."""
from __future__ import annotations

import math

from pydantic import BaseModel, Field


class GroundTruthParam(BaseModel):
    """Vérité terrain d'un paramètre biologique dans un document de test."""

    code: str
    value: float | None = None
    unit: str | None = None
    reference_min: float | None = None
    reference_max: float | None = None


class DocumentGroundTruth(BaseModel):
    """Vérité terrain complète d'un document d'évaluation."""

    doc_id: str
    filename: str
    source_type: str = "synthetic_varied"
    parameters: list[GroundTruthParam] = Field(default_factory=list)


class DocumentEvalDetail(BaseModel):
    """Résultat détaillé d'évaluation sur un document."""

    doc_id: str
    filename: str
    source_type: str
    expected_count: int
    predicted_count: int
    true_positives: int
    value_matches: int
    unit_matches: int
    reference_matches: int
    full_matches: int
    missing_codes: list[str] = Field(default_factory=list)
    extra_codes: list[str] = Field(default_factory=list)


class EvaluationSummary(BaseModel):
    """Synthèse agrégée sur l'ensemble d'un jeu d'évaluation."""

    total_documents: int
    total_expected_params: int
    total_predicted_params: int
    true_positives: int
    identification_precision: float
    identification_recall: float
    identification_f1: float
    value_accuracy: float
    unit_accuracy: float
    reference_accuracy: float
    full_parameter_accuracy: float
    details: list[DocumentEvalDetail] = Field(default_factory=list)


def _float_equal(a: float | None, b: float | None, tol: float = 1e-3) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return math.isclose(float(a), float(b), rel_tol=tol, abs_tol=tol)


def evaluate_document_prediction(
    gt: DocumentGroundTruth,
    predicted: list[dict],
) -> DocumentEvalDetail:
    """Compare les paramètres prédits à la vérité terrain d'un document."""
    gt_by_code = {p.code: p for p in gt.parameters}
    pred_by_code = {p["code"]: p for p in predicted if "code" in p}

    expected_codes = set(gt_by_code.keys())
    predicted_codes = set(pred_by_code.keys())

    matched_codes = sorted(expected_codes & predicted_codes)
    missing_codes = sorted(expected_codes - predicted_codes)
    extra_codes = sorted(predicted_codes - expected_codes)

    value_matches = 0
    unit_matches = 0
    reference_matches = 0
    full_matches = 0

    for code in matched_codes:
        truth = gt_by_code[code]
        pred = pred_by_code[code]

        v_ok = _float_equal(pred.get("value"), truth.value)
        u_ok = pred.get("unit") == truth.unit
        r_ok = _float_equal(pred.get("reference_min"), truth.reference_min) and _float_equal(
            pred.get("reference_max"), truth.reference_max
        )

        if v_ok:
            value_matches += 1
        if u_ok:
            unit_matches += 1
        if r_ok:
            reference_matches += 1
        if v_ok and u_ok and r_ok:
            full_matches += 1

    return DocumentEvalDetail(
        doc_id=gt.doc_id,
        filename=gt.filename,
        source_type=gt.source_type,
        expected_count=len(gt_by_code),
        predicted_count=len(pred_by_code),
        true_positives=len(matched_codes),
        value_matches=value_matches,
        unit_matches=unit_matches,
        reference_matches=reference_matches,
        full_matches=full_matches,
        missing_codes=missing_codes,
        extra_codes=extra_codes,
    )


def _safe_ratio(num: int, den: int) -> float:
    return round(num / den, 4) if den > 0 else 0.0


def aggregate_evaluation(details: list[DocumentEvalDetail]) -> EvaluationSummary:
    """Agrège les métriques sur tous les documents évalués."""
    expected_total = sum(d.expected_count for d in details)
    predicted_total = sum(d.predicted_count for d in details)
    tp = sum(d.true_positives for d in details)

    precision = _safe_ratio(tp, predicted_total)
    recall = _safe_ratio(tp, expected_total)
    f1 = (
        round((2 * precision * recall) / (precision + recall), 4)
        if (precision + recall) > 0
        else 0.0
    )

    return EvaluationSummary(
        total_documents=len(details),
        total_expected_params=expected_total,
        total_predicted_params=predicted_total,
        true_positives=tp,
        identification_precision=precision,
        identification_recall=recall,
        identification_f1=f1,
        value_accuracy=_safe_ratio(sum(d.value_matches for d in details), tp),
        unit_accuracy=_safe_ratio(sum(d.unit_matches for d in details), tp),
        reference_accuracy=_safe_ratio(sum(d.reference_matches for d in details), tp),
        full_parameter_accuracy=_safe_ratio(sum(d.full_matches for d in details), expected_total),
        details=details,
    )