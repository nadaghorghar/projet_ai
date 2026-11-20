"""Benchmark léger CPU/RAM de deux modèles d'embeddings multilingues français."""
from __future__ import annotations

import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.knowledge.chunker import KnowledgePassage  # noqa: E402
from app.knowledge.registry import MedicalCategory  # noqa: E402
from app.knowledge.retriever import FaissKnowledgeIndex, SentenceTransformerEmbedder  # noqa: E402

CANDIDATE_MODELS = [
    "intfloat/multilingual-e5-small",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
]

SAMPLE_PASSAGES = [
    KnowledgePassage(
        passage_id="bench-nfs#001",
        source_id="bench-nfs",
        title="Hémogramme",
        organisme="Benchmark",
        url="https://example.org/nfs",
        categories=[MedicalCategory.nfs],
        text="L'hémoglobine assure le transport de l'oxygène dans les globules rouges.",
    ),
    KnowledgePassage(
        passage_id="bench-gly#001",
        source_id="bench-gly",
        title="Glycémie et HbA1c",
        organisme="Benchmark",
        url="https://example.org/gly",
        categories=[MedicalCategory.bilan_glycemique],
        text="La glycémie mesure le taux de glucose dans le sang, généralement à jeun.",
    ),
    KnowledgePassage(
        passage_id="bench-renal#001",
        source_id="bench-renal",
        title="Fonction rénale",
        organisme="Benchmark",
        url="https://example.org/renal",
        categories=[MedicalCategory.bilan_renal],
        text="La créatinine sanguine permet d'estimer le débit de filtration glomérulaire des reins.",
    ),
]

TEST_QUERIES = [
    ("À quoi sert le dosage de la créatinine pour les reins ?", "bench-renal#001"),
    ("Que mesure la glycémie à jeun ?", "bench-gly#001"),
    ("Quel est le rôle de l'hémoglobine ?", "bench-nfs#001"),
]


def main() -> int:
    for model_name in CANDIDATE_MODELS:
        print(f"\n=== Modèle : {model_name} ===")
        t0 = time.perf_counter()
        embedder = SentenceTransformerEmbedder(model_name)
        load_s = time.perf_counter() - t0

        t1 = time.perf_counter()
        index = FaissKnowledgeIndex.build(SAMPLE_PASSAGES, embedder)
        index_s = time.perf_counter() - t1

        hits = 0
        t2 = time.perf_counter()
        for query, expected_id in TEST_QUERIES:
            res = index.search(query, top_k=1)
            if res and res[0].passage_id == expected_id:
                hits += 1
        query_ms = (time.perf_counter() - t2) * 1000.0 / len(TEST_QUERIES)

        print(f"Chargement : {load_s:.2f} s")
        print(f"Indexation (3 passages) : {index_s:.3f} s")
        print(f"Latence moyenne requête : {query_ms:.1f} ms")
        print(f"Précision Top-1 (test jouet) : {hits}/{len(TEST_QUERIES)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())