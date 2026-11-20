import json

from app.generation import (
    ExplanationStatus,
    GenerationRequest,
    ParameterExplanation,
    RagExplanationGenerator,
    RetrievedPassage,
    check_explanation_grounding,
    find_citation_errors,
)
from app.schemas import Source, parameter_from_dict
from app.validation.analysis import analyze_parameters


def _param():
    item = analyze_parameters(
        [
            {
                "code": "HGB",
                "name_printed": "Hémoglobine",
                "value": 10.5,
                "unit": "g/dL",
                "reference_min": 12.0,
                "reference_max": 16.0,
                "raw_line": "Hémoglobine 10,5 g/dL 12,0 - 16,0",
            }
        ]
    )[0]
    return parameter_from_dict(item)


def _passages():
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
            excerpt=(
                "L'hémoglobine est une protéine présente dans les globules rouges "
                "qui assure le transport de l'oxygène dans l'organisme."
            ),
        )
    ]


class _SequenceLLM:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.prompts: list[str] = []

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.prompts.append(user_prompt)
        return self.responses.pop(0)


def test_grounding_accepts_faithful_explanation():
    param = _param()
    passages = _passages()
    exp = ParameterExplanation(
        code="HGB",
        status=ExplanationStatus.grounded,
        text=(
            "Votre taux est de 10.5 g/dL pour un intervalle de 12.0 à 16.0. "
            "L'hémoglobine est une protéine des globules rouges qui transporte l'oxygène."
        ),
        source_ids=["ameli-nfs-2025"],
    )

    check = check_explanation_grounding(exp, param, passages)
    assert check.is_grounded is True
    assert check.overlap_ratio >= 0.25
    assert check.ungrounded_numbers == []
    assert check.safety_violations == []


def test_grounding_rejects_invented_number():
    param = _param()
    passages = _passages()
    exp = ParameterExplanation(
        code="HGB",
        status=ExplanationStatus.grounded,
        text="L'hémoglobine transporte l'oxygène et nécessite 500 unités par jour.",
        source_ids=["ameli-nfs-2025"],
    )

    check = check_explanation_grounding(exp, param, passages)
    assert check.is_grounded is False
    assert "500" in check.ungrounded_numbers


def test_grounding_rejects_diagnostic_statement():
    param = _param()
    passages = _passages()
    exp = ParameterExplanation(
        code="HGB",
        status=ExplanationStatus.grounded,
        text="Vous souffrez d'une maladie liée à l'hémoglobine des globules rouges.",
        source_ids=["ameli-nfs-2025"],
    )

    check = check_explanation_grounding(exp, param, passages)
    assert check.is_grounded is False
    assert check.safety_violations


def test_rag_retries_once_and_accepts_corrected_answer():
    param = _param()
    passages = _passages()

    first_bad = json.dumps(
        {
            "status": "grounded",
            "text": "Vous souffrez d'une anémie et il faut 999 mg.",
            "source_ids": ["ameli-nfs-2025"],
        }
    )
    second_good = json.dumps(
        {
            "status": "grounded",
            "text": "L'hémoglobine transporte l'oxygène dans les globules rouges.",
            "source_ids": ["ameli-nfs-2025"],
        }
    )
    llm = _SequenceLLM([first_bad, second_good])
    gen = RagExplanationGenerator(llm, max_retries=1)

    result = gen.generate(GenerationRequest(parameters=[param], passages=passages))

    assert len(llm.prompts) == 2
    assert "CORRECTION OBLIGATOIRE" in llm.prompts[1]
    assert result.parameter_explanations[0].status == ExplanationStatus.grounded
    assert find_citation_errors(result, passages) == []


def test_rag_falls_back_if_retry_also_fails_grounding():
    param = _param()
    passages = _passages()

    ungrounded = json.dumps(
        {
            "status": "grounded",
            "text": "Texte inventé avec un seuil imaginaire de 420.",
            "source_ids": ["ameli-nfs-2025"],
        }
    )
    llm = _SequenceLLM([ungrounded, ungrounded])
    gen = RagExplanationGenerator(llm, max_retries=1)

    result = gen.generate(GenerationRequest(parameters=[param], passages=passages))

    assert len(llm.prompts) == 2
    assert result.parameter_explanations[0].status == ExplanationStatus.insufficient_sources
    assert result.sources == []
    assert find_citation_errors(result, passages) == []