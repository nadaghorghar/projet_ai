"""Tests ciblés ajoutés lors de l'audit et de la finalisation LabMind."""
from __future__ import annotations

import json
from pathlib import Path

from app.agent.orchestrator import AgentOrchestrator
from app.agent.planner import AgentState
from app.generation.grounding import check_explanation_grounding
from app.generation.interface import ExplanationStatus, ParameterExplanation, RetrievedPassage
from app.identification.parser import identify_parameters
from app.knowledge.registry import load_sources_registry, validate_registry_consistency
from app.schemas import Source, parameter_from_dict
from app.validation.analysis import analyze_parameters


class _FailingOCRReader:
    def extract(self, file_path: Path):
        raise RuntimeError("Tesseract OCR introuvable (binaire non détecté).")


def test_photo_ocr_16_parameters_and_prior_extraction():
    raw_ocr = """
    HEMOGRAMME
    Globules rouges ............ 4,50 Millions/mm3   ( 3,8 - 5,5 )
    Hémoglobine ................ 13,3 g/dl           ( 12 - 15,5 )   antér. 12,5 g/dl (10/01/2026)
    Hématocrite ................ 38,9 %              ( 36 - 46 )
    VGM ........................ 86 fl               ( 80 - 100 )
    TCMH ....................... 30 pg               ( 28 - 32 )
    CCMH ....................... 34 g/dl             ( 30 - 36 )
    Globules blancs ............ 6 870 /mm3          ( 4000 - 10000 )
    FORMULE LEUCOCYTAIRE
    Neutrophiles ............... 62,6 %  4301 /mm3   ( 1700 - 7000 )
    Lymphocytes ................ 31,7 %  2178 /mm3   ( 1500 - 4000 )
    Monocytes .................. 4,9 %   337 /mm3    ( 100 - 1000 )
    Eosinophiles ............... 0,7 %   48 /mm3     ( Inférieur à 500 )
    Basophiles ................. 0,1 %   7 /mm3      ( Inférieur à 50 )
    Plaquettes ................. 228 000 /mm3        ( 150000 - 450000 )
    ANALYSES DE BIOCHIMIE (SANG)
    CREATININE ................. 66,98 µmol/l        ( 44 - 97 )
    CALCIUM .................... 89 mg/L             ( 88 - 108 )
    MAGNESIUM PLASMATIQUE ...... 17,39 mg/L          ( 18 - 26 )
    """
    identified = identify_parameters(raw_ocr)
    analyzed = analyze_parameters(identified, method="ocr", compute_confidence=True)
    by_code = {item["code"]: item for item in analyzed}

    expected_codes = {
        "RBC", "HGB", "HCT", "VGM", "TCMH", "CCMH", "WBC",
        "NEUT", "LYMPH", "MONO", "EOS", "BASO", "PLT",
        "CREAT", "CA", "MG",
    }
    assert expected_codes.issubset(by_code.keys())
    assert by_code["MG"]["status"] == "below_reference"
    assert by_code["HGB"]["prior"]["comparable"] is True
    assert by_code["HGB"]["prior"]["delta"] == 0.8
    assert by_code["HGB"]["prior"]["prior_date"] == "10/01/2026"


def test_prior_unit_mismatch_and_marked_deviation():
    analyzed = analyze_parameters(
        [
            {
                "code": "HGB",
                "name_printed": "Hémoglobine",
                "value": 7.5,
                "unit": "g/dL",
                "reference_min": 12.0,
                "reference_max": 16.0,
                "prior_value": 7.8,
                "prior_unit": "mmol/L",
                "prior_date": "02/02/2026",
                "raw_line": "Hémoglobine 7,5 g/dL 12,0 - 16,0 antér. 7,8 mmol/L",
            }
        ],
        method="pdf_text",
        compute_confidence=True,
    )
    param = analyzed[0]
    assert param["marked_deviation"] is True
    assert param["prior"]["comparable"] is False
    assert param["prior"]["trend"] == "not_comparable"


def test_grounding_accepts_prior_numbers():
    analyzed = analyze_parameters(
        [
            {
                "code": "HGB",
                "name_printed": "Hémoglobine",
                "value": 13.3,
                "unit": "g/dL",
                "reference_min": 12.0,
                "reference_max": 15.5,
                "prior_value": 12.5,
                "prior_unit": "g/dL",
                "prior_date": "10/01/2026",
                "raw_line": "Hémoglobine 13,3 g/dL 12 - 15,5 antér. 12,5 g/dL (10/01/2026)",
            }
        ]
    )
    param = parameter_from_dict(analyzed[0])
    passage = RetrievedPassage(
        passage_id="ameli-nfs#001",
        source=Source(
            source_id="ameli-hemogramme-2025",
            title="Hémogramme",
            organisme="Assurance Maladie",
            url="https://www.ameli.fr/assure/sante/examen/analyse/lire-resultats-prise-sang",
            date="2025-01-20",
        ),
        excerpt="L'hémoglobine est une protéine des globules rouges qui transporte l'oxygène dans le sang.",
        score=0.9,
    )
    explanation = ParameterExplanation(
        code="HGB",
        status=ExplanationStatus.grounded,
        text=(
            "L'hémoglobine transporte l'oxygène dans les globules rouges. "
            "La valeur actuelle (13.3 g/dL) évolue de +0.8 par rapport au résultat antérieur (12.5 du 10/01/2026)."
        ),
        source_ids=["ameli-hemogramme-2025"],
    )
    check = check_explanation_grounding(explanation, param, [passage], min_overlap_ratio=0.15)
    assert check.is_grounded is True
    assert check.ungrounded_numbers == []


def test_knowledge_registry_contains_international_and_french_sources():
    corpus_dir = Path(__file__).resolve().parents[2] / "knowledge_corpus"
    registry = load_sources_registry(corpus_dir / "metadata" / "sources_registry.json")
    errors = validate_registry_consistency(registry, corpus_dir / "sources")
    assert errors == []
    collected_ids = {s.source_id for s in registry.collected_sources()}
    assert "medlineplus-niddk-ada-lab-tests-2026" in collected_ids
    assert "oms-has-nutrition-suivi-2025" in collected_ids


def test_orchestrator_surfaces_actionable_ocr_error(tmp_path):
    fake_img = tmp_path / "bilan.jpg"
    fake_img.write_bytes(b"\xff\xd8\xff\xe0dummy")
    orch = AgentOrchestrator(ocr_reader=_FailingOCRReader())
    state = AgentState(task_id="t-ocr-fail", file_path=str(fake_img), filename="bilan.jpg")
    final_state = orch.run(state)
    assert final_state.status.value == "error"
    assert final_state.error is not None
    assert "Tesseract" in final_state.error.message


def test_food_image_key_resolution_is_unique_and_semantic():
    from app.generation.rag import _resolve_food_image_key

    used: set[str] = set()
    samples = [
        ("Amandes et noix", "Oléagineux riches en minéraux", "almonds_walnuts", "almonds_walnuts"),
        ("Épinards frais", "Légumes verts riches en folates", "spinach", "spinach"),
        ("Lentilles et pois chiches", "Légumineuses et fibres", "lentils_chickpeas", "lentils_chickpeas"),
        ("Poissons gras", "Saumon, sardine ou maquereau", "fish", "fish"),
        ("Fruits frais de saison", "Source de vitamine C", "fruits", "fruits"),
        ("Céréales complètes", "Avoine et pain complet", "whole_grains", "whole_grains"),
        ("Légumes variés", "Brocoli et carottes", "vegetables", "vegetables"),
    ]
    resolved = []
    for title, sub, raw_k, expected in samples:
        key = _resolve_food_image_key(title, sub, raw_k, used)
        assert key == expected
        resolved.append(key)
    assert len(set(resolved)) == len(samples)

    # Doublon ou aliment sans image dédiée -> repli neutre (jamais d'image répétée)
    dup_key = _resolve_food_image_key("Amandes grillées", "Encore des amandes", "almonds_walnuts", used)
    assert dup_key == "neutral"
    unknown_key = _resolve_food_image_key("Eau minérale", "Hydratation quotidienne", "unknown_key", used)
    assert unknown_key == "neutral"


def test_six_section_pdf_structure_and_no_removed_sections():
    from app.generation.interface import GenerationResult, GuidanceSections, MealPlanRow, NutritionHighlight, NutritionPlan
    from app.report import build_labmind_report_pdf
    from app.schemas import DISCLAIMER, DocumentInfo, Evidence, ExtractionMethod, ParameterResult, ParameterStatus, Reference, Task, TaskStatus
    import pymupdf

    src = Source(
        source_id="oms-has-nutrition-suivi-2025",
        title="Alimentation saine et repères de suivi",
        organisme="OMS / HAS",
        url="https://www.who.int/news-room/fact-sheets/detail/healthy-diet",
        date="2025-07-15",
    )
    gen_result = GenerationResult(
        summary="Explications pédagogiques produites exclusivement à partir des sources documentaires vérifiées.",
        general_summary="Sur 2 paramètre(s) analysé(s), 1 est conforme aux bornes. Point(s) à discuter avec votre médecin : Magnésium.",
        parameter_explanations=[
            ParameterExplanation(
                code="MG",
                status=ExplanationStatus.grounded,
                text="Le magnésium contribue au bon fonctionnement musculaire et nerveux. Ce taux est légèrement inférieur à la borne du laboratoire.",
                source_ids=["oms-has-nutrition-suivi-2025"],
            )
        ],
        nutrition_plan=NutritionPlan(
            status=ExplanationStatus.grounded,
            intro="Une alimentation variée soutient l'équilibre général.",
            section_title="Aliments adaptés",
            highlights=[
                NutritionHighlight(title="Amandes", subtitle="Apport minéral.", image_key="almonds_walnuts"),
                NutritionHighlight(title="Noix", subtitle="Apport minéral.", image_key="walnuts"),
                NutritionHighlight(title="Épinards", subtitle="Légumes verts.", image_key="spinach"),
                NutritionHighlight(title="Lentilles", subtitle="Légumineuses.", image_key="lentils_chickpeas"),
                NutritionHighlight(title="Graines de courge", subtitle="Graines.", image_key="pumpkin_seeds"),
            ],
            daily_meal_plan=[MealPlanRow(meal="Déjeuner", example="Poisson + légumes verts")],
            source_ids=["oms-has-nutrition-suivi-2025"],
        ),
        guidance_sections=GuidanceSections(
            nutrition=["Associer légumes verts, oléagineux et hydratation régulière."],
            physical_activity=["Pratiquer une marche régulière et limiter la position assise prolongée."],
            lifestyle_prevention=["Maintenir un sommeil régulier et éviter le tabac."],
        ),
        consultation_questions=["Mon taux de magnésium est légèrement inférieur à la normale. Est-il nécessaire de le contrôler ?"],
        sources=[src],
    )
    task = Task(
        task_id="t-6sec",
        status=TaskStatus.done,
        document=DocumentInfo(filename="bilan_ref.pdf", extraction_method=ExtractionMethod.pdf_text),
        parameters=[
            ParameterResult(
                code="CA",
                name_printed="Calcium",
                value=89.0,
                unit="mg/L",
                reference=Reference(min=88.0, max=108.0, origin="document_laboratoire"),
                status=ParameterStatus.within_reference,
                confidence=0.95,
                evidence=Evidence(raw_text="Calcium 89 mg/L (88 - 108)", page=1),
            ),
            ParameterResult(
                code="MG",
                name_printed="Magnésium",
                value=17.39,
                unit="mg/L",
                reference=Reference(min=18.0, max=26.0, origin="document_laboratoire"),
                status=ParameterStatus.below_reference,
                confidence=0.95,
                evidence=Evidence(raw_text="Magnésium 17,39 mg/L (18 - 26)", page=1),
            ),
        ],
        report_id="r-6sec",
        explanations=gen_result.to_task_explanations(),
        sources=[src],
        disclaimer=DISCLAIMER,
    )
    pdf_bytes = build_labmind_report_pdf(task)
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        text = " ".join(" ".join(p.get_text("text") for p in doc).split())
    assert "1. Résumé général du bilan" in text
    assert "2. Tableau des résultats avec leur statut" in text
    assert "3. Explication concise des anomalies" in text
    assert "4. Conseils alimentaires personnalisés" in text
    assert "5. Activité physique et habitudes de vie pertinentes" in text
    assert "6. Questions à poser au médecin" in text
    assert "Suivi médical recommandé" not in text
    assert "Sources médicales" not in text
    assert "oms-has-nutrition-suivi-2025" not in text
    assert "Limites d'interprétation" not in text
    assert "1 à 3 repères" not in text
    assert "2 à 3 repères" not in text


def test_ocr_decimal_preservation_and_plausibility_guard():
    from app.validation.reference import plausible

    noisy_ocr = """
    Globules rouges   4 , 50  Millions/mm3   ( 3 , 8 - 5 , 5 )
    Hémoglobine       13,3 g/dl              ( 12 - 15,5 )  Hématocrite   38,9 %   ( 36 - 46 )
    VGM               86 fl                  ( 80 - 100 )
    CCMH              34 g/dl                ( 30 - 36 )
    Créatinine        66,98 µmol/l           ( 44 - 97 )
    Calcium           89 mg/L                ( 88 - 108 )
    Magnésium         17,39 mg/L             ( 18 - 26 )
    """
    identified = identify_parameters(noisy_ocr)
    analyzed = analyze_parameters(identified, method="ocr", compute_confidence=True)
    by_code = {item["code"]: item for item in analyzed}

    assert by_code["RBC"]["value"] == 4.5
    assert by_code["RBC"]["reference_min"] == 3.8
    assert by_code["RBC"]["reference_max"] == 5.5
    assert by_code["RBC"]["status"] == "within_reference"

    assert by_code["HCT"]["value"] == 38.9
    assert by_code["HCT"]["unit"] == "%"
    assert by_code["HCT"]["reference_min"] == 36.0
    assert by_code["HCT"]["reference_max"] == 46.0
    assert by_code["HCT"]["status"] == "within_reference"

    assert by_code["CCMH"]["value"] == 34.0
    assert by_code["CCMH"]["status"] == "within_reference"
    assert by_code["MG"]["status"] == "below_reference"

    # Vérifie que (38 - 55) sur RBC 4.50 Millions/mm3 est rejeté comme erreur de virgule
    assert plausible({
        "code": "RBC",
        "value": 4.5,
        "unit": "Millions/mm³",
        "reference_min": 38.0,
        "reference_max": 55.0,
    }) is False
    assert plausible({
        "code": "RBC",
        "value": 4.5,
        "unit": "Millions/mm³",
        "reference_min": 3.8,
        "reference_max": 5.5,
    }) is True


def test_contradiction_and_placeholder_filters():
    from app.generation.grounding import is_placeholder_text, sanitize_action_steps
    from app.generation.rag import _resolve_food_image_key

    # Placeholder détecté et filtré
    assert is_placeholder_text("1 à 3 repères d'hygiène de vie (sommeil régulier, hydratation, modération alcool)") is True
    assert sanitize_action_steps(["1 à 3 repères d'hygiène de vie (sommeil régulier)"]) == []

    # Contradiction sur paramètre normal rejetée
    hgb_norm = parameter_from_dict(
        analyze_parameters(
            [{
                "code": "HGB",
                "name_printed": "Hémoglobine",
                "value": 13.3,
                "unit": "g/dL",
                "reference_min": 12.0,
                "reference_max": 15.5,
                "raw_line": "Hémoglobine 13,3 g/dL (12 - 15,5)",
            }]
        )[0]
    )
    passage = RetrievedPassage(
        passage_id="ameli-nfs#001",
        source=Source(
            source_id="ameli-hemogramme-2025",
            title="Hémogramme",
            organisme="Assurance Maladie",
            url="https://www.ameli.fr/",
            date="2025-01-20",
        ),
        excerpt="L'hémoglobine transporte l'oxygène dans le sang.",
        score=0.9,
    )
    bad_exp = ParameterExplanation(
        code="HGB",
        status=ExplanationStatus.grounded,
        text="L'hémoglobine transporte l'oxygène mais ce taux suggère une anémie ou une carence en fer.",
        source_ids=["ameli-hemogramme-2025"],
    )
    assert check_explanation_grounding(bad_exp, hgb_norm, [passage]).is_grounded is False

    # Images alimentaires distinctes (Amandes vs Noix vs Épinards vs Lentilles vs Graines de courge + Fer héminique -> neutral)
    used: set[str] = set()
    assert _resolve_food_image_key("Amandes", "Oléagineux", "almonds_walnuts", used) == "almonds_walnuts"
    assert _resolve_food_image_key("Noix", "Cerneaux de noix", "almonds_walnuts", used) == "walnuts"
    assert _resolve_food_image_key("Épinards", "Légumes verts", "spinach", used) == "spinach"
    assert _resolve_food_image_key("Lentilles", "Légumineuses", "lentils_chickpeas", used) == "lentils_chickpeas"
    assert _resolve_food_image_key("Graines de courge", "Graines", "pumpkin_seeds", used) == "pumpkin_seeds"
    assert _resolve_food_image_key("Fer héminique", "Viandes, poissons, abats", "lentils_chickpeas", used) == "neutral"
