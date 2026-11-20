"""Script de démonstration : exécute l'agent sur un PDF ambigu et affiche ses traces."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.agent import AgentOrchestrator, AgentState  # noqa: E402
from app.schemas import AnswerIn, TaskStatus  # noqa: E402


def _create_demo_pdf(path: Path) -> None:
    styles = getSampleStyleSheet()
    elements = [
        Paragraph("<b>Laboratoire Demo</b>", styles["Title"]),
        Paragraph("Hématocrite : 42,0 (réf. : 37,0 - 47,0)", styles["Normal"]),
        Paragraph("Glycémie : 0,92 g/L (réf. : 0,70 - 1,10)", styles["Normal"]),
    ]
    SimpleDocTemplate(str(path), pagesize=A4).build(elements)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / "bilan_demo.pdf"
        _create_demo_pdf(pdf_path)

        orchestrator = AgentOrchestrator()
        state = AgentState(
            task_id="demo-agent-001",
            file_path=str(pdf_path),
            filename=pdf_path.name,
        )

        print("=== Phase 1 : Lancement de l'agent ===")
        state = orchestrator.run(state)
        print("Statut après phase 1 :", state.status.value)

        if state.status == TaskStatus.waiting_for_user and state.pending_question:
            q = state.pending_question
            print(f"Question posée [{q.question_id}] : {q.message}")
            print(f"Options proposées : {q.options}")

            print("\n=== Phase 2 : Réponse utilisateur ('%') et reprise ===")
            state = orchestrator.resume(
                state,
                AnswerIn(question_id=q.question_id, answer="%"),
            )

        print("\n=== Trace complète des décisions de l'agent ===")
        for step in state.steps:
            print(
                f"[{step.step_number}] outil={step.tool.value} | ok={step.success} | "
                f"raison={step.reason} -> {step.summary}"
            )

        print("\n=== Objet Task final (contrat API v1) ===")
        print(state.to_task(report_id="r-demo-001").model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())