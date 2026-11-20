# Décision 0006 : API FastAPI v1, cycle des tâches et sécurité des erreurs (18/11/2026)

## Contexte
Le contrat `docs/api-contract/API_V1.md` définit 6 endpoints pour le frontend : dépôt asynchrone, suivi par polling, réponse à une question de l'agent, téléchargement PDF et suppression immédiate.

## Décisions
1. **Architecture FastAPI modulaire** (`backend/app/api/` + `backend/app/main.py`) :
   - `POST /v1/tasks` valide extension (`.pdf`, `.png`, `.jpg`, `.jpeg` -> HTTP 415) et taille maximale (HTTP 413), enregistre sous un identifiant `UUID4` sans jamais réutiliser le nom utilisateur sur disque, renvoie HTTP 202 et lance l'agent en tâche de fond.
   - `GET /v1/tasks/{task_id}` expose l'objet `Task` complet (incluant `detected_categories`, `confidence`, `evidence.page`, `pending_question`).
   - `POST /v1/tasks/{task_id}/answer` mappe `InvalidQuestionStateError` -> HTTP 409 (`invalid_state`) et `InvalidAnswerError` -> HTTP 422 (`invalid_answer`).
   - `GET /v1/tasks/{task_id}/report.pdf` exige l'état `done` (HTTP 409 sinon) et sert actuellement un PDF technique provisoire avant le générateur ReportLab complet (Étape 8).
   - `DELETE /v1/tasks/{task_id}` supprime immédiatement la tâche, le fichier uploadé et le PDF généré (HTTP 204).
2. **Confidentialité et erreurs uniformes** (`ErrorResponse`) : aucun nom de paramètre biologique, valeur extraite ou extrait de texte n'apparaît dans les réponses d'erreur HTTP ni dans les journaux (`task_id` uniquement).
3. **Chargement RAG au démarrage (`lifespan`)** : si `knowledge_corpus/processed/` existe, l'API branche FAISS + `OllamaLLMClient` ; sinon elle démarre proprement en mode repli neutre.

## Limite connue (prochaine étape)
- Les tâches sont stockées en mémoire (`TaskManager`) : un redémarrage du serveur les efface et aucune expiration automatique à 1 h n'est encore persistée. Cela sera traité à l'Étape 7 (base SQLite + nettoyage programmé).