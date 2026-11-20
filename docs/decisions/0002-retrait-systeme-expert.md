# Décision 0002 : Retrait et verrouillage anti-système-expert (18/11/2026)

## Contexte
Le prototype `Analyse (5).ipynb` contenait des listes de conseils médicaux/alimentaires prédéfinis, des questions figées par paramètre et un repli vers ces conseils en cas d'échec du LLM. La contrainte du projet interdit tout système expert ou moteur de règles médicales.

## Décisions
1. **Garde-fou AST automatisé (`backend/tests/test_no_expert_system.py`)** : analyse statique continue de `backend/app/` pour bloquer les anciens symboles (`TIPS`, `tips_for`, `doctor_questions`, etc.), les noms typiques de moteurs de règles, les conseils/prescriptions codés en dur, les tables `statut -> texte` et vérifier le `DISCLAIMER` pédagogique.
2. **Interface de génération strictement sourcée (`backend/app/generation/interface.py`)** : toute explication marquée `grounded` doit citer au moins un `source_id` présent dans les passages documentaires fournis en entrée (`find_citation_errors`).
3. **Repli honnête en cas de source insuffisante (`backend/app/generation/fallback.py`)** : `InsufficientSourcesGenerator` produit un message neutre et identique quel que soit le statut biologique (`below_reference`, `within_reference`, `above_reference`), ou mentionne le motif technique pour `not_analyzed`. Aucune information n'est inventée.
4. **Archivage en lecture seule** : `Analyse (5).ipynb` est archivé dans `docs/archive/` avec un avertissement explicite.

## Conséquences
- Avant l'Étape 3 (corpus + RAG), le backend est volontairement incapable de produire des explications médicales : il reste 100 % conforme à la règle « aucune source = aucune explication ».
- Toute future implémentation RAG/LLM devra respecter le contrat `ExplanationGenerator` et passer `test_no_expert_system.py`.