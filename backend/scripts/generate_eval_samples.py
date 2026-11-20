"""Génère un jeu varié de départ dans evaluation/ couvrant les 6 catégories."""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.evaluation.metrics import DocumentGroundTruth, GroundTruthParam  # noqa: E402


def _save_gt(gt_dir: Path, gt: DocumentGroundTruth) -> None:
    (gt_dir / f"{gt.doc_id}.json").write_text(
        gt.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    eval_dir = REPO_ROOT / "evaluation"
    docs_dir = eval_dir / "documents"
    gt_dir = eval_dir / "ground_truth"
    results_dir = eval_dir / "results"
    for d in (docs_dir, gt_dir, results_dir):
        d.mkdir(parents=True, exist_ok=True)

    st = getSampleStyleSheet()

    # 1. PDF mixte NFS + Bilan martial (format tableau)
    doc1 = docs_dir / "eval_01_nfs_martial.pdf"
    SimpleDocTemplate(str(doc1), pagesize=A4).build(
        [
            Paragraph("<b>Centre Biologique Val d'Oise</b>", st["Title"]),
            Spacer(1, 12),
            Table(
                [
                    ["Analyse", "Résultat", "Unité", "Valeurs de référence"],
                    ["Hémoglobine", "11,2", "g/dL", "12,0 - 16,0"],
                    ["Plaquettes", "235", "10^3/µL", "150 - 400"],
                    ["Ferritine", "22", "ng/mL", "30 - 300"],
                    ["Fer sérique", "10,4", "µmol/L", "11,0 - 28,0"],
                ],
                hAlign="LEFT",
                style=TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]),
            ),
        ]
    )
    _save_gt(
        gt_dir,
        DocumentGroundTruth(
            doc_id="eval_01_nfs_martial",
            filename=doc1.name,
            parameters=[
                GroundTruthParam(code="HGB", value=11.2, unit="g/dL", reference_min=12.0, reference_max=16.0),
                GroundTruthParam(code="PLT", value=235.0, unit="10^3/µL", reference_min=150.0, reference_max=400.0),
                GroundTruthParam(code="FERR", value=22.0, unit="ng/mL", reference_min=30.0, reference_max=300.0),
                GroundTruthParam(code="FER", value=10.4, unit="µmol/L", reference_min=11.0, reference_max=28.0),
            ],
        ),
    )

    # 2. PDF multi-pages : Glycémie + Lipides (seuils unilatéraux <) + Hépatique + Rénal (>)
    doc2 = docs_dir / "eval_02_complet_multipages.pdf"
    SimpleDocTemplate(str(doc2), pagesize=A4).build(
        [
            Paragraph("<b>Laboratoire Métabolique</b>", st["Title"]),
            Paragraph("Glycémie à jeun : 1,02 g/L (réf. : 0,70 - 1,10)", st["Normal"]),
            Paragraph("HbA1c : 5,9 % (< 6,5 %)", st["Normal"]),
            Paragraph("Cholestérol LDL : 1,72 g/L (< 1,60 g/L)", st["Normal"]),
            PageBreak(),
            Paragraph("<b>Suite du compte rendu - Page 2</b>", st["Title"]),
            Paragraph("ALAT (TGP) : 48 U/L (< 40 U/L)", st["Normal"]),
            Paragraph("GGT : 32 UI/L (10 - 55)", st["Normal"]),
            Paragraph("Créatinine : 9,8 mg/L (7,0 - 13,0)", st["Normal"]),
            Paragraph("DFG estimé (CKD-EPI) : 84 mL/min/1.73m² (> 60)", st["Normal"]),
        ]
    )
    _save_gt(
        gt_dir,
        DocumentGroundTruth(
            doc_id="eval_02_complet_multipages",
            filename=doc2.name,
            parameters=[
                GroundTruthParam(code="GLY", value=1.02, unit="g/L", reference_min=0.70, reference_max=1.10),
                GroundTruthParam(code="HBA1C", value=5.9, unit="%", reference_min=None, reference_max=6.5),
                GroundTruthParam(code="LDL", value=1.72, unit="g/L", reference_min=None, reference_max=1.60),
                GroundTruthParam(code="ALAT", value=48.0, unit="U/L", reference_min=None, reference_max=40.0),
                GroundTruthParam(code="GGT", value=32.0, unit="UI/L", reference_min=10.0, reference_max=55.0),
                GroundTruthParam(code="CREAT", value=9.8, unit="mg/L", reference_min=7.0, reference_max=13.0),
                GroundTruthParam(code="DFG", value=84.0, unit="mL/min/1.73m²", reference_min=60.0, reference_max=None),
            ],
        ),
    )

    # 3. PDF avec unité manquante volontaire (test de non-invention)
    doc3 = docs_dir / "eval_03_unite_absente.pdf"
    SimpleDocTemplate(str(doc3), pagesize=A4).build(
        [
            Paragraph("<b>Laboratoire Test Ambigu</b>", st["Title"]),
            Paragraph("Hématocrite : 43,0 (37,0 - 47,0)", st["Normal"]),
            Paragraph("Urée : 0,34 g/L (0,15 - 0,45)", st["Normal"]),
        ]
    )
    _save_gt(
        gt_dir,
        DocumentGroundTruth(
            doc_id="eval_03_unite_absente",
            filename=doc3.name,
            parameters=[
                GroundTruthParam(code="HCT", value=43.0, unit=None, reference_min=37.0, reference_max=47.0),
                GroundTruthParam(code="UREE", value=0.34, unit="g/L", reference_min=0.15, reference_max=0.45),
            ],
        ),
    )

    # 4. Image PNG propre pour évaluer la voie OCR réelle
    doc4 = docs_dir / "eval_04_scan_ocr.png"
    img = Image.new("RGB", (1600, 520), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=28)
    except TypeError:
        font = ImageFont.load_default()
    lines = [
        "LABORATOIRE SCAN",
        "Glycemie : 0,88 g/L (0,70 - 1,10)",
        "Cholesterol total : 1,85 g/L (< 2,00)",
        "Triglycerides : 1,20 g/L (< 1,50)",
    ]
    y = 50
    for line in lines:
        draw.text((50, y), line, fill="black", font=font)
        y += 90
    img.save(doc4)
    _save_gt(
        gt_dir,
        DocumentGroundTruth(
            doc_id="eval_04_scan_ocr",
            filename=doc4.name,
            parameters=[
                GroundTruthParam(code="GLY", value=0.88, unit="g/L", reference_min=0.70, reference_max=1.10),
                GroundTruthParam(code="CHOL", value=1.85, unit="g/L", reference_min=None, reference_max=2.00),
                GroundTruthParam(code="TG", value=1.20, unit="g/L", reference_min=None, reference_max=1.50),
            ],
        ),
    )

    print(f"Jeu d'évaluation généré dans : {eval_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())