"""Contrôle d'ancrage (grounding check) et de prudence sur les explications générées.

Vérifie qu'une explication marquée 'grounded' :
1. ne contient aucune formulation de diagnostic ou de traitement ;
2. ne contredit pas le statut réel du paramètre (normal vs hors norme) ;
3. n'introduit aucun chiffre absent du paramètre et des passages cités ;
4. recouvre lexicalement les extraits documentaires cités.
"""

from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, Field

from app.schemas import ParameterResult, ParameterStatus

from .interface import (
    ExplanationStatus,
    LifestyleInfo,
    NutritionPlan,
    ParameterExplanation,
    RetrievedPassage,
)

SAFETY_FORBIDDEN_PATTERNS = (
    r"\bvous\s+(?:souffrez|êtes\s+atteint)\b",
    r"\bvous\s+avez\s+(?:une?\s+)?(?:maladie|pathologie|anémie|diabète|insuffisance)\b",
    r"\bdiagnostic\s+(?:confirmé|positif|établi|certain)\b",
    r"\bje\s+vous\s+(?:prescris|diagnostique)\b",
    r"\btraitement\s+(?:recommandé|à\s+suivre|médicamenteux)\b",
    r"\bdébuter\s+un\s+traitement\b",
    r"\bmodifier\s+votre\s+traitement\b",
    r"\bdose\s+quotidienne\b",
)

_PLACEHOLDER_PATTERNS = (
    r"\b\d+\s*[àa-]\s*\d+\s+(?:rep[eè]res?|actions?|questions?|conseils?|exemples?|phrases?)\b",
    r"\bnom\s+exact\s+de\s+l['’]?aliment\b",
    r"\bcourte\s+phrase\s+pratique\b",
    r"\bexemple\s+issu\s+des\s+extraits\b",
    r"\btitre\s+court\s+adapt[ée]\b",
    r"\bsource_id_exact\b",
    r"\brep[eè]res?\s+d['’]hygi[eè]ne\s+de\s+vie\s*\(sommeil\b",
    r"\brep[eè]res?\s+de\s+suivi\s*\(consulter\b",
)

_NORMAL_CONTRADICTION_PATTERNS = (
    r"(?<!sans\s)(?<!aucune\s)(?<!pas\sde\s)(?<!pas\sd')\banemie\b",
    r"(?<!sans\s)(?<!aucune\s)(?<!pas\sde\s)\bcarence\b",
    r"(?<!sans\s)(?<!aucun\s)(?<!pas\sde\s)\bdeficit\b",
    r"\bhors\s+(?:des\s+)?normes?\b",
    r"\bau[-\s]dessus\s+de\s+(?:la\s+)?(?:norme|reference|fourchette|borne)\b",
    r"\ben\s+dessous\s+de\s+(?:la\s+)?(?:norme|reference|fourchette|borne)\b",
    r"\btrop\s+(?:eleve|elevee|bas|basse)\b",
    r"(?<!sans\s)(?<!aucune\s)(?<!pas\sd')\banormal(?:e|es|ite)?\b",
)

_STOPWORDS = {
    "avec",
    "ainsi",
    "alors",
    "aussi",
    "autre",
    "autres",
    "avant",
    "avoir",
    "bien",
    "cette",
    "chez",
    "comme",
    "dans",
    "depuis",
    "donc",
    "dont",
    "elle",
    "elles",
    "entre",
    "etre",
    "fait",
    "faut",
    "hors",
    "intervalle",
    "laboratoire",
    "leur",
    "leurs",
    "mais",
    "meme",
    "moins",
    "norme",
    "normes",
    "nous",
    "parametre",
    "parce",
    "parmi",
    "peut",
    "peuvent",
    "plus",
    "pour",
    "quand",
    "quel",
    "quelle",
    "quelles",
    "quels",
    "rassurant",
    "reference",
    "resultat",
    "resultats",
    "sans",
    "selon",
    "sera",
    "seront",
    "sont",
    "sous",
    "taux",
    "tous",
    "tout",
    "toute",
    "toutes",
    "tres",
    "unite",
    "utile",
    "valeur",
    "valeurs",
    "vers",
    "vous",
}


class GroundingCheckResult(BaseModel):
    """Résultat détaillé du contrôle d'ancrage d'une explication."""

    is_grounded: bool
    overlap_ratio: float
    ungrounded_numbers: list[str] = Field(default_factory=list)
    safety_violations: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def is_placeholder_text(text: str) -> bool:
    """Détecte les textes parasites ou gabarits développeur recopiés par le LLM."""
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return True
    norm = _strip_accents(cleaned.lower())
    return any(re.search(pat, norm, flags=re.IGNORECASE) for pat in _PLACEHOLDER_PATTERNS)


def check_status_consistency(text: str, status: ParameterStatus) -> list[str]:
    """Vérifie l'absence de contradiction entre le statut numérique et le texte généré."""
    norm = _strip_accents(text.lower())
    issues: list[str] = []
    if status == ParameterStatus.within_reference:
        for pat in _NORMAL_CONTRADICTION_PATTERNS:
            if re.search(pat, norm, flags=re.IGNORECASE):
                issues.append("Contradiction : le paramètre est normal mais le texte évoque une anomalie ou carence.")
                break
    elif status == ParameterStatus.above_reference:
        if re.search(r"\b(?:en\s+dessous\s+de\s+la\s+norme|trop\s+bas(?:se)?)\b", norm):
            issues.append("Contradiction : résultat au-dessus de la norme décrit comme trop bas.")
    elif status == ParameterStatus.below_reference:
        if re.search(r"\b(?:au[-\s]dessus\s+de\s+la\s+norme|trop\s+eleve(?:e)?)\b", norm):
            issues.append("Contradiction : résultat en dessous de la norme décrit comme trop élevé.")
    return issues


def _stem_fr(token: str) -> str:
    """Normalisation morphologique légère pour le français (pluriels, féminins, dérivés)."""
    if len(token) <= 4:
        return token
    for suffix in ("ements", "ement", "iques", "ique", "aires", "aire", "tions", "tion"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)]
    for suffix in ("eaux", "aux", "ees", "ies", "es", "er", "ir", "ee", "ie", "s", "x", "e"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def _content_tokens(text: str) -> set[str]:
    normalized = _strip_accents(text.lower())
    raw_tokens = set(re.findall(r"[a-z]{4,}", normalized))
    out: set[str] = set()
    for tok in raw_tokens:
        if tok in _STOPWORDS:
            continue
        out.add(_stem_fr(tok))
    return out


def _extract_numbers(text: str) -> set[str]:
    raw_nums = re.findall(r"\b\d+(?:[.,]\d+)?\b", text)
    normalized: set[str] = set()
    for item in raw_nums:
        val_str = item.replace(",", ".")
        try:
            num = float(val_str)
            normalized.add(f"{num:g}")
        except ValueError:
            normalized.add(val_str)
    return normalized


def _allowed_numbers_for(
    parameter: ParameterResult,
    cited_passages: list[RetrievedPassage],
) -> set[str]:
    allowed: set[str] = set()
    for num in (parameter.value, parameter.reference.min, parameter.reference.max):
        if num is not None:
            allowed.add(f"{float(num):g}")
    if parameter.prior is not None:
        if parameter.prior.prior_value is not None:
            allowed.add(f"{float(parameter.prior.prior_value):g}")
        if parameter.prior.delta is not None:
            allowed.add(f"{float(parameter.prior.delta):g}")
            allowed.add(f"{abs(float(parameter.prior.delta)):g}")
        if parameter.prior.prior_date:
            allowed.update(_extract_numbers(parameter.prior.prior_date))
    for passage in cited_passages:
        allowed.update(_extract_numbers(passage.excerpt))
        allowed.update(_extract_numbers(passage.source.source_id))
        if passage.source.date:
            allowed.update(_extract_numbers(passage.source.date))
    return allowed


def _allowed_numbers_for_lifestyle(
    parameters: list[ParameterResult],
    cited_passages: list[RetrievedPassage],
) -> set[str]:
    allowed: set[str] = set()
    for parameter in parameters:
        for num in (parameter.value, parameter.reference.min, parameter.reference.max):
            if num is not None:
                allowed.add(f"{float(num):g}")
    for passage in cited_passages:
        allowed.update(_extract_numbers(passage.excerpt))
        allowed.update(_extract_numbers(passage.source.source_id))
        if passage.source.date:
            allowed.update(_extract_numbers(passage.source.date))
    return allowed


def check_safety_compliance(text: str) -> list[str]:
    """Vérifie l'absence de formulation de diagnostic ou de traitement."""
    lowered = text.lower()
    violations: list[str] = []
    for pattern in SAFETY_FORBIDDEN_PATTERNS:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            violations.append(pattern)
    return violations


def check_explanation_grounding(
    explanation: ParameterExplanation,
    parameter: ParameterResult,
    passages: list[RetrievedPassage],
    min_overlap_ratio: float = 0.18,
) -> GroundingCheckResult:
    """Vérifie qu'une explication est sûre, cohérente avec le statut et ancrée dans ses passages cités."""
    if explanation.status != ExplanationStatus.grounded:
        return GroundingCheckResult(
            is_grounded=False,
            overlap_ratio=0.0,
            reasons=["L'explication n'est pas au statut 'grounded'."],
        )

    passages_by_sid: dict[str, list[RetrievedPassage]] = {}
    for passage in passages:
        passages_by_sid.setdefault(passage.source.source_id, []).append(passage)

    cited_passages: list[RetrievedPassage] = []
    for sid in explanation.source_ids:
        cited_passages.extend(passages_by_sid.get(sid, []))

    if not cited_passages:
        return GroundingCheckResult(
            is_grounded=False,
            overlap_ratio=0.0,
            reasons=["Aucun passage correspondant aux source_ids cités."],
        )

    reasons: list[str] = []
    if is_placeholder_text(explanation.text):
        reasons.append("Texte gabarit non valide détecté.")

    safety_violations = check_safety_compliance(explanation.text)
    if safety_violations:
        reasons.append("Formulation non conforme aux garde-fous de prudence détectée.")

    reasons.extend(check_status_consistency(explanation.text, parameter.status))

    allowed_nums = _allowed_numbers_for(parameter, cited_passages)
    found_nums = _extract_numbers(explanation.text)
    ungrounded_numbers = sorted(found_nums - allowed_nums)
    if ungrounded_numbers:
        reasons.append(
            f"Nombres non présents dans les passages ou le bilan : {', '.join(ungrounded_numbers)}."
        )

    text_for_tokens = explanation.text
    for sid in explanation.source_ids:
        text_for_tokens = text_for_tokens.replace(sid, " ")

    explanation_tokens = _content_tokens(text_for_tokens)
    passage_tokens: set[str] = set()
    for passage in cited_passages:
        passage_tokens.update(_content_tokens(passage.excerpt))

    if not explanation_tokens:
        overlap_ratio = 0.0
        reasons.append("Explication trop pauvre en termes vérifiables.")
    else:
        overlap_ratio = len(explanation_tokens & passage_tokens) / len(explanation_tokens)
        if overlap_ratio < min_overlap_ratio:
            reasons.append(
                f"Recouvrement lexical insuffisant ({overlap_ratio:.2f} < {min_overlap_ratio:.2f})."
            )

    return GroundingCheckResult(
        is_grounded=len(reasons) == 0,
        overlap_ratio=round(overlap_ratio, 4),
        ungrounded_numbers=ungrounded_numbers,
        safety_violations=safety_violations,
        reasons=reasons,
    )


def check_lifestyle_grounding(
    lifestyle_info: LifestyleInfo,
    lifestyle_passages: list[RetrievedPassage],
    parameters: list[ParameterResult] | None = None,
    min_overlap_ratio: float = 0.18,
) -> GroundingCheckResult:
    """Vérifie qu'une synthèse d'hygiène de vie est sûre et ancrée dans ses passages cités."""
    if lifestyle_info.status != ExplanationStatus.grounded:
        return GroundingCheckResult(
            is_grounded=False,
            overlap_ratio=0.0,
            reasons=["La section d'hygiène de vie n'est pas au statut 'grounded'."],
        )

    passages_by_sid: dict[str, list[RetrievedPassage]] = {}
    for passage in lifestyle_passages:
        passages_by_sid.setdefault(passage.source.source_id, []).append(passage)

    cited_passages: list[RetrievedPassage] = []
    for sid in lifestyle_info.source_ids:
        cited_passages.extend(passages_by_sid.get(sid, []))

    if not cited_passages:
        return GroundingCheckResult(
            is_grounded=False,
            overlap_ratio=0.0,
            reasons=["Aucun passage d'hygiène de vie correspondant aux source_ids cités."],
        )

    reasons: list[str] = []
    if is_placeholder_text(lifestyle_info.text):
        reasons.append("Texte gabarit non valide détecté.")

    safety_violations = check_safety_compliance(lifestyle_info.text)
    if safety_violations:
        reasons.append("Formulation non conforme aux garde-fous de prudence détectée.")

    allowed_nums = _allowed_numbers_for_lifestyle(parameters or [], cited_passages)
    found_nums = _extract_numbers(lifestyle_info.text)
    ungrounded_numbers = sorted(found_nums - allowed_nums)
    if ungrounded_numbers:
        reasons.append(
            f"Nombres non présents dans les passages d'hygiène de vie : {', '.join(ungrounded_numbers)}."
        )

    text_for_tokens = lifestyle_info.text
    for sid in lifestyle_info.source_ids:
        text_for_tokens = text_for_tokens.replace(sid, " ")

    text_tokens = _content_tokens(text_for_tokens)
    passage_tokens: set[str] = set()
    for passage in cited_passages:
        passage_tokens.update(_content_tokens(passage.excerpt))

    if not text_tokens:
        overlap_ratio = 0.0
        reasons.append("Texte d'hygiène de vie trop pauvre en termes vérifiables.")
    else:
        overlap_ratio = len(text_tokens & passage_tokens) / len(text_tokens)
        if overlap_ratio < min_overlap_ratio:
            reasons.append(
                f"Recouvrement lexical insuffisant ({overlap_ratio:.2f} < {min_overlap_ratio:.2f})."
            )

    return GroundingCheckResult(
        is_grounded=len(reasons) == 0,
        overlap_ratio=round(overlap_ratio, 4),
        ungrounded_numbers=ungrounded_numbers,
        safety_violations=safety_violations,
        reasons=reasons,
    )


def check_nutrition_grounding(
    nutrition_plan: NutritionPlan,
    lifestyle_passages: list[RetrievedPassage],
    parameters: list[ParameterResult] | None = None,
    min_overlap_ratio: float = 0.16,
) -> GroundingCheckResult:
    """Vérifie qu'un plan nutritionnel structuré reste sûr et ancré dans les passages officiels."""
    parts = [nutrition_plan.intro, nutrition_plan.section_title]
    for h in nutrition_plan.highlights:
        parts.extend([h.title, h.subtitle])
    for row in nutrition_plan.daily_meal_plan:
        parts.extend([row.meal, row.example])
    combined_text = " ".join(p for p in parts if p).strip()
    if not combined_text or not nutrition_plan.source_ids:
        return GroundingCheckResult(
            is_grounded=False,
            overlap_ratio=0.0,
            reasons=["Plan nutritionnel vide ou sans citation."],
        )
    proxy = LifestyleInfo(
        status=nutrition_plan.status,
        text=combined_text,
        source_ids=nutrition_plan.source_ids,
    )
    return check_lifestyle_grounding(
        lifestyle_info=proxy,
        lifestyle_passages=lifestyle_passages,
        parameters=parameters,
        min_overlap_ratio=min_overlap_ratio,
    )


def sanitize_consultation_questions(
    raw_questions: list[object],
    max_questions: int = 4,
) -> list[str]:
    """Filtre les questions générées pour garantir neutralité, sûreté et absence de texte gabarit."""
    cleaned_questions: list[str] = []
    seen_normalized: set[str] = set()

    for item in raw_questions:
        if not isinstance(item, str):
            continue
        stripped = re.sub(r"^(?:[-*•]+|\d+[.)])\s*", "", item.strip())
        normalized = " ".join(stripped.split())
        if len(normalized) < 10 or len(normalized) > 240:
            continue
        if not normalized.endswith("?"):
            continue
        if is_placeholder_text(normalized):
            continue
        if check_safety_compliance(normalized):
            continue
        dedup_key = normalized.lower()
        if dedup_key in seen_normalized:
            continue
        seen_normalized.add(dedup_key)
        cleaned_questions.append(normalized)
        if len(cleaned_questions) >= max_questions:
            break

    return cleaned_questions


def sanitize_action_steps(
    raw_steps: list[object],
    max_steps: int = 6,
) -> list[str]:
    """Filtre les étapes d'action pour garantir prudence, clarté et absence de gabarits/doublons."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw_steps:
        if not isinstance(item, str):
            continue
        stripped = re.sub(r"^(?:[-*•]+|\d+[.)])\s*", "", item.strip())
        normalized = " ".join(stripped.split())
        if len(normalized) < 12 or len(normalized) > 260:
            continue
        if is_placeholder_text(normalized):
            continue
        if check_safety_compliance(normalized):
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(normalized)
        if len(cleaned) >= max_steps:
            break
    return cleaned
