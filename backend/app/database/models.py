"""Modèles relationnels SQLAlchemy couvrant les entités du domaine LabMind."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Classe de base des modèles SQLAlchemy LabMind."""


class TaskDB(Base):
    """Tâche racine identifiée par UUID4 avec date d'expiration (rétention)."""

    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    detected_categories_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    pending_question_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanations_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    document: Mapped[DocumentDB | None] = relationship(
        back_populates="task",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    extraction_result: Mapped[ExtractionResultDB | None] = relationship(
        back_populates="task",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    parameters: Mapped[list[ParameterDB]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    agent_run: Mapped[AgentRunDB | None] = relationship(
        back_populates="task",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    retrieved_passages: Mapped[list[RetrievedPassageDB]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    report: Mapped[ReportDB | None] = relationship(
        back_populates="task",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DocumentDB(Base):
    """Métadonnées du fichier déposé (supprimé dès la fin du traitement)."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tasks.task_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_from_disk: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    task: Mapped[TaskDB] = relationship(back_populates="document")


class ExtractionResultDB(Base):
    """Résumé technique de l'extraction (sans conserver tout le texte brut)."""

    __tablename__ = "extraction_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tasks.task_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    task: Mapped[TaskDB] = relationship(back_populates="extraction_result")


class ParameterDB(Base):
    """Paramètre biologique extrait, validé techniquement et rattaché à une preuve."""

    __tablename__ = "parameters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tasks.task_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name_printed: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_origin: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_raw_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_page: Mapped[int | None] = mapped_column(Integer, nullable=True)

    task: Mapped[TaskDB] = relationship(back_populates="parameters")


class AgentRunDB(Base):
    """Exécution de l'agent associée à une tâche."""

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tasks.task_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    iterations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_iterations: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    question_counter: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    knowledge_searched: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    task: Mapped[TaskDB] = relationship(back_populates="agent_run")
    steps: Mapped[list[AgentStepDB]] = relationship(
        back_populates="agent_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AgentStepDB.step_number",
    )


class AgentStepDB(Base):
    """Trace d'une décision / action de l'agent."""

    __tablename__ = "agent_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    agent_run: Mapped[AgentRunDB] = relationship(back_populates="steps")


class KnowledgeSourceDB(Base):
    """Métadonnées d'une source documentaire officielle (sans donnée patient)."""

    __tablename__ = "knowledge_sources"

    source_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    organisme: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    published_date: Mapped[str | None] = mapped_column(String(32), nullable=True)


class RetrievedPassageDB(Base):
    """Passage documentaire récupéré par le RAG pour une tâche donnée."""

    __tablename__ = "retrieved_passages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tasks.task_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("knowledge_sources.source_id", ondelete="RESTRICT"),
        nullable=False,
    )
    passage_id: Mapped[str] = mapped_column(String(128), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)

    task: Mapped[TaskDB] = relationship(back_populates="retrieved_passages")
    source: Mapped[KnowledgeSourceDB] = relationship()


class ReportDB(Base):
    """Métadonnées du rapport PDF généré pour une tâche terminée."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tasks.task_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    report_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    task: Mapped[TaskDB] = relationship(back_populates="report")