import io
import uuid

from fastapi.testclient import TestClient
from PIL import Image

from app.agent import AgentOrchestrator
from app.api.app import create_app
from app.api.store import TaskManager
from app.core.config import Settings
from app.schemas import ErrorResponse, TaskStatus
from tests.helpers import render_pdf


def _make_client(tmp_path) -> tuple[TestClient, Settings]:
    settings = Settings(data_dir=tmp_path / "data")
    manager = TaskManager(
        settings=settings,
        orchestrator_factory=lambda: AgentOrchestrator(),
    )
    app = create_app(settings=settings, task_manager=manager)
    return TestClient(app), settings


def test_fake_pdf_magic_bytes_rejected_with_422(tmp_path):
    client, settings = _make_client(tmp_path)
    resp = client.post(
        "/v1/tasks",
        files={"file": ("piege.pdf", b"<html><script>alert(1)</script></html>", "application/pdf")},
    )
    assert resp.status_code == 422
    assert ErrorResponse.model_validate(resp.json()).error.code == "unreadable_document"
    assert list(settings.uploads_dir.iterdir()) == []


def test_fake_or_corrupted_png_rejected_with_422(tmp_path):
    client, _ = _make_client(tmp_path)
    bad_sig = client.post(
        "/v1/tasks",
        files={"file": ("faux.png", b"NOT_A_PNG_FILE", "image/png")},
    )
    assert bad_sig.status_code == 422
    assert ErrorResponse.model_validate(bad_sig.json()).error.code == "unreadable_document"

    corrupted_png = client.post(
        "/v1/tasks",
        files={"file": ("casse.png", b"\x89PNG\r\n\x1a\ncorrupted_bytes", "image/png")},
    )
    assert corrupted_png.status_code == 422
    assert ErrorResponse.model_validate(corrupted_png.json()).error.code == "unreadable_document"


def test_valid_png_upload_accepted(tmp_path):
    client, _ = _make_client(tmp_path)
    buf = io.BytesIO()
    Image.new("RGB", (400, 120), "white").save(buf, format="PNG")
    resp = client.post(
        "/v1/tasks",
        files={"file": ("scan.png", buf.getvalue(), "image/png")},
    )
    assert resp.status_code == 202


def test_path_traversal_filename_is_isolated_to_uuid_upload(tmp_path):
    client, settings = _make_client(tmp_path)
    pdf_path = tmp_path / "bilan.pdf"
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
    with pdf_path.open("rb") as fh:
        resp = client.post(
            "/v1/tasks",
            files={"file": ("../../outside_secret.pdf", fh, "application/pdf")},
        )
    assert resp.status_code == 202
    data = resp.json()
    uuid.UUID(data["task_id"])
    assert "/" not in data["document"]["filename"]
    assert ".." not in data["document"]["filename"]
    assert not (tmp_path / "outside_secret.pdf").exists()
    assert list(settings.uploads_dir.iterdir()) == []


def test_non_uuid_task_id_rejected_as_404(tmp_path):
    client, _ = _make_client(tmp_path)
    for bad_id in ("not-a-uuid", "abc"):
        resp = client.get(f"/v1/tasks/{bad_id}")
        assert resp.status_code == 404
        assert ErrorResponse.model_validate(resp.json()).error.code == "task_not_found"

    traversal_resp = client.get("/v1/tasks/..%2F..%2Fetc%2Fpasswd")
    assert traversal_resp.status_code == 404
    assert ErrorResponse.model_validate(traversal_resp.json()).error.code in ("task_not_found", "not_found")


def test_corrupted_pdf_with_valid_header_produces_error_status_and_cleans_up(tmp_path):
    client, settings = _make_client(tmp_path)
    resp = client.post(
        "/v1/tasks",
        files={"file": ("malforme.pdf", b"%PDF-1.4\ngarbage_not_a_real_pdf_stream", "application/pdf")},
    )
    assert resp.status_code == 202
    task_id = resp.json()["task_id"]

    status_resp = client.get(f"/v1/tasks/{task_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == TaskStatus.error.value
    assert status_resp.json()["errors"][0]["code"] == "unreadable_document"
    assert list(settings.uploads_dir.iterdir()) == []


def test_privacy_no_cache_and_security_headers_present(tmp_path):
    client, _ = _make_client(tmp_path)
    pdf_path = tmp_path / "bilan.pdf"
    render_pdf(
        pdf_path,
        "table1",
        True,
        [
            {
                "name_printed": "Glycémie",
                "value": 0.90,
                "unit": "g/L",
                "reference_min": 0.70,
                "reference_max": 1.10,
            }
        ],
    )
    with pdf_path.open("rb") as fh:
        task_id = client.post(
            "/v1/tasks",
            files={"file": ("bilan.pdf", fh, "application/pdf")},
        ).json()["task_id"]

    for endpoint in (f"/v1/tasks/{task_id}", f"/v1/tasks/{task_id}/report.pdf"):
        r = client.get(endpoint)
        assert r.status_code == 200
        assert "no-store" in r.headers.get("cache-control", "")
        assert r.headers.get("x-content-type-options") == "nosniff"
        assert r.headers.get("x-frame-options") == "DENY"