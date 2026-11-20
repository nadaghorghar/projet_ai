# LabMind : contrat API v1

Base : `/v1`. Format : JSON (UTF-8), sauf upload (multipart) et téléchargement PDF.
Aucune authentification ni compte. L'accès à une tâche repose sur son `task_id` (UUID4).

## 1. Cycle de vie d'une tâche

received -> processing -> done
                |   ^
                v   |
         waiting_for_user      (l'agent attend une réponse, puis reprend)
                |
                +-> error       (échec non récupérable)

| État | Signification | Action du frontend |
|---|---|---|
| received | Fichier reçu, pas encore traité | Continuer le polling |
| processing | Traitement en cours | Continuer le polling (toutes les 2 s) |
| waiting_for_user | L'agent a besoin d'une réponse | Afficher `pending_question`, puis POST de la réponse |
| done | Résultat prêt | Afficher le résultat, proposer le PDF |
| error | Échec | Afficher `errors[0].message` |

## 2. Endpoints

| Méthode | Route | Rôle |
|---|---|---|
| GET | /v1/health | Vérifier que le service répond |
| POST | /v1/tasks | Déposer un document (multipart, champ `file`) -> 202 |
| GET | /v1/tasks/{task_id} | Statut et résultat courant |
| POST | /v1/tasks/{task_id}/answer | Répondre à la question en attente |
| GET | /v1/tasks/{task_id}/report.pdf | Télécharger le rapport PDF (état `done`) |
| DELETE | /v1/tasks/{task_id} | Supprimer fichier, résultats et artefacts -> 204 |

## 3. Codes HTTP

| Code | Cas | `error.code` |
|---|---|---|
| 202 | Document accepté | |
| 200 | Lecture réussie | |
| 204 | Suppression réussie | |
| 400 | Requête mal formée (champ manquant) | invalid_request |
| 404 | task_id inconnu ou déjà supprimé | task_not_found |
| 409 | Action impossible dans l'état courant (ex. réponse sans question en attente, PDF avant `done`) | invalid_state |
| 413 | Fichier trop gros (défaut 10 Mo) | file_too_large |
| 415 | Format non supporté (pdf, png, jpg, jpeg) | unsupported_format |
| 422 | Fichier illisible, ou réponse invalide à la question | unreadable_document / invalid_answer |
| 500 | Erreur interne | internal_error |

Corps d'erreur HTTP :
```json
{"error": {"code": "unsupported_format", "message": "Format non supporté (pdf, png, jpg, jpeg)."}}