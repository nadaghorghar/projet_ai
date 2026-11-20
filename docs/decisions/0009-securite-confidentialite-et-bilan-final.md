# Décision 0009 : Sécurité, confidentialité et bilan final backend/IA (18/11/2026)

## Contexte
Avant l'intégration finale avec le frontend et la soutenance, il fallait durcir la validation des fichiers entrants, verrouiller la confidentialité HTTP et dresser le bilan honnête de la couverture documentaire.

## Décisions
1. **Validation binaire des uploads (`backend/app/api/security.py`)** :
   - Contrôle d'extension (`.pdf`, `.png`, `.jpg`, `.jpeg`), taille maximale (10 Mo par défaut), signatures *magic bytes* (`%PDF-`, PNG, JPEG) et vérification d'intégrité Pillow sur les images.
   - Rejet de tout `task_id` non UUID4 aux bornes HTTP (`404 task_not_found`) pour empêcher tout *path traversal*.
   - Gestionnaire d'erreurs unifié au format `ErrorResponse` sans fuite de données médicales ni de traces techniques.
2. **Confidentialité HTTP** : en-têtes `Cache-Control: no-store...`, `Pragma: no-cache`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` et `Referrer-Policy: no-referrer` ajoutés sur toutes les réponses.
3. **État honnête du corpus (`knowledge_corpus/`)** :
   - La fiche officielle Assurance Maladie (`ameli-prise-sang-2026`) est collectée et indexée dans FAISS (`15 passages`) ; aucune source n'a été inventée.
   - Les fiches complémentaires (`Inserm`, `HAS`, `ANSES` hygiène de vie) restent en `pending_collection` dans `sources_registry.json` et peuvent être ajoutées sans modifier une ligne de code applicative via `python scripts\build_knowledge_index.py`.