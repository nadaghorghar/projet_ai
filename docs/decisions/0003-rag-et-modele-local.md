# Décision 0003 : Architecture RAG locale et contrôle d'ancrage (18/11/2026)

## Contexte
Machine cible : AMD Ryzen 7 4700U (CPU uniquement), 15,4 Go de RAM totale (~6,37 Go libres).
Contraintes : aucune API d'IA externe, aucun système expert, explications strictement sourcées.

## Décisions
1. **Index vectoriel local** : `faiss-cpu` (`IndexFlatIP` normalisé) avec métadonnées en JSONL (`knowledge_corpus/processed/index/`).
2. **Modèle d'embeddings** : `intfloat/multilingual-e5-small` (mesuré à ~55 ms par requête sur le CPU cible après mise en cache, Top-1 3/3 sur le jeu de test initial).
3. **LLM local quantifié** : client HTTP strictement local (`127.0.0.1` / `localhost` obligatoire) ciblant Ollama avec `qwen2.5:1.5b` (~1 Go en RAM) plutôt qu'un chargement PyTorch non quantifié.
4. **Contrôle d'ancrage (`grounding.py`)** : vérification déterministe de sécurité, de cohérence numérique et de recouvrement lexical, avec une tentative de reformulation puis repli automatique vers `InsufficientSourcesGenerator`.

## Risques restants
- Le contrôle d'ancrage actuel est lexical/numérique : la collecte complète des textes institutionnels pour les 6 catégories reste à finaliser dans `knowledge_corpus/sources/`.