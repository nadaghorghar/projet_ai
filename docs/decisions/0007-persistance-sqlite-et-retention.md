# Décision 0007 : Persistance SQLite (SQLAlchemy) et rétention 1 h (18/11/2026)

## Contexte
À l'Étape 6, les tâches vivaient en mémoire : un redémarrage effaçait les tâches en attente (`waiting_for_user`) et aucune durée de conservation n'était appliquée en base.

## Décisions
1. **SQLAlchemy + SQLite (`LABMIND_DATA_DIR/labmind.db`)** :
   - 9 tables relationnelles : `tasks`, `documents`, `extraction_results`, `parameters`, `agent_runs`, `agent_steps`, `knowledge_sources`, `retrieved_passages`, `reports`.
   - `PRAGMA foreign_keys=ON` activé à chaque connexion SQLite avec `ON DELETE CASCADE` sur les données liées aux tâches ; migration possible vers PostgreSQL via `LABMIND_DATABASE_URL`.
2. **Confidentialité et minimisation des données** :
   - Le texte brut extrait (`raw_text`, `extracted_pages`) n'est pas conservé dans le snapshot après extraction.
   - Le fichier déposé sur disque est supprimé dès que la tâche atteint `done` ou `error` (ou immédiatement via `DELETE`).
   - Aucune valeur biologique, aucun nom de paramètre et aucun nom de fichier patient n'apparaissent dans les journaux applicatifs.
3. **Rétention stricte (défaut : 1 heure / `LABMIND_RETENTION_SECONDS=3600`)** :
   - Purge automatique au démarrage de l'API, lors des nouveaux dépôts et à l'accès d'une tâche expirée, supprimant à la fois les lignes SQLite et les rapports PDF sur disque.