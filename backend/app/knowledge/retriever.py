"""Indexation vectorielle locale (FAISS) et recherche de passages sourcés."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import faiss
import numpy as np

from app.generation.interface import RetrievedPassage

from .chunker import KnowledgePassage, load_passages_jsonl, save_passages_jsonl
from .registry import MedicalCategory

DEFAULT_EMBEDDING_MODEL = "intfloat/multilingual-e5-small"


@runtime_checkable
class TextEmbedder(Protocol):
    """Interface minimale d'un encodeur de texte vers vecteurs flottants."""

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        ...

    def embed_query(self, query: str) -> np.ndarray:
        ...


def _l2_normalize(vectors: np.ndarray) -> np.ndarray:
    arr = np.asarray(vectors, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    safe_norms = np.where(norms == 0.0, 1.0, norms)
    return arr / safe_norms


class SentenceTransformerEmbedder:
    """Wrapper SentenceTransformer adapté aux modèles CPU multilingues."""

    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self._is_e5 = "e5" in model_name.lower()
        self._model = SentenceTransformer(model_name, device="cpu")

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        prepared = [f"passage: {t}" for t in texts] if self._is_e5 else texts
        vectors = self._model.encode(
            prepared,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        prepared = f"query: {query}" if self._is_e5 else query
        vector = self._model.encode(
            [prepared],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vector, dtype=np.float32)


class FaissKnowledgeIndex:
    """Index vectoriel local persistant (FAISS IndexFlatIP + passages JSONL)."""

    INDEX_FILENAME = "index.faiss"
    PASSAGES_FILENAME = "passages.jsonl"

    def __init__(
        self,
        passages: list[KnowledgePassage],
        index: faiss.Index | None,
        embedder: TextEmbedder,
    ) -> None:
        self.passages = passages
        self.index = index
        self.embedder = embedder

    @classmethod
    def build(
        cls,
        passages: list[KnowledgePassage],
        embedder: TextEmbedder,
    ) -> FaissKnowledgeIndex:
        if not passages:
            return cls(passages=[], index=None, embedder=embedder)

        vectors = _l2_normalize(embedder.embed_documents([p.text for p in passages]))
        dimension = vectors.shape[1]
        index = faiss.IndexFlatIP(dimension)
        index.add(vectors)
        return cls(passages=list(passages), index=index, embedder=embedder)

    def save(self, index_dir: Path) -> None:
        index_dir.mkdir(parents=True, exist_ok=True)
        save_passages_jsonl(self.passages, index_dir / self.PASSAGES_FILENAME)
        if self.index is not None:
            faiss.write_index(self.index, str(index_dir / self.INDEX_FILENAME))

    @classmethod
    def load(
        cls,
        index_dir: Path,
        embedder: TextEmbedder,
    ) -> FaissKnowledgeIndex:
        passages = load_passages_jsonl(index_dir / cls.PASSAGES_FILENAME)
        index_path = index_dir / cls.INDEX_FILENAME
        index = faiss.read_index(str(index_path)) if index_path.is_file() else None
        return cls(passages=passages, index=index, embedder=embedder)

    def search(
        self,
        query: str,
        top_k: int = 5,
        categories: list[MedicalCategory] | None = None,
        min_score: float = 0.0,
    ) -> list[RetrievedPassage]:
        if not query.strip() or self.index is None or not self.passages or top_k <= 0:
            return []

        query_vec = _l2_normalize(self.embedder.embed_query(query))
        search_k = len(self.passages) if categories else min(top_k, len(self.passages))
        scores, indices = self.index.search(query_vec, search_k)

        allowed_categories = set(categories) if categories else None
        results: list[RetrievedPassage] = []

        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.passages):
                continue
            score_val = float(score)
            if score_val < min_score:
                continue

            passage = self.passages[idx]
            if allowed_categories and not allowed_categories.intersection(
                passage.categories
            ):
                continue

            results.append(passage.to_retrieved_passage(score=score_val))
            if len(results) >= top_k:
                break

        return results