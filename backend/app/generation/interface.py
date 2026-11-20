"""Contrat du composant de génération d'explications.

Ce module ne contient aucune connaissance médicale ni règle métier :
il définit uniquement les structures d'entrée/sortie, l'interface abstraite
d'un générateur et les vérifications techniques d'ancrage des citations.
"""
from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field, model_validator

from app.schemas import DISCLAIMER, ParameterResult, Source


class ExplanationStatus(str, Enum):
    """État de disponibilité documentaire pour l'explication d'un paramètre."""

    grounded = "grounded"
    insufficient_sources = "insufficient_sources"
    not_analyzed = "not_analyzed"


class RetrievedPassage(BaseModel):
    """Passage documentaire issu d'une source vérifiée (fourni par le RAG)."""

    passage_id: str = Field(min_length=1)
    source: Source
    excerpt: str = Field(min_length=1)
    score: float | None = None


class ParameterExplanation(BaseModel):
    """Explication pédagogique associée à un paramètre biologique."""

    code: str = Field(min_length=1)
    status: ExplanationStatus
    text: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_citations_consistency(self) -> ParameterExplanation:
        if self.status == ExplanationStatus.grounded and not self.source_ids:
            raise ValueError(
                "Une explication au statut 'grounded' doit citer au moins un source_id."
            )
        if self.status != ExplanationStatus.grounded and self.source_ids:
            raise ValueError(
                "Une explication sans base documentaire suffisante ne doit pas citer de source_id."
            )
        return self


class LifestyleInfo(BaseModel):
    """Informations générales d'hygiène de vie issues exclusivement de sources officielles."""

    status: ExplanationStatus
    text: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_citations_consistency(self) -> LifestyleInfo:
        if self.status == ExplanationStatus.grounded and not self.source_ids:
            raise ValueError(
                "Une information d'hygiène de vie au statut 'grounded' doit citer au moins un source_id."
            )
        if self.status != ExplanationStatus.grounded and self.source_ids:
            raise ValueError(
                "Une information d'hygiène de vie sans source suffisante ne doit pas citer de source_id."
            )
        return self


class SectionSummaryItem(BaseModel):
    """Synthèse pédagogique d'un sous-groupe de paramètres issue des sources vérifiées."""

    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)


class NutritionHighlight(BaseModel):
    """Famille ou aliment mis en avant à partir des sources publiques ANSES/Ciqual."""

    title: str = Field(min_length=1)
    subtitle: str = Field(min_length=1)
    image_key: str = "balanced"


class MealPlanRow(BaseModel):
    """Ligne d'exemple d'une journée alimentaire équilibrée issue des sources."""

    meal: str = Field(min_length=1)
    example: str = Field(min_length=1)


class NutritionPlan(BaseModel):
    """Section structurée d'orientation alimentaire sourcée (ANSES / Ciqual / Ameli)."""

    status: ExplanationStatus
    intro: str = ""
    section_title: str = ""
    highlights: list[NutritionHighlight] = Field(default_factory=list)
    daily_meal_plan: list[MealPlanRow] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class GenerationRequest(BaseModel):
    """Entrée attendue par tout générateur d'explications."""

    parameters: list[ParameterResult] = Field(default_factory=list)
    passages: list[RetrievedPassage] = Field(default_factory=list)
    lifestyle_passages: list[RetrievedPassage] = Field(default_factory=list)
    include_consultation_questions: bool = False


class GenerationResult(BaseModel):
    """Sortie structurée du module de génération, alignée sur le contrat API v1."""

    summary: str | None = None
    parameter_explanations: list[ParameterExplanation] = Field(default_factory=list)
    section_summaries: list[SectionSummaryItem] = Field(default_factory=list)
    lifestyle_info: LifestyleInfo | None = None
    nutrition_plan: NutritionPlan | None = None
    action_steps: list[str] = Field(default_factory=list)
    consultation_questions: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER

    def to_task_explanations(self) -> dict:
        """Sérialise la partie explicative pour le champ `Task.explanations`."""
        payload: dict = {
            "summary": self.summary,
            "parameter_explanations": [
                item.model_dump(mode="json") for item in self.parameter_explanations
            ],
        }
        if self.section_summaries:
            payload["section_summaries"] = [
                item.model_dump(mode="json") for item in self.section_summaries
            ]
        if self.lifestyle_info is not None:
            payload["lifestyle_info"] = self.lifestyle_info.model_dump(mode="json")
        if self.nutrition_plan is not None:
            payload["nutrition_plan"] = self.nutrition_plan.model_dump(mode="json")
        if self.action_steps:
            payload["action_steps"] = list(self.action_steps)
        if self.consultation_questions:
            payload["consultation_questions"] = list(self.consultation_questions)
        return payload


@runtime_checkable
class ExplanationGenerator(Protocol):
    """Interface à implémenter par tout générateur (repli neutre ou LLM+RAG)."""

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """Produit des explications uniquement à partir de la requête fournie."""
        ...


def find_citation_errors(
    result: GenerationResult,
    passages: list[RetrievedPassage],
    lifestyle_passages: list[RetrievedPassage] | None = None,
) -> list[str]:
    """Vérifie techniquement la cohérence entre citations, sources exposées et passages reçus."""
    errors: list[str] = []
    all_passages = list(passages)
    if lifestyle_passages:
        all_passages.extend(lifestyle_passages)

    allowed_source_ids = {p.source.source_id for p in all_passages}
    exposed_source_ids = {s.source_id for s in result.sources}

    if result.disclaimer != DISCLAIMER:
        errors.append("Le disclaimer du résultat ne correspond pas au disclaimer officiel.")

    for src in result.sources:
        if src.source_id not in allowed_source_ids:
            errors.append(
                f"Source exposée absente des passages fournis : '{src.source_id}'."
            )

    for exp in result.parameter_explanations:
        for sid in exp.source_ids:
            if sid not in allowed_source_ids:
                errors.append(
                    f"Paramètre {exp.code} : source_id inconnu '{sid}'."
                )
            if sid not in exposed_source_ids:
                errors.append(
                    f"Paramètre {exp.code} : source_id '{sid}' cité mais absent de result.sources."
                )

    for summary_item in result.section_summaries:
        for sid in summary_item.source_ids:
            if sid not in allowed_source_ids:
                errors.append(f"Synthèse {summary_item.title} : source_id inconnu '{sid}'.")
            if sid not in exposed_source_ids:
                errors.append(
                    f"Synthèse {summary_item.title} : source_id '{sid}' cité mais absent de result.sources."
                )

    if result.lifestyle_info is not None:
        for sid in result.lifestyle_info.source_ids:
            if sid not in allowed_source_ids:
                errors.append(
                    f"Hygiène de vie : source_id inconnu '{sid}'."
                )
            if sid not in exposed_source_ids:
                errors.append(
                    f"Hygiène de vie : source_id '{sid}' cité mais absent de result.sources."
                )

    if result.nutrition_plan is not None:
        for sid in result.nutrition_plan.source_ids:
            if sid not in allowed_source_ids:
                errors.append(f"Plan nutritionnel : source_id inconnu '{sid}'.")
            if sid not in exposed_source_ids:
                errors.append(
                    f"Plan nutritionnel : source_id '{sid}' cité mais absent de result.sources."
                )

    return errors
