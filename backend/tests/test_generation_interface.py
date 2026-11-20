import pytest
from pydantic import ValidationError

from app.generation import (
    ExplanationGenerator,
    ExplanationStatus,
    GenerationRequest,
    GenerationResult,
    ParameterExplanation,
    RetrievedPassage,
    find_citation_errors,
)
from app.schemas import DISCLAIMER, Source, Task, TaskStatus, parameter_from_dict
from app.validation.analysis import analyze_parameters


def _sample_parameter():
    raw = analyze_parameters(
        [
            {
                "code": "HGB",
                "name_printed": "Hémoglobine",
                "value": 13.5,
                "unit": "g/dL",
                "reference_min": 12.0,
                "reference_max": 16.0,
                "raw_line": "Hémoglobine 13,5 g/dL 12,0 - 16,0",
            }
        ]
    )[0]
    return parameter_from_dict(raw)


def _sample_passage():
    return RetrievedPassage(
        passage_id="p-001",
        source=Source(
            source_id="inserm-hgb-01",
            title="Comprendre l'hémogramme",
            organisme="Inserm",
            url="https://example.org/hgb",
            date="2025-01-15",
        ),
        excerpt="L'hémoglobine est une protéine des globules rouges qui transporte l'oxygène.",
        score=0.92,
    )


class _DummyGenerator:
    """Faux générateur utilisé uniquement pour valider le contrat Protocol en test."""

    def generate(self, request: GenerationRequest) -> GenerationResult:
        if not request.passages:
            return GenerationResult(
                summary=None,
                parameter_explanations=[
                    ParameterExplanation(
                        code=p.code,
                        status=ExplanationStatus.insufficient_sources,
                        text="Information documentaire non disponible pour ce paramètre.",
                    )
                    for p in request.parameters
                ],
                sources=[],
            )

        first_passage = request.passages[0]
        return GenerationResult(
            summary="Résumé basé uniquement sur les sources fournies.",
            parameter_explanations=[
                ParameterExplanation(
                    code=p.code,
                    status=ExplanationStatus.grounded,
                    text=first_passage.excerpt,
                    source_ids=[first_passage.source.source_id],
                )
                for p in request.parameters
            ],
            sources=[first_passage.source],
        )


def test_protocol_compliance():
    generator = _DummyGenerator()
    assert isinstance(generator, ExplanationGenerator)


def test_grounded_explanation_requires_at_least_one_source_id():
    with pytest.raises(ValidationError):
        ParameterExplanation(
            code="HGB",
            status=ExplanationStatus.grounded,
            text="Explication sans citation.",
            source_ids=[],
        )


def test_insufficient_sources_cannot_attach_citations():
    with pytest.raises(ValidationError):
        ParameterExplanation(
            code="HGB",
            status=ExplanationStatus.insufficient_sources,
            text="Aucune source disponible.",
            source_ids=["inserm-hgb-01"],
        )


def test_valid_generation_integrates_with_task_contract():
    param = _sample_parameter()
    passage = _sample_passage()
    request = GenerationRequest(parameters=[param], passages=[passage])

    result = _DummyGenerator().generate(request)

    assert find_citation_errors(result, request.passages) == []

    task = Task(
        task_id="3f2b8c1e-6a52-4d7e-9a0c-1b2d3e4f5a6b",
        status=TaskStatus.done,
        parameters=[param],
        explanations=result.to_task_explanations(),
        sources=result.sources,
        disclaimer=result.disclaimer,
    )
    assert task.disclaimer == DISCLAIMER
    assert task.sources[0].source_id == "inserm-hgb-01"
    assert task.explanations["parameter_explanations"][0]["status"] == "grounded"


def test_find_citation_errors_detects_invented_source():
    passage = _sample_passage()
    invented = Source(
        source_id="source-inventee",
        title="Faux document",
        organisme="Inconnu",
        url="https://example.org/fake",
    )
    result = GenerationResult(
        parameter_explanations=[
            ParameterExplanation(
                code="HGB",
                status=ExplanationStatus.grounded,
                text="Texte non vérifié.",
                source_ids=["source-inventee"],
            )
        ],
        sources=[invented],
    )

    errors = find_citation_errors(result, [passage])
    assert len(errors) >= 2
    assert any("source-inventee" in err for err in errors)


def test_find_citation_errors_detects_missing_from_result_sources():
    passage = _sample_passage()
    result = GenerationResult(
        parameter_explanations=[
            ParameterExplanation(
                code="HGB",
                status=ExplanationStatus.grounded,
                text="Texte cité.",
                source_ids=[passage.source.source_id],
            )
        ],
        sources=[],  # oubli volontaire dans result.sources
    )

    errors = find_citation_errors(result, [passage])
    assert any("absent de result.sources" in err for err in errors)