from __future__ import annotations

import json

from app.generation.grounding import (
    check_lifestyle_grounding,
    sanitize_consultation_questions,
)
from app.generation.interface import (
    ExplanationStatus,
    GenerationRequest,
    GenerationResult,
    LifestyleInfo,
    RetrievedPassage,
    find_citation_errors,
)
from app.generation.llm_client import LocalLLMError
from app.generation.rag import RagExplanationGenerator
from app.schemas import ParameterResult, ParameterStatus, Source


class _QueuedLLMClient:
    def __init__(self, responses: list[str | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _make_ferritine() -> ParameterResult:
    return ParameterResult.model_validate(
        {
            "code": "FER",
            "name_printed": "Ferritine",
            "value": 12.0,
            "unit": "ng/mL",
            "reference": {
                "min": 15.0,
                "max": 150.0,
                "origin": "document_laboratoire",
            },
            "status": ParameterStatus.below_reference,
            "confidence": 0.95,
            "evidence": {
                "raw_text": "Ferritine : 12 ng/mL",
                "page": 1,
            },
        }
    )


def _make_bio_passage() -> RetrievedPassage:
    return RetrievedPassage(
        passage_id="ameli-fer-01",
        source=Source(
            source_id="ameli-fer-2026",
            title="Comprendre le bilan martial",
            organisme="Assurance Maladie",
            url="https://www.ameli.fr/assure/sante/examen/analyse/ferritine",
            date="2026-01-08",
        ),
        excerpt=(
            "La ferritine reflète les réserves en fer de l'organisme. "
            "Une valeur inférieure aux bornes du laboratoire nécessite une "
            "interprétation médicale dans le contexte clinique."
        ),
        score=0.91,
    )


def _make_lifestyle_passage() -> RetrievedPassage:
    return RetrievedPassage(
        passage_id="anses-lifestyle-01",
        source=Source(
            source_id="anses-reperes-2026",
            title="Repères nutritionnels officiels pour la population adulte",
            organisme="ANSES",
            url="https://www.anses.fr/fr/content/les-reperes-nutritionnels",
            date="2026-02-01",
        ),
        excerpt=(
            "Les repères de santé publique encouragent une alimentation variée "
            "comprenant des légumineuses, des fruits, des légumes et une activité "
            "physique régulière adaptée à l'état de santé de chacun."
        ),
        score=0.88,
    )


def test_lifestyle_info_and_questions_generated_with_grounding() -> None:
    bio_passage = _make_bio_passage()
    lifestyle_passage = _make_lifestyle_passage()

    llm = _QueuedLLMClient(
        [
            json.dumps(
                {
                    "status": "grounded",
                    "text": (
                        "La ferritine reflète les réserves en fer de l'organisme "
                        "et demande une interprétation médicale dans son contexte."
                    ),
                    "source_ids": ["ameli-fer-2026"],
                }
            ),
            json.dumps(
                {
                    "status": "grounded",
                    "text": (
                        "Selon les repères de santé publique, une alimentation variée "
                        "avec des légumineuses, des fruits, des légumes et une activité "
                        "physique régulière accompagne l'hygiène de vie générale."
                    ),
                    "source_ids": ["anses-reperes-2026"],
                }
            ),
            json.dumps(
                {
                    "questions": [
                        "Comment interpréter cette ferritine par rapport à mes symptômes ?",
                        "Vous souffrez d'anémie sévère ?",
                        "Une phrase qui n'est pas une question.",
                        "Un contrôle biologique ultérieur est-il utile pour le suivi ?",
                    ]
                }
            ),
        ]
    )

    generator = RagExplanationGenerator(llm_client=llm, min_overlap_ratio=0.25)
    request = GenerationRequest(
        parameters=[_make_ferritine()],
        passages=[bio_passage],
        lifestyle_passages=[lifestyle_passage],
        include_consultation_questions=True,
    )

    result = generator.generate(request)

    assert result.parameter_explanations[0].status == ExplanationStatus.grounded
    assert result.lifestyle_info is not None
    assert result.lifestyle_info.status == ExplanationStatus.grounded
    assert result.lifestyle_info.source_ids == ["anses-reperes-2026"]

    exposed_ids = {s.source_id for s in result.sources}
    assert exposed_ids == {"ameli-fer-2026", "anses-reperes-2026"}
    assert (
        find_citation_errors(
            result,
            request.passages,
            lifestyle_passages=request.lifestyle_passages,
        )
        == []
    )

    assert result.consultation_questions == [
        "Comment interpréter cette ferritine par rapport à mes symptômes ?",
        "Un contrôle biologique ultérieur est-il utile pour le suivi ?",
    ]

    task_payload = result.to_task_explanations()
    assert task_payload["lifestyle_info"]["status"] == "grounded"
    assert task_payload["consultation_questions"] == result.consultation_questions


def test_lifestyle_grounding_retries_on_ungrounded_numbers() -> None:
    bio_passage = _make_bio_passage()
    lifestyle_passage = _make_lifestyle_passage()

    llm = _QueuedLLMClient(
        [
            json.dumps(
                {
                    "status": "grounded",
                    "text": "La ferritine reflète les réserves en fer de l'organisme.",
                    "source_ids": ["ameli-fer-2026"],
                }
            ),
            json.dumps(
                {
                    "status": "grounded",
                    "text": (
                        "Une alimentation variée avec des légumineuses, des fruits "
                        "et 45 minutes d'activité physique régulière."
                    ),
                    "source_ids": ["anses-reperes-2026"],
                }
            ),
            json.dumps(
                {
                    "status": "grounded",
                    "text": (
                        "Les repères encouragent une alimentation variée avec des "
                        "légumineuses, des fruits, des légumes et une activité physique régulière."
                    ),
                    "source_ids": ["anses-reperes-2026"],
                }
            ),
        ]
    )

    generator = RagExplanationGenerator(llm_client=llm, max_retries=1)
    result = generator.generate(
        GenerationRequest(
            parameters=[_make_ferritine()],
            passages=[bio_passage],
            lifestyle_passages=[lifestyle_passage],
            include_consultation_questions=False,
        )
    )

    assert len(llm.calls) == 3
    assert result.lifestyle_info is not None
    assert result.lifestyle_info.status == ExplanationStatus.grounded


def test_lifestyle_fallback_when_grounding_or_llm_fails() -> None:
    lifestyle_passage = _make_lifestyle_passage()

    llm = _QueuedLLMClient(
        [
            LocalLLMError("Ollama hors ligne"),
            LocalLLMError("Ollama hors ligne"),
        ]
    )
    generator = RagExplanationGenerator(llm_client=llm, max_retries=0)
    result = generator.generate(
        GenerationRequest(
            parameters=[_make_ferritine()],
            passages=[],
            lifestyle_passages=[lifestyle_passage],
            include_consultation_questions=True,
        )
    )

    assert result.lifestyle_info is not None
    assert result.lifestyle_info.status == ExplanationStatus.insufficient_sources
    assert result.lifestyle_info.source_ids == []
    assert result.consultation_questions == []
    assert result.sources == []


def test_check_lifestyle_grounding_and_question_sanitizer() -> None:
    lifestyle_passage = _make_lifestyle_passage()

    bad_lifestyle = LifestyleInfo(
        status=ExplanationStatus.grounded,
        text="Vous souffrez d'une maladie et devez prendre 99 doses.",
        source_ids=["anses-reperes-2026"],
    )
    check = check_lifestyle_grounding(bad_lifestyle, [lifestyle_passage])
    assert check.is_grounded is False
    assert check.safety_violations
    assert "99" in check.ungrounded_numbers

    sanitized = sanitize_consultation_questions(
        [
            "- Quels facteurs peuvent expliquer cette variation ?",
            "1. Quels facteurs peuvent expliquer cette variation ?",
            "Je vous prescris un suivi ?",
            "Texte trop court",
            "Ce résultat justifie-t-il des examens complémentaires ?",
        ]
    )
    assert sanitized == [
        "Quels facteurs peuvent expliquer cette variation ?",
        "Ce résultat justifie-t-il des examens complémentaires ?",
    ]


def test_find_citation_errors_flags_unknown_lifestyle_source() -> None:
    result = GenerationResult(
        summary="Test",
        lifestyle_info=LifestyleInfo(
            status=ExplanationStatus.grounded,
            text="Texte cité.",
            source_ids=["source-inconnue"],
        ),
        sources=[],
    )
    errors = find_citation_errors(result, passages=[], lifestyle_passages=[])
    assert any("Hygiène de vie" in err for err in errors)