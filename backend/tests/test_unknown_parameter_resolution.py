"""Tests pour la reconnaissance de PAL/GGT/HbA1c, extraction générique et résolution intelligente."""
from __future__ import annotations

import json
from pathlib import Path

from app.identification.parser import identify_parameters, identify_parameters_from_pages
from app.identification.unknown_resolver import (
    UNIDENTIFIED_PARAMETER_MESSAGE,
    load_catalog_extensions,
    resolve_unknown_parameter,
)
from app.knowledge.retriever import RetrievedPassage
from app.schemas import Source
from app.validation.analysis import analyze_parameters


def test_identify_pal_ggt_hba1c_and_units():
    text = "\n".join(
        [
            "Globules blancs 8 380 /mm3 (4500-10000) 9900 (23/06/26)",
            "Globules rouges 4,68 10^6/mm3 (4-5,4) 4,75 (23/06/26)",
            "Hémoglobine glycosylée (HbA1c) 7,00 % (Inférieur à 6,5)",
            "GAMMA GLUTAMYL TRANSFERASE 42 UI/L (10 - 55)",
            "Phosphatases alcalines 85 UI/L (35 - 104)",
            "RDW 14 % (11-15)",
        ]
    )
    items = identify_parameters(text, include_generic=True)
    by_code = {it["code"]: it for it in items}

    assert "WBC" in by_code and by_code["WBC"]["value"] == 8380.0
    assert "RBC" in by_code and by_code["RBC"]["unit"] == "10^6/mm³"
    assert "HBA1C" in by_code and by_code["HBA1C"]["reference_max"] == 6.5
    assert "GGT" in by_code and by_code["GGT"]["value"] == 42.0
    assert "PAL" in by_code and by_code["PAL"]["value"] == 85.0
    assert "GEN_RDW" in by_code
    assert by_code["GEN_RDW"]["is_generic"] is True
    assert by_code["GEN_RDW"]["value"] == 14.0
    assert by_code["GEN_RDW"]["unit"] == "%"
    assert by_code["GEN_RDW"]["reference_min"] == 11.0
    assert by_code["GEN_RDW"]["reference_max"] == 15.0


def test_multiline_vn_reference_parsed():
    pages = [
        {
            "page": 1,
            "text": "GAMMA GLUTAMYL TRANSFERASE 62 UI/L\n( V.N : 10 - 55 )",
            "table_rows": [],
            "ocr_confidence": 0.9,
        }
    ]
    items = identify_parameters_from_pages(pages, include_generic=True)
    assert len(items) == 1
    assert items[0]["code"] == "GGT"
    assert items[0]["reference_min"] == 10.0
    assert items[0]["reference_max"] == 55.0


def test_unknown_parameter_unidentified_without_hallucination(tmp_path: Path):
    ext_file = tmp_path / "catalog_extensions.json"
    param = {
        "code": "GEN_XYZ_INCONNU",
        "name_printed": "ParametreMystere",
        "value": 12.5,
        "unit": "mg/L",
        "reference_min": 5.0,
        "reference_max": 15.0,
        "raw_line": "ParametreMystere 12,5 mg/L (5 - 15)",
        "is_generic": True,
    }
    resolved = resolve_unknown_parameter(
        param,
        knowledge_index=None,
        llm_client=None,
        extensions_path=ext_file,
    )
    assert resolved["identification_status"] == "unidentified"
    assert resolved["normalized_name"] is None
    assert load_catalog_extensions(ext_file) == {}

    analyzed = analyze_parameters([resolved])
    assert len(analyzed) == 1
    assert analyzed[0]["value"] == 12.5


def test_unknown_parameter_grounded_via_faiss_and_llm_persists_extension(tmp_path: Path):
    ext_file = tmp_path / "catalog_extensions.json"
    passage = RetrievedPassage(
        passage_id="medline-rdw#001",
        source=Source(
            source_id="medlineplus-rdw",
            title="Indice de distribution des globules rouges (RDW)",
            organisme="MedlinePlus",
            url="https://medlineplus.gov/",
        ),
        excerpt="Le RDW (Red Cell Distribution Width) mesure la variation de taille des globules rouges.",
        score=0.92,
    )

    class _FakeIndex:
        def search(self, query: str, top_k: int = 4):
            return [passage]

    class _FakeLLM:
        def generate(self, system_prompt: str, user_prompt: str) -> str:
            return json.dumps(
                {
                    "decision": "recognized",
                    "normalized_name": "Indice de distribution des globules rouges (RDW)",
                    "synonyms": ["RDW", "IDR"],
                    "category": "Autres paramètres",
                    "biological_role": "Mesure la variabilité de taille des globules rouges.",
                    "explanation": "Le RDW évalue l'homogénéité de taille des globules rouges.",
                    "confidence": 0.91,
                    "source_ids": ["medlineplus-rdw"],
                }
            )

    param = {
        "code": "GEN_RDW",
        "name_printed": "RDW",
        "value": 14.0,
        "unit": "%",
        "reference_min": 11.0,
        "reference_max": 15.0,
        "raw_line": "RDW 14 % (11-15)",
        "is_generic": True,
    }
    resolved = resolve_unknown_parameter(
        param,
        knowledge_index=_FakeIndex(),
        llm_client=_FakeLLM(),
        extensions_path=ext_file,
        persist_validated=True,
    )
    assert resolved["identification_status"] == "recognized"
    assert "RDW" in resolved["normalized_name"]
    assert len(resolved["sources"]) == 1
    saved = load_catalog_extensions(ext_file)
    assert len(saved) == 1
    assert UNIDENTIFIED_PARAMETER_MESSAGE
