"""Pipeline RAG réel pour LabMind : prompts stricts, parsing JSON et contrôle d'ancrage."""
from __future__ import annotations

import inspect
import json
import re
import unicodedata

from app.schemas import DISCLAIMER, ParameterResult, ParameterStatus, Source

from .fallback import (
    INSUFFICIENT_SOURCES_SUMMARY,
    InsufficientSourcesGenerator,
    build_unavailable_explanation,
    build_unavailable_lifestyle_info,
)
from .grounding import (
    check_explanation_grounding,
    check_lifestyle_grounding,
    check_nutrition_grounding,
    is_placeholder_text,
    sanitize_action_steps,
    sanitize_consultation_questions,
)
from .interface import (
    ExplanationStatus,
    GenerationRequest,
    GenerationResult,
    GuidanceSections,
    LifestyleInfo,
    MealPlanRow,
    NutritionHighlight,
    NutritionPlan,
    ParameterExplanation,
    RetrievedPassage,
    SectionSummaryItem,
)
from .llm_client import LocalLLMClient, LocalLLMError

SYSTEM_PROMPT = (
    "Tu es un assistant d'information biologique pédagogique pour LabMind.\n"
    "Règles absolues :\n"
    "1. Réponds uniquement en JSON valide avec les clés : "
    '"status" ("grounded" ou "insufficient_sources"), "text" (chaîne sur une seule ligne), '
    '"source_ids" (liste de chaînes).\n'
    "2. Rédige `text` en français simple, direct et concis (2 phrases courtes maximum, 3 si hors norme) :\n"
    "   - phrase 1 : rôle du paramètre dans l'organisme (strictement issu de l'extrait) ;\n"
    "   - phrase 2 : signification du résultat par rapport aux bornes du laboratoire (si NORMAL : confirme clairement que la valeur est dans les normes et n'évoque JAMAIS d'anémie, de carence ou d'anomalie) ;\n"
    "   - phrase 3 (uniquement si hors norme) : brève piste issue de l'extrait et invitation à en parler au médecin (avis rapide si écart marqué), sans jamais diagnostiquer.\n"
    "   - si l'extrait ne couvre pas ce paramètre, retourne status=\"insufficient_sources\" et source_ids=[].\n"
    "3. Cite uniquement le source_id exact de l'extrait utilisé, sans inventer de chiffre."
)


LIFESTYLE_SYSTEM_PROMPT = (
    "Tu es un assistant d'information de santé publique pédagogique pour LabMind.\n"
    "Règles absolues :\n"
    "1. Réponds uniquement en JSON valide avec les clés : "
    '"status" ("grounded" ou "insufficient_sources"), "text" (liste de 3 à 4 puces courtes commençant par « - »), '
    '"source_ids" (liste de chaînes).\n'
    "2. Synthétise uniquement les repères généraux d'alimentation variée, d'hydratation, d'activité physique, de sommeil et d'arrêt du tabac/modération alcool présents dans les extraits officiels fournis.\n"
    "3. Ne mentionne un nutriment particulier que s'il figure dans les paramètres du bilan et dans les extraits.\n"
    "4. N'écris JAMAIS de valeur chiffrée absente des extraits, ni de contre-indication ignorée.\n"
    "5. Cite uniquement les source_ids exacts des extraits utilisés ; retourne status=\"grounded\" dès qu'un extrait officiel est fourni."
)

NUTRITION_SYSTEM_PROMPT = (
    "Tu es un assistant d'information nutritionnelle pédagogique pour LabMind, strictement ancré dans les extraits officiels fournis.\n"
    "Réponds UNIQUEMENT en JSON valide respectant les clés suivantes :\n"
    "{\n"
    '  "status": "grounded",\n'
    '  "intro": "...",\n'
    '  "section_title": "Aliments adaptés à votre bilan",\n'
    '  "highlights": [{"title": "...", "subtitle": "...", "image_key": "almonds_walnuts"}],\n'
    '  "daily_meal_plan": [{"meal": "Petit-déjeuner", "example": "..."}],\n'
    '  "source_ids": ["..."]\n'
    "}\n"
    "Règles impératives :\n"
    "- N'écris JAMAIS de texte générique ou de consigne recopiée.\n"
    "- `highlights` doit contenir 4 à 5 aliments précis et simples (par exemple : Amandes, Noix, Graines de courge, Poissons, Céréales complètes, Fruits, Légumes), JAMAIS d'intitulé vague comme 'Fer héminique' ou 'Viandes, poissons, abats'.\n"
    "- Clés `image_key` autorisées (chacune utilisée UNE SEULE FOIS maximum) : almonds_walnuts, walnuts, pumpkin_seeds, spinach, lentils_chickpeas, fish, fruits, whole_grains, vegetables.\n"
    "- `daily_meal_plan` : propose 3 ou 4 repas (Petit-déjeuner, Déjeuner, Goûter, Dîner) issus uniquement des extraits, sans chiffre inventé."
)


ACTIONS_SYSTEM_PROMPT = (
    "Tu es un assistant pédagogique pour LabMind.\n"
    "À partir du bilan et des extraits officiels fournis, réponds uniquement en JSON valide :\n"
    "{\n"
    '  "categories": {\n'
    '    "nutrition": [],\n'
    '    "physical_activity": [],\n'
    '    "lifestyle_prevention": []\n'
    "  },\n"
    '  "steps": [],\n'
    '  "questions": []\n'
    "}\n"
    "Règles impératives :\n"
    "- Remplis chaque liste avec des phrases complètes, concrètes et rédigées pour le patient (JAMAIS de méta-instruction du style '1 à 3 repères...').\n"
    "- `physical_activity` : 1 à 2 phrases d'activité physique adaptée et progressive.\n"
    "- `lifestyle_prevention` : 1 à 2 phrases d'hygiène de vie (sommeil régulier, hydratation, arrêt du tabac, modération de l'alcool).\n"
    "- `questions` : 4 questions polies, courtes et naturelles pour le médecin, ciblant uniquement les anomalies réelles du bilan.\n"
    "- Aucune prescription, aucune dose chiffrée, aucun diagnostic."
)


QUESTIONS_SYSTEM_PROMPT = (
    "Tu es un assistant pédagogique pour LabMind qui aide un patient à préparer sa consultation médicale.\n"
    "Règles absolues :\n"
    "1. Réponds uniquement en JSON valide avec la clé "
    "\"questions\" (liste de 4 questions courtes, polies et naturelles en français se terminant par \"?\").\n"
    "2. Exemple de formulation attendue pour un paramètre légèrement bas : "
    '"Mon taux de magnésium est légèrement inférieur à la normale. Est-il nécessaire de le contrôler ?", '
    '"Quelles peuvent être les causes de cette diminution ?", '
    '"Mon alimentation peut-elle influencer ce résultat ?", '
    "\"Faut-il réaliser d'autres examens pour mieux comprendre cette anomalie ?\".\n"
    "3. Respecte strictement le sens observé (bas vs élevé) et n'interroge pas sur des paramètres satisfaisants sauf suivi pertinent.\n"
    "4. Évite les formulations alarmistes (« est-ce que je suis malade ? »), les répétitions, le jargon complexe et toute mention de médicament ou de dose."
)

GROUNDED_SUMMARY = (
    "Explications pédagogiques produites exclusivement à partir des sources "
    "documentaires vérifiées."
)

_GENERIC_NOISE_WORDS = {
    "taux",
    "sang",
    "sanguin",
    "serique",
    "plasmatique",
    "total",
    "totale",
    "totaux",
    "jeun",
    "prise",
    "bilan",
    "calcul",
    "indice",
    "dosage",
    "polynucleaires",
}

_PARAMETER_ALIASES: dict[str, tuple[str, ...]] = {
    "RBC": ("globule rouge", "globules rouges", "hematie", "erythrocyte"),
    "WBC": ("globule blanc", "globules blancs", "leucocyte"),
    "HGB": ("hemoglobine",),
    "HCT": ("hematocrite",),
    "VGM": ("volume globulaire moyen", "vgm"),
    "TCMH": ("teneur corpusculaire moyenne", "tcmh"),
    "CCMH": ("concentration corpusculaire moyenne", "ccmh"),
    "PLT": ("plaquette", "thrombocyte"),
    "NEUT": ("neutrophile", "neutrophiles"),
    "LYMPH": ("lymphocyte", "lymphocytes"),
    "MONO": ("monocyte", "monocytes"),
    "EOS": ("eosinophile", "eosinophiles"),
    "BASO": ("basophile", "basophiles"),
    "GLY": ("glycemie", "glucose"),
    "HBA1C": ("glyquee", "hba1c", "glycemie"),
    "CREAT": ("creatinine", "renal"),
    "UREE": ("uree", "renal"),
    "DFG": ("filtration", "glomerulaire", "renal", "dfg"),
    "URIC": ("urique", "uricemie"),
    "FER": ("fer", "martial"),
    "FERR": ("ferritine", "fer", "martial"),
    "TRANSF": ("transferrine", "fer", "martial"),
    "CA": ("calcium",),
    "MG": ("magnesium",),
    "CHOL": ("cholesterol", "lipidique"),
    "HDL": ("hdl", "cholesterol"),
    "LDL": ("ldl", "cholesterol"),
    "TG": ("triglyceride", "lipidique"),
    "ALAT": ("alat", "transaminase", "hepatique"),
    "ASAT": ("asat", "transaminase", "hepatique"),
    "GGT": ("ggt", "gamma", "hepatique"),
    "BILI": ("bilirubine", "hepatique"),
}

_LIFESTYLE_NOISE_MARKERS = (
    "contaminants",
    "arsenic",
    "acrylamide",
    "plomb",
    "ces valeurs reperes comprennent",
    "besoin nutritionnel moyen",
    "apport satisfaisant",
    "limite superieure de securite",
)

_ALLOWED_IMAGE_KEYS = {
    "almonds_walnuts",
    "walnuts",
    "pumpkin_seeds",
    "spinach",
    "lentils_chickpeas",
    "fish",
    "fruits",
    "whole_grains",
    "vegetables",
    "neutral",
}

_FOOD_STEM_MAP: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("walnuts", ("cerneau", "noix de grenoble", "noix")),
    ("almonds_walnuts", ("amand", "noisett", "oleagineu", "pistach")),
    ("pumpkin_seeds", ("courge", "graine", "sesame", "tournesol", "lin")),
    ("spinach", ("epinard", "bette", "feuille verte")),
    ("lentils_chickpeas", ("lentill", "chiche", "haricot", "legumineus", "pois", "feve")),
    ("fish", ("poisson", "saumon", "sardine", "maquereau", "hareng", "truite", "thon")),
    ("fruits", ("fruit", "orange", "agrume", "pomme", "kiwi", "baie", "fraise", "banane", "citron")),
    ("whole_grains", ("cereal", "complet", "avoine", "quinoa", "riz", "pain", "seigle", "ble")),
    ("vegetables", ("legume", "brocoli", "carotte", "poivron", "courgette", "tomate")),
)

_NON_MAPPED_PRIMARY_FOOD_STEMS = (
    "fer heminique",
    "viande",
    "abat",
    "boudin",
    "foie",
    "oeuf",
    "fromage",
    "yaourt",
    "lait",
    "eau",
)


def _matches_stem_word(norm_text: str, stem: str) -> bool:
    if " " in stem:
        return stem in norm_text
    return bool(re.search(rf"\b{re.escape(stem)}\w*", norm_text))


def _resolve_food_image_key(
    title: str,
    subtitle: str,
    raw_key: str,
    used_keys: set[str],
) -> str:
    """Associe chaque aliment à une image distincte correspondant réellement à son nom."""
    norm_title = _strip_accents(title)
    norm_sub = _strip_accents(subtitle)

    if any(_matches_stem_word(norm_title, stem) for stem in _NON_MAPPED_PRIMARY_FOOD_STEMS):
        if not any(
            _matches_stem_word(norm_title, fstem)
            for _, fstems in _FOOD_STEM_MAP
            for fstem in fstems
        ):
            return "neutral"

    candidates: list[str] = []
    for key, stems in _FOOD_STEM_MAP:
        if any(_matches_stem_word(norm_title, stem) for stem in stems):
            candidates.append(key)

    if not candidates:
        for key, stems in _FOOD_STEM_MAP:
            if any(_matches_stem_word(norm_sub, stem) for stem in stems):
                candidates.append(key)

    cleaned_raw = raw_key.strip()
    if cleaned_raw in _ALLOWED_IMAGE_KEYS and cleaned_raw not in ("balanced", "neutral"):
        if not candidates:
            candidates.append(cleaned_raw)

    for candidate in candidates:
        if candidate not in used_keys:
            used_keys.add(candidate)
            return candidate

    return "neutral"


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(ch)
    )


def _describe_position(parameter: ParameterResult) -> str:
    """Décrit de façon purement arithmétique la position par rapport à la référence."""
    if parameter.status == ParameterStatus.below_reference:
        return "en dessous de la fourchette de référence du laboratoire"
    if parameter.status == ParameterStatus.within_reference:
        return "dans la fourchette de référence du laboratoire"
    if parameter.status == ParameterStatus.above_reference:
        return "au-dessus de la fourchette de référence du laboratoire"
    if parameter.status == ParameterStatus.reference_unavailable:
        return "fourchette de référence non indiquée sur le document"
    if parameter.status == ParameterStatus.value_unavailable:
        return "valeur numérique non disponible"
    return "non analysé"


def _format_reference(parameter: ParameterResult) -> str:
    """Formate proprement la référence, y compris les bornes simples (< max ou > min)."""
    ref = parameter.reference
    unit_suffix = f" {parameter.unit}" if parameter.unit else ""
    if ref.min is not None and ref.max is not None:
        return f"entre {ref.min:g} et {ref.max:g}{unit_suffix}"
    if ref.max is not None:
        return f"inférieure à {ref.max:g}{unit_suffix}"
    if ref.min is not None:
        return f"supérieure à {ref.min:g}{unit_suffix}"
    return "non fournie sur le document"


def _parameter_search_terms(parameter: ParameterResult) -> tuple[list[str], list[str]]:
    """Retourne les expressions et mots-clés propres à un paramètre."""
    name_words = [
        w
        for w in re.findall(r"[a-z]{3,}", _strip_accents(parameter.name_printed))
        if w not in _GENERIC_NOISE_WORDS
    ]
    code_norm = _strip_accents(parameter.code)
    aliases = _PARAMETER_ALIASES.get(parameter.code.upper(), ())

    phrases = [a for a in aliases if " " in a]
    single_terms: list[str] = []
    for term in [*name_words, code_norm, *(a for a in aliases if " " not in a)]:
        if len(term) >= 2 and term not in single_terms:
            single_terms.append(term)

    return phrases, single_terms


def _select_relevant_passages(
    parameter: ParameterResult,
    passages: list[RetrievedPassage],
    limit: int = 2,
) -> list[RetrievedPassage]:
    """Sélectionne uniquement les extraits qui traitent réellement du paramètre."""
    if not passages:
        return []

    phrases, single_terms = _parameter_search_terms(parameter)
    scored: list[tuple[int, int, RetrievedPassage]] = []

    for idx, passage in enumerate(passages):
        haystack = _strip_accents(f"{passage.source.title} {passage.excerpt}")
        haystack_words = set(re.findall(r"[a-z0-9]{2,}", haystack))
        hits = 0
        for phrase in phrases:
            if phrase in haystack:
                hits += 3
        for term in single_terms:
            if len(term) >= 4:
                if term in haystack:
                    hits += 2
            elif term in haystack_words:
                hits += 2
        scored.append((hits, -idx, passage))

    scored.sort(reverse=True)
    matched = [item[2] for item in scored if item[0] > 0][:limit]
    if matched:
        return matched

    return passages[:limit] if len(passages) <= 2 else []


def _select_lifestyle_passages(
    lifestyle_passages: list[RetrievedPassage],
    limit: int = 3,
) -> list[RetrievedPassage]:
    """Garde les extraits d'hygiène de vie les plus utiles sans bruit réglementaire."""
    if len(lifestyle_passages) <= limit:
        return lifestyle_passages

    clean = [
        p
        for p in lifestyle_passages
        if not any(marker in _strip_accents(p.excerpt) for marker in _LIFESTYLE_NOISE_MARKERS)
    ]
    selected = list(clean[:limit])
    for p in lifestyle_passages:
        if p not in selected:
            selected.append(p)
        if len(selected) >= limit:
            break
    return selected


def _build_extractive_lifestyle_fallback(
    lifestyle_passages: list[RetrievedPassage],
    parameters: list[ParameterResult],
) -> LifestyleInfo | None:
    """Construit une synthèse à puces directement extraite des passages officiels FAISS."""
    if not lifestyle_passages:
        return None

    bullets: list[str] = []
    source_ids: list[str] = []
    seen_lines: set[str] = set()

    for passage in _select_lifestyle_passages(lifestyle_passages, limit=3):
        for raw_line in passage.excerpt.splitlines():
            clean = raw_line.strip()
            norm = _strip_accents(clean)
            if not clean or clean.endswith(":") or len(clean) < 25:
                continue
            if any(marker in norm for marker in _LIFESTYLE_NOISE_MARKERS):
                continue
            bullet = clean if clean.startswith("-") else f"- {clean}"
            key = bullet.lower()
            if key in seen_lines:
                continue
            seen_lines.add(key)
            bullets.append(bullet)
            if passage.source.source_id not in source_ids:
                source_ids.append(passage.source.source_id)
            if len(bullets) >= 4:
                break
        if len(bullets) >= 4:
            break

    if not bullets or not source_ids:
        return None

    candidate = LifestyleInfo(
        status=ExplanationStatus.grounded,
        text="\n".join(bullets),
        source_ids=source_ids,
    )
    check = check_lifestyle_grounding(
        lifestyle_info=candidate,
        lifestyle_passages=lifestyle_passages,
        parameters=parameters,
        min_overlap_ratio=0.18,
    )
    return candidate if check.is_grounded else None


def build_parameter_prompt(
    parameter: ParameterResult,
    passages: list[RetrievedPassage],
) -> str:
    """Construit le prompt utilisateur pour un paramètre et son extrait ciblé."""
    selected = _select_relevant_passages(parameter, passages, limit=2) or passages[:1]
    val_str = (
        f"{parameter.value:g} {parameter.unit or ''}".strip()
        if parameter.value is not None
        else "absente"
    )
    ref_str = _format_reference(parameter)

    if parameter.status == ParameterStatus.within_reference:
        statut_exact = "NORMAL (DANS LA NORME DU LABORATOIRE — ne pas évoquer d'anémie, de carence ou d'anomalie)"
    elif parameter.status == ParameterStatus.below_reference:
        statut_exact = "ANOMALIE : VALEUR BASSE (EN DESSOUS DU MINIMUM)"
    elif parameter.status == ParameterStatus.above_reference:
        statut_exact = "ANOMALIE : VALEUR ÉLEVÉE (AU-DESSUS DU MAXIMUM)"
    else:
        statut_exact = _describe_position(parameter).upper()
    lines = [
        "Paramètre biologique à expliquer :",
        f"- Code : {parameter.code}",
        f"- Nom imprimé : {parameter.name_printed}",
        f"- Valeur extraite : {val_str}",
        f"- Référence du laboratoire : {ref_str}",
        f"- STATUT EXACT : {statut_exact}",
        f"- Position arithmétique : {_describe_position(parameter)}",
    ]
    if parameter.prior is not None:
        lines.append(f"- Comparaison antérieure : {parameter.prior.note}")
    if getattr(parameter, "marked_deviation", False):
        lines.append(
            "- Écart arithmétique marqué : oui (mentionner l'intérêt d'un avis médical rapide, sans diagnostic)"
        )
    lines.extend([
        "",
        "Extrait documentaire autorisé (cite uniquement son source_id) :",
    ])

    for idx, passage in enumerate(selected, start=1):
        lines.append(
            f"[{idx}] source_id={passage.source.source_id} | "
            f"organisme={passage.source.organisme} | titre={passage.source.title}\n"
            f"Extrait : {passage.excerpt}"
        )

    return "\n".join(lines)


def build_lifestyle_prompt(
    parameters: list[ParameterResult],
    lifestyle_passages: list[RetrievedPassage],
) -> str:
    """Construit le prompt utilisateur pour la synthèse documentée d'hygiène de vie."""
    selected_passages = _select_lifestyle_passages(lifestyle_passages, limit=3)
    lines = ["Paramètres hors fourchette ou notables sur ce bilan :"]
    out_of_range = [
        p
        for p in parameters
        if p.status in (ParameterStatus.below_reference, ParameterStatus.above_reference)
    ]
    if out_of_range:
        for param in out_of_range:
            lines.append(
                f"- {param.name_printed} ({param.code}) : {_describe_position(param)}"
            )
    else:
        lines.append("- Bilan biologique général")

    lines.append("")
    lines.append(
        "Extraits officiels d'hygiène de vie autorisés (utilise exclusivement ces faits et source_id) :"
    )
    for idx, passage in enumerate(selected_passages, start=1):
        lines.append(
            f"[{idx}] source_id={passage.source.source_id} | "
            f"organisme={passage.source.organisme} | titre={passage.source.title}\n"
            f"Extrait : {passage.excerpt}"
        )

    return "\n".join(lines)


def build_questions_prompt(
    parameters: list[ParameterResult],
    passages: list[RetrievedPassage],
) -> str:
    """Construit le prompt pour générer des questions cohérentes de consultation médicale."""
    below = [p for p in parameters if p.status == ParameterStatus.below_reference]
    above = [p for p in parameters if p.status == ParameterStatus.above_reference]
    within = [p for p in parameters if p.status == ParameterStatus.within_reference]
    no_ref = [
        p for p in parameters if p.status == ParameterStatus.reference_unavailable
    ]

    lines = ["Résumé exact du bilan biologique :"]
    if below or above:
        lines.append("PARAMÈTRES PRIORITAIRES À QUESTIONNER :")
        for param in below:
            val_str = f"{param.value:g} {param.unit or ''}".strip() if param.value is not None else "absente"
            lines.append(
                f"- VALEUR BASSE (en dessous du minimum) : {param.name_printed} ({param.code}) = {val_str} "
                f"(réf. : {_format_reference(param)})"
            )
        for param in above:
            val_str = f"{param.value:g} {param.unit or ''}".strip() if param.value is not None else "absente"
            lines.append(
                f"- VALEUR ÉLEVÉE (au-dessus du maximum) : {param.name_printed} ({param.code}) = {val_str} "
                f"(réf. : {_format_reference(param)})"
            )

        if within:
            lines.append(
                f"- {len(within)} autre(s) paramètre(s) analysé(s) se situent dans la fourchette de référence (valeurs satisfaisantes)."
            )
    elif within:
        lines.append(
            f"- Les {len(within)} paramètre(s) avec référence se situent tous dans la fourchette du laboratoire."
        )

    if no_ref:
        names = ", ".join(p.name_printed for p in no_ref[:3])
        lines.append(f"- Référence non imprimée sur le document pour : {names}.")

    return "\n".join(lines)


def _filter_contradictory_questions(
    questions: list[str],
    parameters: list[ParameterResult],
) -> list[str]:
    """Écarte les questions qui inversent le sens arithmétique observé."""
    below_terms: list[str] = []
    above_terms: list[str] = []
    within_terms: list[str] = []

    for param in parameters:
        _, terms = _parameter_search_terms(param)
        key_terms = [t for t in terms if len(t) >= 4]
        if param.status == ParameterStatus.below_reference:
            below_terms.extend(key_terms)
        elif param.status == ParameterStatus.above_reference:
            above_terms.extend(key_terms)
        elif param.status == ParameterStatus.within_reference:
            within_terms.extend(key_terms)

    high_re = re.compile(r"\b(?:eleve|elevee|eleves|elevees|hausse|augment\w*|reduire|hyper\w*)\b")
    low_re = re.compile(r"\b(?:bas|basse|baisse|diminu\w*|hypo\w*)\b")

    kept: list[str] = []
    for question in questions:
        norm_q = _strip_accents(question)
        mentions_below = any(t in norm_q for t in below_terms)
        mentions_above = any(t in norm_q for t in above_terms)
        mentions_within = any(t in norm_q for t in within_terms)

        if mentions_below and not mentions_above and high_re.search(norm_q):
            continue
        if mentions_above and not mentions_below and low_re.search(norm_q):
            continue
        if mentions_within and not mentions_below and not mentions_above:
            if high_re.search(norm_q) or low_re.search(norm_q):
                continue

        kept.append(question)

    return kept if kept else questions


def _extract_json_object(raw_text: str) -> dict | None:
    """Extrait un objet JSON même si le modèle ajoute des balises Markdown ou des sauts de ligne."""
    cleaned = raw_text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, flags=re.DOTALL)
    if fenced:
        cleaned = fenced.group(1)
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end > start:
            cleaned = cleaned[start : end + 1]

    try:
        parsed = json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_llm_explanation(
    parameter: ParameterResult,
    raw_response: str,
    allowed_source_ids: set[str],
) -> ParameterExplanation:
    """Valide strictement la réponse du LLM ou bascule vers un repli neutre."""
    payload = _extract_json_object(raw_response)
    if payload is None:
        return build_unavailable_explanation(parameter)

    raw_status = payload.get("status")
    raw_text = payload.get("text")
    raw_source_ids = payload.get("source_ids")

    if raw_status != ExplanationStatus.grounded.value:
        return build_unavailable_explanation(parameter)

    if isinstance(raw_text, list):
        raw_text = " ".join(str(item).strip() for item in raw_text if str(item).strip())

    if not isinstance(raw_text, str) or not raw_text.strip():
        return build_unavailable_explanation(parameter)

    if not isinstance(raw_source_ids, list):
        return build_unavailable_explanation(parameter)

    valid_ids: list[str] = []
    for item in raw_source_ids:
        if isinstance(item, str) and item in allowed_source_ids and item not in valid_ids:
            valid_ids.append(item)

    if not valid_ids:
        return build_unavailable_explanation(parameter)

    return ParameterExplanation(
        code=parameter.code,
        status=ExplanationStatus.grounded,
        text=raw_text.strip(),
        source_ids=valid_ids,
    )


def parse_llm_lifestyle(
    raw_response: str,
    allowed_source_ids: set[str],
) -> LifestyleInfo:
    """Valide strictement la réponse du LLM pour la section d'hygiène de vie."""
    payload = _extract_json_object(raw_response)
    if payload is None:
        return build_unavailable_lifestyle_info()

    raw_status = payload.get("status")
    raw_text = payload.get("text")
    raw_source_ids = payload.get("source_ids")

    if raw_status != ExplanationStatus.grounded.value:
        return build_unavailable_lifestyle_info()

    if isinstance(raw_text, list):
        items = []
        for item in raw_text:
            s = str(item).strip()
            if not s:
                continue
            items.append(s if s.startswith("-") else f"- {s}")
        raw_text = "\n".join(items)

    if not isinstance(raw_text, str) or not raw_text.strip():
        return build_unavailable_lifestyle_info()

    if not isinstance(raw_source_ids, list):
        return build_unavailable_lifestyle_info()

    valid_ids: list[str] = []
    for item in raw_source_ids:
        if isinstance(item, str) and item in allowed_source_ids and item not in valid_ids:
            valid_ids.append(item)

    if not valid_ids:
        return build_unavailable_lifestyle_info()

    return LifestyleInfo(
        status=ExplanationStatus.grounded,
        text=raw_text.strip(),
        source_ids=valid_ids,
    )


def parse_llm_nutrition_plan(
    raw_response: str,
    allowed_source_ids: set[str],
) -> NutritionPlan | None:
    """Valide le plan nutritionnel structuré JSON issu des extraits ANSES/Ameli."""
    payload = _extract_json_object(raw_response)
    if payload is None or payload.get("status") != ExplanationStatus.grounded.value:
        return None
    raw_source_ids = payload.get("source_ids")
    if not isinstance(raw_source_ids, list):
        return None
    valid_ids = [
        item for item in raw_source_ids
        if isinstance(item, str) and item in allowed_source_ids
    ]
    valid_ids = list(dict.fromkeys(valid_ids))
    if not valid_ids:
        return None

    raw_intro = str(payload.get("intro") or "").strip()
    intro = "" if (raw_intro and is_placeholder_text(raw_intro)) else raw_intro
    raw_sec_title = str(payload.get("section_title") or "").strip()
    section_title = "" if (raw_sec_title and is_placeholder_text(raw_sec_title)) else raw_sec_title
    highlights: list[NutritionHighlight] = []
    used_image_keys: set[str] = set()
    for raw_h in (payload.get("highlights") or []):
        if not isinstance(raw_h, dict):
            continue
        title = str(raw_h.get("title") or "").strip()
        subtitle = str(raw_h.get("subtitle") or "").strip()
        raw_img_key = str(raw_h.get("image_key") or "neutral").strip()
        if not title or not subtitle:
            continue
        if is_placeholder_text(title) or is_placeholder_text(subtitle):
            continue
        img_key = _resolve_food_image_key(title, subtitle, raw_img_key, used_image_keys)
        highlights.append(NutritionHighlight(title=title, subtitle=subtitle, image_key=img_key))
        if len(highlights) >= 5:
            break
    meal_rows: list[MealPlanRow] = []
    for raw_m in (payload.get("daily_meal_plan") or []):
        if not isinstance(raw_m, dict):
            continue
        meal = str(raw_m.get("meal") or "").strip()
        example = str(raw_m.get("example") or "").strip()
        if not meal or not example:
            continue
        if is_placeholder_text(meal) or is_placeholder_text(example):
            continue
        meal_rows.append(MealPlanRow(meal=meal, example=example))
        if len(meal_rows) >= 5:
            break
    if not intro and not highlights and not meal_rows:
        return None

    return NutritionPlan(
        status=ExplanationStatus.grounded,
        intro=intro,
        section_title=section_title,
        highlights=highlights,
        daily_meal_plan=meal_rows,
        source_ids=valid_ids,
    )


def parse_llm_questions(
    raw_response: str,
    max_questions: int = 4,
) -> list[str]:
    """Extrait et filtre la liste de questions proposée par le LLM."""
    payload = _extract_json_object(raw_response)
    if payload is None:
        return []

    raw_questions = payload.get("questions")
    if not isinstance(raw_questions, list):
        return []

    return sanitize_consultation_questions(raw_questions, max_questions=max_questions)


class RagExplanationGenerator:
    """Générateur RAG avec vérification d'ancrage et reformulation prudente."""

    def __init__(
        self,
        llm_client: LocalLLMClient,
        system_prompt: str = SYSTEM_PROMPT,
        lifestyle_system_prompt: str = LIFESTYLE_SYSTEM_PROMPT,
        questions_system_prompt: str = QUESTIONS_SYSTEM_PROMPT,
        min_overlap_ratio: float = 0.18,
        max_retries: int = 1,
        include_extended_sections: bool = False,
    ) -> None:
        self.llm_client = llm_client
        self.system_prompt = system_prompt
        self.lifestyle_system_prompt = lifestyle_system_prompt
        self.questions_system_prompt = questions_system_prompt
        self.min_overlap_ratio = min_overlap_ratio
        self.max_retries = max_retries
        self.include_extended_sections = include_extended_sections
        self._fallback = InsufficientSourcesGenerator()
        self._supports_max_tokens = self._check_supports_max_tokens(llm_client)

    @staticmethod
    def _check_supports_max_tokens(llm_client: LocalLLMClient) -> bool:
        try:
            sig = inspect.signature(llm_client.generate)
            return "max_tokens" in sig.parameters
        except (TypeError, ValueError):
            return False

    def _invoke_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
    ) -> str:
        if self._supports_max_tokens and max_tokens is not None:
            return self.llm_client.generate(system_prompt, user_prompt, max_tokens=max_tokens)  # type: ignore[call-arg]
        return self.llm_client.generate(system_prompt, user_prompt)

    def _generate_for_parameter(
        self,
        parameter: ParameterResult,
        passages: list[RetrievedPassage],
        allowed_source_ids: set[str],
    ) -> ParameterExplanation:
        targeted_passages = _select_relevant_passages(parameter, passages, limit=2)
        if not targeted_passages:
            return build_unavailable_explanation(parameter)

        base_prompt = build_parameter_prompt(parameter, targeted_passages)
        prompt = base_prompt

        for attempt in range(self.max_retries + 1):
            try:
                max_tok = 180 if parameter.status == ParameterStatus.within_reference else 240
                raw_response = self._invoke_llm(self.system_prompt, prompt, max_tokens=max_tok)
            except LocalLLMError:
                return build_unavailable_explanation(parameter)

            explanation = parse_llm_explanation(
                parameter, raw_response, allowed_source_ids
            )
            if explanation.status != ExplanationStatus.grounded:
                return explanation

            check = check_explanation_grounding(
                explanation=explanation,
                parameter=parameter,
                passages=passages,
                min_overlap_ratio=self.min_overlap_ratio,
            )
            if check.is_grounded:
                return explanation

            if attempt < self.max_retries:
                reasons_text = " ; ".join(check.reasons)
                prompt = (
                    f"{base_prompt}\n\n"
                    f"CORRECTION OBLIGATOIRE : ta tentative précédente a été rejetée "
                    f"({reasons_text}). Reformule uniquement avec les faits et termes "
                    f"présents dans l'extrait fourni, sans chiffre non sourcé, ou "
                    f'retourne status="insufficient_sources" et source_ids=[].'
                )

        return build_unavailable_explanation(parameter)

    def _generate_lifestyle_info(
        self,
        parameters: list[ParameterResult],
        lifestyle_passages: list[RetrievedPassage],
    ) -> LifestyleInfo:
        selected_passages = _select_lifestyle_passages(lifestyle_passages, limit=3)
        allowed_ids = {passage.source.source_id for passage in selected_passages}
        base_prompt = build_lifestyle_prompt(parameters, selected_passages)
        prompt = base_prompt

        for attempt in range(self.max_retries + 1):
            try:
                raw_response = self._invoke_llm(
                    self.lifestyle_system_prompt,
                    prompt,
                    max_tokens=420,
                )
            except LocalLLMError:
                return build_unavailable_lifestyle_info()

            lifestyle_info = parse_llm_lifestyle(raw_response, allowed_ids)
            if lifestyle_info.status == ExplanationStatus.grounded:
                check = check_lifestyle_grounding(
                    lifestyle_info=lifestyle_info,
                    lifestyle_passages=lifestyle_passages,
                    parameters=parameters,
                    min_overlap_ratio=self.min_overlap_ratio,
                )
                if check.is_grounded:
                    return lifestyle_info

                if attempt < self.max_retries:
                    reasons_text = " ; ".join(check.reasons)
                    prompt = (
                        f"{base_prompt}\n\n"
                        f"CORRECTION OBLIGATOIRE : ta tentative précédente a été rejetée "
                        f"({reasons_text}). Reformule uniquement avec les faits et termes "
                        f"présents dans les extraits fournis, sans chiffre non sourcé."
                    )
                    continue

        extractive = _build_extractive_lifestyle_fallback(lifestyle_passages, parameters)
        return extractive if extractive is not None else build_unavailable_lifestyle_info()

    def _generate_nutrition_plan(
        self,
        parameters: list[ParameterResult],
        lifestyle_passages: list[RetrievedPassage],
    ) -> NutritionPlan | None:
        selected_passages = _select_lifestyle_passages(lifestyle_passages, limit=3)
        if not selected_passages:
            return None
        allowed_ids = {passage.source.source_id for passage in selected_passages}
        prompt = build_lifestyle_prompt(parameters, selected_passages)
        try:
            raw_response = self._invoke_llm(
                NUTRITION_SYSTEM_PROMPT,
                prompt,
                max_tokens=850,
            )
        except LocalLLMError:
            return None
        plan = parse_llm_nutrition_plan(raw_response, allowed_ids)
        if plan is None:
            return None
        check = check_nutrition_grounding(
            nutrition_plan=plan,
            lifestyle_passages=lifestyle_passages,
            parameters=parameters,
            min_overlap_ratio=0.14,
        )
        return plan if check.is_grounded else None

    def _generate_actions_and_questions(
        self,
        parameters: list[ParameterResult],
        passages: list[RetrievedPassage],
    ) -> tuple[GuidanceSections | None, list[str], list[str]]:
        active_parameters = [
            param
            for param in parameters
            if param.status != ParameterStatus.not_analyzed
        ]
        if not active_parameters:
            return None, [], []

        prompt = build_questions_prompt(active_parameters, passages)
        if passages:
            snippets = "\n".join(
                f"- [{p.source.source_id}] {p.excerpt[:300]}"
                for p in passages[:4]
            )
            prompt = f"{prompt}\n\nExtraits officiels de contexte :\n{snippets}"

        try:
            raw_response = self._invoke_llm(
                ACTIONS_SYSTEM_PROMPT,
                prompt,
                max_tokens=780,
            )
        except LocalLLMError:
            return None, [], []

        payload = _extract_json_object(raw_response)
        if payload is None:
            return None, [], []

        raw_cats = payload.get("categories")
        guidance: GuidanceSections | None = None
        if isinstance(raw_cats, dict):
            nutrition = sanitize_action_steps(raw_cats.get("nutrition") or [], max_steps=4) if isinstance(raw_cats.get("nutrition"), list) else []
            physical = sanitize_action_steps(raw_cats.get("physical_activity") or [], max_steps=4) if isinstance(raw_cats.get("physical_activity"), list) else []
            lifestyle_prev = sanitize_action_steps(raw_cats.get("lifestyle_prevention") or [], max_steps=4) if isinstance(raw_cats.get("lifestyle_prevention"), list) else []
            followup = sanitize_action_steps(raw_cats.get("medical_followup") or [], max_steps=4) if isinstance(raw_cats.get("medical_followup"), list) else []
            if nutrition or physical or lifestyle_prev or followup:
                guidance = GuidanceSections(
                    nutrition=nutrition,
                    physical_activity=physical,
                    lifestyle_prevention=lifestyle_prev,
                    medical_followup=followup,
                )

        raw_steps = payload.get("steps")
        steps = sanitize_action_steps(raw_steps) if isinstance(raw_steps, list) else []
        if not steps and guidance is not None:
            steps = sanitize_action_steps(
                [*guidance.medical_followup, *guidance.nutrition, *guidance.physical_activity, *guidance.lifestyle_prevention],
                max_steps=6,
            )

        raw_questions = payload.get("questions")
        questions = (
            sanitize_consultation_questions(raw_questions)
            if isinstance(raw_questions, list)
            else []
        )
        questions = _filter_contradictory_questions(questions, active_parameters)
        return guidance, steps, questions

    def _generate_consultation_questions(
        self,
        parameters: list[ParameterResult],
        passages: list[RetrievedPassage],
    ) -> list[str]:
        active_parameters = [
            param
            for param in parameters
            if param.status != ParameterStatus.not_analyzed
        ]
        if not active_parameters:
            return []

        prompt = build_questions_prompt(active_parameters, passages)
        try:
            raw_response = self._invoke_llm(
                self.questions_system_prompt,
                prompt,
                max_tokens=420,
            )
        except LocalLLMError:
            return []

        sanitized = parse_llm_questions(raw_response)
        return _filter_contradictory_questions(sanitized, active_parameters)

    def _build_general_summary(
        self,
        parameters: list[ParameterResult],
    ) -> str:
        """Construit une synthèse générale courte et neutre du bilan (sans diagnostic)."""
        analyzed = [p for p in parameters if p.status != ParameterStatus.not_analyzed]
        within = [p for p in analyzed if p.status == ParameterStatus.within_reference]
        out = [
            p
            for p in analyzed
            if p.status in (ParameterStatus.below_reference, ParameterStatus.above_reference)
        ]
        marked = [p for p in out if getattr(p, "marked_deviation", False)]
        parts: list[str] = []
        if within and not out:
            parts.append(
                f"Les {len(within)} paramètre(s) analysé(s) avec intervalle de référence se situent dans les normes du laboratoire."
            )
            parts.append(
                "Ce résultat global est rassurant et pourra être partagé lors de votre prochain suivi médical."
            )
        elif out:
            if within:
                parts.append(
                    f"Sur {len(analyzed)} paramètre(s) analysé(s), {len(within)} se situent dans les normes du laboratoire."
                )
            out_labels = ", ".join(
                f"{p.name_printed} ({'en dessous' if p.status == ParameterStatus.below_reference else 'au-dessus'})"
                for p in out[:4]
            )
            if len(out) > 4:
                out_labels += f" et {len(out) - 4} autre(s)"
            parts.append(f"Écart(s) relevé(s) par rapport aux bornes du laboratoire : {out_labels}.")
            if marked:
                parts.append(
                    "Un écart arithmétique marqué est présent : un avis médical rapide est recommandé."
                )
            else:
                parts.append(
                    "Un échange avec votre médecin permettra d'interpréter ces éléments selon votre contexte clinique."
                )
        elif analyzed:
            parts.append(
                f"{len(analyzed)} paramètre(s) ont été extraits, mais certaines bornes de référence ne figurent pas sur le document."
            )
        return " ".join(parts)

    def _build_section_summaries(
        self,
        parameters: list[ParameterResult],
        explanations: list[ParameterExplanation],
    ) -> list[SectionSummaryItem]:
        """Regroupe les explications sourcées de l'hémogramme pour la synthèse rapide."""
        exp_by_code = {e.code: e for e in explanations if e.status == ExplanationStatus.grounded}
        groups = [
            ("Globules rouges et hémoglobine", ("RBC", "HGB", "HCT", "VGM", "TCMH", "CCMH")),
            ("Globules blancs", ("WBC",)),
            ("Plaquettes", ("PLT",)),
        ]
        summaries: list[SectionSummaryItem] = []
        active_codes = {p.code for p in parameters}
        for title, codes in groups:
            if not any(c in active_codes for c in codes):
                continue
            texts: list[str] = []
            sids: list[str] = []
            for code in codes:
                exp = exp_by_code.get(code)
                if exp and exp.text not in texts:
                    texts.append(exp.text)
                    for sid in exp.source_ids:
                        if sid not in sids:
                            sids.append(sid)
                if len(texts) >= 2:
                    break
            if texts and sids:
                summaries.append(
                    SectionSummaryItem(
                        title=title,
                        text=" ".join(texts),
                        source_ids=sids,
                    )
                )
        return summaries

    def generate(self, request: GenerationRequest) -> GenerationResult:
        if not request.parameters and not request.lifestyle_passages:
            return self._fallback.generate(request)

        if not request.passages and not request.lifestyle_passages:
            return self._fallback.generate(request)

        sources_by_id: dict[str, Source] = {
            passage.source.source_id: passage.source
            for passage in (*request.passages, *request.lifestyle_passages)
        }
        allowed_param_ids = {
            passage.source.source_id for passage in request.passages
        }

        explanations: list[ParameterExplanation] = []
        used_sources: dict[str, Source] = {}

        for parameter in request.parameters:
            if parameter.code.startswith("RAW_"):
                continue
            if parameter.status == ParameterStatus.not_analyzed or not request.passages:
                explanations.append(build_unavailable_explanation(parameter))
                continue

            explanation = self._generate_for_parameter(
                parameter, request.passages, allowed_param_ids
            )
            explanations.append(explanation)
            for sid in explanation.source_ids:
                if sid not in used_sources:
                    used_sources[sid] = sources_by_id[sid]

        nutrition_plan: NutritionPlan | None = None
        if request.lifestyle_passages:
            lifestyle_info: LifestyleInfo | None = self._generate_lifestyle_info(
                request.parameters, request.lifestyle_passages
            )
            for sid in lifestyle_info.source_ids:
                if sid not in used_sources:
                    used_sources[sid] = sources_by_id[sid]
            if request.include_consultation_questions and self.include_extended_sections:
                nutrition_plan = self._generate_nutrition_plan(
                    request.parameters, request.lifestyle_passages
                )
                if nutrition_plan is not None:
                    for sid in nutrition_plan.source_ids:
                        if sid not in used_sources:
                            used_sources[sid] = sources_by_id[sid]
        elif request.include_consultation_questions:
            lifestyle_info = build_unavailable_lifestyle_info()
        else:
            lifestyle_info = None

        guidance_sections: GuidanceSections | None = None
        action_steps: list[str] = []
        consultation_questions: list[str] = []
        if request.include_consultation_questions:
            combined_passages = [*request.passages, *request.lifestyle_passages]
            if self.include_extended_sections:
                guidance_sections, action_steps, consultation_questions = self._generate_actions_and_questions(
                    request.parameters, combined_passages
                )
            if not consultation_questions:
                consultation_questions = self._generate_consultation_questions(
                    request.parameters, combined_passages
                )

        section_summaries = (
            self._build_section_summaries(request.parameters, explanations)
            if request.include_consultation_questions
            else []
        )
        general_summary = (
            self._build_general_summary(request.parameters)
            if request.include_consultation_questions
            else None
        )

        has_grounded = any(
            item.status == ExplanationStatus.grounded for item in explanations
        ) or (
            lifestyle_info is not None
            and lifestyle_info.status == ExplanationStatus.grounded
        )
        summary = GROUNDED_SUMMARY if has_grounded else INSUFFICIENT_SOURCES_SUMMARY

        return GenerationResult(
            summary=summary,
            general_summary=general_summary,
            parameter_explanations=explanations,
            section_summaries=section_summaries,
            lifestyle_info=lifestyle_info,
            nutrition_plan=nutrition_plan,
            guidance_sections=guidance_sections,
            action_steps=action_steps,
            consultation_questions=consultation_questions,
            sources=list(used_sources.values()),
            disclaimer=DISCLAIMER,
        )
