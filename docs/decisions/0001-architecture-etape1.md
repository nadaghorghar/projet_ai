# Décision 0001 : modularisation et contrat d'abord (17/11/2026)

## Contexte
Le prototype était un notebook Colab. L'équipe frontend doit travailler en parallèle.

## Décisions
1. Backend Python modulaire (extraction / identification / validation) ; logique du notebook conservée telle quelle.
2. Configuration par variables d'environnement (aucun chemin codé en dur).
3. `accepted_units` séparé du contenu médical : c'est de la validation de format, pas de l'interprétation.
4. Contrat API v1 écrit avant les endpoints ; traitement asynchrone avec polling et état `waiting_for_user`.
5. Champs non calculés (`confidence`, `evidence.page`) exposés à `null` plutôt qu'inventés.
6. Le contenu médical figé du notebook n'est PAS migré : il contredit la contrainte « aucun système expert » et sera remplacé par un RAG.

## Conséquences
- Le dépôt actuel ne génère aucun conseil : c'est normal et voulu.
- La comparaison valeur / fourchette du laboratoire est conservée (contrôle arithmétique, pas une interprétation).