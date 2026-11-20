from __future__ import annotations

import json
from pathlib import Path

from app.agent.state import AgentState
from app.agent.tools import run_generate_explanations, run_retrieve_knowledge
from app.extraction.extractor import extract_pdf_native_pages
from app.generation.interface import ExplanationStatus, RetrievedPassage
from app.generation.rag import RagExplanationGenerator
from app.knowledge.registry import MedicalCategory
from app.report.pdf_generator import build_labmind_report_pdf
from app.schemas import DISCLAIMER, ParameterResult, ParameterStatus, Source, TaskStatus


class _DualCategoryFakeIndex:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[MedicalCategory] | None]] = []
        self._bio = RetrievedPassage(
            passage_id="ameli-fer-01",
            source=Source(
                source_id="ameli-fer-2026",
                title="Comprendre le bilan martial",
                organisme="Assurance Maladie",
                url="https://www.ameli.fr/assure/sante/examen/analyse/ferritine",
                date="2026-01-08",
            ),
            excerpt=(
                "La ferritine reflète les réserves en fer de l'organisme. "
                "Une interprétation médicale tient compte du contexte clinique."
            ),
            score=0.92,
        )
        self._lifestyle = RetrievedPassage(
            passage_id="anses-lifestyle-01",
            source=Source(
                source_id="anses-reperes-2026",
                title="Repères nutritionnels et activité physique",
                organisme="ANSES",
                url="https://www.anses.fr/fr/content/les-reperes-nutritionnels",
                date="2026-02-01",
            ),
            excerpt=(
                "Une alimentation variée comprenant des fruits, des légumes, "
                "des légumineuses et une activité physique régulière contribue "
                "aux repères généraux d'hygiène de vie."
            ),
            score=0.87,
        )

    def search(
        self,
        query: str,
        top_k: int = 5,
        categories: list[MedicalCategory] | None = None,
        min_score: float = 0.0,
    ) -> list[RetrievedPassage]:
        self.calls.append((query, categories))
        if categories == [MedicalCategory.hygiene_de_vie]:
            return [self._lifestyle][:top_k]
        return [self._bio][:top_k]


class _QueuedLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        return self._responses.pop(0)


def test_agent_tools_and_pdf_render_lifestyle_and_questions(tmp_path: Path) -> None:
    state = AgentState(
        task_id="task-10-2",
        file_path="bilan.pdf",
        filename="bilan.pdf",
        status=TaskStatus.processing,
        validated_parameters=[
            ParameterResult.model_validate(
                {
                    "code": "FER",
                    "name_printed": "Ferritine",
                    "value": 12.0,
                    "unit": "ng/mL",
                    "reference": {
                        "min": 15.0,
                        "max": 150.0,
                        "origin": "document_laboratoire",
                    },
                    "status": ParameterStatus.below_reference,
                    "confidence": 0.95,
                    "evidence": {"raw_text": "Ferritine : 12 ng/mL", "page": 1},
                }
            )
        ],
    )

    fake_index = _DualCategoryFakeIndex()
    retrieve_res = run_retrieve_knowledge(state, knowledge_index=fake_index)
    assert retrieve_res.success is True
    assert len(state.retrieved_passages) == 1
    assert len(state.lifestyle_passages) == 1

    llm = _QueuedLLM(
        [
            json.dumps(
                {
                    "status": "grounded",
                    "text": (
                        "La ferritine reflète les réserves en fer de l'organisme "
                        "dans le contexte clinique."
                    ),
                    "source_ids": ["ameli-fer-2026"],
                }
            ),
            json.dumps(
                {
                    "status": "grounded",
                    "text": (
                        "Une alimentation variée avec des fruits, des légumes, "
                        "des légumineuses et une activité physique régulière "
                        "correspond aux repères généraux d'hygiène de vie."
                    ),
                    "source_ids": ["anses-reperes-2026"],
                }
            ),
            json.dumps(
                {
                    "questions": [
                        "Comment interpréter cette ferritine selon mes symptômes ?",
                        "Un contrôle biologique est-il pertinent lors du prochain suivi ?",
                    ]
                }
            ),
        ]
    )

    generator = RagExplanationGenerator(llm_client=llm, min_overlap_ratio=0.25)
    gen_res = run_generate_explanations(state, generator=generator)
    assert gen_res.success is True
    assert state.generation_result is not None
    assert state.generation_result.lifestyle_info is not None
    assert state.generation_result.lifestyle_info.status == ExplanationStatus.grounded
    assert len(state.generation_result.consultation_questions) == 2

    state.status = TaskStatus.done
    task = state.to_task(report_id="rep-10-2")
    assert task.explanations is not None
    assert task.explanations["lifestyle_info"]["status"] == "grounded"
    assert len(task.explanations["consultation_questions"]) == 2
    assert {s.source_id for s in task.sources} == {
        "ameli-fer-2026",
        "anses-reperes-2026",
    }

    pdf_bytes = build_labmind_report_pdf(task)
    pdf_path = tmp_path / "rapport_10_2.pdf"
    pdf_path.write_bytes(pdf_bytes)

    pages = extract_pdf_native_pages(pdf_path)
    full_text = " ".join(page.get("text", "") for page in pages)
    normalized = " ".join(full_text.split())

    assert "Informations générales documentées (hygiène de vie)" in normalized
    assert "anses-reperes-2026" in normalized
    assert "Questions à préparer pour votre médecin" in normalized
    assert "Comment interpréter cette ferritine selon mes symptômes ?" in normalized
    assert normalized.count(" ".join(DISCLAIMER.split())) == 1