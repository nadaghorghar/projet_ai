"""Fabrique de l'application FastAPI LabMind avec en-têtes de confidentialité."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings

from .errors import install_error_handlers
from .routes import router
from .store import TaskManager


def create_app(
    settings: Settings | None = None,
    task_manager: TaskManager | None = None,
) -> FastAPI:
    """Construit l'instance FastAPI configurée avec ses routes et middlewares."""
    active_settings = settings or get_settings()
    active_settings.ensure_dirs()

    app = FastAPI(
        title="LabMind API",
        version="1.0.0",
        description="API pédagogique d'analyse de comptes rendus biologiques (sans diagnostic).",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(active_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_privacy_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    app.state.settings = active_settings
    app.state.task_manager = task_manager or TaskManager(settings=active_settings)

    install_error_handlers(app)
    app.include_router(router)
    return app