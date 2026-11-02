"""The answer key for `make regression` still fits the code it plants defects in.

`make regression` itself plants each defect and checks what catches it (minutes).
These checks are quick, so `make test` notices when the code moves on.
"""

import pytest

from app.paths import REPO_ROOT
from app.regression_key import PLANTS, Plant


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
    assert {p.caught_at for p in PLANTS} == {"artifacts", "smoke", None}
    assert len({p.name for p in PLANTS}) == len(PLANTS)
