"""Identification des paramètres dans un texte extrait (regex + alias + pages)."""
from __future__ import annotations

import difflib
import re
import unicodedata

from .catalog import ACCEPTED_UNITS, ALIASES, KNOWN_UNITS

SIMPLE_NUM = r"\d+(?:[.,]\d+)?"
NUM = r"(?<!\d)\d{1,3}\s\d{3}(?![.,\d])|\d+(?:[.,]\d+)?"
PAREN_RANGE_RE = re.compile(rf"\(\s*({NUM})\s*[-–—~]\s*({NUM})\s*\)")
RANGE_RE = re.compile(rf"({NUM})(?:\s*[-–—~]\s*|\s+[àa]\s+)({NUM})")
SIMPLE_RANGE_RE = re.compile(rf"({SIMPLE_NUM})(?:\s*[-–—~]\s*|\s+[àa]\s+)({SIMPLE_NUM})")
UPPER_BOUND_RE = re.compile(
    rf"\(?\s*(?:réf\.?\s*:?\s*)?(?:<=?|[il]?nf[ée]rieur[e]?\s+[àa])\s*({NUM})"
    rf"(?:\s*[a-zA-Zµμ/%0-9^.,²³]+)?\s*\)?",
    re.I,
)
LOWER_BOUND_RE = re.compile(
    rf"\(?\s*(?:réf\.?\s*:?\s*)?(?:>=?|sup[ée]rieur[e]?\s+[àa])\s*({NUM})"
    rf"(?:\s*[a-zA-Zµμ/%0-9^.,²³]+)?\s*\)?",
    re.I,
)
NUM_RE = re.compile(NUM)
LEADER_RE = re.compile(r"(?:\.\s*){2,}|[_\u2026]{1,}|-{3,}|(?:\s*[.,·•'‘’\"`~-]\s*){3,}")
PRIOR_DATE_RE = re.compile(
    rf"(?:(?:ant[ée]r(?:iorit[ée])?|pr[ée]c(?:[ée]d(?:ent)?)?)\s*:?\s*)?"
    rf"({NUM})(?:\s*([a-zA-Zµμ/%][a-zA-Zµμ/%0-9^.,²³]*))?\s*"
    rf"\(\s*(\d{{1,2}}/\d{{1,2}}/\d{{2,4}})\s*\)",
    re.I,
)
UNIT_NUMBER_TOKEN_RE = re.compile(
    r"10\s*\^\s*[36]\s*/\s*[µμu]?l|1[.,]73\s*m(?:\s*\^\s*2|²)",
    re.I,
)
VALUE_UNIT_RE = re.compile(
    rf"({NUM})\s*([a-zA-Zµμ/%\[][a-zA-Zµμ/%0-9^.,²³°\*!®'’]*)"
)

CANONICAL_DISPLAY_NAMES: dict[str, str] = {
    "HGB": "Hémoglobine",
    "WBC": "Globules blancs",
    "RBC": "Globules rouges",
    "PLT": "Plaquettes",
    "HCT": "Hématocrite",
    "VGM": "VGM",
    "TCMH": "TCMH",
    "CCMH": "CCMH",
    "NEUT": "Neutrophiles",
    "LYMPH": "Lymphocytes",
    "MONO": "Monocytes",
    "EOS": "Éosinophiles",
    "BASO": "Basophiles",
    "FER": "Fer sérique",
    "FERR": "Ferritine",
    "TRANSF": "Transferrine",
    "GLY": "Glycémie",
    "HBA1C": "HbA1c",
    "CHOL": "Cholestérol total",
    "HDL": "Cholestérol HDL",
    "LDL": "Cholestérol LDL",
    "TG": "Triglycérides",
    "ALAT": "ALAT (TGP)",
    "ASAT": "ASAT (TGO)",
    "GGT": "Gamma-GT",
    "BILI": "Bilirubine totale",
    "CREAT": "Créatinine",
    "UREE": "Urée",
    "DFG": "DFG estimé",
    "URIC": "Acide urique",
    "CA": "Calcium",
    "MG": "Magnésium",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _normalize_ocr_decimals(text: str) -> str:
    """Reconstitue les nombres décimaux scindés par des espaces OCR (ex. '3 , 8' -> '3,8') sans altérer les milliers."""
    return re.sub(r"(\d)\s*([.,])\s*(\d)", r"\1\2\3", text)


def _dedup_faux_bold(line: str) -> str:
    """Corrige les mots doublés lettre à lettre en faux gras PDF (ex. 'GGllyyccéémmiiee àà jjeeûûnn..')."""
    tokens = re.split(r"(\s+)", line)
    has_long_faux_bold = any(
        len(tok) >= 4
        and len(tok) % 2 == 0
        and any(c.isalpha() for c in tok)
        and tok[::2] == tok[1::2]
        for tok in tokens
    )
    if not has_long_faux_bold:
        return line

    out: list[str] = []
    for tok in tokens:
        if (
            len(tok) >= 4
            and len(tok) % 2 == 0
            and any(c.isalpha() for c in tok)
            and tok[::2] == tok[1::2]
        ):
            out.append(tok[::2])
        elif tok == "àà":
            out.append("à")
        else:
            out.append(tok)
    return "".join(out)


_ALIAS_LIST = sorted(
    ((_norm(a), code) for code, al in ALIASES.items() for a in al),
    key=lambda x: -len(x[0]),
)
_SPLIT_ALIAS_PATTERNS = [
    re.escape(a)
    for _, al in ALIASES.items()
    for a in al
    if len(_norm(a)) >= 5
]
_SECONDARY_PARAM_RE = re.compile(
    r"(?<=\s)(?=" + "|".join(sorted(_SPLIT_ALIAS_PATTERNS, key=len, reverse=True)) + r")(?=[\wÀ-ÿ]+(?:\s|:|\.))",
    re.I,
)
_KNOWN_UNITS_SET = set(KNOWN_UNITS)


def to_float(s: str) -> float:
    return float(re.sub(r"\s+", "", s).replace(",", "."))


def normalize_unit(u: str | None) -> str | None:
    """Nettoie l'unité et corrige les variantes typographiques et erreurs OCR."""
    if not u:
        return None
    u = u.strip().strip("()[]:;|_.,")
    u = re.sub(r"\s+", "", u).replace("μ", "µ")
    if not u:
        return None

    low = u.lower().replace("µ", "u").replace(",", ".")
    if low in ("%", "yo", "°/o", "o/o", "°%", "%o", "9/0"):
        return "%"
    if re.match(r"^ml/min/1\.73m(?:\^?2|²)$", low):
        return "mL/min/1.73m²"
    if re.match(r"^millions?/mm[3³°\*\?'’®s]?$", low) or low in (
        "m/mm3", "m/mm³", "millions/mm", "millions", "miiiions/mm3",
    ):
        return "Millions/mm³"
    if (
        re.match(r"^/?mm[3³°\*\?'’®s]?$", low)
        or re.match(r"^[/fiIl\[\(\{]?(?:m{1,2}|[mnr]{2})[3³°\*\?'’®s]?$", low)
        or re.match(r"^(?:el(?:ts|ements)?)/mm[3³]$", low)
        or low in ("fram®", "fram", "/°", "imm3", "lmm3", "/mm")
    ):
        return "/mm³"
    if low in ("pg", "pq", "p9", "p.g"):
        return "pg"
    if low in ("g/d!", "g/d1", "glal", "g/di", "g/dl", "g/cl", "g/ol", "gid", "gldl"):
        return "g/dL"
    if low in ("urmol/l", "umo1/l", "umo1/1", "umol/1", "umol/i", "pmol/l", "ymol/l", "pmol/1"):
        return "µmol/L"
    if low in ("mmov/l", "mmo1/l", "mmol/1", "mm0l/l"):
        return "mmol/L"

    exact = {k.lower().replace("µ", "u"): k for k in KNOWN_UNITS}
    if low in exact:
        return exact[low]

    m = re.match(r"^10\W?([36])/\w*l$", low)
    if m:
        return f"10^{m.group(1)}/µL"

    # Préserve les unités médicales valides non cataloguées (mUI/L, pg/mL, mEq/L, etc.)
    if re.match(r"^[a-zµ]+(?:/[a-z0-9²³µ]+)+$", low):
        return u

    cand = difflib.get_close_matches(low, list(exact), n=1, cutoff=0.78)
    return exact[cand[0]] if cand else u


def _exact_match_alias(text: str) -> tuple[str | None, str | None]:
    stripped = text.lstrip()
    if not stripped:
        return None, None
    norm_chars: list[str] = []
    orig_end_indices: list[int] = []

    for idx, ch in enumerate(stripped):
        decomposed = unicodedata.normalize("NFD", ch.lower())
        for sub in decomposed:
            if unicodedata.category(sub) != "Mn":
                norm_chars.append(sub)
                orig_end_indices.append(idx + 1)

    norm_line = "".join(norm_chars)
    for alias, code in _ALIAS_LIST:
        if re.match(rf"^{re.escape(alias)}(?=[\s:;|(\[.,]|$)", norm_line):
            raw_end = orig_end_indices[len(alias) - 1]
            return code, stripped[:raw_end]
    return None, None


def _match_alias_with_mode(line: str) -> tuple[str | None, str | None, bool]:
    """Retourne (code, texte_brut_correspondant, is_fuzzy)."""
    code, raw = _exact_match_alias(line)
    if code is not None:
        return code, raw, False

    trimmed = line.lstrip(" \t.,:;|'\"`‘’“”-_*•·…")
    if trimmed != line:
        code, raw = _exact_match_alias(trimmed)
        if code is not None:
            return code, raw, False

    m_prefix = re.match(r"^[^\s]{1,2}\s+(.+)$", trimmed)
    if m_prefix:
        sub_line = m_prefix.group(1)
        code, raw = _exact_match_alias(sub_line)
        if code is not None:
            return code, raw, False

    for candidate_source in (trimmed, m_prefix.group(1) if m_prefix else ""):
        if not candidate_source:
            continue
        label_part = re.split(
            r"\s{2,}|(?:\.\s*){2,}|\s+[.,:]|_|\u2026|\d", candidate_source, maxsplit=1
        )[0].strip(" .,:;|")
        norm_label = _norm(label_part)
        if len(norm_label) < 4:
            continue

        best_score = 0.0
        best_code: str | None = None
        for alias, al_code in _ALIAS_LIST:
            if len(alias) < 4:
                continue
            max_len_diff = 4 if len(alias) >= 7 else 3
            if abs(len(norm_label) - len(alias)) > max_len_diff:
                continue
            ratio = difflib.SequenceMatcher(None, norm_label, alias).ratio()
            if ratio > best_score:
                best_score = ratio
                best_code = al_code
        min_ratio = 0.74 if len(norm_label) >= 4 else 0.80
        if best_code is not None and best_score >= min_ratio:
            return best_code, label_part, True

    return None, None, False


def match_alias(line: str) -> tuple[str | None, str | None]:
    """Retourne (code, texte_brut_correspondant) si un alias ouvre la ligne."""
    code, raw, _ = _match_alias_with_mode(line)
    return code, raw


_OCR_MISREAD_ALIASES = {
    "tomb",
    "tomh",
    "tcmn",
    "tcnh",
    "tcmb",
    "tgmh",
    "icmh",
    "comb",
    "comh",
    "ccmn",
    "cchm",
    "ccmb",
    "cgmh",
}


def _clean_display_name(code: str, raw_alias: str, is_fuzzy: bool) -> str:
    """Remplace les intitulés déformés par l'OCR par un nom français lisible."""
    raw_clean = raw_alias.strip()
    has_ocr_casing_glitch = bool(
        re.search(r"[a-zà-ÿ][A-ZÀ-Ý]", raw_clean)
    ) and code not in ("HBA1C",)
    is_ocr_misread_alias = _norm(raw_clean) in _OCR_MISREAD_ALIASES
    if is_fuzzy or has_ocr_casing_glitch or is_ocr_misread_alias:
        return CANONICAL_DISPLAY_NAMES.get(code, raw_clean)
    return raw_clean


def _pick_value_and_unit(
    rest: str,
    ref_min: float | None,
    ref_max: float | None,
    ref_raw: str = "",
    code: str | None = None,
) -> tuple[float, str | None] | None:
    """Sélectionne (valeur, unité) sans confondre points de suite OCR, chiffres d'unités ni %."""
    masked = UNIT_NUMBER_TOKEN_RE.sub(lambda m: " " * len(m.group(0)), rest)

    pairs = list(VALUE_UNIT_RE.finditer(masked))
    if pairs:
        raw_candidates: list[tuple[float, str | None]] = [
            (to_float(m.group(1)), normalize_unit(m.group(2)))
            for m in pairs
        ]
        known_candidates = [c for c in raw_candidates if c[1] in _KNOWN_UNITS_SET]
        candidates = known_candidates or raw_candidates

        if len(candidates) >= 2:
            if (ref_min is not None or ref_max is not None) and "%" not in ref_raw:
                non_pct = [c for c in candidates if c[1] != "%"]
                if non_pct:
                    candidates = non_pct
            if code and code in ACCEPTED_UNITS:
                accepted = [c for c in candidates if c[1] in ACCEPTED_UNITS[code]]
                if accepted:
                    return accepted[0]
            return candidates[0]

        if len(known_candidates) == 1:
            only_val, only_unit = known_candidates[0]
            if (
                only_unit == "%"
                and "%" not in ref_raw
                and (ref_max is not None and ref_max >= 40)
                and code in ("NEUT", "LYMPH", "MONO", "EOS", "BASO")
            ):
                alt_nums = [
                    to_float(m.group(0))
                    for m in NUM_RE.finditer(masked)
                    if abs(to_float(m.group(0)) - only_val) > 1e-6
                ]
                if alt_nums:
                    return alt_nums[0], "/mm³"
            return known_candidates[0]

    mv = NUM_RE.search(masked)
    if not mv:
        return None
    value = to_float(mv.group(0))
    unit_txt = (rest[: mv.start()] + " " + rest[mv.end() :]).strip()
    unit = normalize_unit(unit_txt) if unit_txt else None
    return value, unit


_METADATA_IGNORE_RE = re.compile(
    r"\b(?:compte\s+rendu|patient|dossier|n[ée]\(?e\)?\s+le|pvt\s+du|pr[ée]l[èe]vement|"
    r"demand[ée]\s+par|docteur|laboratoire|biologiste|valeurs?\s+usuelles?|"
    r"r[ée]sultats?\s+d['’]analyses?|page\s*:?\s*\d|t[ée]l\.?|fax|email|"
    r"h[ée]mogramme|formule\s+leucocytaire|analyses?\s+d[e']|sp[ée]cialiste|"
    r"remercions|r[ée]tablissement|adresse|avenue|boulevard|rue|code\s+patient|"
    r"moknine|tunis|bact[ée]riologie|virologie|s[ée]rologie|immunologie|biochimie|"
    r"hormonologie|h[ée]matologie|parasitologie|mycologie|biologie\s+mol[ée]culaire)\b",
    re.I,
)
_RAW_UNIT_HINT_RE = re.compile(
    r"^(?:"
    r"[a-zµμ]{1,8}(?:/[a-z0-9²³µμ.]{1,10})+"
    r"|%|fL|pg|UI|mUI|µUI|kUI|kat|nkat|mm|sec|pH|mOsm|osm"
    r"|/mm³|Millions/mm³|10\^[36]/µL"
    r")$",
    re.I,
)
_TINY_CONNECTOR_WORDS = {"de", "du", "des", "en", "et", "au", "aux", "ou", "a", "à", "la", "le", "ph"}
_OCR_LABEL_GARBAGE_CHAR_RE = re.compile(r"[~!?=$@#\\{}^|\[\]]")


def _is_ocr_leader_gibberish_token(tok: str) -> bool:
    """Détecte les faux mots générés par l'OCR sur les pointillés (ex: 'nsssstidtssiis...', 'essessesses...')."""
    core = tok.strip(".,:;|_-•·…'\"`‘’“”()")
    if len(core) < 4:
        return False
    if re.search(r"([a-zA-Z])\1\1", core):
        return True
    if len(core) >= 12 and core.isalpha() and core.islower():
        unique_ratio = len(set(core)) / len(core)
        dot_letters = sum(core.count(c) for c in "esncitaor") / len(core)
        bigram_repeats = len(re.findall(r"(?:ss|ee|es|se|ns|sn|cc|tt|ii)", core))
        if (len(set(core)) <= 9 and dot_letters >= 0.72) or bigram_repeats >= 3 or (len(core) >= 20 and unique_ratio < 0.42):
            return True
    return False


def _strip_ocr_leader_noise(text: str) -> str:
    """Supprime les séquences parasites issues des pointillés de mise en page."""
    tokens = text.split()
    if len(tokens) < 2:
        return text
    drop_indices: set[int] = set()
    for idx, tok in enumerate(tokens):
        if _is_ocr_leader_gibberish_token(tok):
            drop_indices.add(idx)
            # Retire un court artéfact OCR juste avant les pointillés (ex: 'TOMB ons nsssstid...', 'COMB ss essess...')
            if idx >= 2:
                prev = tokens[idx - 1]
                if (
                    prev.isalpha()
                    and prev.islower()
                    and len(prev) <= 3
                    and _norm(prev) not in _TINY_CONNECTOR_WORDS
                ):
                    drop_indices.add(idx - 1)
    if not drop_indices:
        return text
    kept = [tok for idx, tok in enumerate(tokens) if idx not in drop_indices]
    return " ".join(kept)


def _make_raw_code(label: str) -> str:
    slug = re.sub(r"[^A-Z0-9]+", "_", _norm(label).upper()).strip("_")
    return f"RAW_{(slug or 'PARAM')[:40]}"


def _extract_prior_and_refs(rest: str) -> tuple[str, float | None, str | None, str | None, float | None, float | None, str]:
    prior_value: float | None = None
    prior_unit: str | None = None
    prior_date: str | None = None
    m_prior = PRIOR_DATE_RE.search(rest)
    if m_prior:
        prior_value = to_float(m_prior.group(1))
        raw_prior_unit = m_prior.group(2)
        prior_unit = normalize_unit(raw_prior_unit) if raw_prior_unit else None
        prior_date = m_prior.group(3)
    rest = PRIOR_DATE_RE.sub(" ", rest)

    ref_min = ref_max = None
    ref_raw = ""

    m_paren = PAREN_RANGE_RE.search(rest)
    if m_paren:
        ref_min, ref_max = to_float(m_paren.group(1)), to_float(m_paren.group(2))
        ref_raw = m_paren.group(0)
        rest = rest[: m_paren.start()] + " " + rest[m_paren.end() :]
    else:
        m = RANGE_RE.search(rest)
        if m:
            candidate_rest = rest[: m.start()] + " " + rest[m.end() :]
            if " " in m.group(2) and not NUM_RE.search(UNIT_NUMBER_TOKEN_RE.sub(" ", candidate_rest)):
                m_simple = SIMPLE_RANGE_RE.search(rest)
                if m_simple:
                    m = m_simple
                    candidate_rest = rest[: m.start()] + " " + rest[m.end() :]
            ref_min, ref_max = to_float(m.group(1)), to_float(m.group(2))
            ref_raw = m.group(0)
            rest = candidate_rest
        else:
            m_upper = UPPER_BOUND_RE.search(rest)
            if m_upper:
                ref_max = to_float(m_upper.group(1))
                ref_raw = m_upper.group(0)
                rest = rest[: m_upper.start()] + " " + rest[m_upper.end() :]
            else:
                m_lower = LOWER_BOUND_RE.search(rest)
                if m_lower:
                    ref_min = to_float(m_lower.group(1))
                    ref_raw = m_lower.group(0)
                    rest = rest[: m_lower.start()] + " " + rest[m_lower.end() :]

    if ref_min is not None and ref_max is not None and ref_min > ref_max:
        ref_min = ref_max = None

    rest = re.sub(r"\(\s*réf\.?\s*:?\s*", " ", rest, flags=re.I)
    rest = re.sub(r"[()]", " ", rest)
    return rest, prior_value, prior_unit, prior_date, ref_min, ref_max, ref_raw


def _parse_unrecognized_line(line: str, cleaned: str) -> dict | None:
    """Extrait un paramètre biologique non présent dans le catalogue pour l'afficher dans le tableau."""
    if not cleaned or len(cleaned) > 180:
        return None
    if "@" in cleaned or "http" in cleaned.lower():
        return None
    if re.search(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", cleaned) and not PRIOR_DATE_RE.search(cleaned):
        return None
    if _METADATA_IGNORE_RE.search(_norm(cleaned)):
        return None

    m_split = re.search(r"\s+(?=\d+(?:[.,]\d+)?(?:\s|$))", cleaned)
    if not m_split:
        return None

    raw_label = cleaned[: m_split.start()].strip(" .,:;|_-•·…")
    rest = cleaned[m_split.end() :].strip()
    if len(raw_label) < 2 or len(raw_label) > 65:
        return None
    if _OCR_LABEL_GARBAGE_CHAR_RE.search(raw_label):
        return None
    if raw_label[0] in ("(", "[", "{", "'", '"', "«"):
        return None
    alpha_count = sum(1 for ch in raw_label if ch.isalpha())
    compact_len = len(raw_label.replace(" ", ""))
    if alpha_count < 2 or (compact_len > 0 and alpha_count / compact_len < 0.55):
        return None
    if raw_label[0].isdigit():
        return None
    if any(_is_ocr_leader_gibberish_token(tok) for tok in raw_label.split()):
        return None
    if _METADATA_IGNORE_RE.search(_norm(raw_label)):
        return None
    # Évite les lignes d'adresse ou d'identifiants
    if re.search(r"\b(?:n°|no|code|tel|portable|cabinet)\b", _norm(raw_label)):
        return None

    rest_clean, prior_value, prior_unit, prior_date, ref_min, ref_max, ref_raw = _extract_prior_and_refs(rest)
    picked = _pick_value_and_unit(rest_clean, ref_min, ref_max, ref_raw=ref_raw, code=None)
    if picked is None:
        return None

    value, unit = picked
    has_ref = ref_min is not None or ref_max is not None
    has_valid_unit = bool(unit and (_RAW_UNIT_HINT_RE.match(unit) or unit in _KNOWN_UNITS_SET))
    # Exige au moins une unité biologique plausible ou une fourchette de référence pour éviter les faux positifs
    if not has_ref and not has_valid_unit:
        return None
    # Sans fourchette de référence et sans unité connue, rejette les labels trop courts ou au format incohérent
    if not has_ref and len(raw_label) <= 4 and not raw_label.isupper():
        return None

    out = {
        "code": _make_raw_code(raw_label),
        "name_printed": raw_label,
        "value": value,
        "unit": unit,
        "reference_min": ref_min,
        "reference_max": ref_max,
        "raw_line": line.strip(),
    }
    if prior_value is not None:
        out["prior_value"] = prior_value
        out["prior_unit"] = prior_unit
        out["prior_date"] = prior_date
    return out


def parse_line(line: str) -> dict | None:
    deduped = _dedup_faux_bold(line)
    normalized = _normalize_ocr_decimals(deduped)
    cleaned = LEADER_RE.sub(" ", normalized)
    cleaned = _strip_ocr_leader_noise(cleaned)
    cleaned = re.sub(r"\bMillions\s*/\s*mm[3³°\*\?'’®s]?", "Millions/mm³", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*/\s*mm[3³°\*\?'’®s]?", " /mm³", cleaned, flags=re.I)
    code, raw_alias, is_fuzzy = _match_alias_with_mode(cleaned)
    if code is None or raw_alias is None:
        return _parse_unrecognized_line(line, cleaned)

    idx = cleaned.find(raw_alias)
    rest = cleaned[idx + len(raw_alias) :].lstrip(" .,:;|") if idx >= 0 else cleaned

    while True:
        dup_code, dup_alias = _exact_match_alias(rest)
        if dup_code == code and dup_alias is not None:
            rest = rest.lstrip()[len(dup_alias) :].lstrip(" .,:;|")
        else:
            break

    rest, prior_value, prior_unit, prior_date, ref_min, ref_max, ref_raw = _extract_prior_and_refs(rest)

    picked = _pick_value_and_unit(rest, ref_min, ref_max, ref_raw=ref_raw, code=code)
    if picked is None:
        return None

    value, unit = picked
    if code == "HCT" and unit is None and ("%" in line or "yo" in line.lower() or "°/o" in line.lower()):
        unit = "%"

    out = {
        "code": code,
        "name_printed": _clean_display_name(code, raw_alias, is_fuzzy),
        "value": value,
        "unit": unit,
        "reference_min": ref_min,
        "reference_max": ref_max,
        "raw_line": line.strip(),
    }
    if prior_value is not None:
        out["prior_value"] = prior_value
        out["prior_unit"] = prior_unit
        out["prior_date"] = prior_date
    return out


def _split_glued_parameter_segments(line: str) -> list[str]:
    """Sépare deux paramètres accidentellement fusionnés sur une même ligne par l'OCR."""
    parts = [seg.strip() for seg in _SECONDARY_PARAM_RE.split(line) if seg and seg.strip()]
    return parts if len(parts) > 1 else [line]


def identify_parameters(text: str) -> list[dict]:
    out = []
    for raw_line in text.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        for seg in _split_glued_parameter_segments(raw_line):
            p = parse_line(seg)
            if p:
                out.append(p)
    return out


def _candidate_quality_score(param: dict) -> tuple[int, int, int]:
    """Priorise la cohérence d'échelle (évite 38-55 vs 3,8-5,5), la complétude et les décimales."""
    completeness = 0
    if param.get("value") is not None:
        completeness += 1
    if param.get("unit"):
        completeness += 1
    lo = param.get("reference_min")
    hi = param.get("reference_max")
    val = param.get("value")
    if lo is not None or hi is not None:
        completeness += 1

    scale_ok = 1
    if val is not None:
        if lo is not None and lo > 0 and val < lo * 0.2:
            scale_ok = 0
        if hi is not None and hi > 0 and val > hi * 5.0:
            scale_ok = 0

    decimal_pts = 0
    for num in (val, lo, hi):
        if isinstance(num, float) and not num.is_integer():
            decimal_pts += 1

    return (scale_ok, completeness, decimal_pts)


def _completeness_score(param: dict) -> int:
    score = 0
    if param.get("value") is not None:
        score += 1
    if param.get("unit"):
        score += 1
    if param.get("reference_min") is not None or param.get("reference_max") is not None:
        score += 1
    return score


def _find_duplicate_raw_key(page_candidates: dict[str, dict], parsed: dict) -> str:
    """Évite les doublons RAW_* entre passes OCR quand la valeur, l'unité et le préfixe coïncident."""
    code = parsed["code"]
    if code in page_candidates or not code.startswith("RAW_"):
        return code
    p_name = _norm(parsed.get("name_printed") or "")
    p_val = parsed.get("value")
    p_unit = parsed.get("unit")
    for existing_code, existing in page_candidates.items():
        if not existing_code.startswith("RAW_"):
            continue
        if existing.get("value") == p_val and existing.get("unit") == p_unit:
            e_name = _norm(existing.get("name_printed") or "")
            if (
                difflib.SequenceMatcher(None, p_name, e_name).ratio() >= 0.72
                or (p_name.split()[:1] and p_name.split()[:1] == e_name.split()[:1])
            ):
                return existing_code
    return code


def identify_parameters_from_pages(pages: list[dict]) -> list[dict]:
    """Identifie les paramètres page par page (tableaux + texte) avec sélection du meilleur candidat."""
    results: list[dict] = []

    for page_info in pages:
        page_num = page_info.get("page")
        ocr_conf = page_info.get("ocr_confidence")
        page_candidates: dict[str, dict] = {}

        raw_lines: list[str] = []
        raw_lines.extend((page_info.get("text") or "").splitlines())
        raw_lines.extend(page_info.get("table_rows") or [])

        candidate_lines: list[str] = []
        for rl in raw_lines:
            rl = rl.strip()
            if not rl:
                continue
            candidate_lines.extend(_split_glued_parameter_segments(rl))

        n_lines = len(candidate_lines)
        for idx_line, raw_line in enumerate(candidate_lines):
            line = raw_line.strip()
            if not line:
                continue
            parsed = parse_line(line)
            if not parsed and idx_line + 1 < n_lines:
                alias_code, _ = match_alias(_strip_ocr_leader_noise(LEADER_RE.sub(" ", _dedup_faux_bold(line))))
                next_line = candidate_lines[idx_line + 1].strip()
                if alias_code is not None and next_line:
                    next_alias, _ = match_alias(_strip_ocr_leader_noise(LEADER_RE.sub(" ", _dedup_faux_bold(next_line))))
                    if next_alias is None:
                        parsed = parse_line(f"{line} {next_line}")
            if not parsed:
                continue

            parsed["page"] = page_num
            if ocr_conf is not None:
                parsed["source_ocr_confidence"] = ocr_conf

            target_key = _find_duplicate_raw_key(page_candidates, parsed)
            existing = page_candidates.get(target_key)
            if existing is None or _candidate_quality_score(parsed) > _candidate_quality_score(existing):
                page_candidates[target_key] = parsed

        results.extend(page_candidates.values())

    return results
