# LabMind

Application web **informative** : analyse pédagogique structurée d'un compte rendu d'analyses biologiques (PDF ou image).
LabMind ne pose aucun diagnostic et ne prescrit aucun traitement.

## Prérequis

- **Python 3.10+**
- **Node.js 18+ & npm** (pour le frontend Angular)
- **Tesseract OCR** avec le pack français (`tesseract --list-langs` doit afficher `fra`)
- **Ollama** (local) avec **`qwen2.5:3b`** (recommandé pour la précision en français et le respect strict du format JSON) :
  ```bash
  ollama pull qwen2.5:3b
  ```
  > Alternatives selon votre RAM disponible : `qwen3:4b` ou `qwen2.5:7b` (si ≥ 12 Go libres) ou `qwen2.5:1.5b` (machines très modestes, moins précis).

## Calibrage du modèle et du pipeline RAG (appliqué)

- **Modèle par défaut** : `qwen2.5:3b` (surchargeable via `LABMIND_LLM_MODEL`)
- **Paramètres Ollama calibrés** : `num_ctx=4096`, `num_predict=900`, `temperature=0.15`, `top_p=0.85`, `repeat_penalty=1.12`, `timeout=120s` (`LABMIND_LLM_TIMEOUT`)
- **Ancrage & RAG** : lemmatisation française légère, seuil de recouvrement calibré (`0.18`), corpus enrichi (indices NFS, formule leucocytaire, biochimie, repères nutritionnels ANSES / Ciqual) et reconstruction automatique de l'index FAISS au démarrage si le corpus change.
- **Parser** : prise en charge des séparateurs de milliers français (`4 000 - 10 000`, `150 000 - 450 000`), bornes `Inférieur à ...` et intervalles `44 à 97`.

## Lancement étape par étape

### 1. Démarrer Ollama (local)
```bash
ollama pull qwen2.5:3b
ollama serve
```

### 2. Démarrer le Backend (FastAPI)

**Windows (PowerShell)** :
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts\build_knowledge_index.py
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Linux / macOS** :
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/build_knowledge_index.py
uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Swagger disponible sur `http://127.0.0.1:8000/docs`.

### 3. Démarrer le Frontend (Angular)
Dans un second terminal :
```bash
cd frontend
npm install
npx ng serve --port 5173
```
Ouvrez ensuite **`http://localhost:5173`**.

## Tests et évaluation

```bash
cd backend
python -m pytest -v
python scripts/demo_agent_trace.py
python scripts/run_evaluation.py
```
