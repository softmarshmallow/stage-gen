"""Offline layout, state and operation-budget contracts for portrait motion."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from stage_gen.components.portrait_motion.models import PortraitMotionSpec, StageReceipt


def specification() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "width": 128,
        "height": 128,
        "columns": 2,
        "rows": 1,
        "states": [
            {"state_id": "blink", "feature_group": "eyes", "instruction": "Close visible eyes."},
            {"state_id": "mouth_a", "feature_group": "mouth", "instruction": "Open mouth for A."},
        ],
        "requested_features": ["canvas_left_eye", "canvas_right_eye", "mouth"],
        "feather_panel_px": 3.0,
        "playback": [
            {"eyes": "rest", "mouth": "rest", "duration_ms": 100},
            {"eyes": "blink", "mouth": "mouth_a", "duration_ms": 100},
            {"eyes": "rest", "mouth": "rest", "duration_ms": 100},
        ],
    }


def test_valid_spec_keeps_declared_source_and_state_layout() -> None:
    spec = PortraitMotionSpec.model_validate(specification())
    assert spec.panel_size == (64, 128)
    assert [state.state_id for state in spec.states] == ["blink", "mouth_a"]
    assert spec.playback[0].eyes == spec.playback[-1].eyes == "rest"
    assert PortraitMotionSpec.model_validate_json(spec.model_dump_json()) == spec


def test_documented_four_card_example_keeps_independent_blink_and_mouth_states() -> None:
    """Bind docs/spec/portrait-motion.md to its executable four-card input."""
    repository = Path(__file__).resolve().parents[4]
    spec = PortraitMotionSpec.model_validate_json(
        (repository / "docs/examples/portrait-motion/four-card.json").read_bytes()
    )
    assert spec.panel_size == (512, 768)
    assert (spec.columns, spec.rows) == (2, 2)
    assert [(state.state_id, state.feature_group) for state in spec.states] == [
        ("eyes_half", "eyes"),
        ("eyes_closed", "eyes"),
        ("mouth_smile", "mouth"),
        ("mouth_a", "mouth"),
    ]
    assert sum(segment.duration_ms for segment in spec.playback) == 8000
    assert any(segment.eyes != "rest" and segment.mouth == "rest" for segment in spec.playback)
    assert any(segment.eyes == "rest" and segment.mouth != "rest" for segment in spec.playback)
    assert any(segment.eyes != "rest" and segment.mouth != "rest" for segment in spec.playback)


@pytest.mark.parametrize(
    "patch",
    [
        {"width": 127},
        {"height": 2049},
        {"width": 129},
        {"columns": 0},
        {"rows": 2},
        {"width": "128"},
        {"columns": True},
        {"states": []},
        {"requested_features": []},
        {"requested_features": ["jaw"]},
        {"requested_features": ["mouth", "mouth"]},
        {"schema_version": 2},
        {"feather_panel_px": -1.0},
        {"feather_panel_px": float("nan")},
        {"feather_panel_px": float("inf")},
        {"extra_field": "not allowed"},
    ],
)
def test_invalid_canvas_or_feature_contract_is_refused(patch: dict[str, Any]) -> None:
    value = specification()
    value.update(patch)
    with pytest.raises(ValidationError):
        PortraitMotionSpec.model_validate(value)


@pytest.mark.parametrize(
    "patch",
    [
        {"state_id": "../escape"},
        {"state_id": "/absolute"},
        {"state_id": "rest"},
        {"state_id": "mouth_a"},
        {"feature_group": "jaw"},
        {"instruction": ""},
        {"instruction": "x" * 1001},
    ],
)
def test_invalid_or_reserved_motion_state_is_refused(patch: dict[str, Any]) -> None:
    value = specification()
    value["states"][0].update(patch)
    with pytest.raises(ValidationError):
        PortraitMotionSpec.model_validate(value)


@pytest.mark.parametrize(
    "patch",
    [
        {"eyes": "missing"},
        {"eyes": "mouth_a"},
        {"mouth": "blink"},
        {"duration_ms": 19},
        {"duration_ms": 10001},
        {"duration_ms": True},
    ],
)
def test_playback_rejects_unknown_states_wrong_groups_and_unbounded_timing(
    patch: dict[str, Any],
) -> None:
    value = specification()
    value["playback"][1].update(patch)
    with pytest.raises(ValidationError):
        PortraitMotionSpec.model_validate(value)


@pytest.mark.parametrize("index", [0, -1])
def test_playback_requires_original_source_at_both_endpoints(index: int) -> None:
    value = specification()
    value["playback"][index]["eyes"] = "blink"
    with pytest.raises(ValidationError):
        PortraitMotionSpec.model_validate(value)


def test_playback_total_duration_is_bounded() -> None:
    value = specification()
    value["playback"] = [deepcopy(value["playback"][0]) for _ in range(7)]
    for segment in value["playback"]:
        segment["duration_ms"] = 10000
    with pytest.raises(ValidationError):
        PortraitMotionSpec.model_validate(value)


def test_requested_feature_must_have_a_state_family() -> None:
    value = specification()
    value.update(columns=1, rows=1)
    value["states"] = [value["states"][1]]
    value["playback"][1]["eyes"] = "rest"
    with pytest.raises(ValidationError):
        PortraitMotionSpec.model_validate(value)


@pytest.mark.parametrize("operations", [-1, 7, True, "1"])
def test_stage_receipt_operations_are_strict_and_bounded(operations: Any) -> None:
    with pytest.raises(ValidationError):
        StageReceipt.model_validate(
            {
                "stage": "admission",
                "node_cache_key": "a" * 64,
                "status": "passed",
                "reason": "Synthetic receipt",
                "files": {},
                "dependency_records": {},
                "provider_operations": operations,
            }
        )
