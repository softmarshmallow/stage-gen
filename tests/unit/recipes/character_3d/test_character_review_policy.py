"""Explicit review opt-out is validated independently of review quality."""

from __future__ import annotations

from typing import Any

import pytest

from stage_gen.recipes.character_3d.experiment import validate_experiment
from stage_gen.recipes.character_3d.review_policy import review_mode
from tests.unit.recipes.character_3d.test_character_provider_flow import experiment


def test_omission_keeps_existing_required_review_without_mutating_input() -> None:
    request = experiment()
    assert review_mode(validate_experiment(request)) == "required"
    assert "review_mode" not in request


@pytest.mark.parametrize("mode", ["required", "none"])
def test_review_policy_is_independent_of_quality_bar(mode: str) -> None:
    request = {**experiment(), "review_mode": mode, "review_quality_bar": "medium"}
    assert review_mode(validate_experiment(request)) == mode
    assert request["review_quality_bar"] == "medium"


@pytest.mark.parametrize("mode", [None, False, 0, "off", "advisory", []])
def test_unknown_review_modes_are_refused_offline(mode: Any) -> None:
    with pytest.raises(ValueError, match="review_mode"):
        validate_experiment({**experiment(), "review_mode": mode})


def test_review_calibration_cannot_skip_its_review() -> None:
    request = {**experiment(), "pipeline_mode": "rig_review_calibration", "review_mode": "none"}
    with pytest.raises(ValueError, match="Review calibration requires"):
        validate_experiment(request)
