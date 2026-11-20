"""Exécute l'extraction réelle sur evaluation/documents/ et enregistre le rapport."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.evaluation.metrics import (  # noqa: E402
    DocumentEvalDetail,
    DocumentGroundTruth,
    aggregate_evaluation,
    evaluate_document_prediction,
)
from app.extraction.extractor import extract_document  # noqa: E402
from app.identification.parser import identify_parameters_from_pages  # noqa: E402


def main() -> int:
    eval_dir = REPO_ROOT / "evaluation"
    docs_dir = eval_dir / "documents"
    gt_dir = eval_dir / "ground_truth"
    results_dir = eval_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    gt_files = sorted(gt_dir.glob("*.json"))
    if not gt_files:
        print(
            "Aucune vérité terrain trouvée dans evaluation/ground_truth/.\n"
            "Lance d'abord : python scripts\\generate_eval_samples.py"
        )
        return 1

    details: list[DocumentEvalDetail] = []
    for gt_file in gt_files:
        gt = DocumentGroundTruth.model_validate_json(gt_file.read_text(encoding="utf-8"))
        doc_path = docs_dir / gt.filename
        if not doc_path.is_file():
            print(f"Document manquant : {doc_path}")
            continue

        extracted = extract_document(doc_path)
        predicted = identify_parameters_from_pages(extracted["pages"])
        detail = evaluate_document_prediction(gt, predicted)
        details.append(detail)
        print(
            f"- {gt.doc_id} ({extracted['method']}): "
            f"identifiés={detail.true_positives}/{detail.expected_count}, "
            f"complets={detail.full_matches}/{detail.expected_count}"
        )

    summary = aggregate_evaluation(details)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = results_dir / f"eval_{ts}.json"
    out_path.write_text(summary.model_dump_json(indent=2) + "\n", encoding="utf-8")

    print("\n=== Résumé d'évaluation ===")
    print(f"Documents évalués     : {summary.total_documents}")
    print(f"Précision identif.    : {summary.identification_precision:.2%}")
    print(f"Rappel identif.       : {summary.identification_recall:.2%}")
    print(f"Exactitude valeur     : {summary.value_accuracy:.2%}")
    print(f"Exactitude unité      : {summary.unit_accuracy:.2%}")
    print(f"Exactitude référence  : {summary.reference_accuracy:.2%}")
    print(f"Paramètres complets   : {summary.full_parameter_accuracy:.2%}")
    print(f"Rapport enregistré    : {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())