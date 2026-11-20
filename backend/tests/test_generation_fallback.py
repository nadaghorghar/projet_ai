from app.generation import (
    INSUFFICIENT_SOURCES_PARAMETER_MESSAGE,
    INSUFFICIENT_SOURCES_SUMMARY,
    ExplanationGenerator,
    ExplanationStatus,
    GenerationRequest,
    InsufficientSourcesGenerator,
    find_citation_errors,
)
from app.schemas import DISCLAIMER, Task, TaskStatus, parameter_from_dict
from app.validation.analysis import analyze_parameters


def _make_parameters():
    raw_items = analyze_parameters(
        [
            {
                "code": "HGB",
                "name_printed": "Hémoglobine",
                "value": 10.5,
                "unit": "g/dL",
                "reference_min": 12.0,
                "reference_max": 16.0,
                "raw_line": "Hémoglobine 10,5 g/dL 12,0 - 16,0",
            },
            {
                "code": "GLY",
                "name_printed": "Glycémie",
                "value": 0.90,
                "unit": "g/L",
                "reference_min": 0.70,
                "reference_max": 1.10,
                "raw_line": "Glycémie 0,90 g/L 0,70 - 1,10",
            },
            {
                "code": "TG",
                "name_printed": "Triglycérides",
                "value": 2.10,
                "unit": "g/L",
                "reference_min": 0.40,
                "reference_max": 1.50,
                "raw_line": "Triglycérides 2,10 g/L 0,40 - 1,50",
            },
            {
                "code": "HCT",
                "name_printed": "Hématocrite",
                "value": 46.0,
                "unit": None,
                "reference_min": 37.0,
                "reference_max": 47.0,
                "raw_line": "Hématocrite 46,0 37,0 - 47,0",
            },
        ]
    )
    return [parameter_from_dict(item) for item in raw_items]


def test_fallback_generator_implements_protocol():
    generator = InsufficientSourcesGenerator()
    assert isinstance(generator, ExplanationGenerator)


def test_fallback_empty_parameters():
    request = GenerationRequest(parameters=[], passages=[])
    result = InsufficientSourcesGenerator().generate(request)

    assert result.summary == INSUFFICIENT_SOURCES_SUMMARY
    assert result.parameter_explanations == []
    assert result.sources == []
    assert result.disclaimer == DISCLAIMER
    assert find_citation_errors(result, request.passages) == []


def test_fallback_is_neutral_across_biological_statuses():
    params = _make_parameters()
    request = GenerationRequest(parameters=params, passages=[])

    result = InsufficientSourcesGenerator().generate(request)
    by_code = {exp.code: exp for exp in result.parameter_explanations}

    # En dessous, dans, ou au-dessus de la référence : exactement le même message neutre
    for code in ("HGB", "GLY", "TG"):
        assert by_code[code].status == ExplanationStatus.insufficient_sources
        assert by_code[code].text == INSUFFICIENT_SOURCES_PARAMETER_MESSAGE
        assert by_code[code].source_ids == []

    # Paramètre non analysé : statut dédié et motif technique conservé
    assert by_code["HCT"].status == ExplanationStatus.not_analyzed
    assert "unité absente du document" in by_code["HCT"].text
    assert by_code["HCT"].source_ids == []

    assert result.sources == []
    assert find_citation_errors(result, request.passages) == []


def test_fallback_serializes_cleanly_into_task_contract():
    params = _make_parameters()
    result = InsufficientSourcesGenerator().generate(
        GenerationRequest(parameters=params, passages=[])
    )

    task = Task(
        task_id="3f2b8c1e-6a52-4d7e-9a0c-1b2d3e4f5a6b",
        status=TaskStatus.done,
        parameters=params,
        explanations=result.to_task_explanations(),
        sources=result.sources,
        disclaimer=result.disclaimer,
    )

    assert task.sources == []
    assert task.explanations["summary"] == INSUFFICIENT_SOURCES_SUMMARY
    assert len(task.explanations["parameter_explanations"]) == 4