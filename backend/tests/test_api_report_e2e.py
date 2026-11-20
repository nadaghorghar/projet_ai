import json

import numpy as np
import pymupdf
from fastapi.testclient import TestClient

from app.agent import AgentOrchestrator
from app.api.app import create_app
from app.api.store import TaskManager
from app.core.config import Settings
from app.generation import RagExplanationGenerator
from app.knowledge.chunker import KnowledgePassage
from app.knowledge.registry import MedicalCategory
from app.knowledge.retriever import FaissKnowledgeIndex
from app.schemas import DISCLAIMER, Task, TaskStatus
from tests.helpers import render_pdf


class _FakeEmbedder:
    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.ones((len(texts), 4), dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        return np.ones((1, 4), dtype=np.float32)


class _FakeLLM:
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if "GLY" in user_prompt or "Glycémie" in user_prompt:
            return json.dumps(
                {
                    "status": "grounded",
                    "text": "La glycémie mesure le taux de sucre dans le sang pour évaluer l'équilibre glycémique.",
                    "source_ids": ["ameli-prise-sang-2026"],
                }
            )
        return json.dumps(
            {"status": "insufficient_sources", "text": "", "source_ids": []}
        )


def test_api_end_to_end_generates_real_sourced_pdf_and_cleans_up(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    passage = KnowledgePassage(
        passage_id="ameli-prise-sang-2026#001",
        source_id="ameli-prise-sang-2026",
        title="Lire les résultats d'une prise de sang",
        organisme="Assurance Maladie",
        url="https://www.ameli.fr/assure/sante/examen/analyse/lire-resultats-prise-sang",
        published_date="2026-01-08",
        categories=[next(iter(MedicalCategory))],
        themes=["glycemie"],
        text="La glycémie mesure le taux de sucre dans le sang et aide à évaluer l'équilibre glycémique.",
    )
    index = FaissKnowledgeIndex.build([passage], _FakeEmbedder())
    generator = RagExplanationGenerator(llm_client=_FakeLLM())

    manager = TaskManager(
        settings=settings,
        orchestrator_factory=lambda: AgentOrchestrator(
            knowledge_index=index,
            generator=generator,
        ),
    )
    app = create_app(settings=settings, task_manager=manager)

    pdf_input = tmp_path / "bilan_multicategories.pdf"
    render_pdf(
        pdf_input,
        "lines",
        True,
        [
            {
                "name_printed": "Hématocrite",
                "value": 42.0,
                "unit": None,
                "reference_min": 37.0,
                "reference_max": 47.0,
            },
            {
                "name_printed": "Glycémie",
                "value": 0.94,
                "unit": "g/L",
                "reference_min": 0.70,
                "reference_max": 1.10,
            },
            {
                "name_printed": "Cholestérol LDL",
                "value": 1.72,
                "unit": "g/L",
                "reference_min": 0.60,
                "reference_max": 1.60,
            },
        ],
    )

    with TestClient(app) as client:
        with pdf_input.open("rb") as fh:
            task_id = client.post(
                "/v1/tasks",
                files={"file": ("bilan_multi.pdf", fh, "application/pdf")},
            ).json()["task_id"]

        waiting = Task.model_validate(client.get(f"/v1/tasks/{task_id}").json())
        assert waiting.status == TaskStatus.waiting_for_user
        assert waiting.pending_question is not None

        done = Task.model_validate(
            client.post(
                f"/v1/tasks/{task_id}/answer",
                json={"question_id": waiting.pending_question.question_id, "answer": "%"},
            ).json()
        )
        assert done.status == TaskStatus.done
        assert sorted(done.detected_categories) == [
            "Bilan glycémique",
            "Bilan lipidique",
            "NFS",
        ]

        pdf_resp = client.get(f"/v1/tasks/{task_id}/report.pdf")
        assert pdf_resp.status_code == 200
        assert pdf_resp.headers["content-type"].startswith("application/pdf")

        with pymupdf.open(stream=pdf_resp.content, filetype="pdf") as doc:
            extracted = " ".join(
                " ".join(page.get_text("text") for page in doc).split()
            )

        assert "Glycémie" in extracted
        assert "Cholestérol LDL" in extracted
        assert "Hématocrite" in extracted
        assert "La glycémie mesure le taux de sucre dans le sang" in extracted
        assert "ameli-prise-sang-2026" in extracted
        assert "Assurance Maladie" in extracted
        assert extracted.count(DISCLAIMER) == 1

        assert client.delete(f"/v1/tasks/{task_id}").status_code == 204
        assert list(settings.reports_dir.glob("*.pdf")) == []

    manager.close()