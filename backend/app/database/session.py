"""Initialisation du moteur SQLAlchemy et activation des clés étrangères SQLite."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return
    raw_path = database_url[len(prefix) :].split("?", 1)[0]
    if raw_path and raw_path != ":memory:":
        Path(raw_path).parent.mkdir(parents=True, exist_ok=True)


def create_db_engine(database_url: str) -> Engine:
    """Crée un moteur SQLAlchemy configuré pour SQLite (FK ON) ou PostgreSQL."""
    is_sqlite = database_url.startswith("sqlite")
    if is_sqlite:
        _ensure_sqlite_parent_dir(database_url)
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            future=True,
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine

    return create_engine(database_url, future=True)


def init_db(engine: Engine) -> None:
    """Crée les tables si elles n'existent pas encore."""
    Base.metadata.create_all(bind=engine)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Fabrique de sessions transactionnelles."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)