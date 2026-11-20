

```markdown
# Décision 0005 : Catalogue 6 catégories, extraction par page/confiance et évaluation (18/11/2026)

## Contexte
La version initiale ne couvrait que 10 paramètres (principalement NFS, glycémie, lipides), concaténait toutes les pages sans numéro de page, laissait `confidence` à `null` et n'avait pas de script d'évaluation out-of-the-box.

## Décisions
1. **Extension du catalogue à 6 catégories / 21 paramètres** (`backend/app/identification/catalog.py`) :
   - NFS (`HGB`, `WBC`, `RBC`, `PLT`, `HCT`)
   - Bilan martial (`FER`, `FERR`, `TRANSF`)
   - Bilan glycémique (`GLY`, `HBA1C`)
   - Bilan lipidique (`CHOL`, `HDL`, `LDL`, `TG`)
   - Bilan hépatique (`ALAT`, `ASAT`, `GGT`, `BILI`)
   - Bilan rénal (`CREAT`, `UREE`, `DFG`)
   - Aucune valeur de référence médicale n'est codée en dur ; `detected_categories` est calculé dynamiquement à partir des paramètres extraits.
2. **Bornes unilatérales (`< max`, `> min`)** : ajoutées dans `parser.py` et `reference.py` pour supporter les seuils courants (ex. LDL, ALAT, DFG) sans inventer la borne manquante.
3. **Extraction par page + tableaux + score de confiance technique** :
   - `pdfplumber` extrait le texte et les tableaux page par page (`evidence.page`).
   - `pytesseract.image_to_data` fournit une confiance OCR moyenne utilisée pour calculer `confidence` dans `[0.0, 1.0]` (`compute_parameter_confidence`).
   - Choix matériel : sur machine CPU (16 Go RAM, pas de GPU), conservation de Tesseract + prétraitement OpenCV plutôt que l'ajout de modèles OCR lourds (PaddleOCR/docTR) ou d'une extraction par LLM.
4. **Module d'évaluation métrique** (`backend/app/evaluation/metrics.py`) : mesure séparément précision, rappel d'identification et exactitude sur valeur, unité, référence et paramètre complet.

## Limites connues
- Les 4 documents de départ (`evaluation/documents/`) sont synthétiques et donnent 100 % en local ; un jeu indépendant anonymisé devra compléter la validation avant la soutenance.