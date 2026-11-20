"""Routes HTTP /v1 conformes au contrat API v1 et durcies."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, File, Request, Response, UploadFile, status

from app.agent.orchestrator import InvalidAnswerError, InvalidQuestionStateError
from app.schemas import AnswerIn, Task

from .errors import ApiError
from .security import validate_task_id_or_404, validate_upload_file
from .store import ReportNotReadyError, TaskManager, TaskNotFoundError

router = APIRouter(prefix="/v1", tags=["tasks"])


def _get_manager(request: Request) -> TaskManager:
    return request.app.state.task_manager


@router.get("/health")
def health() -> dict[str, str]:
    """Vérifie que le service API répond."""
    return {"status": "ok"}


@router.post(
    "/tasks",
    response_model=Task,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_task(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> Task:
    """Dépose un document PDF ou image validé et démarre l'analyse en arrière-plan."""
    manager = _get_manager(request)
    settings = manager.settings

    content = file.file.read(settings.max_upload_bytes + 1)
    safe_name = validate_upload_file(
        raw_filename=file.filename,
        content=content,
        max_upload_bytes=settings.max_upload_bytes,
        allowed_extensions=settings.allowed_extensions,
    )

    task = manager.create_task(original_filename=safe_name, content=content)
    background_tasks.add_task(manager.process_task, task.task_id)
    return task


@router.get("/tasks/{task_id}", response_model=Task)
def get_task(task_id: str, request: Request) -> Task:
    """Retourne le statut et le résultat courant d'une tâche."""
    valid_id = validate_task_id_or_404(task_id)
    manager = _get_manager(request)
    task = manager.get_task(valid_id)
    if task is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "task_not_found",
            "Tâche introuvable ou supprimée.",
        )
    return task


@router.post("/tasks/{task_id}/answer", response_model=Task)
def answer_task(task_id: str, body: AnswerIn, request: Request) -> Task:
    """Transmet la réponse utilisateur à une question de l'agent et reprend le traitement."""
    valid_id = validate_task_id_or_404(task_id)
    manager = _get_manager(request)
    try:
        return manager.answer_task(valid_id, body)
    except TaskNotFoundError as exc:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "task_not_found",
            "Tâche introuvable ou supprimée.",
        ) from exc
    except InvalidQuestionStateError as exc:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "invalid_state",
            str(exc),
        ) from exc
    except InvalidAnswerError as exc:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_answer",
            str(exc),
        ) from exc


@router.get("/tasks/{task_id}/report.pdf")
def download_report_pdf(task_id: str, request: Request) -> Response:
    """Télécharge le rapport PDF lorsque la tâche est terminée (`done`)."""
    valid_id = validate_task_id_or_404(task_id)
    manager = _get_manager(request)
    try:
        pdf_bytes, filename = manager.get_report_pdf(valid_id)
    except TaskNotFoundError as exc:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "task_not_found",
            "Tâche introuvable ou supprimée.",
        ) from exc
    except ReportNotReadyError as exc:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "invalid_state",
            str(exc),
        ) from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str, request: Request) -> Response:
    """Supprime immédiatement la tâche, son fichier uploadé et son rapport."""
    valid_id = validate_task_id_or_404(task_id)
    manager = _get_manager(request)
    deleted = manager.delete_task(valid_id)
    if not deleted:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "task_not_found",
            "Tâche introuvable ou déjà supprimée.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)