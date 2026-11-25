"""Résolution intelligente des paramètres biologiques inconnus (Section 4).

Procédure en 7 étapes sans invention :
1. Conservation des données extraites (nom imprimé, valeur, unité, référence, ligne OCR).
2. Recherche de correspondances (catalogue, synonymes, abréviations, FR/EN, extensions).
3. Recherche documentaire locale via FAISS (MedlinePlus, Ameli, ANSES, OMS, HAS).
4. Identification et synthèse prudente via Qwen local (Ollama) uniquement sur preuves.
5. Décision selon confiance : 'recognized', 'to_verify', 'unidentified'.
6. Correction manuelle de l'intitulé et ré-évaluation complète.
7. Enrichissement progressif et validé du catalogue local (`catalog_extensions.json`).
"""
from __future__ import annotations

import difflib
import json
import re
import unicodedata
from pathlib import Path

from app.core.config import PROJECT_DIR
from app.generation.llm_client import LocalLLMClient, LocalLLMError
from app.knowledge.retriever import FaissKnowledgeIndex
from app.schemas import Source

from .catalog import ALIASES, CATEGORY_BY_CODE, CLINICAL_TAB_BY_CODE
from .parser import CANONICAL_DISPLAY_NAMES

EXTENSIONS_PATH = PROJECT_DIR / "knowledge_corpus" / "metadata" / "catalog_extensions.json"

UNIDENTIFIED_PARAMETER_MESSAGE = (
    "Ce paramètre a été détecté dans votre bilan, mais son identification n'a pas pu être confirmée. "
    "Les informations extraites ont été conservées. Une vérification de son intitulé est nécessaire avant toute interprétation."
)

# Synonymes médicaux FR/EN complémentaires pour la recherche de correspondance (sans conseil médical)
_MULTILINGUAL_SYNONYMS: dict[str, tuple[str, ...]] = {
    "RBC": ("red blood cells", "erythrocytes", "rbc count"),
    "WBC": ("white blood cells", "leukocytes", "wbc count"),
    "HGB": ("hemoglobin", "haemoglobin"),
    "HCT": ("hematocrit", "haematocrit", "pcv"),
    "VGM": ("mean corpuscular volume", "mcv"),
    "TCMH": ("mean corpuscular hemoglobin", "mch"),
    "CCMH": ("mean corpuscular hemoglobin concentration", "mchc"),
    "PLT": ("platelets", "thrombocytes"),
    "GLY": ("fasting blood glucose", "blood sugar", "fasting glucose"),
    "HBA1C": ("glycated hemoglobin", "a1c", "hemoglobin a1c"),
    "CHOL": ("total cholesterol",),
    "HDL": ("hdl cholesterol",),
    "LDL": ("ldl cholesterol",),
    "TG": ("triglycerides",),
    "ALAT": ("alanine aminotransferase", "alt", "sgpt"),
    "ASAT": ("aspartate aminotransferase", "ast", "sgot"),
    "GGT": ("gamma glutamyl transferase", "gamma-gt"),
    "PAL": ("alkaline phosphatase", "alp"),
    "BILI": ("total bilirubin",),
    "CREAT": ("serum creatinine", "creatinine"),
    "UREE": ("blood urea nitrogen", "bun", "urea"),
    "DFG": ("egfr", "glomerular filtration rate"),
    "URIC": ("uric acid",),
    "FER": ("serum iron", "iron"),
    "FERR": ("ferritin",),
    "TRANSF": ("transferrin",),
    "CA": ("serum calcium", "calcium"),
    "MG": ("serum magnesium", "magnesium"),
}

_UNKNOWN_IDENTIFICATION_PROMPT = (
    "Tu es un assistant technique d'identification de paramètres biologiques pour LabMind.\n"
    "À partir du nom extrait, de l'unité, de la référence imprimée et des extraits officiels FAISS fournis, "
    "réponds UNIQUEMENT en JSON valide avec les clés :\n"
    '{"decision": "recognized"|"to_verify"|"unidentified", "normalized_name": "...", '
    '"synonyms": ["..."], "category": "Biochimie"|"Hémogramme"|"Formule leucocytaire"|"Enzymologie"|"Autres paramètres", '
    '"biological_role": "...", "explanation": "...", "confidence": 0.0, "source_ids": ["..."]}\n'
    "Règles absolues :\n"
    "- N'invente JAMAIS une identité médicale si les extraits ne couvrent pas ce paramètre.\n"
    "- Si plusieurs correspondances ambiguës existent, utilise decision=\"to_verify\".\n"
    "- Si aucune preuve fiable n'existe dans les extraits, utilise decision=\"unidentified\", biological_role=\"\", explanation=\"\", source_ids=[].\n"
    "- Cite uniquement les source_ids exacts présents dans les extraits fournis."
)


def _norm_text(s: str) -> str:
    decomposed = unicodedata.normalize("NFD", s.lower().strip())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def load_catalog_extensions(path: Path = EXTENSIONS_PATH) -> dict[str, dict]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data.get("entries")
        return entries if isinstance(entries, dict) else {}
    except Exception:
        return {}


def save_catalog_extension(entry: dict, path: Path = EXTENSIONS_PATH) -> None:
    """Enrichit progressivement le catalogue uniquement pour les paramètres validés."""
    if entry.get("validation_level") != "validated" or not entry.get("normalized_name"):
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = load_catalog_extensions(path)
        key = _norm_text(entry["normalized_name"])
        existing[key] = {
            "normalized_name": entry["normalized_name"],
            "synonyms": list(dict.fromkeys(entry.get("synonyms") or [])),
            "units": list(dict.fromkeys(entry.get("units") or [])),
            "category": entry.get("category") or "Autres paramètres",
            "description": entry.get("description") or "",
            "sources": entry.get("sources") or [],
            "validation_level": "validated",
        }
        payload = {"version": "1.0", "entries": existing}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _search_catalog_and_synonyms(name_printed: str, extensions: dict[str, dict]) -> tuple[str | None, float, list[str]]:
    """Étape 2 : recherche dans catalogue, synonymes FR/EN, abréviations et extensions validées."""
    norm_query = _norm_text(name_printed)
    if not norm_query:
        return None, 0.0, []

    # 1. Correspondance exacte catalogue ou synonymes FR/EN
    for code, alias_list in ALIASES.items():
        all_names = [*alias_list, *_MULTILINGUAL_SYNONYMS.get(code, ())]
        for candidate in all_names:
            if norm_query == _norm_text(candidate):
                return code, 0.98, list(alias_list)

    # 2. Extensions validées précédemment
    if norm_query in extensions:
        ext = extensions[norm_query]
        return f"EXT_{norm_query.upper()[:20]}", 0.92, list(ext.get("synonyms") or [])

    # 3. Correspondance orthographique prudente (évite confusion sur sigles courts <= 4)
    if len(norm_query) >= 5:
        best_code: str | None = None
        best_ratio = 0.0
        for code, alias_list in ALIASES.items():
            for candidate in [*alias_list, *_MULTILINGUAL_SYNONYMS.get(code, ())]:
                nc = _norm_text(candidate)
                if len(nc) < 5:
                    continue
                ratio = difflib.SequenceMatcher(None, norm_query, nc).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_code = code
        if best_code and best_ratio >= 0.86:
            return best_code, round(best_ratio, 2), list(ALIASES.get(best_code, []))
        if best_code and best_ratio >= 0.72:
            return best_code, round(best_ratio, 2), list(ALIASES.get(best_code, []))

    return None, 0.0, []


def _extract_json_dict(raw: str) -> dict | None:
    cleaned = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, flags=re.DOTALL)
    if fenced:
        cleaned = fenced.group(1)
    else:
        s, e = cleaned.find("{"), cleaned.rfind("}")
        if s != -1 and e > s:
            cleaned = cleaned[s : e + 1]
    try:
        parsed = json.loads(cleaned, strict=False)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def resolve_unknown_parameter(
    param: dict,
    knowledge_index: FaissKnowledgeIndex | None = None,
    llm_client: LocalLLMClient | None = None,
    extensions_path: Path = EXTENSIONS_PATH,
    persist_validated: bool = True,
) -> dict:
    """Exécute les étapes 1 à 5 (et 7 si validé) sur un paramètre générique/inconnu."""
    updated = dict(param)
    name_printed = str(updated.get("name_printed") or "").strip()
    extensions = load_catalog_extensions(extensions_path)

    # Étape 2 : catalogue / synonymes / abréviations / extensions
    matched_code, score, synonyms = _search_catalog_and_synonyms(name_printed, extensions)
    if matched_code and score >= 0.86:
        if matched_code in CATEGORY_BY_CODE:
            updated["code"] = matched_code
            updated["is_generic"] = False
            updated["normalized_name"] = CANONICAL_DISPLAY_NAMES.get(matched_code, name_printed)
            updated["category"] = CLINICAL_TAB_BY_CODE.get(matched_code, "Biochimie")
        else:
            ext = extensions.get(_norm_text(name_printed), {})
            updated["normalized_name"] = ext.get("normalized_name", name_printed)
            updated["category"] = ext.get("category", "Autres paramètres")
            updated["sources"] = ext.get("sources", [])
        updated["identification_status"] = "recognized"
        updated["identification_confidence"] = score
        updated["synonyms"] = synonyms[:6]
        return updated

    if matched_code and 0.72 <= score < 0.86:
        proposed = CANONICAL_DISPLAY_NAMES.get(matched_code, matched_code)
        updated["identification_status"] = "to_verify"
        updated["identification_confidence"] = score
        updated["normalized_name"] = proposed
        updated["synonyms"] = synonyms[:6]
        updated["category"] = "Autres paramètres"
        return updated

    # Étape 3 : recherche documentaire locale FAISS
    passages = []
    if knowledge_index is not None and name_printed:
        query = f"{name_printed} {updated.get('unit') or ''} analyse biologique prise de sang".strip()
        passages = knowledge_index.search(query=query, top_k=4)

    # Vérifier si un passage mentionne directement le terme extrait
    norm_name = _norm_text(name_printed)
    name_tokens = [tok for tok in re.findall(r"[a-z0-9]{2,}", norm_name)]
    relevant_passages = [
        p
        for p in passages
        if norm_name in _norm_text(p.excerpt)
        or (len(name_tokens) == 1 and len(name_tokens[0]) >= 3 and re.search(rf"\b{re.escape(name_tokens[0])}\b", _norm_text(p.excerpt)))
    ]

    # Étape 4 : identification prudente via Qwen local si disponible
    if llm_client is not None and relevant_passages:
        allowed_ids = {p.source.source_id for p in relevant_passages}
        snippets = "\n".join(
            f"[{idx}] source_id={p.source.source_id} | titre={p.source.title}\nExtrait : {p.excerpt}"
            for idx, p in enumerate(relevant_passages[:3], start=1)
        )
        prompt = (
            f"Paramètre extrait :\n"
            f"- Nom imprimé : {name_printed}\n"
            f"- Valeur : {updated.get('value')}\n"
            f"- Unité : {updated.get('unit') or 'absente'}\n"
            f"- Référence imprimée : {updated.get('reference_min')} - {updated.get('reference_max')}\n"
            f"- Ligne OCR : {updated.get('raw_line', '')}\n\n"
            f"Extraits documentaires autorisés :\n{snippets}"
        )
        try:
            raw_reply = llm_client.generate(_UNKNOWN_IDENTIFICATION_PROMPT, prompt)
            payload = _extract_json_dict(raw_reply)
        except LocalLLMError:
            payload = None

        if payload:
            decision = str(payload.get("decision") or "").strip()
            conf = float(payload.get("confidence") or 0.0)
            valid_sids = [
                sid for sid in (payload.get("source_ids") or [])
                if isinstance(sid, str) and sid in allowed_ids
            ]
            cited_sources = [
                p.source.model_dump(mode="json")
                for p in relevant_passages
                if p.source.source_id in valid_sids
            ]
            # Dédupliquer les sources par source_id
            dedup_sources: list[dict] = []
            seen_sids: set[str] = set()
            for src in cited_sources:
                if src["source_id"] not in seen_sids:
                    seen_sids.add(src["source_id"])
                    dedup_sources.append(src)

            if decision == "recognized" and conf >= 0.75 and dedup_sources:
                norm_label = str(payload.get("normalized_name") or name_printed).strip()
                role = str(payload.get("biological_role") or "").strip()
                expl = str(payload.get("explanation") or role).strip()
                syns = [str(s).strip() for s in (payload.get("synonyms") or []) if str(s).strip()]
                updated["identification_status"] = "recognized"
                updated["identification_confidence"] = round(min(1.0, conf), 2)
                updated["normalized_name"] = norm_label
                updated["synonyms"] = syns[:6]
                updated["category"] = "Autres paramètres"
                updated["sources"] = dedup_sources
                updated["resolved_explanation"] = expl
                if persist_validated:
                    save_catalog_extension(
                        {
                            "normalized_name": norm_label,
                            "synonyms": [name_printed, *syns],
                            "units": [updated["unit"]] if updated.get("unit") else [],
                            "category": "Autres paramètres",
                            "description": expl,
                            "sources": dedup_sources,
                            "validation_level": "validated",
                        },
                        path=extensions_path,
                    )
                return updated

            if decision == "to_verify" and conf >= 0.45:
                updated["identification_status"] = "to_verify"
                updated["identification_confidence"] = round(conf, 2)
                updated["normalized_name"] = str(payload.get("normalized_name") or name_printed).strip()
                updated["synonyms"] = [str(s).strip() for s in (payload.get("synonyms") or []) if str(s).strip()][:6]
                updated["sources"] = dedup_sources
                updated["category"] = "Autres paramètres"
                return updated

    # Étape 5 Situation C : paramètre non identifié -> conservation sans invention
    updated["identification_status"] = "unidentified"
    updated["identification_confidence"] = 0.0
    updated["normalized_name"] = None
    updated["category"] = "Autres paramètres"
    updated["sources"] = []
    return updated
