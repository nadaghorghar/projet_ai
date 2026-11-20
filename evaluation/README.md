# Évaluation de l'extraction LabMind

Ce dossier regroupe les documents de test, leurs vérités terrain et les rapports mesurés.

## Structure
- `documents/` : comptes rendus PDF et images (`.pdf`, `.png`, `.jpg`).
- `ground_truth/` : fichiers JSON attendus (un fichier `<doc_id>.json` par document).
- `results/` : rapports horodatés générés par `backend/scripts/run_evaluation.py`.

## Règle de rigueur
- Les fichiers générés par `generate_eval_samples.py` portent `source_type = "synthetic_varied"` : ils mesurent la robustesse sur des formats variés des 6 catégories, **pas** la performance finale sur de vrais comptes rendus hospitaliers.
- Pour l'évaluation finale de soutenance, ajouter des comptes rendus publics ou strictement anonymisés (`source_type = "public_anonymized"`) dans `documents/` avec leur JSON dans `ground_truth/`, puis relancer `run_evaluation.py`.