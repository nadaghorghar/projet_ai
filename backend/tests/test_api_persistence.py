import logging
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.core.config import Settings
from app.database import TaskDB, create_db_engine, create_session_factory
from app.schemas import ParameterStatus, Task, TaskStatus
from tests.helpers import render_pdf


def test_task_survives_api_restart_and_completes_via_sqlite(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    pdf_path = tmp_path / "attente.pdf"
    render_pdf(
        pdf_path,
        "lines",
        True,
        [
            {
                "name_printed": "Hématocrite",
                "value": 42.0,
                "unit": None,
                "reference_min": 37.0,
                "reference_max": 47.0,
            }
        ],
    )

    app1 = create_app(settings=settings)
    with TestClient(app1) as client1:
        with pdf_path.open("rb") as fh:
            resp = client1.post("/v1/tasks", files={"file": ("bilan.pdf", fh, "application/pdf")})
        assert resp.status_code == 202
        task_id = resp.json()["task_id"]
    app1.state.task_manager.close()

    # Seconde instance de l'application pointant vers le même data_dir (redémarrage)
    app2 = create_app(settings=settings)
    with TestClient(app2) as client2:
        waiting = Task.model_validate(client2.get(f"/v1/tasks/{task_id}").json())
        assert waiting.status == TaskStatus.waiting_for_user
        assert waiting.pending_question is not None

        done = Task.model_validate(
            client2.post(
                f"/v1/tasks/{task_id}/answer",
                json={"question_id": waiting.pending_question.question_id, "answer": "%"},
            ).json()
        )
        assert done.status == TaskStatus.done
        assert done.parameters[0].status == ParameterStatus.within_reference
        assert client2.get(f"/v1/tasks/{task_id}/report.pdf").status_code == 200
        assert client2.delete(f"/v1/tasks/{task_id}").status_code == 204
    app2.state.task_manager.close()


def test_expired_task_returns_404_and_removes_pdf_on_disk(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    pdf_path = tmp_path / "done.pdf"
    render_pdf(
        pdf_path,
        "table1",
        True,
        [
            {
                "name_printed": "Hémoglobine",
                "value": 13.5,
                "unit": "g/dL",
                "reference_min": 12.0,
                "reference_max": 16.0,
            }
        ],
    )

    app = create_app(settings=settings)
    with TestClient(app) as client:
        with pdf_path.open("rb") as fh:
            task_id = client.post("/v1/tasks", files={"file": ("ok.pdf", fh, "application/pdf")}).json()["task_id"]
        assert client.get(f"/v1/tasks/{task_id}/report.pdf").status_code == 200
        assert list(settings.reports_dir.glob("*.pdf")) != []

        # Simulation d'une tâche expirée depuis 5 minutes
        engine = create_db_engine(settings.resolved_database_url)
        SessionLocal = create_session_factory(engine)
        with SessionLocal() as session:
            row = session.get(TaskDB, task_id)
            assert row is not None
            row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
            session.commit()
        engine.dispose()

        assert client.get(f"/v1/tasks/{task_id}").status_code == 404
        assert list(settings.reports_dir.glob("*.pdf")) == []
    app.state.task_manager.close()


def test_logs_never_contain_medical_values_or_filenames(tmp_path, caplog):
    settings = Settings(data_dir=tmp_path / "data")
    pdf_path = tmp_path / "confidentiel.pdf"
    render_pdf(
        pdf_path,
        "table1",
        True,
        [
            {
                "name_printed": "Glycémie",
                "value": 1.48,
                "unit": "g/L",
                "reference_min": 0.70,
                "reference_max": 1.10,
            }
        ],
    )

    app = create_app(settings=settings)
    with caplog.at_level(logging.INFO, logger="labmind"):
        with TestClient(app) as client:
            with pdf_path.open("rb") as fh:
                task_id = client.post(
                    "/v1/tasks",
                    files={"file": ("jean_dupont_glycemie.pdf", fh, "application/pdf")},
                ).json()["task_id"]
            client.get(f"/v1/tasks/{task_id}/report.pdf")
            client.delete(f"/v1/tasks/{task_id}")
    app.state.task_manager.close()

    logs_text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "Glycémie" not in logs_text
    assert "1.48" not in logs_text
    assert "1,48" not in logs_text
    assert "jean_dupont" not in logs_text