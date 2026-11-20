from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.agent import AgentOrchestrator, AgentState
from app.core.config import Settings
from app.database import (
    KnowledgeSourceDB,
    ParameterDB,
    RetrievedPassageDB,
    TaskDB,
    TaskRepository,
    create_db_engine,
    create_session_factory,
    init_db,
)
from app.generation.interface import RetrievedPassage
from app.schemas import AnswerIn, Source, TaskStatus
from tests.helpers import render_pdf


def _make_repo(tmp_path, retention_seconds: int = 3600):
    settings = Settings(
        data_dir=tmp_path / "data",
        retention_seconds=retention_seconds,
    )
    settings.ensure_dirs()
    engine = create_db_engine(settings.resolved_database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)
    repo = TaskRepository(session_factory, retention_seconds=retention_seconds)
    return settings, engine, session_factory, repo


def test_save_and_reload_waiting_state_across_restart_and_resume(tmp_path):
    settings, engine, session_factory, repo = _make_repo(tmp_path)
    pdf_path = settings.uploads_dir / "task-repo-1.pdf"
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

    state = AgentState(
        task_id="task-repo-1",
        file_path=str(pdf_path),
        filename="bilan.pdf",
        status=TaskStatus.processing,
    )
    AgentOrchestrator().run(state)
    assert state.status == TaskStatus.waiting_for_user
    assert state.pending_question is not None

    # Ajout de 2 passages partageant la même source pour tester la déduplication FK
    shared_src = Source(
        source_id="ameli-demo-2026",
        title="Prise de sang",
        organisme="Ameli",
        url="https://www.ameli.fr/",
        date="2026-01-08",
    )
    state.retrieved_passages = [
        RetrievedPassage(passage_id="ameli-demo-2026#001", source=shared_src, excerpt="Extrait 1", score=0.9),
        RetrievedPassage(passage_id="ameli-demo-2026#002", source=shared_src, excerpt="Extrait 2", score=0.8),
    ]

    repo.save_state(state)

    with session_factory() as session:
        assert len(session.scalars(select(KnowledgeSourceDB)).all()) == 1
        assert len(session.scalars(select(RetrievedPassageDB)).all()) == 2

    # Nouveau repository (simule un redémarrage du serveur)
    restarted_repo = TaskRepository(session_factory, retention_seconds=3600)
    loaded = restarted_repo.load_state("task-repo-1")
    assert loaded is not None
    reloaded_state, report_id, _ = loaded
    assert report_id is None
    assert reloaded_state.status == TaskStatus.waiting_for_user
    assert reloaded_state.pending_question is not None

    # Reprise de l'agent après redémarrage
    AgentOrchestrator().resume(
        reloaded_state,
        AnswerIn(question_id=reloaded_state.pending_question.question_id, answer="%"),
    )
    restarted_repo.save_state(reloaded_state, report_id="r-taskrepo")

    with session_factory() as session:
        assert session.get(TaskDB, "task-repo-1").status == "done"
        assert len(session.scalars(select(ParameterDB)).all()) == 1

    # Une fois `done`, le texte brut n'est plus conservé dans le snapshot
    final_loaded = restarted_repo.load_state("task-repo-1")
    assert final_loaded is not None
    assert final_loaded[0].raw_text == ""
    assert final_loaded[0].extracted_pages == []

    engine.dispose()


def test_purge_expired_tasks_removes_db_rows_and_files(tmp_path):
    settings, engine, session_factory, repo = _make_repo(tmp_path, retention_seconds=3600)

    old_pdf = settings.uploads_dir / "old.pdf"
    old_pdf.write_bytes(b"%PDF-1.4 old")
    old_report = settings.reports_dir / "r-old.pdf"
    old_report.write_bytes(b"%PDF-1.4 old report")

    fresh_pdf = settings.uploads_dir / "fresh.pdf"
    fresh_pdf.write_bytes(b"%PDF-1.4 fresh")

    t0 = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
    repo.save_state(
        AgentState(task_id="task-old", file_path=str(old_pdf), filename="old.pdf", status=TaskStatus.done),
        report_id="r-old",
        report_pdf_path=str(old_report),
        file_deleted=False,
        now=t0,
    )
    repo.save_state(
        AgentState(task_id="task-fresh", file_path=str(fresh_pdf), filename="fresh.pdf", status=TaskStatus.waiting_for_user),
        file_deleted=False,
        now=t0 + timedelta(minutes=50),
    )

    # À t0 + 61 minutes : task-old est expirée, task-fresh reste active
    purged = repo.purge_expired_tasks(now=t0 + timedelta(minutes=61))
    assert purged == 1
    assert not old_pdf.exists()
    assert not old_report.exists()
    assert fresh_pdf.exists()
    assert repo.get_task("task-old", now=t0 + timedelta(minutes=61)) is None
    assert repo.get_task("task-fresh", now=t0 + timedelta(minutes=61)) is not None

    # Vérifie aussi delete_task sur une tâche active
    assert repo.delete_task("task-fresh") is True
    assert not fresh_pdf.exists()
    assert repo.delete_task("task-fresh") is False

    with session_factory() as session:
        assert session.scalars(select(TaskDB)).all() == []

    engine.dispose()