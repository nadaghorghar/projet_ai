from app.agent import AgentOrchestrator, AgentState
from app.identification.catalog import (
    ACCEPTED_UNITS,
    ALIASES,
    CATEGORY_BY_CODE,
    get_categories_for_codes,
)
from app.identification.parser import identify_parameters, normalize_unit
from app.schemas import TaskStatus
from app.validation.analysis import analyze_parameters
from tests.helpers import render_pdf


def test_catalog_covers_all_six_target_categories():
    expected_categories = {
        "NFS",
        "Bilan martial",
        "Bilan glycémique",
        "Bilan lipidique",
        "Bilan hépatique",
        "Bilan rénal",
        "Bilan minéral",
    }
    assert set(CATEGORY_BY_CODE.values()) == expected_categories
    assert set(ALIASES.keys()) == set(CATEGORY_BY_CODE.keys())
    assert set(ACCEPTED_UNITS.keys()) == set(CATEGORY_BY_CODE.keys())
    assert len(CATEGORY_BY_CODE) == 32


def test_normalize_unit_handles_new_units_and_ocr_variants():
    assert normalize_unit("umol/l") == "µmol/L"
    assert normalize_unit("urmol/l") == "µmol/L"
    assert normalize_unit("ug/L") == "µg/L"
    assert normalize_unit("ui/l") == "UI/L"
    assert normalize_unit("u/l") == "U/L"
    assert normalize_unit("ml/min/1,73m2") == "mL/min/1.73m²"
    assert normalize_unit("mL/min/1.73m^2") == "mL/min/1.73m²"
    assert normalize_unit("Millions/mm*") == "Millions/mm³"
    assert normalize_unit("g/d!") == "g/dL"


def test_identify_and_analyze_new_categories_and_one_sided_bounds():
    text = "\n".join(
        [
            "Ferritine : 45 ng/mL (30 - 300)",
            "Fer sérique : 18,5 µmol/L (11,0 - 28,0)",
            "HbA1c : 5,8 % (< 6,5 %)",
            "ALAT (TGP) : 52 U/L (< 40)",
            "GGT : 30 UI/L (10 - 55)",
            "Bilirubine totale : 12 mg/L (< 17)",
            "Créatinine : 9,5 mg/L (7,0 - 13,0)",
            "Urée : 0,35 g/L (0,15 - 0,45)",
            "DFG estimé (CKD-EPI) : 88 mL/min/1,73m2 (> 60)",
        ]
    )

    identified = identify_parameters(text)
    analyzed = analyze_parameters(identified)
    by_code = {item["code"]: item for item in analyzed}

    assert set(by_code) == {
        "FERR",
        "FER",
        "HBA1C",
        "ALAT",
        "GGT",
        "BILI",
        "CREAT",
        "UREE",
        "DFG",
    }
    assert by_code["HBA1C"]["reference_min"] is None
    assert by_code["HBA1C"]["reference_max"] == 6.5
    assert by_code["HBA1C"]["status"] == "within_reference"

    assert by_code["ALAT"]["status"] == "above_reference"
    assert by_code["DFG"]["reference_min"] == 60.0
    assert by_code["DFG"]["reference_max"] is None
    assert by_code["DFG"]["status"] == "within_reference"
    assert by_code["DFG"]["unit"] == "mL/min/1.73m²"

    categories = get_categories_for_codes(list(by_code))
    assert set(categories) == {
        "Bilan martial",
        "Bilan glycémique",
        "Bilan hépatique",
        "Bilan rénal",
    }


def test_identify_faux_bold_pdf_minerals_and_leukocytes():
    text = "\n".join(
        [
            "GGllyyccéémmiiee àà jjeeûûnn.. .. .. .. .. 5,77 mmol/l ( 4,5 - 6 ) 6,22 (09/10/25)",
            "CCrrééaattiinniinnee.. .. .. 91 µmol/l ( 65 - 120 ) 98 (15/08/25)",
            "AAcciiddee UUrriiqquuee.. .. .. 151 µmol/l ( 210 - 420 ) 468 (15/08/25)",
            "Basophiles …… 0,1 % 7 fmm° ( Inférieur à 50 )",
            "CALCIUM …… 89 mg/L (88 - 108)",
            "MAGNESIUM PLASMATIQUE …… 17,39 mg/L (18 - 26)",
        ]
    )
    identified = identify_parameters(text)
    analyzed = analyze_parameters(identified)
    by_code = {item["code"]: item for item in analyzed}

    assert set(by_code) == {"GLY", "CREAT", "URIC", "BASO", "CA", "MG"}
    assert by_code["GLY"]["value"] == 5.77
    assert by_code["URIC"]["status"] == "below_reference"
    assert by_code["BASO"]["value"] == 7.0
    assert by_code["BASO"]["unit"] == "/mm³"
    assert by_code["MG"]["value"] == 17.39
    assert by_code["MG"]["status"] == "below_reference"


def test_agent_populates_detected_categories_in_task(tmp_path):
    pdf = tmp_path / "multi_cat.pdf"
    render_pdf(
        pdf,
        "table1",
        True,
        [
            {
                "name_printed": "Hémoglobine",
                "value": 13.5,
                "unit": "g/dL",
                "reference_min": 12.0,
                "reference_max": 16.0,
            },
            {
                "name_printed": "Ferritine",
                "value": 55.0,
                "unit": "ng/mL",
                "reference_min": 30.0,
                "reference_max": 300.0,
            },
            {
                "name_printed": "Créatinine",
                "value": 9.2,
                "unit": "mg/L",
                "reference_min": 7.0,
                "reference_max": 13.0,
            },
        ],
    )

    state = AgentState(
        task_id="task-6cat",
        file_path=str(pdf),
        filename=pdf.name,
    )
    final_state = AgentOrchestrator().run(state)

    assert final_state.status == TaskStatus.done
    task = final_state.to_task(report_id="r-6cat")
    assert task.detected_categories == ["NFS", "Bilan martial", "Bilan rénal"]