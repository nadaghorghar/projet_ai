import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas import AnswerIn, ErrorResponse, Task, TaskStatus

EXAMPLES = Path(__file__).resolve().parents[2] / "docs" / "api-contract" / "examples"


def _load(name):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name,statut", [
    ("task_processing.json", TaskStatus.processing),
    ("task_waiting_for_user.json", TaskStatus.waiting_for_user),
    ("task_done.json", TaskStatus.done),
])
def test_exemples_de_taches_valides(name, statut):
    t = Task.model_validate(_load(name))
    assert t.status == statut


def test_question_seulement_en_attente():
    assert Task.model_validate(_load("task_waiting_for_user.json")).pending_question is not None
    assert Task.model_validate(_load("task_done.json")).pending_question is None


def test_exemple_d_erreur_valide():
    e = ErrorResponse.model_validate(_load("error_unsupported_format.json"))
    assert e.error.code == "unsupported_format"


def test_disclaimer_toujours_present():
    d = _load("task_done.json")
    del d["disclaimer"]
    assert Task.model_validate(d).disclaimer  # valeur par défaut


def test_reponse_vide_refusee():
    with pytest.raises(ValidationError):
        AnswerIn(question_id="q-001", answer="")


def test_champ_de_question_invalide_refuse():
    d = _load("task_waiting_for_user.json")
    d["pending_question"]["field"] = "diagnostic"
    with pytest.raises(ValidationError):
        Task.model_validate(d)