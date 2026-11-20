import io

import pymupdf
import pytest
from PIL import Image

from app.extraction.extractor import extract_document
from app.identification.parser import identify_parameters


def test_pdf_numerique(pdf_lignes):
    r = extract_document(pdf_lignes)
    assert r["method"] == "pdf_text"
    codes = {p["code"] for p in identify_parameters(r["text"])}
    assert codes == {"HGB", "GLY", "TG"}


def test_format_non_supporte(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("bonjour")
    with pytest.raises(ValueError):
        extract_document(f)


def test_image_passe_par_ocr(pdf_lignes, tmp_path):
    """Un PDF rasterisé (scan propre) doit passer par l'OCR et retrouver les 3 paramètres."""
    with pymupdf.open(pdf_lignes) as doc:
        png = doc[0].get_pixmap(dpi=200).tobytes("png")
    img_path = tmp_path / "scan.png"
    Image.open(io.BytesIO(png)).save(img_path)
    r = extract_document(img_path)
    assert r["method"] == "ocr"
    codes = {p["code"] for p in identify_parameters(r["text"])}
    assert "HGB" in codes and "GLY" in codes