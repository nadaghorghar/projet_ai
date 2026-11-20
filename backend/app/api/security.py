"""Contrôles de sécurité des fichiers déposés, identifiants et en-têtes HTTP."""
from __future__ import annotations

import io
import uuid
from pathlib import Path

from fastapi import status
from PIL import Image, UnidentifiedImageError

from .errors import ApiError

_PDF_MAGIC = b"%PDF-"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"


def sanitize_filename(raw_filename: str | None) -> str:
    """Retourne un nom de fichier sûr sans chemin parent."""
    if not raw_filename:
        return "document"
    cleaned = raw_filename.replace("\\", "/").split("/")[-1].strip()
    return Path(cleaned).name or "document"


def validate_upload_file(
    raw_filename: str | None,
    content: bytes,
    max_upload_bytes: int,
    allowed_extensions: tuple[str, ...],
) -> str:
    """Valide extension, taille non nulle, signature binaire (magic bytes) et intégrité image."""
    safe_name = sanitize_filename(raw_filename)
    suffix = Path(safe_name).suffix.lower()

    if suffix not in allowed_extensions:
        raise ApiError(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "unsupported_format",
            "Format non supporté (pdf, png, jpg, jpeg).",
        )

    if not content:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "invalid_request",
            "Le fichier déposé est vide.",
        )

    if len(content) > max_upload_bytes:
        raise ApiError(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "file_too_large",
            f"Le fichier dépasse la limite autorisée ({max_upload_bytes} octets).",
        )

    if suffix == ".pdf":
        if not content[:1024].lstrip().startswith(_PDF_MAGIC):
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "unreadable_document",
                "Le fichier déposé n'a pas une signature PDF valide.",
            )
    elif suffix == ".png":
        if not content.startswith(_PNG_MAGIC):
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "unreadable_document",
                "Le fichier déposé n'a pas une signature PNG valide.",
            )
        _verify_image_bytes(content)
    elif suffix in (".jpg", ".jpeg"):
        if not content.startswith(_JPEG_MAGIC):
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "unreadable_document",
                "Le fichier déposé n'a pas une signature JPEG valide.",
            )
        _verify_image_bytes(content)

    return safe_name


def _verify_image_bytes(content: bytes) -> None:
    try:
        with Image.open(io.BytesIO(content)) as img:
            img.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "unreadable_document",
            "L'image déposée est corrompue ou illisible.",
        ) from exc


def validate_task_id_or_404(task_id: str) -> str:
    """Vérifie que task_id est un UUID valide pour empêcher tout path traversal."""
    try:
        parsed = uuid.UUID(task_id)
    except ValueError as exc:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "task_not_found",
            "Tâche introuvable ou supprimée.",
        ) from exc
    return str(parsed)