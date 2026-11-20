from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _fmt(x, comma):
    if x is None:
        return ""
    s = str(x)
    return s.replace(".", ",") if comma else s


def _ref(lo, hi, comma):
    if lo is None:
        return ""
    return f"{_fmt(lo, comma)} - {_fmt(hi, comma)}"


def render_pdf(path, layout, comma, params):
    """params : liste de dicts {name_printed, value, unit, reference_min, reference_max}."""
    st = getSampleStyleSheet()
    els = [Paragraph("<b>Laboratoire Test</b>", st["Title"]),
           Paragraph("Compte rendu fictif - Patient : TEST ANONYME", st["Normal"]),
           Spacer(1, 20)]
    if layout == "table1":
        rows = [["Examen", "Résultat", "Unité", "Valeurs de référence"]] + [
            [p["name_printed"], _fmt(p["value"], comma), p["unit"] or "",
             _ref(p["reference_min"], p["reference_max"], comma)] for p in params]
    elif layout == "table2":
        rows = [["Paramètre", "Valeurs usuelles", "Résultat", "Unité"]] + [
            [p["name_printed"], _ref(p["reference_min"], p["reference_max"], comma),
             _fmt(p["value"], comma), p["unit"] or ""] for p in params]
    if layout in ("table1", "table2"):
        t = Table(rows, hAlign="LEFT")
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                               ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey)]))
        els.append(t)
    else:
        for p in params:
            ref = (f' (réf. : {_ref(p["reference_min"], p["reference_max"], comma)})'
                   if p["reference_min"] is not None else "")
            els.append(Paragraph(
                f'{p["name_printed"]} : {_fmt(p["value"], comma)} {p["unit"] or ""}{ref}', st["Normal"]))
    SimpleDocTemplate(str(path), pagesize=A4).build(els)