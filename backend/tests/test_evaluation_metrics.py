from app.evaluation import (
    DocumentGroundTruth,
    GroundTruthParam,
    aggregate_evaluation,
    evaluate_document_prediction,
)


def test_evaluate_document_separates_name_value_unit_and_reference():
    gt = DocumentGroundTruth(
        doc_id="doc-1",
        filename="doc-1.pdf",
        parameters=[
            GroundTruthParam(
                code="HGB",
                value=13.5,
                unit="g/dL",
                reference_min=12.0,
                reference_max=16.0,
            ),
            GroundTruthParam(
                code="CREAT",
                value=9.2,
                unit="mg/L",
                reference_min=7.0,
                reference_max=13.0,
            ),
            GroundTruthParam(
                code="FERR",
                value=45.0,
                unit="ng/mL",
                reference_min=30.0,
                reference_max=300.0,
            ),
        ],
    )

    predicted = [
        {
            "code": "HGB",
            "value": 13.5,
            "unit": "g/dL",
            "reference_min": 12.0,
            "reference_max": 16.0,
        },
        {
            "code": "CREAT",
            "value": 9.2,
            "unit": None,  # unité ratée
            "reference_min": 7.0,
            "reference_max": 13.0,
        },
        {
            "code": "GLY",  # faux positif
            "value": 1.0,
            "unit": "g/L",
            "reference_min": None,
            "reference_max": None,
        },
    ]

    detail = evaluate_document_prediction(gt, predicted)
    assert detail.true_positives == 2
    assert detail.missing_codes == ["FERR"]
    assert detail.extra_codes == ["GLY"]
    assert detail.value_matches == 2
    assert detail.unit_matches == 1
    assert detail.reference_matches == 2
    assert detail.full_matches == 1

    summary = aggregate_evaluation([detail])
    assert summary.identification_precision == 0.6667
    assert summary.identification_recall == 0.6667
    assert summary.value_accuracy == 1.0
    assert summary.unit_accuracy == 0.5
    assert summary.reference_accuracy == 1.0
    assert summary.full_parameter_accuracy == 0.3333