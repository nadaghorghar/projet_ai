# Décision 0004 : Architecture agentique à outils et reprise utilisateur (18/11/2026)

## Contexte
L'ancien prototype `run_agent` du notebook était un enchaînement linéaire sans état explicite ni interaction utilisateur (les cas incomplets passaient en `not_analyzed` sans poser de question).

## Décisions
1. **État explicite et traçable (`app/agent/state.py`)** : `AgentState` regroupe l'état d'extraction, les paramètres validés, les incertitudes détectées, la question en attente, les passages récupérés, les explications générées et la trace complète (`AgentStep`).
2. **Outils découplés (`app/agent/tools.py`)** : `extract_pdf_text`, `extract_ocr`, `identify_and_validate`, `request_user_confirmation`, `retrieve_knowledge`, `generate_explanations`. L'échec de `extract_pdf_text` ne déclenche plus de bascule cachée vers l'OCR : c'est l'agent qui observe et adapte son parcours.
3. **Planificateur encadré (`app/agent/planner.py`)** : `LLMAgentPlanner` permet au modèle local de sélectionner l'outil suivant parmi `available_tools(state)`, avec garde-fou déterministe `ObservationStatePlanner` et borne `max_iterations`.
4. **Boucle et reprise (`app/agent/orchestrator.py`)** : interruption propre en `waiting_for_user` sur `PendingQuestion` unique, validation des réponses (`InvalidQuestionStateError` / `InvalidAnswerError`) et reprise sur `AnswerIn`. Si l'utilisateur répond `je ne sais pas`, le paramètre reste `not_analyzed`.

## Conséquences
- Le cœur de l'agent est indépendant de FastAPI et prêt à être appelé par les futures tâches asynchrones (Étape 6).
- Le comportement adaptatif et l'historique de décisions sont démontrables et testés automatiquement.