# Évaluation de l'extraction — LabMind

Ce dossier mesure la qualité d'extraction et d'identification des paramètres biologiques **indépendamment** du reste de l'application.

## Structure
- `documents/` : documents de test (PDF et images).
- `ground_truth/` : vérité terrain attendue au format JSON (`DocumentGroundTruth`).
- `results/` : rapports horodatés générés par `run_evaluation.py`.

## Commandes (depuis `backend/`, avec `.venv` activé)
```powershell
python scripts\generate_eval_samples.py
python scripts\run_evaluation.py