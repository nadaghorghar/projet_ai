"""Générateur de rapport PDF pédagogique LabMind (ReportLab, UTF-8 / accents FR, 6 sections)."""

from __future__ import annotations

import io
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.config import PROJECT_DIR
from app.generation.grounding import is_placeholder_text
from app.schemas import ParameterResult, ParameterStatus, Source, Task

_PRIMARY_PURPLE = "#5126B5"
_SECONDARY_PURPLE = "#6D45C5"
_LAVENDER_BG = "#F0EBFF"
_LIGHT_BG = "#F7F4FF"
_BORDER_LAVENDER = "#DDD3FA"
_TEXT_DARK = "#1A152E"
_TEXT_MUTED = "#524B6E"

_FOOD_ASSETS_DIR = PROJECT_DIR / "frontend" / "public" / "assets" / "foods"
_PDF_FOOD_STEMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("meat_poultry", ("viand", "abat", "boudin", "=foie", "boeuf", "volaille", "poulet", "dinde", "fer heminique")),
    ("fish", ("poisson", "saumon", "sardine", "maquereau", "hareng", "truite", "thon")),
    ("lentils_chickpeas", ("lentill", "pois chiche", "petits pois", "=pois", "haricot sec", "legumineus", "feve")),
    ("walnuts", ("cerneau", "noix de grenoble", "=noix")),
    ("almonds_walnuts", ("amand", "noisett", "oleagineu", "pistach")),
    ("pumpkin_seeds", ("courge", "graine", "sesame", "tournesol", "=lin")),
    ("spinach", ("epinard", "bette", "feuille verte", "feuilles vertes", "legumes verts", "cresson", "roquette")),
    ("fruits", ("fruit", "orange", "agrume", "pomme", "kiwi", "baie", "fraise", "banane", "citron")),
    ("whole_grains", ("cereal", "complet", "avoine", "quinoa", "=riz", "=pain", "seigle", "=ble")),
    ("vegetables", ("legume", "brocoli", "carotte", "poivron", "courgette", "tomate")),
    ("dairy_yogurt", ("produit laitier", "laitier", "yaourt", "fromage", "kefir", "=lait")),
    ("eggs_protein", ("oeuf", "proteine")),
    ("avocado_olive_oil", ("avocat", "colza", "=olive")),
    ("dark_chocolate", ("chocolat", "cacao")),
    ("hydration_water", ("=eau", "hydrat", "infusion", "tisane")),
)

_UNICODE_FONT_CANDIDATES: tuple[tuple[str, str, str, str], ...] = (
    (
        "LabMindSans",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "LabMindSans-Bold",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
    (
        "LabMindSans",
        r"C:\Windows\Fonts\arial.ttf",
        "LabMindSans-Bold",
        r"C:\Windows\Fonts\arialbd.ttf",
    ),
    (
        "LabMindSans",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "LabMindSans-Bold",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ),
)


def _strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower().replace("'", " ").replace("’", " ")


def _find_pdf_stem_pos(haystack: str, raw_stem: str) -> int:
    exact = raw_stem.startswith("=")
    stem = raw_stem[1:] if exact else raw_stem
    pattern = rf"\b{re.escape(stem)}\b" if exact else rf"\b{re.escape(stem)}\w*"
    m = re.search(pattern, haystack)
    return m.start() if m else -1


def _resolve_pdf_food_image(title: str, subtitle: str, raw_key: str, used: set[str]) -> Path | None:
    if not _FOOD_ASSETS_DIR.is_dir():
        return None
    norm_title = _strip_accents(title)
    norm_sub = _strip_accents(subtitle)
    for text in (norm_title, norm_sub):
        if not text:
            continue
        ranked: list[tuple[int, str]] = []
        for key, stems in _PDF_FOOD_STEMS:
            if key in used:
                continue
            for stem in stems:
                pos = _find_pdf_stem_pos(text, stem)
                if pos != -1:
                    ranked.append((pos, key))
        if ranked:
            ranked.sort(key=lambda item: item[0])
            chosen = ranked[0][1]
            candidate = _FOOD_ASSETS_DIR / f"{chosen}.jpg"
            if candidate.is_file():
                used.add(chosen)
                return candidate

    cleaned_key = re.sub(r"[^a-z0-9_]", "", (raw_key or "").strip().lower())
    if cleaned_key and cleaned_key != "neutral" and cleaned_key not in used:
        candidate = _FOOD_ASSETS_DIR / f"{cleaned_key}.jpg"
        if candidate.is_file():
            used.add(cleaned_key)
            return candidate
    return None


def _register_fonts() -> tuple[str, str]:
    """Enregistre une police Unicode supportant les accents français si disponible."""
    registered = set(pdfmetrics.getRegisteredFontNames())
    if "LabMindSans" in registered and "LabMindSans-Bold" in registered:
        return "LabMindSans", "LabMindSans-Bold"

    for reg_name, reg_path, bold_name, bold_path in _UNICODE_FONT_CANDIDATES:
        if Path(reg_path).is_file() and Path(bold_path).is_file():
            try:
                pdfmetrics.registerFont(TTFont(reg_name, reg_path))
                pdfmetrics.registerFont(TTFont(bold_name, bold_path))
                return reg_name, bold_name
            except Exception:
                continue

    return "Helvetica", "Helvetica-Bold"


def _status_label(status: ParameterStatus) -> str:
    if status == ParameterStatus.below_reference:
        return "En dessous de la norme"
    if status == ParameterStatus.within_reference:
        return "Dans la norme"
    if status == ParameterStatus.above_reference:
        return "Au-dessus de la norme"
    if status == ParameterStatus.reference_unavailable:
        return "Référence absente"
    if status == ParameterStatus.value_unavailable:
        return "Valeur absente"
    return "Non analysé"


def _format_value(param: ParameterResult) -> str:
    if param.value is None:
        return "Non disponible"
    unit = f" {param.unit}" if param.unit else ""
    return f"{param.value:g}{unit}"


def _format_reference(param: ParameterResult) -> str:
    lo = param.reference.min
    hi = param.reference.max
    if lo is not None and hi is not None:
        return f"{lo:g} - {hi:g}"
    if lo is not None:
        return f"> {lo:g}"
    if hi is not None:
        return f"< {hi:g}"
    return "Non fournie"


def _format_param_label(name_printed: str, code: str) -> str:
    clean_name = (name_printed or code or "").strip()
    if not code or code.startswith("RAW_"):
        return f"<b>{escape(clean_name)}</b>"
    return f"<b>{escape(clean_name)}</b> ({escape(code)})"


def _has_general_lifestyle_sources(sources: list[Source]) -> bool:
    keywords = ("alimentation", "nutrition", "hygiene", "hygiène", "vie", "anses", "mangerbouger", "oms", "who", "has")
    for src in sources:
        haystack = f"{src.source_id} {src.title} {src.organisme}".lower()
        if any(kw in haystack for kw in keywords):
            return True
    return False


def _fallback_general_summary(task: Task) -> str:
    analyzed = [p for p in task.parameters if p.status != ParameterStatus.not_analyzed]
    within = [p for p in analyzed if p.status == ParameterStatus.within_reference]
    out = [
        p
        for p in analyzed
        if p.status in (ParameterStatus.below_reference, ParameterStatus.above_reference)
    ]
    if not analyzed:
        return "Aucun paramètre analysable n'a été retenu sur ce document."
    if within and not out:
        return (
            f"Les {len(within)} paramètre(s) analysé(s) se situent dans les intervalles de référence du laboratoire. "
            "Ce bilan d'ensemble peut être présenté à votre médecin lors d'une visite de routine."
        )
    if out:
        names = ", ".join(p.name_printed for p in out[:4])
        prefix = f"Sur {len(analyzed)} paramètre(s) analysé(s), {len(within)} sont conformes aux bornes. " if within else ""
        return (
            f"{prefix}Point(s) à discuter avec votre médecin : {names}."
        )
    return f"{len(analyzed)} paramètre(s) extrait(s) sur ce document."


def build_labmind_report_pdf(task: Task) -> bytes:
    """Construit le rapport PDF pédagogique LabMind en 6 sections organisées."""
    regular_font, bold_font = _register_fonts()
    base_styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "LabMindTitle",
        parent=base_styles["Title"],
        fontName=bold_font,
        fontSize=16.5,
        leading=20,
        textColor=colors.HexColor(_PRIMARY_PURPLE),
        spaceAfter=4,
    )
    heading_style = ParagraphStyle(
        "LabMindHeading",
        parent=base_styles["Heading2"],
        fontName=bold_font,
        fontSize=11.5,
        leading=15,
        textColor=colors.HexColor(_PRIMARY_PURPLE),
        spaceBefore=12,
        spaceAfter=6,
    )
    subhead_style = ParagraphStyle(
        "LabMindSubhead",
        parent=base_styles["Normal"],
        fontName=bold_font,
        fontSize=9.8,
        leading=13,
        textColor=colors.HexColor(_SECONDARY_PURPLE),
        spaceBefore=6,
        spaceAfter=3,
    )
    body_style = ParagraphStyle(
        "LabMindBody",
        parent=base_styles["Normal"],
        fontName=regular_font,
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor(_TEXT_DARK),
    )
    small_style = ParagraphStyle(
        "LabMindSmall",
        parent=body_style,
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor(_TEXT_DARK),
    )
    muted_small_style = ParagraphStyle(
        "LabMindMutedSmall",
        parent=small_style,
        textColor=colors.HexColor(_TEXT_MUTED),
    )
    cell_header_style = ParagraphStyle(
        "LabMindCellHeader",
        parent=small_style,
        fontName=bold_font,
        textColor=colors.white,
    )
    kpi_num_style = ParagraphStyle(
        "LabMindKpiNum",
        parent=body_style,
        fontName=bold_font,
        fontSize=14,
        leading=17,
        alignment=1,
        textColor=colors.HexColor(_PRIMARY_PURPLE),
    )
    kpi_label_style = ParagraphStyle(
        "LabMindKpiLabel",
        parent=small_style,
        fontSize=8.2,
        leading=11,
        alignment=1,
        textColor=colors.HexColor(_TEXT_MUTED),
    )
    disclaimer_style = ParagraphStyle(
        "LabMindDisclaimer",
        parent=body_style,
        fontName=bold_font,
        fontSize=9.0,
        leading=12.5,
        textColor=colors.HexColor("#78350F"),
        backColor=colors.HexColor("#FFFBEB"),
        borderColor=colors.HexColor("#FCD34D"),
        borderWidth=0.8,
        borderPadding=8,
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title="LabMind - Compte rendu pédagogique",
    )

    elements: list = []
    explanations = task.explanations or {}

    # En-tête violet / lavande
    doc_name = task.document.filename if task.document else "Document"
    categories_text = ", ".join(task.detected_categories) if task.detected_categories else "Bilan biologique"
    generated_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    header_table = Table(
        [
            [
                Paragraph("LabMind — Synthèse pédagogique de votre bilan biologique", title_style),
            ],
            [
                Paragraph(
                    f"<b>Document :</b> {escape(doc_name)} &nbsp;|&nbsp; "
                    f"<b>Catégories :</b> {escape(categories_text)} &nbsp;|&nbsp; "
                    f"<b>Édité le :</b> {escape(generated_at)}",
                    muted_small_style,
                )
            ],
        ],
        colWidths=[180 * mm],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(_LAVENDER_BG)),
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor(_BORDER_LAVENDER)),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (0, 0), 9),
                ("BOTTOMPADDING", (0, 0), (0, 0), 2),
                ("TOPPADDING", (0, 1), (0, 1), 2),
                ("BOTTOMPADDING", (0, 1), (0, 1), 9),
            ]
        )
    )
    elements.append(header_table)
    elements.append(Spacer(1, 6))

    # 1. Résumé général du bilan
    section_idx = 1
    elements.append(Paragraph(f"{section_idx}. Résumé général du bilan", heading_style))

    total_params = len(task.parameters)
    normal_count = sum(1 for p in task.parameters if p.status == ParameterStatus.within_reference)
    attention_count = sum(
        1
        for p in task.parameters
        if p.status in (ParameterStatus.below_reference, ParameterStatus.above_reference)
    )
    kpi_table = Table(
        [
            [
                Paragraph(f"{total_params}", kpi_num_style),
                Paragraph(f"<font color='#047857'>{normal_count}</font>", kpi_num_style),
                Paragraph(
                    f"<font color='{'#B91C1C' if attention_count else _TEXT_MUTED}'>{attention_count}</font>",
                    kpi_num_style,
                ),
            ],
            [
                Paragraph("Paramètres extraits", kpi_label_style),
                Paragraph("Dans la norme", kpi_label_style),
                Paragraph("À surveiller", kpi_label_style),
            ],
        ],
        colWidths=[60 * mm, 60 * mm, 60 * mm],
    )
    kpi_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor(_LIGHT_BG)),
                ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#ECFDF5")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#FEF2F2" if attention_count else _LIGHT_BG)),
                ("BOX", (0, 0), (0, -1), 0.5, colors.HexColor(_BORDER_LAVENDER)),
                ("BOX", (1, 0), (1, -1), 0.5, colors.HexColor("#A7F3D0")),
                ("BOX", (2, 0), (2, -1), 0.5, colors.HexColor("#FECACA" if attention_count else _BORDER_LAVENDER)),
                ("TOPPADDING", (0, 0), (-1, 0), 7),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
                ("TOPPADDING", (0, 1), (-1, 1), 1),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    elements.append(kpi_table)
    elements.append(Spacer(1, 6))

    general_summary = str(explanations.get("general_summary") or "").strip() or _fallback_general_summary(task)
    elements.append(Paragraph(escape(general_summary), body_style))
    section_idx += 1

    # 2. Tableau des résultats avec leur statut
    elements.append(Paragraph(f"{section_idx}. Tableau des résultats avec leur statut", heading_style))
    if task.parameters:
        table_rows = [
            [
                Paragraph("Paramètre", cell_header_style),
                Paragraph("Résultat", cell_header_style),
                Paragraph("Normes du laboratoire", cell_header_style),
                Paragraph("Statut", cell_header_style),
            ]
        ]
        anomaly_row_indices: list[int] = []
        for idx_row, param in enumerate(task.parameters, start=1):
            name_cell = _format_param_label(param.name_printed, param.code)
            if getattr(param, "prior", None) is not None and param.prior and param.prior.note:
                name_cell += f"<br/><font color='{_SECONDARY_PURPLE}'><i>{escape(param.prior.note)}</i></font>"

            status_text = _status_label(param.status)
            if param.reason and param.status in (
                ParameterStatus.not_analyzed,
                ParameterStatus.reference_unavailable,
                ParameterStatus.value_unavailable,
            ):
                status_text += f" ({param.reason})"
            if getattr(param, "marked_deviation", False):
                status_text += " [Écart marqué]"

            is_anomaly = param.status in (ParameterStatus.below_reference, ParameterStatus.above_reference)
            if is_anomaly:
                anomaly_row_indices.append(idx_row)
                status_html = f"<font color='#B91C1C'><b>{escape(status_text)}</b></font>"
            elif param.status == ParameterStatus.within_reference:
                status_html = f"<font color='#047857'><b>{escape(status_text)}</b></font>"
            else:
                status_html = f"<font color='{_TEXT_MUTED}'>{escape(status_text)}</font>"

            table_rows.append(
                [
                    Paragraph(name_cell, small_style),
                    Paragraph(f"<b>{escape(_format_value(param))}</b>", small_style),
                    Paragraph(escape(_format_reference(param)), muted_small_style),
                    Paragraph(status_html, small_style),
                ]
            )

        table = Table(
            table_rows,
            colWidths=[62 * mm, 32 * mm, 40 * mm, 46 * mm],
            repeatRows=1,
        )
        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_PRIMARY_PURPLE)),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(_BORDER_LAVENDER)),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(_LIGHT_BG)]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]
        for row_i in anomaly_row_indices:
            style_cmds.append(("BACKGROUND", (0, row_i), (-1, row_i), colors.HexColor("#FEF2F2")))
        table.setStyle(TableStyle(style_cmds))
        elements.append(table)
    else:
        elements.append(Paragraph("Aucun paramètre biologique n'a pu être extrait.", body_style))
    section_idx += 1

    # 3. Explication concise des anomalies
    elements.append(Paragraph(f"{section_idx}. Explication concise des anomalies", heading_style))
    param_explanations = (
        explanations.get("parameter_explanations")
        or explanations.get("parameters")
        or []
    )
    status_by_code = {p.code: p.status for p in task.parameters}
    name_by_code = {p.code: p.name_printed for p in task.parameters}
    ordered_explanations = sorted(
        [
            item
            for item in param_explanations
            if item.get("status") != "not_analyzed"
            and not str(item.get("code") or "").startswith("RAW_")
            and str(item.get("text") or "").strip()
            and not is_placeholder_text(str(item.get("text") or ""))
        ],
        key=lambda item: (
            0
            if status_by_code.get(str(item.get("code", "")))
            in (ParameterStatus.below_reference, ParameterStatus.above_reference)
            else 1
        ),
    )
    if ordered_explanations:
        for item in ordered_explanations:
            code = str(item.get("code", ""))
            label = name_by_code.get(code) or code
            exp_text = str(item.get("text", "")).strip()
            elements.append(
                Paragraph(
                    f"<b>{escape(label)} ({escape(code)}) :</b> {escape(exp_text)}",
                    body_style,
                )
            )
            elements.append(Spacer(1, 3))
    else:
        summary_text = str(explanations.get("summary") or "").strip()
        elements.append(
            Paragraph(
                escape(summary_text)
                if summary_text
                else "Aucune explication pédagogique disponible : aucune source documentaire suffisante n'a été fournie.",
                body_style,
            )
        )
    section_idx += 1

    # 4. Conseils alimentaires personnalisés
    nutrition_plan = explanations.get("nutrition_plan")
    guidance_sections = explanations.get("guidance_sections") or {}
    nutrition_bullets = [
        str(x).strip()
        for x in (guidance_sections.get("nutrition") or [])
        if str(x).strip() and not is_placeholder_text(str(x))
    ]
    has_nutrition = (
        (isinstance(nutrition_plan, dict) and nutrition_plan.get("status") == "grounded")
        or bool(nutrition_bullets)
    )
    if has_nutrition:
        elements.append(Paragraph(f"{section_idx}. Conseils alimentaires personnalisés", heading_style))
        if isinstance(nutrition_plan, dict) and nutrition_plan.get("status") == "grounded":
            intro_txt = str(nutrition_plan.get("intro") or "").strip()
            if intro_txt and not is_placeholder_text(intro_txt):
                elements.append(Paragraph(escape(intro_txt), body_style))
                elements.append(Spacer(1, 5))

            used_pdf_images: set[str] = set()
            card_cells: list = []
            for hl in nutrition_plan.get("highlights") or []:
                t = str(hl.get("title", "")).strip()
                s = str(hl.get("subtitle", "")).strip()
                if not t or not s or is_placeholder_text(t) or is_placeholder_text(s):
                    continue
                img_path = _resolve_pdf_food_image(
                    t,
                    s,
                    str(hl.get("image_key") or ""),
                    used_pdf_images,
                )
                if img_path is not None:
                    try:
                        thumb = RLImage(str(img_path), width=22 * mm, height=16.5 * mm)
                        card_inner = Table(
                            [
                                [
                                    thumb,
                                    Paragraph(
                                        f"<b>{escape(t)}</b><br/><font color='{_TEXT_MUTED}'>{escape(s)}</font>",
                                        small_style,
                                    ),
                                ]
                            ],
                            colWidths=[24 * mm, 63 * mm],
                        )
                        card_inner.setStyle(
                            TableStyle(
                                [
                                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                                ]
                            )
                        )
                        card_cells.append(card_inner)
                    except Exception:
                        card_cells.append(Paragraph(f"• <b>{escape(t)}</b> : {escape(s)}", body_style))
                else:
                    card_cells.append(Paragraph(f"• <b>{escape(t)}</b> : {escape(s)}", body_style))

            if card_cells:
                grid_rows = []
                for idx_c in range(0, len(card_cells), 2):
                    left_c = card_cells[idx_c]
                    right_c = card_cells[idx_c + 1] if idx_c + 1 < len(card_cells) else Spacer(1, 1)
                    grid_rows.append([left_c, right_c])
                food_grid = Table(grid_rows, colWidths=[89 * mm, 89 * mm])
                food_grid.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(_LIGHT_BG)),
                            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(_BORDER_LAVENDER)),
                            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor(_BORDER_LAVENDER)),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 4),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ]
                    )
                )
                elements.append(food_grid)
                elements.append(Spacer(1, 5))

            meal_rows = [
                row
                for row in (nutrition_plan.get("daily_meal_plan") or [])
                if str(row.get("meal", "")).strip()
                and str(row.get("example", "")).strip()
                and not is_placeholder_text(str(row.get("example", "")))
            ]
            if meal_rows:
                elements.append(Spacer(1, 4))
                m_table_data = [[Paragraph("Repas", cell_header_style), Paragraph("Exemple", cell_header_style)]]
                for row in meal_rows:
                    m_table_data.append([
                        Paragraph(f"<b>{escape(str(row.get('meal', '')))}</b>", small_style),
                        Paragraph(escape(str(row.get("example", ""))), small_style),
                    ])
                m_table = Table(m_table_data, colWidths=[40 * mm, 140 * mm], repeatRows=1)
                m_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_PRIMARY_PURPLE)),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(_BORDER_LAVENDER)),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(_LIGHT_BG)]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]))
                elements.append(m_table)
                elements.append(Spacer(1, 4))
        for item in nutrition_bullets:
            elements.append(Paragraph(f"• {escape(item)}", body_style))
        section_idx += 1

    # 5. Activité physique et habitudes de vie pertinentes
    lifestyle_info = explanations.get("lifestyle_info")
    ls_raw_text = str(lifestyle_info.get("text") or "").strip() if isinstance(lifestyle_info, dict) else ""
    has_grounded_lifestyle = (
        isinstance(lifestyle_info, dict)
        and lifestyle_info.get("status") == "grounded"
        and bool(ls_raw_text)
        and not is_placeholder_text(ls_raw_text)
    )
    has_legacy_lifestyle_sources = bool(task.sources and _has_general_lifestyle_sources(task.sources))
    activity_bullets = [
        str(x).strip()
        for x in (guidance_sections.get("physical_activity") or [])
        if str(x).strip() and not is_placeholder_text(str(x))
    ]
    prevention_bullets = [
        str(x).strip()
        for x in (guidance_sections.get("lifestyle_prevention") or [])
        if str(x).strip() and not is_placeholder_text(str(x))
    ]
    if activity_bullets or prevention_bullets or has_grounded_lifestyle or has_legacy_lifestyle_sources:
        elements.append(
            Paragraph(
                f"{section_idx}. Activité physique et habitudes de vie pertinentes",
                heading_style,
            )
        )
        if activity_bullets:
            elements.append(Paragraph("Activité physique", subhead_style))
            for item in activity_bullets:
                elements.append(Paragraph(f"• {escape(item)}", body_style))
        if prevention_bullets:
            elements.append(Paragraph("Habitudes de vie et prévention", subhead_style))
            for item in prevention_bullets:
                elements.append(Paragraph(f"• {escape(item)}", body_style))
        if has_grounded_lifestyle:
            elements.append(Paragraph("Repères généraux d'hygiène de vie", subhead_style))
            elements.append(Paragraph(escape(ls_raw_text), body_style))
        elif has_legacy_lifestyle_sources and not activity_bullets and not prevention_bullets:
            elements.append(Paragraph("Repères généraux d'hygiène de vie", subhead_style))
            elements.append(
                Paragraph(
                    "Une alimentation équilibrée, une hydratation régulière, un sommeil suffisant et une activité physique adaptée contribuent au bien-être général.",
                    body_style,
                )
            )
        section_idx += 1

    # 6. Questions à poser au médecin
    consultation_questions = [
        str(q).strip()
        for q in (explanations.get("consultation_questions") or [])
        if str(q).strip() and not is_placeholder_text(str(q))
    ]
    if consultation_questions:
        elements.append(
            Paragraph(
                f"{section_idx}. Questions à poser au médecin",
                heading_style,
            )
        )
        for question in consultation_questions:
            elements.append(Paragraph(f"• {escape(question)}", body_style))
            elements.append(Spacer(1, 2))
        section_idx += 1

    # Message de précaution unique
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(escape(task.disclaimer), disclaimer_style))

    doc.build(elements)
    return buffer.getvalue()
