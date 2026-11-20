import json

import pytest

from app.generation import (
    GROUNDED_SUMMARY,
    INSUFFICIENT_SOURCES_SUMMARY,
    ExplanationGenerator,
    ExplanationStatus,
    GenerationRequest,
    LocalLLMError,
    OllamaLLMClient,
    RagExplanationGenerator,
    RetrievedPassage,
    find_citation_errors,
)
from app.schemas import DISCLAIMER, Source, parameter_from_dict
from app.validation.analysis import analyze_parameters


def _sample_parameters():
    items = analyze_parameters(
        [
            {
                "code": "HGB",
                "name_printed": "Hémoglobine",
                "value": 13.5,
                "unit": "g/dL",
                "reference_min": 12.0,
                "reference_max": 16.0,
                "raw_line": "Hémoglobine 13,5 g/dL 12,0 - 16,0",
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
    return [parameter_from_dict(item) for item in items]


def _sample_passages():
    return [
        RetrievedPassage(
            passage_id="ameli-nfs#001",
            source=Source(
                source_id="ameli-nfs-2025",
                title="Comprendre l'hémogramme",
                organisme="Assurance Maladie",
                url="https://www.ameli.fr/assure/sante/examen/hemogramme",
                date="2025-01-20",
            ),
            excerpt="L'hémoglobine est une protéine des globules rouges qui transporte l'oxygène.",
            score=0.91,
        )
    ]


class _FakeLLMClient:
    def __init__(self, response: str | None = None, error: Exception | None = None):
        self.response = response or ""
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if self.error is not None:
            raise self.error
        return self.response


def test_rag_generator_implements_protocol():
    gen = RagExplanationGenerator(_FakeLLMClient("{}"))
    assert isinstance(gen, ExplanationGenerator)


def test_rag_skips_llm_when_no_passages():
    llm = _FakeLLMClient("{}")
    gen = RagExplanationGenerator(llm)
    params = _sample_parameters()

    result = gen.generate(GenerationRequest(parameters=params, passages=[]))

    assert llm.calls == []
    assert result.summary == INSUFFICIENT_SOURCES_SUMMARY
    assert result.sources == []
    assert result.parameter_explanations[0].status == ExplanationStatus.insufficient_sources
    assert result.parameter_explanations[1].status == ExplanationStatus.not_analyzed


def test_rag_generates_grounded_explanation_and_skips_not_analyzed():
    payload = json.dumps(
        {
            "status": "grounded",
            "text": "L'hémoglobine transporte l'oxygène dans les globules rouges (ameli-nfs-2025).",
            "source_ids": ["ameli-nfs-2025"],
        }
    )
    llm = _FakeLLMClient(f"```json\n{payload}\n```")
    gen = RagExplanationGenerator(llm)
    params = _sample_parameters()
    passages = _sample_passages()

    result = gen.generate(GenerationRequest(parameters=params, passages=passages))

    # Le LLM n'a été appelé qu'une fois (HGB), jamais pour HCT (not_analyzed)
    assert len(llm.calls) == 1
    assert result.summary == GROUNDED_SUMMARY
    assert result.disclaimer == DISCLAIMER
    assert len(result.sources) == 1
    assert result.sources[0].source_id == "ameli-nfs-2025"

    by_code = {item.code: item for item in result.parameter_explanations}
    assert by_code["HGB"].status == ExplanationStatus.grounded
    assert by_code["HGB"].source_ids == ["ameli-nfs-2025"]
    assert by_code["HCT"].status == ExplanationStatus.not_analyzed
    assert find_citation_errors(result, passages) == []


def test_rag_rejects_hallucinated_source_id_and_falls_back():
    payload = json.dumps(
        {
            "status": "grounded",
            "text": "Affirmation non vérifiée.",
            "source_ids": ["source-inventee-999"],
        }
    )
    llm = _FakeLLMClient(payload)
    gen = RagExplanationGenerator(llm)
    params = [_sample_parameters()[0]]
    passages = _sample_passages()

    result = gen.generate(GenerationRequest(parameters=params, passages=passages))

    assert result.parameter_explanations[0].status == ExplanationStatus.insufficient_sources
    assert result.parameter_explanations[0].source_ids == []
    assert result.sources == []
    assert result.summary == INSUFFICIENT_SOURCES_SUMMARY
    assert find_citation_errors(result, passages) == []


def test_rag_falls_back_cleanly_on_invalid_json_or_llm_error():
    params = [_sample_parameters()[0]]
    passages = _sample_passages()

    for llm in (
        _FakeLLMClient("ceci n'est pas du json"),
        _FakeLLMClient(error=LocalLLMError("Ollama hors ligne")),
    ):
        result = RagExplanationGenerator(llm).generate(
            GenerationRequest(parameters=params, passages=passages)
        )
        assert result.parameter_explanations[0].status == ExplanationStatus.insufficient_sources
        assert result.sources == []
        assert find_citation_errors(result, passages) == []


def test_ollama_client_blocks_remote_urls_by_default():
    with pytest.raises(ValueError):
        OllamaLLMClient(base_url="https://api.openai.com/v1")

    local_client = OllamaLLMClient(base_url="http://127.0.0.1:11434")
    assert local_client.base_url == "http://127.0.0.1:11434"