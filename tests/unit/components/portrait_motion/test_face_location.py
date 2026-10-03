"""The face box is a syntax and bounds contract only: never a judgment of animation."""

from __future__ import annotations

from typing import Any

import pytest

from stage_gen.components.portrait_motion.face_location import locator_schema, validate_location


def test_a_located_box_and_a_reasoned_refusal_are_both_answers() -> None:
    located = {"status": "located", "bbox_xyxy": [100, 80, 400, 420], "reason": "One face."}
    assert validate_location(located) == located
    refused = {"status": "not_locatable", "bbox_xyxy": None, "reason": "No face is drawn."}
    assert validate_location(refused) == refused
    assert locator_schema()["required"] == ["status", "bbox_xyxy", "reason"]


@pytest.mark.parametrize(
    "value",
    [
        {
            "status": "located",
            "bbox_xyxy": [True, 0, 100, 100],
            "reason": "Boolean is not a coordinate.",
        },
        {"status": "located", "bbox_xyxy": [0, 0, 1001, 100], "reason": "Outside the image."},
        {"status": "located", "bbox_xyxy": [400, 0, 100, 100], "reason": "Left after right."},
        {"status": "not_locatable", "bbox_xyxy": [0, 0, 100, 100], "reason": "Contradictory box."},
        {"status": "located", "bbox_xyxy": [0, 0, 100, 100], "reason": " "},
    ],
)
def test_location_bounds_are_syntax_checks_only(value: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        validate_location(value)
