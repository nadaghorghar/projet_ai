import numpy as np

from app.knowledge import (
    FaissKnowledgeIndex,
    KnowledgePassage,
    MedicalCategory,
)


class _KeywordToyEmbedder:
    """Encodeur déterministe hors-ligne pour tester l'index FAISS sans réseau."""

    KEYWORDS = (
        "hémoglobine",
        "glycémie",
        "créatinine",
        "cholestérol",
    )

    def _encode(self, text: str) -> np.ndarray:
        lower = text.lower()
        return np.array(
            [1.0 if kw in lower else 0.0 for kw in self.KEYWORDS],
            dtype=np.float32,
        )

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.vstack([self._encode(t) for t in texts])

    def embed_query(self, query: str) -> np.ndarray:
        return self._encode(query)


def _sample_passages() -> list[KnowledgePassage]:
    return [
        KnowledgePassage(
            passage_id="src-nfs#001",
            source_id="src-nfs",
            title="Hémogramme",
            organisme="Inserm",
            url="https://www.inserm.fr/dossier/hemogramme",
            published_date="2025-01-01",
            categories=[MedicalCategory.nfs],
            text="L'hémoglobine est une protéine des globules rouges.",
        ),
        KnowledgePassage(
            passage_id="src-gly#001",
            source_id="src-gly",
            title="Glycémie",
            organisme="Ameli",
            url="https://www.ameli.fr/assure/sante/glycemie",
            published_date="2025-01-02",
            categories=[MedicalCategory.bilan_glycemique],
            text="La glycémie mesure le glucose sanguin.",
        ),
        KnowledgePassage(
            passage_id="src-renal#001",
            source_id="src-renal",
            title="Fonction rénale",
            organisme="HAS",
            url="https://www.has-sante.fr/jcms/p_001/fr/mrc",
            published_date="2025-01-03",
            categories=[MedicalCategory.bilan_renal],
            text="La créatinine permet d'évaluer la filtration des reins.",
        ),
    ]


def test_faiss_index_build_save_load_and_search(tmp_path):
    embedder = _KeywordToyEmbedder()
    passages = _sample_passages()

    index = FaissKnowledgeIndex.build(passages, embedder)
    save_dir = tmp_path / "index"
    index.save(save_dir)

    reloaded = FaissKnowledgeIndex.load(save_dir, embedder)
    results = reloaded.search("Quel est le rôle de la créatinine ?", top_k=2)

    assert len(results) >= 1
    assert results[0].passage_id == "src-renal#001"
    assert results[0].source.source_id == "src-renal"
    assert results[0].score == 1.0


def test_faiss_index_filters_by_category():
    embedder = _KeywordToyEmbedder()
    passages = _sample_passages()
    index = FaissKnowledgeIndex.build(passages, embedder)

    results = index.search(
        "créatinine",
        top_k=3,
        categories=[MedicalCategory.nfs],
        min_score=0.5,
    )
    assert results == []


def test_faiss_index_handles_empty_corpus():
    embedder = _KeywordToyEmbedder()
    index = FaissKnowledgeIndex.build([], embedder)
    assert index.search("hémoglobine") == []