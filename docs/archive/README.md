# Archive — Prototype initial (`Analyse (5).ipynb`)

Ce dossier contient le notebook Colab d'origine à titre de **référence historique et de documentation de travail uniquement** (lecture seule).

## Avertissement — Contenu non conforme à ne PAS réutiliser

Les éléments suivants du notebook contiennent un **système expert médical** interdit par les contraintes du projet et **ne doivent jamais être copiés dans `backend/app/`** :

- **Cellule `#9`** : tables de conseils figés (`TIPS`, `IRON_LOW`, `BLOOD_HIGH`, `SUGAR_HIGH`, `SUGAR_LOW`, `LIPID_HIGH`, `TG_HIGH`, `HDL_LOW`, `WBC_ANY`, `PLT_ANY`, `CHOL_LOW`, `DEFAULT_KNOW`, `NO_REF`), fonctions `tips_for` / `collect_tips`, descriptions médicales codées en dur (`KB["what_it_measures"]`) et questions prédéfinies (`KB["doctor_questions"]`).
- **Cellule `#11`** : mécanisme de repli de `generate_report_content` vers les conseils figés lorsque le LLM est absent ou rejeté.
- **Cellules `#13` et `#14`** : appels à `collect_tips` et `KB["doctor_questions"]` dans les démos et dans `run_agent`.

## Ce qui a été conservé et modularisé dans `backend/app/`

- Extraction PDF (`pdfplumber`) et OCR Tesseract/OpenCV → `backend/app/extraction/`
- Catalogue d'alias, unités acceptées et parsing des lignes → `backend/app/identification/`
- Validation technique des champs et comparaison arithmétique à l'intervalle du laboratoire → `backend/app/validation/`

## Protection automatisée

Le test `backend/tests/test_no_expert_system.py` analyse statiquement `backend/app/` et échoue automatiquement si l'un de ces symboles, une table `statut -> texte` ou une formulation de conseil/prescription est réintroduit.