"""Démonstration locale complète : Index FAISS + Ollama (qwen2.5:1.5b) + Grounding."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.generation import (  # noqa: E402
    GenerationRequest,
    OllamaLLMClient,
    RagExplanationGenerator,
)
from app.knowledge import (  # noqa: E402
    DEFAULT_EMBEDDING_MODEL,
    FaissKnowledgeIndex,
    SentenceTransformerEmbedder,
)
from app.schemas import parameter_from_dict  # noqa: E402
from app.validation.analysis import analyze_parameters  # noqa: E402


def main() -> int:
    index_dir = REPO_ROOT / "knowledge_corpus" / "processed" / "index"
    if not (index_dir / "index.faiss").is_file():
        print(
            "Index FAISS introuvable. Ajoute d'abord au moins une source dans "
            "knowledge_corpus/sources/, passe son statut à 'collected' puis lance "
            "'python scripts\\build_knowledge_index.py'."
        )
        return 1

    embedder = SentenceTransformerEmbedder(DEFAULT_EMBEDDING_MODEL)
    index = FaissKnowledgeIndex.load(index_dir, embedder)
    passages = index.search("rôle de l'hémoglobine dans le sang", top_k=3)

    raw_params = analyze_parameters(
        [
            {
                "code": "HGB",
                "name_printed": "Hémoglobine",
                "value": 10.5,
                "unit": "g/dL",
                "reference_min": 12.0,
                "reference_max": 16.0,
                "raw_line": "Hémoglobine 10,5 g/dL 12,0 - 16,0",
            }
        ]
    )
    params = [parameter_from_dict(p) for p in raw_params]

    generator = RagExplanationGenerator(OllamaLLMClient())
    result = generator.generate(GenerationRequest(parameters=params, passages=passages))
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())