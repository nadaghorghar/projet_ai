from pathlib import Path

from fastapi.testclient import TestClient

from app.agent import AgentOrchestrator
from app.api.app import create_app
from app.api.store import TaskManager
from app.core.config import Settings
from app.schemas import ErrorResponse, ParameterStatus, Task, TaskStatus
from tests.helpers import render_pdf


def _make_client(tmp_path: Path) -> tuple[TestClient, Settings]:
    settings = Settings(data_dir=tmp_path / "data")
    manager = TaskManager(
        settings=settings,
        orchestrator_factory=lambda: AgentOrchestrator(),
    )
    app = create_app(settings=settings, task_manager=manager)
    return TestClient(app), settings


def _upload_missing_unit_pdf(client: TestClient, tmp_path: Path) -> str:
    pdf_path = tmp_path / "bilan_unite_manquante.pdf"
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
            },
            {
                "name_printed": "Glycémie",
                "value": 0.92,
                "unit": "g/L",
                "reference_min": 0.70,
                "reference_max": 1.10,
            },
        ],
    )
    with pdf_path.open("rb") as fh:
        resp = client.post(
            "/v1/tasks",
            files={"file": ("bilan_ambigu.pdf", fh, "application/pdf")},
        )
    assert resp.status_code == 202
    return resp.json()["task_id"]


def test_full_waiting_for_user_answer_pdf_and_delete(tmp_path):
    client, settings = _make_client(tmp_path)
    task_id = _upload_missing_unit_pdf(client, tmp_path)

    waiting = Task.model_validate(client.get(f"/v1/tasks/{task_id}").json())
    assert waiting.status == TaskStatus.waiting_for_user
    assert waiting.pending_question is not None
    assert waiting.pending_question.code == "HCT"
    assert waiting.pending_question.field == "unit"

    # Le PDF n'est pas encore téléchargeable avant la fin
    pdf_early = client.get(f"/v1/tasks/{task_id}/report.pdf")
    assert pdf_early.status_code == 409
    assert ErrorResponse.model_validate(pdf_early.json()).error.code == "invalid_state"

    # Réponse utilisateur -> reprise -> done
    ans_resp = client.post(
        f"/v1/tasks/{task_id}/answer",
        json={"question_id": waiting.pending_question.question_id, "answer": "%"},
    )
    assert ans_resp.status_code == 200
    done_task = Task.model_validate(ans_resp.json())
    assert done_task.status == TaskStatus.done
    assert done_task.pending_question is None
    assert done_task.report_id is not None

    hct = next(p for p in done_task.parameters if p.code == "HCT")
    assert hct.unit == "%"
    assert hct.status == ParameterStatus.within_reference

    # Téléchargement PDF valide
    pdf_resp = client.get(f"/v1/tasks/{task_id}/report.pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"].startswith("application/pdf")
    assert pdf_resp.content.startswith(b"%PDF")
    assert list(settings.reports_dir.glob("*.pdf")) != []

    # Suppression complète -> 204 puis 404 partout et plus aucun fichier sur disque
    del_resp = client.delete(f"/v1/tasks/{task_id}")
    assert del_resp.status_code == 204
    assert list(settings.uploads_dir.iterdir()) == []
    assert list(settings.reports_dir.iterdir()) == []
    assert client.get(f"/v1/tasks/{task_id}").status_code == 404
    assert client.get(f"/v1/tasks/{task_id}/report.pdf").status_code == 404
    assert client.delete(f"/v1/tasks/{task_id}").status_code == 404


def test_answer_je_ne_sais_pas_never_guesses_unit(tmp_path):
    client, _ = _make_client(tmp_path)
    task_id = _upload_missing_unit_pdf(client, tmp_path)
    waiting = Task.model_validate(client.get(f"/v1/tasks/{task_id}").json())
    assert waiting.pending_question is not None

    resp = client.post(
        f"/v1/tasks/{task_id}/answer",
        json={
            "question_id": waiting.pending_question.question_id,
            "answer": "je ne sais pas",
        },
    )
    assert resp.status_code == 200
    done_task = Task.model_validate(resp.json())
    assert done_task.status == TaskStatus.done
    hct = next(p for p in done_task.parameters if p.code == "HCT")
    assert hct.unit is None
    assert hct.status == ParameterStatus.not_analyzed


def test_invalid_answer_returns_422_and_keeps_question_pending(tmp_path):
    client, _ = _make_client(tmp_path)
    task_id = _upload_missing_unit_pdf(client, tmp_path)
    waiting = Task.model_validate(client.get(f"/v1/tasks/{task_id}").json())
    assert waiting.pending_question is not None

    bad_resp = client.post(
        f"/v1/tasks/{task_id}/answer",
        json={"question_id": waiting.pending_question.question_id, "answer": "kcal"},
    )
    assert bad_resp.status_code == 422
    assert ErrorResponse.model_validate(bad_resp.json()).error.code == "invalid_answer"

    still_waiting = Task.model_validate(client.get(f"/v1/tasks/{task_id}").json())
    assert still_waiting.status == TaskStatus.waiting_for_user
    assert still_waiting.pending_question is not None
    assert still_waiting.pending_question.question_id == waiting.pending_question.question_id


def test_stale_question_id_returns_409(tmp_path):
    client, _ = _make_client(tmp_path)
    task_id = _upload_missing_unit_pdf(client, tmp_path)

    stale_resp = client.post(
        f"/v1/tasks/{task_id}/answer",
        json={"question_id": "q-999", "answer": "%"},
    )
    assert stale_resp.status_code == 409
    assert ErrorResponse.model_validate(stale_resp.json()).error.code == "invalid_state"


def test_delete_while_waiting_removes_uploaded_file(tmp_path):
    client, settings = _make_client(tmp_path)
    task_id = _upload_missing_unit_pdf(client, tmp_path)

    del_resp = client.delete(f"/v1/tasks/{task_id}")
    assert del_resp.status_code == 204
    assert list(settings.uploads_dir.iterdir()) == []