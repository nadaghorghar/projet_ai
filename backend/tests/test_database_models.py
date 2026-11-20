from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect, select

from app.core.config import Settings
from app.database import (
    AgentRunDB,
    AgentStepDB,
    DocumentDB,
    ExtractionResultDB,
    KnowledgeSourceDB,
    ParameterDB,
    ReportDB,
    RetrievedPassageDB,
    TaskDB,
    create_db_engine,
    create_session_factory,
    init_db,
)


def test_settings_database_url_and_default_retention(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    assert settings.retention_seconds == 3600
    assert settings.resolved_database_url.startswith("sqlite:///")
    assert "labmind.db" in settings.resolved_database_url


def test_init_db_creates_all_expected_tables(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    engine = create_db_engine(settings.resolved_database_url)
    init_db(engine)

    tables = set(inspect(engine).get_table_names())
    assert {
        "tasks",
        "documents",
        "extraction_results",
        "parameters",
        "agent_runs",
        "agent_steps",
        "knowledge_sources",
        "retrieved_passages",
        "reports",
    }.issubset(tables)
    engine.dispose()


def test_cascade_delete_removes_all_task_data_and_preserves_sources(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    engine = create_db_engine(settings.resolved_database_url)
    init_db(engine)
    SessionLocal = create_session_factory(engine)

    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        src = KnowledgeSourceDB(
            source_id="ameli-test-2026",
            title="Lire les résultats d'une prise de sang",
            organisme="Assurance Maladie",
            url="https://www.ameli.fr/",
            published_date="2026-01-08",
        )
        session.add(src)

        task = TaskDB(
            task_id="task-db-001",
            status="done",
            agent_snapshot_json='{"task_id": "task-db-001"}',
            expires_at=now + timedelta(hours=1),
            document=DocumentDB(filename="bilan.pdf", deleted_from_disk=True),
            extraction_result=ExtractionResultDB(method="pdf_text", page_count=1),
            parameters=[
                ParameterDB(
                    code="HGB",
                    name_printed="Hémoglobine",
                    value=13.4,
                    unit="g/dL",
                    reference_min=12.0,
                    reference_max=16.0,
                    reference_origin="document_laboratoire",
                    status="within_reference",
                    confidence=0.95,
                    evidence_raw_text="Hémoglobine 13,4 g/dL (12,0 - 16,0)",
                    evidence_page=1,
                )
            ],
            agent_run=AgentRunDB(
                iterations=4,
                steps=[
                    AgentStepDB(
                        step_number=1,
                        tool="extract_pdf_text",
                        reason="PDF reçu",
                        success=True,
                        summary="OK",
                    )
                ],
            ),
            retrieved_passages=[
                RetrievedPassageDB(
                    source_id="ameli-test-2026",
                    passage_id="ameli-test-2026#001",
                    excerpt="Extrait documentaire de test.",
                    score=0.88,
                )
            ],
            report=ReportDB(report_id="r-task-db"),
        )
        session.add(task)
        session.commit()

    with SessionLocal() as session:
        loaded = session.get(TaskDB, "task-db-001")
        assert loaded is not None
        assert loaded.document is not None
        assert loaded.extraction_result is not None
        assert len(loaded.parameters) == 1
        assert loaded.agent_run is not None and len(loaded.agent_run.steps) == 1
        assert len(loaded.retrieved_passages) == 1
        assert loaded.report is not None

        session.delete(loaded)
        session.commit()

    with SessionLocal() as session:
        assert session.scalars(select(TaskDB)).all() == []
        assert session.scalars(select(DocumentDB)).all() == []
        assert session.scalars(select(ExtractionResultDB)).all() == []
        assert session.scalars(select(ParameterDB)).all() == []
        assert session.scalars(select(AgentRunDB)).all() == []
        assert session.scalars(select(AgentStepDB)).all() == []
        assert session.scalars(select(RetrievedPassageDB)).all() == []
        assert session.scalars(select(ReportDB)).all() == []
        # Les sources publiques institutionnelles sont conservées
        assert len(session.scalars(select(KnowledgeSourceDB)).all()) == 1

    engine.dispose()