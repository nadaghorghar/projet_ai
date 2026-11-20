from app.generation.interface import RetrievedPassage
from app.knowledge import (
    CorpusSourceEntry,
    MedicalCategory,
    SourceCollectionStatus,
    SourcesRegistry,
    build_passages_from_registry,
    chunk_text,
    clean_document_text,
    load_passages_jsonl,
    save_passages_jsonl,
)


def test_clean_document_text_normalizes_whitespace_and_paragraphs():
    raw = "Ligne 1   avec   espaces.\r\n\r\n\r\n   Ligne 2\tici.\r\n"
    cleaned = clean_document_text(raw)
    assert cleaned == "Ligne 1 avec espaces.\n\nLigne 2 ici."


def test_chunk_text_respects_max_chars_and_overlap():
    text = "\n\n".join(
        [
            "Paragraphe un sur la numération formule sanguine et ses composants.",
            "Paragraphe deux sur la méthodologie de prélèvement au laboratoire.",
            "Paragraphe trois sur la présentation des intervalles de référence.",
        ]
    )
    chunks = chunk_text(text, max_chars=90, overlap_chars=30)

    assert len(chunks) >= 2
    assert all(len(c) <= 90 for c in chunks)
    assert "méthodologie" in chunks[1]


def test_chunk_text_handles_oversized_single_word_without_infinite_loop():
    chunks = chunk_text("A" * 250, max_chars=80, overlap_chars=10)
    assert len(chunks) >= 3
    assert all(len(c) <= 80 for c in chunks)


def test_build_passages_from_registry_and_jsonl_roundtrip(tmp_path):
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    (sources_dir / "doc_nfs.txt").write_text(
        "L'hémogramme mesure les cellules du sang.\n\nLes plaquettes participent à la coagulation.",
        encoding="utf-8",
    )

    collected_entry = CorpusSourceEntry(
        source_id="ameli-nfs-2025",
        title="Comprendre l'hémogramme",
        organisme="Assurance Maladie",
        url="https://www.ameli.fr/assure/sante/examen/hemogramme",
        published_date="2025-01-20",
        categories=[MedicalCategory.nfs],
        themes=["hemoglobine", "plaquettes"],
        reuse_conditions="Usage pédagogique cité",
        local_filename="doc_nfs.txt",
        status=SourceCollectionStatus.collected,
    )
    pending_entry = CorpusSourceEntry(
        source_id="plan-futur",
        title="Bilan futur",
        organisme="HAS",
        url="https://www.has-sante.fr/",
        categories=[MedicalCategory.bilan_renal],
        reuse_conditions="À vérifier",
        status=SourceCollectionStatus.pending_collection,
    )

    registry = SourcesRegistry(version="1.0", sources=[collected_entry, pending_entry])
    passages = build_passages_from_registry(
        registry, sources_dir, max_chars=80, overlap_chars=15
    )

    assert len(passages) >= 2
    assert all(p.source_id == "ameli-nfs-2025" for p in passages)

    jsonl_path = tmp_path / "processed" / "passages.jsonl"
    save_passages_jsonl(passages, jsonl_path)
    reloaded = load_passages_jsonl(jsonl_path)
    assert reloaded == passages

    retrieved = reloaded[0].to_retrieved_passage(score=0.88)
    assert isinstance(retrieved, RetrievedPassage)
    assert retrieved.source.source_id == "ameli-nfs-2025"
    assert retrieved.score == 0.88