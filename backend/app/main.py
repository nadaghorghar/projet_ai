"""Point d'entrée de l'API LabMind pour uvicorn (`uvicorn app.main:app`)."""
from __future__ import annotations

import hashlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

from fastapi import FastAPI

from app.agent import AgentOrchestrator
from app.core.config import PROJECT_DIR, Settings, get_settings
from app.generation import RagExplanationGenerator
from app.generation.llm_client import LocalLLMClient, OllamaLLMClient
from app.knowledge import (
    build_passages_from_registry,
    load_sources_registry,
    validate_registry_consistency,
)
from app.knowledge.retriever import (
    FaissKnowledgeIndex,
    SentenceTransformerEmbedder,
    TextEmbedder,
)

from .api.app import create_app
from .api.store import TaskManager

logger = logging.getLogger("labmind.startup")
DEFAULT_CORPUS_DIR = PROJECT_DIR / "knowledge_corpus"
DEFAULT_INDEX_DIR = DEFAULT_CORPUS_DIR / "processed" / "index"


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _compute_corpus_fingerprint(corpus_dir: Path) -> str:
    hasher = hashlib.sha256()
    registry_path = corpus_dir / "metadata" / "sources_registry.json"
    if registry_path.is_file():
        hasher.update(registry_path.read_bytes())
    sources_dir = corpus_dir / "sources"
    if sources_dir.is_dir():
        for txt_file in sorted(sources_dir.glob("*.txt")):
            hasher.update(txt_file.name.encode("utf-8"))
            hasher.update(txt_file.read_bytes())
    return hasher.hexdigest()


def _load_knowledge_index(
    index_dir: Path,
    embedder: TextEmbedder | None = None,
) -> FaissKnowledgeIndex | None:
    passages_file = index_dir / FaissKnowledgeIndex.PASSAGES_FILENAME
    faiss_file = index_dir / FaissKnowledgeIndex.INDEX_FILENAME
    manifest_file = index_dir / "corpus.sha256"
    corpus_dir = index_dir.parents[1] if len(index_dir.parents) >= 2 else DEFAULT_CORPUS_DIR
    registry_path = corpus_dir / "metadata" / "sources_registry.json"
    sources_dir = corpus_dir / "sources"

    active_embedder: TextEmbedder | None = embedder

    # Reconstruit automatiquement l'index FAISS si absent ou si les sources ont évolué
    current_fp = _compute_corpus_fingerprint(corpus_dir) if registry_path.is_file() else ""
    saved_fp = manifest_file.read_text(encoding="utf-8").strip() if manifest_file.is_file() else ""
    needs_rebuild = (
        registry_path.is_file()
        and (
            not passages_file.is_file()
            or not faiss_file.is_file()
            or (saved_fp != current_fp and index_dir == DEFAULT_INDEX_DIR)
        )
    )

    if needs_rebuild:
        try:
            registry = load_sources_registry(registry_path)
            if not validate_registry_consistency(registry, sources_dir) and registry.collected_sources():
                passages = build_passages_from_registry(registry, sources_dir)
                active_embedder = active_embedder or SentenceTransformerEmbedder()
                index = FaissKnowledgeIndex.build(passages, active_embedder)
                index.save(index_dir)
                manifest_file.write_text(current_fp, encoding="utf-8")
                logger.info("Index FAISS reconstruit (%d passages).", len(index.passages))
                return index
        except Exception:
            logger.warning("Reconstruction automatique FAISS impossible : chargement de l'index existant.")

    if not passages_file.is_file() or not faiss_file.is_file():
        logger.info("Index FAISS absent dans %s : mode repli neutre actif.", index_dir)
        return None
    try:
        active_embedder = active_embedder or SentenceTransformerEmbedder()
        index = FaissKnowledgeIndex.load(index_dir, active_embedder)
        logger.info("Index FAISS chargé (%d passages).", len(index.passages))
        return index
    except Exception:
        logger.warning("Chargement de l'index FAISS impossible : bascule en mode repli neutre.")
        return None


def build_orchestrator_factory(
    enable_rag: bool = True,
    index_dir: Path = DEFAULT_INDEX_DIR,
    embedder: TextEmbedder | None = None,
    llm_client: LocalLLMClient | None = None,
) -> Callable[[], AgentOrchestrator]:
    """Construit la fabrique d'AgentOrchestrator pour l'API."""
    knowledge_index = _load_knowledge_index(index_dir, embedder=embedder) if enable_rag else None
    generator = (
        RagExplanationGenerator(llm_client=llm_client or OllamaLLMClient(), include_extended_sections=True)
        if knowledge_index is not None
        else None
    )

    def _factory() -> AgentOrchestrator:
        return AgentOrchestrator(
            knowledge_index=knowledge_index,
            generator=generator,
        )

    return _factory


def create_runtime_app(
    settings: Settings | None = None,
    enable_rag: bool | None = None,
    index_dir: Path = DEFAULT_INDEX_DIR,
) -> FastAPI:
    """Crée l'application FastAPI avec purge au démarrage et RAG optionnel."""
    active_settings = settings or get_settings()
    use_rag = _env_flag("LABMIND_ENABLE_RAG", True) if enable_rag is None else enable_rag

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI):
        if use_rag:
            factory = build_orchestrator_factory(
                enable_rag=True,
                index_dir=index_dir,
            )
            fastapi_app.state.task_manager.close()
            fastapi_app.state.task_manager = TaskManager(
                settings=active_settings,
                orchestrator_factory=factory,
            )
        fastapi_app.state.task_manager.purge_expired()
        try:
            yield
        finally:
            fastapi_app.state.task_manager.close()

    fastapi_app = create_app(settings=active_settings)
    fastapi_app.router.lifespan_context = lifespan
    return fastapi_app


app = create_runtime_app()
