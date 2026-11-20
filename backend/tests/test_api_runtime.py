import numpy as np
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.generation import RagExplanationGenerator
from app.knowledge.chunker import KnowledgePassage
from app.knowledge.registry import MedicalCategory
from app.knowledge.retriever import FaissKnowledgeIndex
from app.main import build_orchestrator_factory, create_runtime_app


class _DummyEmbedder:
    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.ones((len(texts), 4), dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        return np.ones((1, 4), dtype=np.float32)


class _DummyLLM:
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        return '{"status": "insufficient_sources", "text": "", "source_ids": []}'


def test_orchestrator_factory_degrades_cleanly_when_index_missing(tmp_path):
    factory = build_orchestrator_factory(
        enable_rag=True,
        index_dir=tmp_path / "absent",
    )
    orch = factory()
    assert orch.knowledge_index is None
    assert orch.generator is None


def test_orchestrator_factory_wires_rag_when_index_present(tmp_path):
    passage = KnowledgePassage(
        passage_id="src-test-1#001",
        source_id="src-test-1",
        title="Source test",
        organisme="Ameli",
        url="https://www.ameli.fr/",
        published_date="2026-01-08",
        categories=[next(iter(MedicalCategory))],
        themes=["glycemie"],
        text="La glycémie mesure le taux de sucre dans le sang.",
    )
    embedder = _DummyEmbedder()
    index = FaissKnowledgeIndex.build([passage], embedder)
    index.save(tmp_path)

    factory = build_orchestrator_factory(
        enable_rag=True,
        index_dir=tmp_path,
        embedder=embedder,
        llm_client=_DummyLLM(),
    )
    orch = factory()
    assert orch.knowledge_index is not None
    assert isinstance(orch.generator, RagExplanationGenerator)


def test_runtime_app_exposes_all_v1_contract_routes_in_openapi(tmp_path):
    app = create_runtime_app(
        settings=Settings(data_dir=tmp_path / "data"),
        enable_rag=False,
    )
    with TestClient(app) as client:
        assert client.get("/v1/health").status_code == 200
        schema = client.get("/openapi.json").json()

    paths = schema["paths"]
    assert "/v1/health" in paths
    assert "/v1/tasks" in paths and "post" in paths["/v1/tasks"]
    assert "/v1/tasks/{task_id}" in paths
    assert "get" in paths["/v1/tasks/{task_id}"]
    assert "delete" in paths["/v1/tasks/{task_id}"]
    assert "/v1/tasks/{task_id}/answer" in paths and "post" in paths["/v1/tasks/{task_id}/answer"]
    assert "/v1/tasks/{task_id}/report.pdf" in paths and "get" in paths["/v1/tasks/{task_id}/report.pdf"]