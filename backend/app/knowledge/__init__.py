"""Module de gestion du corpus documentaire et de la recherche RAG."""

from .chunker import (
    KnowledgePassage,
    build_passages_from_registry,
    chunk_source_entry,
    chunk_text,
    clean_document_text,
    load_passages_jsonl,
    save_passages_jsonl,
)
from .registry import (
    CorpusSourceEntry,
    MedicalCategory,
    SourceCollectionStatus,
    SourcesRegistry,
    load_sources_registry,
    validate_registry_consistency,
)
from .retriever import (
    DEFAULT_EMBEDDING_MODEL,
    FaissKnowledgeIndex,
    SentenceTransformerEmbedder,
    TextEmbedder,
)

__all__ = [
    "CorpusSourceEntry",
    "DEFAULT_EMBEDDING_MODEL",
    "FaissKnowledgeIndex",
    "KnowledgePassage",
    "MedicalCategory",
    "SentenceTransformerEmbedder",
    "SourceCollectionStatus",
    "SourcesRegistry",
    "TextEmbedder",
    "build_passages_from_registry",
    "chunk_source_entry",
    "chunk_text",
    "clean_document_text",
    "load_passages_jsonl",
    "load_sources_registry",
    "save_passages_jsonl",
    "validate_registry_consistency",
]