"""Module de génération d'explications pédagogiques sourcées."""

from .fallback import (
    INSUFFICIENT_SOURCES_PARAMETER_MESSAGE,
    INSUFFICIENT_SOURCES_SUMMARY,
    NOT_ANALYZED_PARAMETER_MESSAGE,
    InsufficientSourcesGenerator,
    build_unavailable_explanation,
)
from .grounding import (
    GroundingCheckResult,
    check_explanation_grounding,
    check_safety_compliance,
)
from .interface import (
    ExplanationGenerator,
    ExplanationStatus,
    GenerationRequest,
    GenerationResult,
    ParameterExplanation,
    RetrievedPassage,
    find_citation_errors,
)
from .llm_client import (
    DEFAULT_LLM_MODEL,
    DEFAULT_OLLAMA_URL,
    LocalLLMClient,
    LocalLLMError,
    OllamaLLMClient,
)
from .rag import (
    GROUNDED_SUMMARY,
    RagExplanationGenerator,
    build_parameter_prompt,
    parse_llm_explanation,
)

__all__ = [
    "DEFAULT_LLM_MODEL",
    "DEFAULT_OLLAMA_URL",
    "ExplanationGenerator",
    "ExplanationStatus",
    "GROUNDED_SUMMARY",
    "GenerationRequest",
    "GenerationResult",
    "GroundingCheckResult",
    "INSUFFICIENT_SOURCES_PARAMETER_MESSAGE",
    "INSUFFICIENT_SOURCES_SUMMARY",
    "InsufficientSourcesGenerator",
    "LocalLLMClient",
    "LocalLLMError",
    "NOT_ANALYZED_PARAMETER_MESSAGE",
    "OllamaLLMClient",
    "ParameterExplanation",
    "RagExplanationGenerator",
    "RetrievedPassage",
    "build_parameter_prompt",
    "build_unavailable_explanation",
    "check_explanation_grounding",
    "check_safety_compliance",
    "find_citation_errors",
    "parse_llm_explanation",
]