"""The answer key for `make regression` still fits the code it plants defects in.

`make regression` itself plants each defect and checks what catches it (it
rebuilds everything per plant). These checks are quick, so `make test`
notices when the code moves on, and they pin how a plant's outcome is judged.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from app.paths import REPO_ROOT
from app.regression import Outcome, apply
from app.regression_key import PLANTS, STAGES, Plant


@pytest.mark.parametrize("plant", PLANTS, ids=lambda p: p.name)
def test_each_plant_still_applies(plant: Plant) -> None:
    text = (REPO_ROOT / plant.file).read_text()
    assert text.count(plant.old) == 1, (
        f"{plant.file} no longer contains the text {plant.name} edits"
    )
    assert plant.new != plant.old


@pytest.mark.parametrize("plant", PLANTS, ids=lambda p: p.name)
def test_each_answer_names_its_evidence(plant: Plant) -> None:
    """A caught plant names the message to expect; a blind spot expects none."""
    assert (plant.caught_at is None) == (plant.message == ""), plant.name
    assert plant.why


def test_the_key_covers_every_stage_and_a_blind_spot() -> None:
    assert {p.caught_at for p in PLANTS} == {*STAGES, None}
    assert len({p.name for p in PLANTS}) == len(PLANTS)


CAUGHT = Plant("p", "d", "f", "old", "new", "tests", "the message", "why")
BLIND = replace(CAUGHT, caught_at=None, message="")


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (Outcome(CAUGHT, "tests", "... the message ..."), True),
        (Outcome(CAUGHT, "tests", "some other failure"), False),  # right stage, wrong reason
        (Outcome(CAUGHT, "smoke", "... the message ..."), False),  # wrong stage
        (Outcome(CAUGHT, None, "... the message ..."), False),  # not caught at all
        (Outcome(BLIND, None, "", ("sum/trace.json",)), True),
        (Outcome(BLIND, None, "", ()), False),  # passed, but the edit changed nothing
        (Outcome(BLIND, "artifacts", "", ("sum/trace.json",)), False),  # caught after all
    ],
)
def test_how_an_outcome_is_judged(outcome: Outcome, expected: bool) -> None:
    assert outcome.as_expected is expected


@pytest.mark.parametrize("text", ["no match here", "old and old"])
def test_apply_refuses_text_that_does_not_occur_exactly_once(tmp_path: Path, text: str) -> None:
    (tmp_path / "f").write_text(text)
    with pytest.raises(ValueError, match="does not contain its text exactly once"):
        apply(CAUGHT, tmp_path)
    assert (tmp_path / "f").read_text() == text


def test_apply_makes_the_one_edit(tmp_path: Path) -> None:
    (tmp_path / "f").write_text("keep old keep")
    apply(CAUGHT, tmp_path)
    assert (tmp_path / "f").read_text() == "keep new keep"
