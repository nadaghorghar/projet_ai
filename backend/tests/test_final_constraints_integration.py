import json

import numpy as np
import pymupdf
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agent import AgentOrchestrator
from app.api.app import create_app
from app.api.store import TaskManager
from app.core.config import Settings
from app.database import ParameterDB, TaskDB, create_db_engine, create_session_factory
from app.generation import RagExplanationGenerator
from app.knowledge.chunker import KnowledgePassage
from app.knowledge.registry import MedicalCategory
from app.knowledge.retriever import FaissKnowledgeIndex
from app.schemas import DISCLAIMER, ParameterStatus, Task, TaskStatus
from tests.helpers import render_pdf


class _FakeEmbedder:
    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.ones((len(texts), 4), dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        return np.ones((1, 4), dtype=np.float32)


class _SelectiveLLM:
    """Simule un LLM local sourcé sur la glycémie et prudent ailleurs."""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if "GLY" in user_prompt or "Glycémie" in user_prompt:
            return json.dumps(
                {
                    "status": "grounded",
                    "text": "La glycémie mesure le taux de sucre dans le sang.",
                    "source_ids": ["ameli-prise-sang-2026"],
                }
            )
        return json.dumps(
            {"status": "insufficient_sources", "text": "", "source_ids": []}
        )


def test_six_categories_agent_rag_pdf_and_full_deletion_e2e(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    passage = KnowledgePassage(
        passage_id="ameli-prise-sang-2026#001",
        source_id="ameli-prise-sang-2026",
        title="Comment lire les résultats d'une prise de sang ?",
        organisme="Assurance Maladie (ameli.fr)",
        url="https://www.ameli.fr/assure/sante/examen/analyse/lire-resultats-prise-sang",
        published_date="2026-01-08",
        categories=[next(iter(MedicalCategory))],
        themes=["glycemie"],
        text="La glycémie mesure le taux de sucre dans le sang lors d'une prise de sang.",
    )
    index = FaissKnowledgeIndex.build([passage], _FakeEmbedder())
    generator = RagExplanationGenerator(llm_client=_SelectiveLLM())

    manager = TaskManager(
        settings=settings,
        orchestrator_factory=lambda: AgentOrchestrator(
            knowledge_index=index,
            generator=generator,
        ),
    )
    app = create_app(settings=settings, task_manager=manager)

    pdf_input = tmp_path / "bilan_six_categories.pdf"
    render_pdf(
        pdf_input,
        "lines",
        True,
        [
            {"name_printed": "Hématocrite", "value": 42.0, "unit": None, "reference_min": 37.0, "reference_max": 47.0},
            {"name_printed": "Ferritine", "value": 24.0, "unit": "ng/mL", "reference_min": 30.0, "reference_max": 300.0},
            {"name_printed": "Glycémie", "value": 0.95, "unit": "g/L", "reference_min": 0.70, "reference_max": 1.10},
            {"name_printed": "Cholestérol LDL", "value": 1.70, "unit": "g/L", "reference_min": 0.60, "reference_max": 1.60},
            {"name_printed": "ALAT", "value": 35.0, "unit": "U/L", "reference_min": 5.0, "reference_max": 40.0},
            {"name_printed": "Créatinine", "value": 9.5, "unit": "mg/L", "reference_min": 7.0, "reference_max": 13.0},
        ],
    )

    with TestClient(app) as client:
        with pdf_input.open("rb") as fh:
            task_id = client.post(
                "/v1/tasks",
                files={"file": ("bilan_complet.pdf", fh, "application/pdf")},
            ).json()["task_id"]

        # 1. Agent en attente de confirmation (sans deviner l'unité absente)
        waiting = Task.model_validate(client.get(f"/v1/tasks/{task_id}").json())
        assert waiting.status == TaskStatus.waiting_for_user
        assert waiting.pending_question is not None
        assert waiting.pending_question.code == "HCT"

        # 2. Reprise après confirmation utilisateur
        done = Task.model_validate(
            client.post(
                f"/v1/tasks/{task_id}/answer",
                json={"question_id": waiting.pending_question.question_id, "answer": "%"},
            ).json()
        )
        assert done.status == TaskStatus.done
        assert sorted(done.detected_categories) == [
            "Bilan glycémique",
            "Bilan hépatique",
            "Bilan lipidique",
            "Bilan martial",
            "Bilan rénal",
            "NFS",
        ]
        assert done.explanations is not None
        exp_by_code = {
            e["code"]: e for e in done.explanations["parameter_explanations"]
        }
        assert exp_by_code["GLY"]["status"] == "grounded"
        assert exp_by_code["GLY"]["source_ids"] == ["ameli-prise-sang-2026"]
        assert exp_by_code["CREAT"]["status"] == "insufficient_sources"
        assert exp_by_code["CREAT"]["source_ids"] == []

        # 3. Rapport PDF final vérifié
        pdf_resp = client.get(f"/v1/tasks/{task_id}/report.pdf")
        assert pdf_resp.status_code == 200
        with pymupdf.open(stream=pdf_resp.content, filetype="pdf") as doc:
            pdf_text = " ".join(" ".join(p.get_text("text") for p in doc).split())
        assert "La glycémie mesure le taux de sucre dans le sang." in pdf_text
        assert "ameli-prise-sang-2026" in pdf_text
        assert pdf_text.count(DISCLAIMER) == 1

        # 4. Suppression définitive (API + disque + base SQLite)
        assert client.delete(f"/v1/tasks/{task_id}").status_code == 204
        assert client.get(f"/v1/tasks/{task_id}").status_code == 404
        assert list(settings.uploads_dir.iterdir()) == []
        assert list(settings.reports_dir.iterdir()) == []

    engine = create_db_engine(settings.resolved_database_url)
    SessionLocal = create_session_factory(engine)
    with SessionLocal() as session:
        assert session.scalars(select(TaskDB)).all() == []
        assert session.scalars(select(ParameterDB)).all() == []
    engine.dispose()
    manager.close()


def test_unavailable_unit_answered_je_ne_sais_pas_stays_not_analyzed_in_pdf(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    manager = TaskManager(settings=settings, orchestrator_factory=lambda: AgentOrchestrator())
    app = create_app(settings=settings, task_manager=manager)

    pdf_input = tmp_path / "hct_inconnu.pdf"
    render_pdf(
        pdf_input,
        "lines",
        True,
        [{"name_printed": "Hématocrite", "value": 42.0, "unit": None, "reference_min": 37.0, "reference_max": 47.0}],
    )

    with TestClient(app) as client:
        with pdf_input.open("rb") as fh:
            task_id = client.post(
                "/v1/tasks",
                files={"file": ("inconnu.pdf", fh, "application/pdf")},
            ).json()["task_id"]

        waiting = Task.model_validate(client.get(f"/v1/tasks/{task_id}").json())
        assert waiting.pending_question is not None

        done = Task.model_validate(
            client.post(
                f"/v1/tasks/{task_id}/answer",
                json={"question_id": waiting.pending_question.question_id, "answer": "je ne sais pas"},
            ).json()
        )
        assert done.parameters[0].status == ParameterStatus.not_analyzed
        pdf_resp = client.get(f"/v1/tasks/{task_id}/report.pdf")
        assert pdf_resp.status_code == 200
        with pymupdf.open(stream=pdf_resp.content, filetype="pdf") as doc:
            pdf_text = " ".join(" ".join(p.get_text("text") for p in doc).split())
        assert "Non analysé" in pdf_text
        assert "unité absente du document" in pdf_text
    manager.close()