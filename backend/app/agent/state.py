"""État explicite, traces de décision et conversion vers le contrat API v1."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from app.generation.interface import GenerationResult, RetrievedPassage
from app.identification.catalog import get_categories_for_codes
from app.schemas import (
    DISCLAIMER,
    DocumentInfo,
    ErrorInfo,
    ExtractionMethod,
    ParameterResult,
    PendingQuestion,
    Task,
    TaskStatus,
)


class ToolName(str, Enum):
    """Ensemble des outils disponibles pour l'agent LabMind."""

    extract_pdf_text = "extract_pdf_text"
    extract_ocr = "extract_ocr"
    identify_and_validate = "identify_and_validate"
    request_user_confirmation = "request_user_confirmation"
    retrieve_knowledge = "retrieve_knowledge"
    generate_explanations = "generate_explanations"
    finish = "finish"
    fail = "fail"


class UncertaintyItem(BaseModel):
    """Incertitude technique détectée nécessitant une confirmation utilisateur."""

    code: str
    name_printed: str
    field: Literal["unit", "value", "reference_min", "reference_max"]
    reason_code: str
    options: list[str] = Field(default_factory=list)
    resolved: bool = False
    user_answer: str | None = None


class AgentStep(BaseModel):
    """Trace vérifiable d'une itération de la boucle agentique."""

    step_number: int
    tool: ToolName
    reason: str
    success: bool
    summary: str


class AgentState(BaseModel):
    """État complet observé et mis à jour à chaque action de l'agent."""

    task_id: str
    file_path: str
    filename: str
    status: TaskStatus = TaskStatus.received

    extraction_method: ExtractionMethod | None = None
    tried_pdf_text: bool = False
    tried_ocr: bool = False
    raw_text: str = ""
    extracted_pages: list[dict] = Field(default_factory=list)

    raw_parameters: list[dict] = Field(default_factory=list)
    validated_parameters: list[ParameterResult] = Field(default_factory=list)
    uncertainties: list[UncertaintyItem] = Field(default_factory=list)

    pending_question: PendingQuestion | None = None
    question_counter: int = 0

    knowledge_searched: bool = False
    retrieved_passages: list[RetrievedPassage] = Field(default_factory=list)
    lifestyle_passages: list[RetrievedPassage] = Field(default_factory=list)
    generation_result: GenerationResult | None = None

    iterations: int = 0
    max_iterations: int = 12
    steps: list[AgentStep] = Field(default_factory=list)
    error: ErrorInfo | None = None

    def unresolved_uncertainties(self) -> list[UncertaintyItem]:
        """Retourne les incertitudes encore en attente de confirmation."""
        return [item for item in self.uncertainties if not item.resolved]

    def record_step(
        self,
        tool: ToolName,
        reason: str,
        success: bool,
        summary: str,
    ) -> None:
        """Ajoute une étape traçable à l'historique de l'agent."""
        self.steps.append(
            AgentStep(
                step_number=len(self.steps) + 1,
                tool=tool,
                reason=reason,
                success=success,
                summary=summary,
            )
        )

    def to_task(self, report_id: str | None = None) -> Task:
        """Projette l'état interne de l'agent vers l'objet `Task` du contrat API v1."""
        explanations = (
            self.generation_result.to_task_explanations()
            if self.generation_result is not None
            else None
        )
        sources = (
            self.generation_result.sources
            if self.generation_result is not None
            else []
        )
        disclaimer = (
            self.generation_result.disclaimer
            if self.generation_result is not None
            else DISCLAIMER
        )
        detected_categories = get_categories_for_codes(
            [p.code for p in self.validated_parameters]
        )

        return Task(
            task_id=self.task_id,
            status=self.status,
            document=DocumentInfo(
                filename=self.filename,
                extraction_method=self.extraction_method,
            ),
            detected_categories=detected_categories,
            parameters=self.validated_parameters,
            pending_question=self.pending_question,
            report_id=report_id if self.status == TaskStatus.done else None,
            explanations=explanations,
            sources=sources,
            disclaimer=disclaimer,
            errors=[self.error] if self.error is not None else [],
        )