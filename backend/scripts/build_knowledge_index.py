"""Script CLI : découpe les sources 'collected' et construit l'index FAISS local."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.knowledge import (  # noqa: E402
    DEFAULT_EMBEDDING_MODEL,
    FaissKnowledgeIndex,
    SentenceTransformerEmbedder,
    build_passages_from_registry,
    load_sources_registry,
    validate_registry_consistency,
)


def main() -> int:
    corpus_dir = REPO_ROOT / "knowledge_corpus"
    registry_path = corpus_dir / "metadata" / "sources_registry.json"
    sources_dir = corpus_dir / "sources"
    index_dir = corpus_dir / "processed" / "index"

    registry = load_sources_registry(registry_path)
    errors = validate_registry_consistency(registry, sources_dir)
    if errors:
        print("Erreurs de cohérence dans sources_registry.json :")
        for err in errors:
            print(" -", err)
        return 1

    collected = registry.collected_sources()
    if not collected:
        print(
            "Aucune source au statut 'collected' pour l'instant.\n"
            "Ajoute des fichiers .txt dans knowledge_corpus/sources/ et mets à jour "
            "sources_registry.json avant de construire l'index."
        )
        return 0

    passages = build_passages_from_registry(registry, sources_dir)
    print(f"{len(collected)} source(s) collectée(s) -> {len(passages)} passage(s) généré(s).")
    print(f"Chargement de l'embedder CPU ({DEFAULT_EMBEDDING_MODEL})...")

    embedder = SentenceTransformerEmbedder(DEFAULT_EMBEDDING_MODEL)
    index = FaissKnowledgeIndex.build(passages, embedder)
    index.save(index_dir)

    print(f"Index FAISS enregistré dans : {index_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())