from pathlib import Path

import pytest

from app.core.config import get_settings


def test_valeurs_par_defaut(monkeypatch):
    for var in ("LABMIND_OCR_LANG", "LABMIND_MIN_PDF_CHARS", "LABMIND_OCR_DPI",
                "LABMIND_MAX_UPLOAD_BYTES", "LABMIND_DATA_DIR"):
        monkeypatch.delenv(var, raising=False)
    s = get_settings()
    assert s.ocr_language == "fra"
    assert s.min_pdf_text_chars == 30
    assert s.ocr_dpi == 200
    assert s.max_upload_bytes == 10_000_000
    assert s.data_dir.name == "data"


def test_surcharge_par_variable_d_environnement(monkeypatch):
    monkeypatch.setenv("LABMIND_OCR_DPI", "300")
    monkeypatch.setenv("LABMIND_OCR_LANG", "eng")
    s = get_settings()
    assert s.ocr_dpi == 300
    assert s.ocr_language == "eng"


def test_valeur_entiere_invalide(monkeypatch):
    monkeypatch.setenv("LABMIND_OCR_DPI", "abc")
    with pytest.raises(ValueError):
        get_settings()


def test_tesseract_cmd_explicite(monkeypatch):
    monkeypatch.setenv("LABMIND_TESSERACT_CMD", r"C:\autre\tesseract.exe")
    assert get_settings().tesseract_cmd == r"C:\autre\tesseract.exe"


def test_creation_des_dossiers(monkeypatch, tmp_path):
    monkeypatch.setenv("LABMIND_DATA_DIR", str(tmp_path / "donnees"))
    s = get_settings()
    s.ensure_dirs()
    assert s.uploads_dir.is_dir()
    assert s.reports_dir.is_dir()
    assert isinstance(s.data_dir, Path)