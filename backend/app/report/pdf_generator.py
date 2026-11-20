"""Générateur PDF final LabMind (ReportLab).

Règles strictes respectées :
- Affiche uniquement les résultats extraits et les fourchettes du laboratoire.
- Affiche les explications documentées avec leurs citations (`source_id`, URL, date).
- Affiche les informations générales d'hygiène de vie uniquement si sourcées par RAG.
- Affiche les questions générées pour la consultation médicale si disponibles.
- N'invente jamais de valeur, de référence ou d'explication sans source.
- Affiche le message de précaution (`task.disclaimer`) exactement une fois.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.schemas import ParameterResult, ParameterStatus, Source, Task

_UNICODE_FONT_CANDIDATES = [
    (
        "LabMindSans",
        r"C:\Windows\Fonts\arial.ttf",
        "LabMindSans-Bold",
        r"C:\Windows\Fonts\arialbd.ttf",
    ),
    (
        "LabMindSans",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "LabMindSans-Bold",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
]


def _register_fonts() -> tuple[str, str]:
    """Enregistre une police TrueType Unicode si disponible pour les symboles (µ, ², accents)."""
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
        return "En dessous de la fourchette du laboratoire"
    if status == ParameterStatus.within_reference:
        return "Dans la fourchette du laboratoire"
    if status == ParameterStatus.above_reference:
        return "Au-dessus de la fourchette du laboratoire"
    if status == ParameterStatus.reference_unavailable:
        return "Fourchette absente du document"
    if status == ParameterStatus.value_unavailable:
        return "Valeur absente du document"
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


def _format_confidence(param: ParameterResult) -> str:
    parts: list[str] = []
    if param.confidence is not None:
        parts.append(f"{round(param.confidence * 100)} %")
    if param.evidence.page is not None:
        parts.append(f"p. {param.evidence.page}")
    return " / ".join(parts) if parts else "-"


def _has_general_lifestyle_sources(sources: list[Source]) -> bool:
    keywords = ("alimentation", "nutrition", "hygiene", "hygiène", "vie", "anses", "mangerbouger")
    for src in sources:
        haystack = f"{src.source_id} {src.title} {src.organisme}".lower()
        if any(kw in haystack for kw in keywords):
            return True
    return False


def build_labmind_report_pdf(task: Task) -> bytes:
    """Construit les octets du rapport PDF pédagogique LabMind à partir de `Task`."""
    regular_font, bold_font = _register_fonts()
    base_styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "LabMindTitle",
        parent=base_styles["Title"],
        fontName=bold_font,
        fontSize=17,
        leading=21,
        textColor=colors.HexColor("#102A43"),
        spaceAfter=6,
    )
    heading_style = ParagraphStyle(
        "LabMindHeading",
        parent=base_styles["Heading2"],
        fontName=bold_font,
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#1D4E89"),
        spaceBefore=12,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "LabMindBody",
        parent=base_styles["Normal"],
        fontName=regular_font,
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#1F2933"),
    )
    small_style = ParagraphStyle(
        "LabMindSmall",
        parent=body_style,
        fontSize=8.5,
        leading=11.5,
    )
    cell_header_style = ParagraphStyle(
        "LabMindCellHeader",
        parent=small_style,
        fontName=bold_font,
        textColor=colors.white,
    )
    disclaimer_style = ParagraphStyle(
        "LabMindDisclaimer",
        parent=body_style,
        fontName=bold_font,
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#7C2D12"),
        backColor=colors.HexColor("#FFF7ED"),
        borderColor=colors.HexColor("#FDBA74"),
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
        title="LabMind - Rapport pédagogique",
    )

    elements: list = []

    # 1. En-tête et métadonnées techniques
    elements.append(
        Paragraph("LabMind — Compte rendu pédagogique d'analyses biologiques", title_style)
    )
    doc_name = task.document.filename if task.document else "Document inconnu"
    method = (
        task.document.extraction_method.value
        if task.document and task.document.extraction_method
        else "non précisée"
    )
    categories_text = (
        ", ".join(task.detected_categories) if task.detected_categories else "Aucune détectée"
    )
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    meta_lines = [
        f"<b>Document :</b> {escape(doc_name)} (méthode d'extraction : {escape(method)})",
        f"<b>Catégories identifiées :</b> {escape(categories_text)}",
        f"<b>Identifiant rapport :</b> {escape(task.report_id or task.task_id)} | <b>Généré le :</b> {escape(generated_at)}",
    ]
    for line in meta_lines:
        elements.append(Paragraph(line, small_style))
    elements.append(Spacer(1, 8))

    # 2. Résultats extraits et fourchettes du laboratoire
    elements.append(Paragraph("1. Résultats extraits du document", heading_style))
    elements.append(
        Paragraph(
            "Les valeurs et fourchettes de référence ci-dessous proviennent uniquement du compte rendu du laboratoire.",
            small_style,
        )
    )
    elements.append(Spacer(1, 4))

    if task.parameters:
        table_rows = [
            [
                Paragraph("Paramètre", cell_header_style),
                Paragraph("Résultat", cell_header_style),
                Paragraph("Fourchette du laboratoire", cell_header_style),
                Paragraph("Position technique", cell_header_style),
                Paragraph("Confiance / Page", cell_header_style),
            ]
        ]
        for param in task.parameters:
            table_rows.append(
                [
                    Paragraph(f"<b>{escape(param.name_printed)}</b> ({escape(param.code)})", small_style),
                    Paragraph(escape(_format_value(param)), small_style),
                    Paragraph(escape(_format_reference(param)), small_style),
                    Paragraph(escape(_status_label(param.status)), small_style),
                    Paragraph(escape(_format_confidence(param)), small_style),
                ]
            )

        table = Table(
            table_rows,
            colWidths=[44 * mm, 28 * mm, 35 * mm, 48 * mm, 25 * mm],
            repeatRows=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1D4E89")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        elements.append(table)
    else:
        elements.append(Paragraph("Aucun paramètre biologique n'a pu être extrait.", body_style))

    # 3. Limites et incertitudes
    uncertain = [
        p
        for p in task.parameters
        if p.status in (ParameterStatus.not_analyzed, ParameterStatus.reference_unavailable, ParameterStatus.value_unavailable)
    ]
    elements.append(Paragraph("2. Limites et données incertaines", heading_style))
    if uncertain:
        for param in uncertain:
            detail = param.reason or _status_label(param.status)
            elements.append(
                Paragraph(
                    f"• <b>{escape(param.name_printed)} ({escape(param.code)})</b> : {escape(detail)}. "
                    "Aucune valeur ni unité absente n'est devinée par LabMind.",
                    body_style,
                )
            )
    else:
        elements.append(
            Paragraph(
                "Tous les paramètres extraits disposaient des champs nécessaires pour la comparaison technique.",
                body_style,
            )
        )

    # 4. Explications pédagogiques sourcées
    elements.append(Paragraph("3. Explications pédagogiques documentées", heading_style))
    explanations = task.explanations or {}
    summary_text = str(explanations.get("summary") or "").strip()
    if summary_text:
        elements.append(Paragraph(escape(summary_text), body_style))
        elements.append(Spacer(1, 4))

    param_explanations = (
        explanations.get("parameter_explanations")
        or explanations.get("parameters")
        or []
    )
    if param_explanations:
        for item in param_explanations:
            code = str(item.get("code", ""))
            exp_text = str(item.get("text", "")).strip()
            source_ids = [str(s) for s in (item.get("source_ids") or []) if str(s).strip()]
            citation_str = f" <i>[Sources : {escape(', '.join(source_ids))}]</i>" if source_ids else ""
            elements.append(
                Paragraph(
                    f"<b>{escape(code)} :</b> {escape(exp_text)}{citation_str}",
                    body_style,
                )
            )
            elements.append(Spacer(1, 3))
    else:
        elements.append(
            Paragraph(
                "Aucune explication pédagogique disponible : aucune source documentaire suffisante n'a été fournie.",
                body_style,
            )
        )

    # 5. Informations générales d'hygiène de vie (uniquement si sourcées par RAG)
    section_idx = 4
    lifestyle_info = explanations.get("lifestyle_info")
    has_grounded_lifestyle = (
        isinstance(lifestyle_info, dict)
        and lifestyle_info.get("status") == "grounded"
        and bool(str(lifestyle_info.get("text") or "").strip())
    )
    has_legacy_lifestyle_sources = bool(task.sources and _has_general_lifestyle_sources(task.sources))

    if has_grounded_lifestyle or has_legacy_lifestyle_sources:
        elements.append(
            Paragraph(
                f"{section_idx}. Informations générales documentées (hygiène de vie)",
                heading_style,
            )
        )
        if has_grounded_lifestyle:
            assert isinstance(lifestyle_info, dict)
            ls_text = str(lifestyle_info.get("text") or "").strip()
            ls_sources = [str(s) for s in (lifestyle_info.get("source_ids") or []) if str(s).strip()]
            ls_citation = f" <i>[Sources : {escape(', '.join(ls_sources))}]</i>" if ls_sources else ""
            elements.append(Paragraph(f"{escape(ls_text)}{ls_citation}", body_style))
        else:
            lifestyle_sources = [s for s in task.sources if _has_general_lifestyle_sources([s])]
            for src in lifestyle_sources:
                elements.append(
                    Paragraph(
                        f"• <b>{escape(src.organisme)}</b> — {escape(src.title)} ({escape(src.source_id)})",
                        body_style,
                    )
                )
        section_idx += 1

    # 5b. Plan nutritionnel structuré (uniquement si sourcé par RAG)
    nutrition_plan = explanations.get("nutrition_plan")
    if isinstance(nutrition_plan, dict) and nutrition_plan.get("status") == "grounded":
        if nutrition_plan.get("intro"):
            elements.append(Paragraph(escape(str(nutrition_plan["intro"])), body_style))
            elements.append(Spacer(1, 4))
        for hl in nutrition_plan.get("highlights") or []:
            t = escape(str(hl.get("title", "")))
            s = escape(str(hl.get("subtitle", "")))
            if t and s:
                elements.append(Paragraph(f"• <b>{t}</b> : {s}", body_style))
        meal_rows = nutrition_plan.get("daily_meal_plan") or []
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
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1D4E89")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            elements.append(m_table)
            elements.append(Spacer(1, 6))

    # 5c. Prochaines étapes pratiques (si générées)
    action_steps = [str(s).strip() for s in (explanations.get("action_steps") or []) if str(s).strip()]
    if action_steps:
        elements.append(Paragraph(f"{section_idx}. Prochaines étapes recommandées", heading_style))
        for idx_step, step_txt in enumerate(action_steps, start=1):
            elements.append(Paragraph(f"{idx_step}. {escape(step_txt)}", body_style))
            elements.append(Spacer(1, 2))
        section_idx += 1

    # 6. Questions à préparer pour le médecin (générées dynamiquement par le LLM)
    consultation_questions = [
        str(q).strip()
        for q in (explanations.get("consultation_questions") or [])
        if str(q).strip()
    ]
    if consultation_questions:
        elements.append(
            Paragraph(
                f"{section_idx}. Questions à préparer pour votre médecin",
                heading_style,
            )
        )
        for question in consultation_questions:
            elements.append(Paragraph(f"• {escape(question)}", body_style))
            elements.append(Spacer(1, 2))
        section_idx += 1

    # 7. Sources documentaires citées
    elements.append(Paragraph(f"{section_idx}. Sources documentaires citées", heading_style))
    if task.sources:
        for src in task.sources:
            date_txt = f" — {src.date}" if src.date else ""
            elements.append(
                Paragraph(
                    f"• <b>[{escape(src.source_id)}]</b> {escape(src.title)} "
                    f"({escape(src.organisme)}{escape(date_txt)}) — {escape(src.url)}",
                    small_style,
                )
            )
    else:
        elements.append(
            Paragraph("Aucune source documentaire citée pour cette analyse.", body_style)
        )

    # 8. Message de précaution unique
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(escape(task.disclaimer), disclaimer_style))

    doc.build(elements)
    return buffer.getvalue()