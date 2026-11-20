"""Catalogue technique : alias de noms, catégories et unités rencontrées.

Aucune valeur de référence médicale ici : les fourchettes proviennent
uniquement du document du laboratoire.
"""
from __future__ import annotations

CATEGORY_BY_CODE: dict[str, str] = {
    # 1. NFS
    "HGB": "NFS",
    "WBC": "NFS",
    "RBC": "NFS",
    "PLT": "NFS",
    "HCT": "NFS",
    "VGM": "NFS",
    "TCMH": "NFS",
    "CCMH": "NFS",
    "NEUT": "NFS",
    "LYMPH": "NFS",
    "MONO": "NFS",
    "EOS": "NFS",
    "BASO": "NFS",
    # 2. Bilan martial
    "FER": "Bilan martial",
    "FERR": "Bilan martial",
    "TRANSF": "Bilan martial",
    # 3. Bilan glycémique
    "GLY": "Bilan glycémique",
    "HBA1C": "Bilan glycémique",
    # 4. Bilan lipidique
    "CHOL": "Bilan lipidique",
    "HDL": "Bilan lipidique",
    "LDL": "Bilan lipidique",
    "TG": "Bilan lipidique",
    # 5. Bilan hépatique
    "ALAT": "Bilan hépatique",
    "ASAT": "Bilan hépatique",
    "GGT": "Bilan hépatique",
    "BILI": "Bilan hépatique",
    # 6. Bilan rénal
    "CREAT": "Bilan rénal",
    "UREE": "Bilan rénal",
    "DFG": "Bilan rénal",
    "URIC": "Bilan rénal",
    # 7. Bilan minéral
    "CA": "Bilan minéral",
    "MG": "Bilan minéral",
}

ALIASES: dict[str, list[str]] = {
    # NFS
    "HGB": ["Hémoglobine", "HGB", "Hb"],
    "WBC": ["Leucocytes totaux", "Globules blancs", "Leucocytes", "WBC"],
    "RBC": ["Hématies (Globules rouges)", "Globules rouges", "Hématies", "RBC"],
    "PLT": ["Plaquettes", "Numération plaquettaire", "PLT"],
    "HCT": ["Hématocrite", "HCT"],
    "VGM": ["Volume globulaire moyen", "V.G.M.", "VGM", "MCV"],
    "TCMH": ["Teneur corpusculaire moyenne en hémoglobine", "T.C.M.H.", "TCMH", "MCH"],
    "CCMH": ["Concentration corpusculaire moyenne en hémoglobine", "C.C.M.H.", "CCMH", "MCHC"],
    "NEUT": ["Polynucléaires neutrophiles", "Neutrophiles", "PNN"],
    "LYMPH": ["Lymphocytes"],
    "MONO": ["Monocytes"],
    "EOS": ["Polynucléaires éosinophiles", "Éosinophiles", "Eosinophiles", "PNE"],
    "BASO": ["Polynucléaires basophiles", "Basophiles", "PNB"],
    # Bilan martial
    "FER": ["Fer sérique", "Sidéremie", "Sidérémie", "Fer"],
    "FERR": ["Ferritine", "Ferritinémie"],
    "TRANSF": ["Transferrine", "Sidérophiline"],
    # Bilan glycémique
    "GLY": ["Glycémie à jeûn", "Glycémie à jeun", "Glycémie", "Glucose"],
    "HBA1C": [
        "Hémoglobine glycosylée (HbA1c)",
        "Hémoglobine glycosylée",
        "Hémoglobine glyquée (HbA1c)",
        "Hémoglobine glyquée",
        "HbA1c",
        "HbA1C",
    ],
    # Bilan lipidique
    "CHOL": ["Cholestérol total", "Cholestérol"],
    "HDL": ["Cholestérol HDL", "HDL-cholestérol", "HDL"],
    "LDL": ["Cholestérol LDL", "LDL-cholestérol", "LDL"],
    "TG": ["Triglycérides", "TG"],
    # Bilan hépatique
    "ALAT": ["ALAT (TGP)", "ALAT (GPT)", "Alanine aminotransférase", "ALAT", "TGP", "GPT"],
    "ASAT": ["ASAT (TGO)", "ASAT (GOT)", "Aspartate aminotransférase", "ASAT", "TGO", "GOT"],
    "GGT": ["Gamma-GT", "Gamma GT", "Gamma-glutamyl transférase", "GGT"],
    "BILI": ["Bilirubine totale", "Bilirubine"],
    # Bilan rénal
    "CREAT": ["Créatinine sérique", "Créatininémie", "Créatinine", "CREAT"],
    "UREE": ["Urée sanguine", "Urée", "Azotémie"],
    "DFG": ["DFG estimé (CKD-EPI)", "DFG (CKD-EPI)", "Débit de filtration glomérulaire", "DFG", "eDFG"],
    "URIC": ["Acide urique sérique", "Acide urique", "Uricémie"],
    # Bilan minéral
    "CA": ["Calcium sérique", "Calcium plasmatique", "Calcium", "Calcémie"],
    "MG": [
        "Magnésium plasmatique",
        "Magnésium sérique",
        "Magnésium érythrocytaire",
        "Magnésium",
        "Magnésémie",
    ],
}

KNOWN_UNITS: list[str] = [
    "g/dL",
    "g/L",
    "mg/dL",
    "mg/L",
    "µg/dL",
    "µg/L",
    "ng/mL",
    "µmol/L",
    "mmol/L",
    "mmol/mol",
    "%",
    "fL",
    "pg",
    "10^3/µL",
    "10^6/µL",
    "Millions/mm³",
    "/mm³",
    "U/L",
    "UI/L",
    "mL/min/1.73m²",
    "mL/min",
]

# Unités acceptées par paramètre (validation technique du format, pas d'interprétation)
ACCEPTED_UNITS: dict[str, list[str]] = {
    "HGB": ["g/dL", "g/L"],
    "WBC": ["10^3/µL", "/mm³"],
    "RBC": ["10^6/µL", "Millions/mm³"],
    "PLT": ["10^3/µL", "/mm³"],
    "HCT": ["%"],
    "VGM": ["fL"],
    "TCMH": ["pg"],
    "CCMH": ["g/dL", "g/L", "%"],
    "NEUT": ["/mm³", "10^3/µL", "%"],
    "LYMPH": ["/mm³", "10^3/µL", "%"],
    "MONO": ["/mm³", "10^3/µL", "%"],
    "EOS": ["/mm³", "10^3/µL", "%"],
    "BASO": ["/mm³", "10^3/µL", "%"],
    "FER": ["µmol/L", "mg/L", "µg/dL"],
    "FERR": ["ng/mL", "µg/L"],
    "TRANSF": ["g/L", "mg/dL"],
    "GLY": ["g/L", "mg/dL", "mmol/L"],
    "HBA1C": ["%", "mmol/mol"],
    "CHOL": ["g/L", "mg/dL", "mmol/L"],
    "HDL": ["g/L", "mg/dL", "mmol/L"],
    "LDL": ["g/L", "mg/dL", "mmol/L"],
    "TG": ["g/L", "mg/dL", "mmol/L"],
    "ALAT": ["U/L", "UI/L"],
    "ASAT": ["U/L", "UI/L"],
    "GGT": ["U/L", "UI/L"],
    "BILI": ["mg/L", "mg/dL", "µmol/L"],
    "CREAT": ["mg/L", "mg/dL", "µmol/L"],
    "UREE": ["g/L", "mmol/L", "mg/dL"],
    "DFG": ["mL/min/1.73m²", "mL/min"],
    "URIC": ["µmol/L", "mg/L", "mg/dL"],
    "CA": ["mg/L", "mg/dL", "mmol/L"],
    "MG": ["mg/L", "mg/dL", "mmol/L"],
}


def get_categories_for_codes(codes: list[str]) -> list[str]:
    """Retourne les catégories uniques détectées, dans l'ordre d'apparition."""
    categories: list[str] = []
    for code in codes:
        cat = CATEGORY_BY_CODE.get(code)
        if cat and cat not in categories:
            categories.append(cat)
    return categories