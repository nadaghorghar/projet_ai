import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.agent import AgentOrchestrator
from app.api.app import create_app
from app.api.store import TaskManager
from app.core.config import Settings
from app.schemas import ErrorResponse, Task, TaskStatus
from tests.helpers import render_pdf


def _make_client(tmp_path: Path, max_upload_bytes: int = 10_000_000) -> tuple[TestClient, Settings]:
    settings = Settings(
        data_dir=tmp_path / "data",
        max_upload_bytes=max_upload_bytes,
    )
    manager = TaskManager(
        settings=settings,
        orchestrator_factory=lambda: AgentOrchestrator(),
    )
    app = create_app(settings=settings, task_manager=manager)
    return TestClient(app), settings


def test_health_endpoint(tmp_path):
    client, _ = _make_client(tmp_path)
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_upload_missing_file_returns_400_contract(tmp_path):
    client, _ = _make_client(tmp_path)
    resp = client.post("/v1/tasks")
    assert resp.status_code == 400
    err = ErrorResponse.model_validate(resp.json())
    assert err.error.code == "invalid_request"


def test_upload_unsupported_format_returns_415(tmp_path):
    client, _ = _make_client(tmp_path)
    resp = client.post(
        "/v1/tasks",
        files={"file": ("notes.txt", b"HGB 13.5 g/dL", "text/plain")},
    )
    assert resp.status_code == 415
    err = ErrorResponse.model_validate(resp.json())
    assert err.error.code == "unsupported_format"


def test_upload_empty_file_returns_400(tmp_path):
    client, _ = _make_client(tmp_path)
    resp = client.post(
        "/v1/tasks",
        files={"file": ("vide.pdf", b"", "application/pdf")},
    )
    assert resp.status_code == 400
    err = ErrorResponse.model_validate(resp.json())
    assert err.error.code == "invalid_request"


def test_upload_too_large_returns_413(tmp_path):
    client, _ = _make_client(tmp_path, max_upload_bytes=128)
    resp = client.post(
        "/v1/tasks",
        files={"file": ("gros.pdf", b"%PDF-1.4 " + b"x" * 200, "application/pdf")},
    )
    assert resp.status_code == 413
    err = ErrorResponse.model_validate(resp.json())
    assert err.error.code == "file_too_large"


def test_upload_pdf_and_poll_task_done(tmp_path):
    client, settings = _make_client(tmp_path)
    pdf_path = tmp_path / "bilan.pdf"
    render_pdf(
        pdf_path,
        "table1",
        True,
        [
            {
                "name_printed": "Hémoglobine",
                "value": 13.2,
                "unit": "g/dL",
                "reference_min": 12.0,
                "reference_max": 16.0,
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
        post_resp = client.post(
            "/v1/tasks",
            files={"file": ("bilan_patient.pdf", fh, "application/pdf")},
        )

    assert post_resp.status_code == 202
    created = Task.model_validate(post_resp.json())
    uuid.UUID(created.task_id)
    assert created.status == TaskStatus.received
    assert created.document is not None
    assert created.document.filename == "bilan_patient.pdf"

    get_resp = client.get(f"/v1/tasks/{created.task_id}")
    assert get_resp.status_code == 200
    finished = Task.model_validate(get_resp.json())
    assert finished.status == TaskStatus.done
    assert finished.report_id is not None
    assert sorted(finished.detected_categories) == ["Bilan glycémique", "NFS"]
    assert {p.code for p in finished.parameters} == {"HGB", "GLY"}
    assert list(settings.uploads_dir.iterdir()) == []


def test_get_unknown_task_returns_404(tmp_path):
    client, _ = _make_client(tmp_path)
    resp = client.get("/v1/tasks/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    err = ErrorResponse.model_validate(resp.json())
    assert err.error.code == "task_not_found"