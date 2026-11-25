# Guide de démarrage local — LabMind (`qwen2.5:3b`)

Ce guide vous permet d'installer et de lancer **LabMind** localement sur votre ordinateur (**Windows**, **macOS** ou **Linux**) avec le backend **Python FastAPI**, l'**OCR Tesseract + OpenCV**, la base documentaire **FAISS**, le modèle local **Ollama (`qwen2.5:3b`)** et le frontend **Angular 19**.

---

## 1. Prérequis système

1. **Python 3.10 à 3.12** (recommandé : Python 3.11)
2. **Node.js 20+** et **npm**
3. **Tesseract OCR** avec le pack de langue française (`fra`) :
   - **Windows** : Installez Tesseract depuis [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki). Pendant l'installation, cochez **French (`fra`)** dans *Additional language data*, puis ajoutez `C:\Program Files\Tesseract-OCR` à votre variable d'environnement `PATH` (ou configurez `TESSERACT_CMD`).
   - **macOS** : `brew install tesseract tesseract-lang`
   - **Ubuntu / Debian** : `sudo apt update && sudo apt install -y tesseract-ocr tesseract-ocr-fra`
4. **Ollama** avec le modèle **`qwen2.5:3b`** :
   - Téléchargez Ollama sur [ollama.com](https://ollama.com) puis téléchargez le modèle :
   ```bash
   ollama pull qwen2.5:3b
   ```
   - Vérifiez qu'Ollama est démarré (en arrière-plan ou via `ollama serve`) sur `http://127.0.0.1:11434`.

---

## 2. Configuration et lancement du Backend (Python FastAPI)

Ouvrez un premier terminal à la racine du projet (`projet_ai/`) :

### Windows (PowerShell)
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
$env:LABMIND_LLM_MODEL = "qwen2.5:3b"
$env:LABMIND_ENABLE_RAG = "1"
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### macOS / Linux (bash / zsh)
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
export LABMIND_LLM_MODEL="qwen2.5:3b"
export LABMIND_ENABLE_RAG="1"
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

> **Astuce FAISS :** L'index vectoriel est déjà fourni dans `knowledge_corpus/processed/index/`. Pour le reconstruire manuellement si vous ajoutez des sources :
> ```bash
> python scripts/build_knowledge_index.py
> ```

---

## 3. Configuration et lancement du Frontend (Angular 19)

Ouvrez un **second terminal** à la racine du projet :

```bash
cd frontend
npm install
npx ng serve --port 5173
```

Ouvrez ensuite votre navigateur sur : **http://127.0.0.1:5173**

> Lorsque le frontend tourne sur le port `5173` (ou `4200`), il communique automatiquement avec votre backend local FastAPI sur `http://127.0.0.1:8000/v1`.

---

## 4. Exécuter les tests automatisés (Backend)

```bash
cd backend
# Avec votre environnement virtuel (.venv) activé :
pytest -v
```
