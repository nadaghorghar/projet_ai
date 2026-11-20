"""Extraction hybride : pdfplumber (texte natif + tableaux) et Tesseract OCR."""
from __future__ import annotations

import io
import re
from pathlib import Path
from statistics import median

import cv2
import numpy as np
import pdfplumber
import pymupdf
import pytesseract
from PIL import Image, ImageOps

from app.core.config import Settings, get_settings

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tif", ".tiff")
_DOT_LEADER_TOKEN_RE = re.compile(r"^[.\u2026·•_\-]{2,}$")
_PARAM_LINE_HINT_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:g/d?l|mg/l|mg/dl|mmol/l|µmol/l|umol/l|%|fl|pg|/mm|millions)",
    re.I,
)


def _setup_tesseract(settings: Settings) -> None:
    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd


def ocr_lang(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    _setup_tesseract(settings)
    try:
        langs = set(pytesseract.get_languages())
        parts = [part.strip() for part in settings.ocr_language.split("+") if part.strip()]
        if parts and all(part in langs for part in parts):
            return settings.ocr_language
        if "fra" in langs and "eng" in langs:
            return "fra+eng"
        return "fra" if "fra" in langs else "eng"
    except Exception:
        return "eng"


def _estimate_skew_angle(gray_norm: np.ndarray) -> float:
    """Estime l'angle d'inclinaison (en degrés) à partir des lignes de texte horizontales."""
    h, w = gray_norm.shape[:2]
    if h < 100 or w < 100:
        return 0.0
    _, bw = cv2.threshold(gray_norm, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(25, w // 55), 3))
    merged = cv2.dilate(bw, kernel, iterations=1)
    contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    angles: list[float] = []
    min_line_w = max(120, w // 10)
    for cnt in contours:
        _, _, bw_w, bw_h = cv2.boundingRect(cnt)
        if bw_w < min_line_w or bw_w < 3 * max(bw_h, 1):
            continue
        vx, vy, _, _ = cv2.fitLine(cnt, cv2.DIST_L2, 0, 0.01, 0.01)
        vx_f = float(vx[0]) if hasattr(vx, "__len__") else float(vx)
        vy_f = float(vy[0]) if hasattr(vy, "__len__") else float(vy)
        if vx_f < 0:
            vx_f, vy_f = -vx_f, -vy_f
        angle = float(np.degrees(np.arctan2(vy_f, vx_f)))
        if -12.0 <= angle <= 12.0:
            angles.append(angle)
    if len(angles) < 3:
        return 0.0
    median_angle = float(np.median(angles))
    if 0.25 <= abs(median_angle) <= 10.0:
        return median_angle
    return 0.0


def _deskew_gray(gray_norm: np.ndarray) -> np.ndarray:
    angle = _estimate_skew_angle(gray_norm)
    if angle == 0.0:
        return gray_norm
    h, w = gray_norm.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.0)
    return cv2.warpAffine(
        gray_norm,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )


def preprocess(img: Image.Image) -> Image.Image:
    """Correction EXIF, agrandissement, éclairage, redressement et nettoyage sans casser les virgules."""
    img = ImageOps.exif_transpose(img)
    g = np.array(img.convert("L"))
    if g.shape[1] < 2400:
        f = min(2.5, 2400 / max(g.shape[1], 1))
        g = cv2.resize(g, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    sigma = max(25, min(85, int(g.shape[1] * 0.025)))
    bg = cv2.GaussianBlur(g, (0, 0), sigmaX=sigma, sigmaY=sigma)
    bg = np.maximum(bg, 1)
    norm = np.clip((g.astype(np.float32) / bg.astype(np.float32)) * 255.0, 0, 255).astype(
        np.uint8
    )
    norm = _deskew_gray(norm)
    bw = cv2.threshold(norm, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    h_lines = cv2.morphologyEx(
        bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (60, 1))
    )
    v_lines = cv2.morphologyEx(
        bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
    )
    line_mask = cv2.dilate(cv2.add(h_lines, v_lines), np.ones((3, 3), np.uint8))
    cleaned = norm.copy()
    cleaned[line_mask > 0] = 255
    stretched = np.clip((cleaned.astype(np.float32) - 35.0) * (255.0 / 190.0), 0, 255).astype(
        np.uint8
    )
    return Image.fromarray(stretched)


def _preprocess_contrast(img: Image.Image) -> Image.Image:
    """Variante CLAHE pour photos smartphone avec ombres, plis ou contraste faible."""
    img = ImageOps.exif_transpose(img)
    g = np.array(img.convert("L"))
    if g.shape[1] < 2400:
        f = min(2.5, 2400 / max(g.shape[1], 1))
        g = cv2.resize(g, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=2.4, tileGridSize=(8, 8))
    enhanced = clahe.apply(g)
    sigma = max(25, min(85, int(enhanced.shape[1] * 0.025)))
    bg = cv2.GaussianBlur(enhanced, (0, 0), sigmaX=sigma, sigmaY=sigma)
    bg = np.maximum(bg, 1)
    norm = np.clip((enhanced.astype(np.float32) / bg.astype(np.float32)) * 255.0, 0, 255).astype(
        np.uint8
    )
    norm = _deskew_gray(norm)
    stretched = np.clip((norm.astype(np.float32) - 45.0) * (255.0 / 170.0), 0, 255).astype(
        np.uint8
    )
    return Image.fromarray(stretched)


def _reconstruct_rows_from_ocr_data(data: dict) -> list[str]:
    """Regroupe les mots OCR par ordonnée Y pour préserver les lignes à points de suite."""
    tokens: list[tuple[float, float, float, str]] = []
    texts = data.get("text", [])
    lefts = data.get("left", [])
    tops = data.get("top", [])
    heights = data.get("height", [])
    confs = data.get("conf", [])

    word_heights: list[float] = []
    for raw_txt, raw_left, raw_top, raw_h, raw_conf in zip(texts, lefts, tops, heights, confs):
        txt = str(raw_txt).strip()
        if not txt or _DOT_LEADER_TOKEN_RE.match(txt):
            continue
        try:
            conf_val = float(raw_conf)
        except (TypeError, ValueError):
            conf_val = 0.0
        if conf_val < 0:
            continue
        h_val = float(raw_h) if raw_h else 18.0
        if 8.0 <= h_val <= 120.0:
            word_heights.append(h_val)
        cy = float(raw_top) + h_val * 0.5
        tokens.append((cy, float(raw_left), h_val, txt))

    if not tokens:
        return []

    med_h = median(word_heights) if word_heights else 22.0
    row_tol = max(12.0, med_h * 0.65)
    tokens.sort(key=lambda item: (item[0], item[1]))

    rows: list[list[tuple[float, float, float, str]]] = []
    row_centers: list[float] = []
    for tok in tokens:
        cy = tok[0]
        if row_centers and abs(cy - row_centers[-1]) <= row_tol:
            rows[-1].append(tok)
            row_centers[-1] = sum(t[0] for t in rows[-1]) / len(rows[-1])
        else:
            rows.append([tok])
            row_centers.append(cy)

    reconstructed: list[str] = []
    for row in rows:
        row.sort(key=lambda item: item[1])
        line = " ".join(item[3] for item in row).strip()
        if line:
            reconstructed.append(line)
    return reconstructed


def _run_ocr_pass(
    prepared: Image.Image,
    lang: str,
    psm: int,
) -> tuple[str, list[str], float | None]:
    config = f"--oem 3 --psm {psm} -c preserve_interword_spaces=1"
    text = pytesseract.image_to_string(prepared, lang=lang, config=config)
    avg_conf: float | None = None
    rows: list[str] = []
    try:
        data = pytesseract.image_to_data(
            prepared,
            lang=lang,
            config=config,
            output_type=pytesseract.Output.DICT,
        )
        rows = _reconstruct_rows_from_ocr_data(data)
        scores = []
        for raw_conf, raw_word in zip(data.get("conf", []), data.get("text", [])):
            if not str(raw_word).strip():
                continue
            val = float(raw_conf)
            if val >= 0:
                scores.append(val / 100.0)
        if scores:
            avg_conf = round(sum(scores) / len(scores), 4)
    except Exception:
        avg_conf = None
    return text, rows, avg_conf


def _count_param_hints(lines: list[str]) -> int:
    return sum(1 for ln in lines if _PARAM_LINE_HINT_RE.search(ln))


def _merge_lines(*line_groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in line_groups:
        for raw in group:
            cleaned = " ".join(raw.split())
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                merged.append(cleaned)
    return merged


def _ocr_image_bundle(
    img: Image.Image,
    settings: Settings | None = None,
) -> tuple[str, list[str], float | None]:
    """Exécute l'OCR multi-passes avec reconstruction de lignes pour tableaux médicaux."""
    settings = settings or get_settings()
    lang = ocr_lang(settings)

    prep_primary = preprocess(img)
    txt1, rows1, conf1 = _run_ocr_pass(prep_primary, lang, psm=4)
    lines1 = _merge_lines(rows1, txt1.splitlines())
    hints1 = _count_param_hints(lines1)

    best_conf = conf1
    all_rows = list(rows1)
    all_texts = [txt1]

    if hints1 < 3 or len("\n".join(lines1)) < 150:
        prep_contrast = _preprocess_contrast(img)
        txt2, rows2, conf2 = _run_ocr_pass(prep_contrast, lang, psm=6)
        lines2 = _merge_lines(rows2, txt2.splitlines())
        hints2 = _count_param_hints(lines2)
        if hints2 > 0 or len(txt2.strip()) > len(txt1.strip()):
            all_rows = _merge_lines(all_rows, rows2)
            all_texts.append(txt2)
            if conf2 is not None and (best_conf is None or conf2 > best_conf):
                best_conf = conf2

        if max(hints1, hints2) == 0:
            for angle in (90, 270, 180):
                rotated = img.rotate(angle, expand=True)
                prep_rot = _preprocess_contrast(rotated)
                txtr, rowsr, confr = _run_ocr_pass(prep_rot, lang, psm=4)
                linesr = _merge_lines(rowsr, txtr.splitlines())
                if _count_param_hints(linesr) >= 2:
                    all_rows = linesr
                    all_texts = [txtr]
                    best_conf = confr
                    break

    combined_lines = _merge_lines(all_rows, *(t.splitlines() for t in all_texts))
    combined_text = "\n".join(combined_lines) if combined_lines else txt1
    return combined_text, all_rows, best_conf


def ocr_image_with_confidence(
    img: Image.Image,
    settings: Settings | None = None,
) -> tuple[str, float | None]:
    """Retourne (texte_ocr, confiance_moyenne_0_1) sur l'image prétraitée."""
    text, _, avg_conf = _ocr_image_bundle(img, settings)
    return text, avg_conf


def ocr_image(img: Image.Image, settings: Settings | None = None) -> str:
    text, _ = ocr_image_with_confidence(img, settings)
    return text


def _extract_table_rows_from_page(page) -> list[str]:
    rows_out: list[str] = []
    try:
        tables = page.extract_tables() or []
    except Exception:
        return rows_out
    for table in tables:
        for row in table or []:
            cells = [
                " ".join(str(cell).split())
                for cell in (row or [])
                if cell and str(cell).strip()
            ]
            if len(cells) >= 2:
                rows_out.append(" | ".join(cells))
    return rows_out


def extract_pdf_native_pages(path: str | Path) -> list[dict]:
    """Extrait texte natif et tableaux page par page sans basculer vers l'OCR."""
    pages: list[dict] = []
    with pdfplumber.open(path) as pdf:
        for idx, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            table_rows = _extract_table_rows_from_page(page)
            pages.append(
                {
                    "page": idx,
                    "text": text,
                    "table_rows": table_rows,
                    "ocr_confidence": None,
                }
            )
    return pages


def extract_document(path, settings: Settings | None = None) -> dict:
    """Retourne {"text", "method", "pages"} ; method = 'pdf_text' ou 'ocr'."""
    settings = settings or get_settings()
    _setup_tesseract(settings)
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        native_pages = extract_pdf_native_pages(path)
        combined_text = "\n".join(p["text"] for p in native_pages)
        if len(combined_text.strip()) >= settings.min_pdf_text_chars:
            return {
                "text": combined_text,
                "method": "pdf_text",
                "pages": native_pages,
            }
        ocr_pages: list[dict] = []
        with pymupdf.open(path) as doc:
            for idx, page in enumerate(doc, start=1):
                png = page.get_pixmap(dpi=settings.ocr_dpi).tobytes("png")
                txt, rows, conf = _ocr_image_bundle(Image.open(io.BytesIO(png)), settings)
                ocr_pages.append(
                    {
                        "page": idx,
                        "text": txt,
                        "table_rows": rows,
                        "ocr_confidence": conf,
                    }
                )
        return {
            "text": "\n".join(p["text"] for p in ocr_pages),
            "method": "ocr",
            "pages": ocr_pages,
        }
    if suffix in IMAGE_SUFFIXES:
        txt, rows, conf = _ocr_image_bundle(Image.open(path), settings)
        return {
            "text": txt,
            "method": "ocr",
            "pages": [
                {
                    "page": 1,
                    "text": txt,
                    "table_rows": rows,
                    "ocr_confidence": conf,
                }
            ],
        }
    raise ValueError(f"Format non supporté : {suffix}")
