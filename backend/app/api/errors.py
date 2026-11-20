"""Gestion centralisée des erreurs HTTP au format ErrorResponse du contrat v1."""
from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas import ErrorInfo, ErrorResponse


class ApiError(Exception):
    """Erreur métier/API traduite en JSON conforme au contrat."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _error_payload(code: str, message: str) -> dict:
    return ErrorResponse(error=ErrorInfo(code=code, message=message)).model_dump()


def install_error_handlers(app: FastAPI) -> None:
    """Enregistre les gestionnaires d'erreurs sans exposer de données médicales."""

    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(exc.code, exc.message),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "invalid_request"
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(code, "Ressource introuvable ou requête refusée."),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_error_payload(
                "invalid_request",
                "Requête invalide ou champ obligatoire manquant.",
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_payload(
                "internal_error",
                "Une erreur interne est survenue pendant le traitement.",
            ),
        )