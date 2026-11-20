"""Repository SQLAlchemy : persistance des tâches, suppression et purge 1 h."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agent.state import AgentState
from app.identification.catalog import get_categories_for_codes
from app.schemas import Task, TaskStatus

from .models import (
    AgentRunDB,
    AgentStepDB,
    DocumentDB,
    ExtractionResultDB,
    KnowledgeSourceDB,
    ParameterDB,
    ReportDB,
    RetrievedPassageDB,
    TaskDB,
    utcnow,
)

logger = logging.getLogger("labmind.database")


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _safe_unlink(path_str: str | None) -> None:
    if not path_str:
        return
    try:
        path = Path(path_str)
        if path.is_file():
            path.unlink()
    except OSError:
        logger.warning("Impossible de supprimer un fichier lors du nettoyage.")


def _sanitize_snapshot_json(state: AgentState) -> str:
    """Efface le texte brut du snapshot dès que la tâche est terminée ou en erreur."""
    snapshot = state.model_copy(deep=True)
    if snapshot.status in (TaskStatus.done, TaskStatus.error):
        snapshot.raw_text = ""
        snapshot.extracted_pages = []
    return snapshot.model_dump_json()


def _compute_avg_ocr_confidence(pages: list[dict]) -> float | None:
    scores = [
        float(p["ocr_confidence"])
        for p in pages
        if p.get("ocr_confidence") is not None
    ]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 4)


class TaskRepository:
    """Opérations CRUD et purge par expiration sur les tâches LabMind."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        retention_seconds: int = 3600,
    ) -> None:
        self._session_factory = session_factory
        self.retention_seconds = retention_seconds

    def save_state(
        self,
        state: AgentState,
        report_id: str | None = None,
        report_pdf_path: str | None = None,
        file_deleted: bool | None = None,
        now: datetime | None = None,
    ) -> Task:
        """Crée ou met à jour une tâche et toutes ses entités liées."""
        current_time = _as_utc(now or utcnow())
        detected_categories = get_categories_for_codes(
            [p.code for p in state.validated_parameters]
        )
        explanations = (
            state.generation_result.to_task_explanations()
            if state.generation_result is not None
            else None
        )
        disk_deleted = (
            file_deleted
            if file_deleted is not None
            else not Path(state.file_path).is_file()
        )
        stored_file_path = None if disk_deleted else state.file_path
        snapshot_json = _sanitize_snapshot_json(state)

        with self._session_factory() as session:
            task_db = session.get(TaskDB, state.task_id)
            if task_db is None:
                task_db = TaskDB(
                    task_id=state.task_id,
                    status=state.status.value,
                    agent_snapshot_json=snapshot_json,
                    created_at=current_time,
                    updated_at=current_time,
                    expires_at=current_time + timedelta(seconds=self.retention_seconds),
                )
                session.add(task_db)
            else:
                task_db.status = state.status.value
                task_db.agent_snapshot_json = snapshot_json
                task_db.updated_at = current_time

            task_db.detected_categories_json = json.dumps(
                detected_categories, ensure_ascii=False
            )
            task_db.pending_question_json = (
                state.pending_question.model_dump_json()
                if state.pending_question is not None
                else None
            )
            task_db.explanations_json = (
                json.dumps(explanations, ensure_ascii=False)
                if explanations is not None
                else None
            )
            task_db.error_code = state.error.code if state.error is not None else None
            task_db.error_message = (
                state.error.message if state.error is not None else None
            )

            if task_db.document is None:
                task_db.document = DocumentDB(
                    filename=state.filename,
                    storage_path=stored_file_path,
                    deleted_from_disk=disk_deleted,
                    created_at=current_time,
                )
            else:
                task_db.document.filename = state.filename
                task_db.document.storage_path = stored_file_path
                task_db.document.deleted_from_disk = disk_deleted

            page_count = len(state.extracted_pages)
            avg_ocr = _compute_avg_ocr_confidence(state.extracted_pages)
            if task_db.extraction_result is None:
                task_db.extraction_result = ExtractionResultDB(
                    method=(
                        state.extraction_method.value
                        if state.extraction_method is not None
                        else None
                    ),
                    page_count=page_count,
                    avg_ocr_confidence=avg_ocr,
                )
            else:
                task_db.extraction_result.method = (
                    state.extraction_method.value
                    if state.extraction_method is not None
                    else task_db.extraction_result.method
                )
                if page_count > 0:
                    task_db.extraction_result.page_count = page_count
                if avg_ocr is not None:
                    task_db.extraction_result.avg_ocr_confidence = avg_ocr

            task_db.parameters.clear()
            for param in state.validated_parameters:
                task_db.parameters.append(
                    ParameterDB(
                        code=param.code,
                        name_printed=param.name_printed,
                        value=param.value,
                        unit=param.unit,
                        reference_min=param.reference.min,
                        reference_max=param.reference.max,
                        reference_origin=param.reference.origin,
                        status=param.status.value,
                        reason=param.reason,
                        confidence=param.confidence,
                        evidence_raw_text=param.evidence.raw_text,
                        evidence_page=param.evidence.page,
                    )
                )

            if task_db.agent_run is None:
                task_db.agent_run = AgentRunDB(
                    iterations=state.iterations,
                    max_iterations=state.max_iterations,
                    question_counter=state.question_counter,
                    knowledge_searched=state.knowledge_searched,
                )
            else:
                task_db.agent_run.iterations = state.iterations
                task_db.agent_run.max_iterations = state.max_iterations
                task_db.agent_run.question_counter = state.question_counter
                task_db.agent_run.knowledge_searched = state.knowledge_searched

            task_db.agent_run.steps.clear()
            for step in state.steps:
                task_db.agent_run.steps.append(
                    AgentStepDB(
                        step_number=step.step_number,
                        tool=step.tool.value,
                        reason=step.reason,
                        success=step.success,
                        summary=step.summary,
                    )
                )

            seen_sources: set[str] = set()
            for passage in state.retrieved_passages:
                src = passage.source
                if src.source_id not in seen_sources:
                    seen_sources.add(src.source_id)
                    session.merge(
                        KnowledgeSourceDB(
                            source_id=src.source_id,
                            title=src.title,
                            organisme=src.organisme,
                            url=src.url,
                            published_date=src.date,
                        )
                    )
            session.flush()

            task_db.retrieved_passages.clear()
            for passage in state.retrieved_passages:
                task_db.retrieved_passages.append(
                    RetrievedPassageDB(
                        source_id=passage.source.source_id,
                        passage_id=passage.passage_id,
                        excerpt=passage.excerpt,
                        score=passage.score,
                    )
                )

            if report_id is not None:
                if task_db.report is None:
                    task_db.report = ReportDB(
                        report_id=report_id,
                        pdf_path=report_pdf_path,
                        created_at=current_time,
                    )
                else:
                    task_db.report.report_id = report_id
                    if report_pdf_path is not None:
                        task_db.report.pdf_path = report_pdf_path

            session.commit()

        return state.to_task(report_id=report_id)

    def load_state(
        self,
        task_id: str,
        now: datetime | None = None,
    ) -> tuple[AgentState, str | None, str | None] | None:
        """Recharge `(AgentState, report_id, report_pdf_path)` ou None si expiré/absent."""
        current_time = _as_utc(now or utcnow())
        expired_paths: list[str | None] = []

        with self._session_factory() as session:
            task_db = session.get(TaskDB, task_id)
            if task_db is None:
                return None

            if _as_utc(task_db.expires_at) <= current_time:
                if task_db.document is not None:
                    expired_paths.append(task_db.document.storage_path)
                if task_db.report is not None:
                    expired_paths.append(task_db.report.pdf_path)
                session.delete(task_db)
                session.commit()
            else:
                state = AgentState.model_validate_json(task_db.agent_snapshot_json)
                report_id = task_db.report.report_id if task_db.report else None
                pdf_path = task_db.report.pdf_path if task_db.report else None
                return state, report_id, pdf_path

        for path_str in expired_paths:
            _safe_unlink(path_str)
        logger.info("Tâche expirée supprimée lors de l'accès : %s", task_id)
        return None

    def get_task(
        self,
        task_id: str,
        now: datetime | None = None,
    ) -> Task | None:
        """Retourne l'objet API `Task` s'il existe et n'est pas expiré."""
        loaded = self.load_state(task_id, now=now)
        if loaded is None:
            return None
        state, report_id, _ = loaded
        return state.to_task(report_id=report_id)

    def set_report_pdf_path(
        self,
        task_id: str,
        report_id: str,
        pdf_path: str,
        now: datetime | None = None,
    ) -> None:
        """Enregistre le chemin disque du PDF généré pour une tâche."""
        current_time = _as_utc(now or utcnow())
        with self._session_factory() as session:
            task_db = session.get(TaskDB, task_id)
            if task_db is None:
                return
            if task_db.report is None:
                task_db.report = ReportDB(
                    report_id=report_id,
                    pdf_path=pdf_path,
                    created_at=current_time,
                )
            else:
                task_db.report.report_id = report_id
                task_db.report.pdf_path = pdf_path
            session.commit()

    def delete_task(self, task_id: str) -> bool:
        """Supprime la tâche de la base et les fichiers associés sur disque."""
        paths_to_remove: list[str | None] = []
        with self._session_factory() as session:
            task_db = session.get(TaskDB, task_id)
            if task_db is None:
                return False
            if task_db.document is not None:
                paths_to_remove.append(task_db.document.storage_path)
            if task_db.report is not None:
                paths_to_remove.append(task_db.report.pdf_path)
            session.delete(task_db)
            session.commit()

        for path_str in paths_to_remove:
            _safe_unlink(path_str)
        logger.info("Tâche supprimée de la base : %s", task_id)
        return True

    def purge_expired_tasks(self, now: datetime | None = None) -> int:
        """Supprime toutes les tâches expirées (base + fichiers associés)."""
        current_time = _as_utc(now or utcnow())
        paths_to_remove: list[str | None] = []
        purged_count = 0

        with self._session_factory() as session:
            all_tasks = session.scalars(select(TaskDB)).all()
            for task_db in all_tasks:
                if _as_utc(task_db.expires_at) <= current_time:
                    if task_db.document is not None:
                        paths_to_remove.append(task_db.document.storage_path)
                    if task_db.report is not None:
                        paths_to_remove.append(task_db.report.pdf_path)
                    session.delete(task_db)
                    purged_count += 1
            if purged_count:
                session.commit()

        for path_str in paths_to_remove:
            _safe_unlink(path_str)
        if purged_count:
            logger.info("Purge automatique : %d tâche(s) expirée(s) supprimée(s).", purged_count)
        return purged_count