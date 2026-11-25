# LabMind — Assistant pédagogique d'interprétation de bilans biologiques

LabMind est une application web **informative et pédagogique** permettant à tout visiteur, **sans création de compte ni authentification**, de déposer un compte rendu d'analyses biologiques (PDF ou image) et d'obtenir un rapport structuré, sourcé et compréhensible.

> **Avertissement médical** : LabMind est un outil pédagogique qui ne pose aucun diagnostic, ne remplace jamais une consultation médicale et ne prescrit aucun traitement.

---

## 1. Présentation du projet et objectifs

Les comptes rendus de laboratoire sont souvent techniques (abréviations, unités multiples, intervalles de référence). LabMind transforme ces documents en un rapport structuré comprenant :
- la mise en regard de chaque résultat avec la fourchette du laboratoire ;
- l'évolution arithmétique neutre lorsqu'une valeur antérieure comparable figure sur le document ;
- la détection des limites de lecture et des écarts arithmétiques marqués nécessitant une vigilance ;
- des explications pédagogiques rédigées **localement** par un modèle de langage pré-entraîné ancré (RAG) dans des sources médicales officielles ;
- des repères généraux d'alimentation et d'hygiène de vie issus de références institutionnelles ;
- des questions ciblées pour préparer la consultation médicale ;
- un export PDF téléchargeable.

---

## 2. Architecture globale du système

```text
[Navigateur Angular 19]  <── HTTP REST (/v1/tasks) ──>  [Backend FastAPI]
   • Accueil + aperçu                                       • Validation & sécurité upload
   • Suivi 4 étapes                                         • AgentOrchestrator (état persistant SQLite)
   • Vérification interactive                               ├── PDF / OCR multi-passes (PyMuPDF, pdfplumber, Tesseract)
   • Rapport + PDF + suppression                            ├── Identification & validation technique (zéro diagnostic)
                                                            ├── Recherche vectorielle FAISS (multilingual-e5-small)
                                                            ├── LLM local Ollama (qwen2.5:3b) + vérif. d'ancrage
                                                            └── Génération PDF (ReportLab) + purge auto 1h
```

---

## 3. Choix technologiques et justification

| Couche | Technologie | Justification |
| :--- | :--- | :--- |
| **Backend API** | Python 3.10+, FastAPI, Pydantic v2, SQLAlchemy (SQLite) | Typage strict des schémas biologiques, gestion asynchrone des tâches et persistance légère sans serveur SQL externe requis. |
| **Extraction & OCR** | PyMuPDF (`fitz`), `pdfplumber`, OpenCV, `pytesseract` | Extraction directe sur PDF natifs et pipeline OCR multi-passes (CLAHE, `--psm 4/6`, regroupement Y, correction rotation) pour photos de téléphone. |
| **Recherche documentaire (RAG)** | FAISS (`IndexFlatIP`) + `intfloat/multilingual-e5-small` | Recherche sémantique locale 100 % hors-ligne et multilingue (français/anglais) avec réindexation automatique (`corpus.sha256`). |
| **Modèle de langage local** | Ollama (`qwen2.5:3b` par défaut) | Exécution locale souveraine (`127.0.0.1:11434`), respect fiable du format JSON et qualité rédactionnelle en français sur CPU/RAM standard. |
| **Frontend Web** | Angular 19 (composants standalone, TypeScript) | Interface réactive sans authentification, aperçu immédiat du fichier, suivi de progression et rendu clair par sections biologiques. |
| **Export PDF** | ReportLab | Génération déterministe de rapports A4 multi-sections avec polices Unicode accentuées et encadré d'avertissement. |

---

## 4. Absence de système expert et d'API d'IA externe

- **Zéro système expert** : aucune règle médicale `IF/THEN` codée en dur, aucun arbre de décision diagnostique, aucun dictionnaire statique associant un statut biologique à un conseil ou une pathologie. Le module `backend/tests/test_no_expert_system.py` analyse statiquement (AST) l'ensemble de `backend/app/` pour garantir cette contrainte.
- **Zéro API d'IA externe** : aucune dépendance ni appel vers OpenAI, Gemini, Claude ou un service cloud tiers. `OllamaLLMClient` bloque par défaut toute URL non locale (`127.0.0.1` / `localhost`), sauf surcharge explicite via `LABMIND_ALLOW_REMOTE_LLM=true`.
- **Aucun entraînement depuis zéro** : LabMind exploite le modèle pré-entraîné local `qwen2.5:3b`, optimisé par ingénierie de prompt, base documentaire RAG vérifiée et contrôle d'ancrage lexical/numérique (`grounding.py`).

---

## 5. Sources documentaires médicales et traçabilité

Toutes les connaissances médicales sont stockées dans `knowledge_corpus/sources/` et indexées par `knowledge_corpus/metadata/sources_registry.json` (`status: "collected"`, URL et date vérifiables) :

- **MedlinePlus (NIH)** (`medlineplus_niddk_ada_lab_tests.txt`) : rôle des paramètres biologiques, limites d'interprétation des intervalles de référence, variabilité inter-laboratoires.
- **NIDDK (NIH)** (`medlineplus_niddk_ada_lab_tests.txt`) : glycémie à jeun, HbA1c, nécessité de confirmation médicale.
- **American Diabetes Association (ADA)** (`medlineplus_niddk_ada_lab_tests.txt`) : précautions de suivi glycémique et facteurs d'influence analytiques.
- **Organisation mondiale de la Santé (OMS / WHO)** (`oms_has_nutrition_suivi.txt`) : repères nutritionnels généraux, équilibre alimentaire, hydratation et activité physique.
- **Haute Autorité de Santé (HAS)** (`oms_has_nutrition_suivi.txt`) : parcours de soins, prise en compte du contexte clinique global, comparaison aux bilans antérieurs et signes nécessitant un avis médical rapide.
- **Assurance Maladie (ameli.fr)** & **ANSES** (`ameli_*.txt`, `anses_*.txt`) : hémogramme, biochimie sanguine, prise de sang et repères nutritionnels en population française.

---

## 6. Prérequis matériels et logiciels

- **Système** : Windows 10/11, Linux ou macOS.
- **RAM recommandée** : 8 Go minimum (12–16 Go recommandés avec `qwen2.5:3b` + embedder `e5-small`).
- **Logiciels requis** :
  - Python **3.10+**
  - Node.js **18+** et `npm`
  - **Tesseract OCR** avec le pack linguistique français (`fra`) — vérifiable via `tesseract --list-langs`
  - **Ollama** installé localement (`https://ollama.com`)

---

## 7. Variables d'environnement et configuration

Aucune clé secrète ni variable d'API cloud n'est nécessaire. Variables optionnelles (préfixe `LABMIND_`) :

| Variable | Valeur par défaut | Rôle |
| :--- | :--- | :--- |
| `LABMIND_LLM_MODEL` | `qwen2.5:3b` | Modèle Ollama utilisé pour la rédaction pédagogique |
| `LABMIND_OLLAMA_URL` | `http://127.0.0.1:11434` | Point d'accès local Ollama |
| `LABMIND_LLM_TIMEOUT` | `120.0` | Délai maximal par requête LLM (secondes) |
| `LABMIND_ENABLE_RAG` | `true` | Active/désactive l'index FAISS + LLM (repli neutre si `false`) |
| `LABMIND_RETENTION_SECONDS` | `3600` | Durée de conservation des résultats avant purge automatique (1h) |
| `LABMIND_TESSERACT_CMD` | Auto-détecté | Chemin explicite vers `tesseract.exe` sous Windows |
| `LABMIND_OCR_LANG` | `fra` | Langue Tesseract utilisée pour l'OCR |
| `LABMIND_MAX_UPLOAD_BYTES` | `10000000` | Taille maximale d'import (10 Mo) |

---

## 8. Installation étape par étape

### Étape 1 — Installer et préparer Ollama + Qwen
```bash
ollama pull qwen2.5:3b
ollama serve
```
*(Sur machine modeste < 8 Go de RAM libre, vous pouvez définir `LABMIND_LLM_MODEL=qwen2.5:1.5b`.)*

### Étape 2 — Installer le Backend FastAPI
**Windows (PowerShell) :**
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts\build_knowledge_index.py
```

**Linux / macOS :**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/build_knowledge_index.py
```

### Étape 3 — Installer le Frontend Angular
```bash
cd frontend
npm install
```

---

## 9. Lancement du projet (Backend, Frontend et Modèle local)

Ouvrez trois terminaux (ou gardez `ollama serve` actif en arrière-plan) :

1. **Modèle local Ollama** : `ollama serve` (écoute sur `http://127.0.0.1:11434`).
2. **Backend FastAPI** (depuis `backend/` avec `.venv` activé) :
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
   Documentation interactive OpenAPI : `http://127.0.0.1:8000/docs`.
3. **Frontend Angular** (depuis `frontend/`) :
   ```bash
   npx ng serve --port 5173
   ```
   Ouvrez ensuite **`http://localhost:5173`** dans votre navigateur.

---

## 10. Guide d'utilisation pas à pas

1. **Dépôt direct** : accédez à `http://localhost:5173` sans inscription ni connexion, puis glissez-déposez un bilan PDF ou une photo (PNG/JPG ≤ 10 Mo). Vérifiez l'aperçu du fichier avant de lancer l'analyse.
2. **Traitement en direct** : observez l'avancement des 4 étapes (extraction/OCR, validation technique, recherche documentaire, rédaction locale).
3. **Vérification éventuelle** : si une unité ou une valeur est illisible sur le document, LabMind vous demande confirmation sans jamais deviner.
4. **Consultation du rapport** : explorez le rapport harmonisé en 8 sections (résumé général, tableaux de résultats avec statuts, explications concises des anomalies et paramètres, conseils alimentaires illustrés par 8 visuels distincts, activité physique et habitudes de vie, suivi médical recommandé, questions pour le médecin, sources médicales officielles).
5. **Export et effacement** : téléchargez le rapport au format PDF ou cliquez sur *Supprimer mes données maintenant* (sinon purge automatique sous 1 heure).

---

## 11. Tests, validation et évaluation

Depuis `backend/` (avec `.venv` activé) :
```bash
python -m pytest -v
python scripts/demo_agent_trace.py
python scripts/run_evaluation.py
```
Les tests couvrent notamment :
- l'absence stricte de système expert (`tests/test_no_expert_system.py`) ;
- la cohérence du registre documentaire (`tests/test_knowledge_registry.py`) ;
- l'extraction PDF/OCR multi-passes et le parseur multi-format (`tests/test_extraction.py`, `tests/test_identification.py`, `tests/test_audit_final_suite.py`) ;
- l'ancrage RAG, la détection des citations inventées et les comparaisons antérieures (`tests/test_generation_rag.py`, `tests/test_audit_final_suite.py`) ;
- le cycle complet API, la sécurité d'upload et la génération PDF (`tests/test_api.py`, `tests/test_report_pdf.py`).

---

## 12. Limites connues et précautions d'usage

- **Qualité OCR** : une photo floue, sous-exposée ou prise de biais peut omettre des lignes ou altérer des unités ; LabMind privilégie alors la demande de confirmation ou signale l'incertitude plutôt que d'inventer une valeur.
- **Comparaison antérieure** : si les unités diffèrent entre deux bilans ou si les conditions de prélèvement sont inconnues, LabMind refuse la comparaison arithmétique directe (`Non comparable`).
- **Performances CPU** : la génération locale par `qwen2.5:3b` sur processeur sans GPU dédié peut prendre de 20 à 90 secondes selon le nombre de paramètres extraits.
- **Usage strictement informatif** : en présence de symptômes aigus ou d'un écart biologique important, consultez un médecin sans attendre.
