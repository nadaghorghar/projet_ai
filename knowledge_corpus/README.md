# LabMind

Application web **informative** : analyse pédagogique d'un compte rendu d'analyses biologiques (PDF ou image).
LabMind ne pose aucun diagnostic et ne prescrit aucun traitement.

## Prérequis
- Python 3.10+
- Tesseract OCR avec le pack français (`tesseract --list-langs` doit afficher `fra`)
- Ollama (local) avec un modèle léger quantifié (ex. `ollama pull qwen2.5:1.5b`)
- Git

## Installation (Windows, PowerShell)
    cd backend
    python -m venv .venv
    .venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt

## Préparation de l'index documentaire (si sources modifiées)
    cd backend
    python scripts\build_knowledge_index.py

## Lancement de l'API locale (Swagger : http://127.0.0.1:8000/docs)
    cd backend
    uvicorn app.main:app --host 127.0.0.1 --port 8000

## Tests, démo et évaluation
    cd backend
    python -m pytest -v
    python scripts\demo_agent_trace.py
    python scripts\generate_eval_samples.py
    python scripts\run_evaluation.py

## Structure
    backend/app/core/            configuration (variables LABMIND_*)
    backend/app/api/             API FastAPI v1, sécurité uploads (magic bytes) et confidentialité HTTP
    backend/app/database/        modèles SQLAlchemy (9 entités), SQLite (FK ON) et purge automatique 1 h
    backend/app/report/          générateur du rapport PDF pédagogique final (ReportLab)
    backend/app/main.py          point d'entrée uvicorn et branchement RAG au démarrage
    backend/app/extraction/      PDF (texte + tableaux par page) et OCR Tesseract avec confiance
    backend/app/identification/  catalogue 6 catégories (21 paramètres), parsing et normalisation
    backend/app/validation/      contrôles techniques, seuils unilatéraux, calcul de confiance
    backend/app/knowledge/       registre des sources, découpage en passages et index FAISS
    backend/app/generation/      client Ollama local, RAG, contrôle d'ancrage et repli neutre
    backend/app/agent/           état, traces, outils, planificateur et boucle avec reprise utilisateur
    backend/app/evaluation/      métriques séparées (identification, valeur, unité, référence)
    backend/app/schemas.py       schémas Pydantic (contrat API v1)
    backend/scripts/             outils CLI (indexation, benchmark, démo agent, évaluation)
    backend/tests/               tests automatisés (AST anti-système-expert, RAG, agent, API, DB, PDF, sécurité)
    knowledge_corpus/            sources officielles, métadonnées et index vectoriel FAISS
    evaluation/                  documents de test, vérités terrain et rapports d'évaluation
    docs/                        contrat API v1, archive Colab et décisions techniques (ADR 0001 à 0009)

## État du projet (Backend/IA terminé)
Réalisé :
- Backend modulaire complet couvrant les 6 catégories (21 paramètres), strictement conforme « zéro système expert » (vérifié par analyse AST automatisée).
- RAG strictement local : FAISS + `intfloat/multilingual-e5-small` + Ollama `qwen2.5:1.5b` + contrôle d'ancrage et repli neutre explicite si source insuffisante.
- Véritable agent à états avec trace des décisions et boucle interactive `waiting_for_user`.
- `detected_categories`, `evidence.page` et `confidence` calculés et exposés dans `Task`.
- Dispositif d'évaluation séparée par champ dans `evaluation/`.
- API FastAPI v1 complète, durcie (magic bytes, UUID4, no-cache) et documentée (OpenAPI + `docs/api-contract/API_V1.md`).
- Persistance SQLite relationnelle, suppression immédiate (`DELETE`) et purge automatique après 1 h.
- Génération du rapport PDF pédagogique final avec sources citées, limites et précaution unique.

Travaux complémentaires recommandés avant soutenance :
- Collecter les fiches officielles encore en `pending_collection` dans `knowledge_corpus/metadata/sources_registry.json` (notamment ANSES pour l'hygiène de vie, Inserm/Ameli pour le fer/NFS) puis relancer `python scripts\build_knowledge_index.py`.
- Tester `evaluation/` sur de vrais comptes rendus anonymisés issus de laboratoires différents.
- Connecter le frontend de ton collègue sur `http://127.0.0.1:8000/v1` (CORS déjà configuré pour `localhost:3000` et `localhost:5173`).