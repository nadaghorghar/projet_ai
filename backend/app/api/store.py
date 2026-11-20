"""Gestionnaire de tâches appuyé sur SQLite (`TaskRepository`), l'agent et le rapport PDF."""
from __future__ import annotations

import logging
import threading
import uuid
from pathlib import Path
from typing import Callable

from app.agent import AgentOrchestrator, AgentState
from app.core.config import Settings
from app.database import (
    TaskRepository,
    create_db_engine,
    create_session_factory,
    init_db,
)
from app.report import build_labmind_report_pdf
from app.schemas import AnswerIn, ErrorInfo, Task, TaskStatus

logger = logging.getLogger("labmind.api")


class TaskNotFoundError(Exception):
    """Levée lorsqu'une tâche est inconnue, expirée ou déjà supprimée."""


class ReportNotReadyError(Exception):
    """Levée lorsque le téléchargement PDF est demandé avant l'état `done`."""


def _cleanup_file(file_path: str | Path) -> None:
    try:
        path = Path(file_path)
        if path.is_file():
            path.unlink()
    except OSError:
        logger.warning("Impossible de supprimer un fichier temporaire.")


class TaskManager:
    """Gestionnaire thread-safe des tâches persistées dans SQLite."""

    def __init__(
        self,
        settings: Settings,
        orchestrator_factory: Callable[[], AgentOrchestrator] | None = None,
        report_builder: Callable[[Task], bytes] | None = None,
        repository: TaskRepository | None = None,
    ) -> None:
        self.settings = settings
        self._orchestrator_factory = orchestrator_factory or AgentOrchestrator
        self._report_builder = report_builder or build_labmind_report_pdf
        self._lock = threading.RLock()

        if repository is None:
            settings.ensure_dirs()
            engine = create_db_engine(settings.resolved_database_url)
            init_db(engine)
            self._engine = engine
            self._repository = TaskRepository(
                create_session_factory(engine),
                retention_seconds=settings.retention_seconds,
            )
        else:
            self._engine = None
            self._repository = repository

    def close(self) -> None:
        """Libère les connexions de base de données à l'arrêt du serveur."""
        if self._engine is not None:
            self._engine.dispose()

    def purge_expired(self) -> int:
        """Supprime les tâches dépassant la durée de conservation."""
        with self._lock:
            return self._repository.purge_expired_tasks()

    def create_task(self, original_filename: str, content: bytes) -> Task:
        """Enregistre le fichier sous un nom technique UUID4 et crée la tâche en base."""
        self.settings.ensure_dirs()
        task_id = str(uuid.uuid4())
        safe_name = Path(original_filename or "document").name
        suffix = Path(safe_name).suffix.lower()
        target_path = self.settings.uploads_dir / f"{task_id}{suffix}"
        target_path.write_bytes(content)

        state = AgentState(
            task_id=task_id,
            file_path=str(target_path),
            filename=safe_name,
            status=TaskStatus.received,
        )
        with self._lock:
            self._repository.purge_expired_tasks()
            task = self._repository.save_state(state, file_deleted=False)
            logger.info("Tâche créée : %s", task_id)
            return task

    def process_task(self, task_id: str) -> None:
        """Exécute la boucle agentique et persiste le nouvel état."""
        with self._lock:
            loaded = self._repository.load_state(task_id)
            if loaded is None:
                return
            state, report_id, _ = loaded
            state.status = TaskStatus.processing
            self._repository.save_state(state, report_id=report_id)

        orchestrator = self._orchestrator_factory()
        try:
            orchestrator.run(state)
        except Exception as exc:
            logger.exception("Erreur interne lors du traitement de la tâche %s", task_id)
            state.status = TaskStatus.error
            state.error = ErrorInfo(
                code="internal_error",
                message=f"Erreur interne lors de l'analyse : {exc}",
            )

        with self._lock:
            if state.status == TaskStatus.done and report_id is None:
                report_id = f"r-{task_id[:8]}"
            if state.status in (TaskStatus.done, TaskStatus.error):
                _cleanup_file(state.file_path)
            self._repository.save_state(state, report_id=report_id)
            logger.info("Tâche %s -> statut %s", task_id, state.status.value)

    def get_task(self, task_id: str) -> Task | None:
        """Retourne la vue API `Task` si existante et non expirée."""
        with self._lock:
            return self._repository.get_task(task_id)

    def answer_task(self, task_id: str, answer_in: AnswerIn) -> Task:
        """Soumet une réponse utilisateur, reprend l'agent et sauvegarde en base."""
        with self._lock:
            loaded = self._repository.load_state(task_id)
            if loaded is None:
                raise TaskNotFoundError(task_id)
            state, report_id, report_pdf_path = loaded

        orchestrator = self._orchestrator_factory()
        orchestrator.resume(state, answer_in)

        with self._lock:
            if state.status == TaskStatus.done and report_id is None:
                report_id = f"r-{task_id[:8]}"
            if state.status in (TaskStatus.done, TaskStatus.error):
                _cleanup_file(state.file_path)
            task = self._repository.save_state(
                state,
                report_id=report_id,
                report_pdf_path=report_pdf_path,
            )
            logger.info("Réponse traitée pour %s -> statut %s", task_id, state.status.value)
            return task

    def get_report_pdf(self, task_id: str) -> tuple[bytes, str]:
        """Retourne (contenu_pdf, nom_fichier) si la tâche est terminée."""
        with self._lock:
            loaded = self._repository.load_state(task_id)
            if loaded is None:
                raise TaskNotFoundError(task_id)
            state, report_id, existing_pdf_path = loaded
            if state.status != TaskStatus.done:
                raise ReportNotReadyError(
                    "Le rapport PDF n'est disponible que lorsque la tâche est terminée."
                )
            if report_id is None:
                report_id = f"r-{task_id[:8]}"
            task_snapshot = state.to_task(report_id=report_id)

        self.settings.ensure_dirs()
        pdf_path = (
            Path(existing_pdf_path)
            if existing_pdf_path
            else self.settings.reports_dir / f"{report_id}.pdf"
        )
        if not pdf_path.is_file():
            pdf_bytes = self._report_builder(task_snapshot)
            pdf_path.write_bytes(pdf_bytes)
            with self._lock:
                self._repository.set_report_pdf_path(task_id, report_id, str(pdf_path))
        else:
            pdf_bytes = pdf_path.read_bytes()

        return pdf_bytes, f"labmind_rapport_{task_id[:8]}.pdf"

    def delete_task(self, task_id: str) -> bool:
        """Supprime immédiatement la tâche en base ainsi que ses fichiers."""
        with self._lock:
            return self._repository.delete_task(task_id)