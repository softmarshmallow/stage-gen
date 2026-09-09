"""Credential-free policy checks for valid refusals and narrow feature admission."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, cast

import pytest

from stage_gen.components.portrait_motion import review

FEATURES: list[str] = list(review.FEATURE_IDS)
STATES: list[dict[str, Any]] = [
    {"state_id": "eyes_half", "feature_group": "eyes", "instruction": "Half blink."},
    {"state_id": "eyes_closed", "feature_group": "eyes", "instruction": "Closed eyes."},
    {"state_id": "mouth_smile", "feature_group": "mouth", "instruction": "Small smile."},
    {"state_id": "mouth_a", "feature_group": "mouth", "instruction": "Open A drawing."},
]


def admission() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "subject_count": 1,
        "subject_unambiguous": True,
        "image_readable": True,
        "features": [
            {
                "feature_id": feature,
                "route": "direct",
                "source_state": "rest" if feature == "mouth" else "open",
                "reason": "clear_feature",
                "evidence": "The complete feature and surrounding skin are readable.",
                "confidence": "high",
            }
            for feature in FEATURES
        ],
    }


def geometry(features: list[str]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "pass",
        "coordinate_space": "registered_panel_pixels",
        "canvas_size": [512, 768],
        "features": [
            {"feature_id": feature, "points": [[10, 10], [20, 10], [15, 20]]}
            for feature in features
        ],
        "reason": "Each opaque core encloses old and new artwork.",
    }


def quality(features: list[str]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "pass",
        "features": [
            {"feature_id": feature, "status": "pass", "reason": "All supplied stills are clean."}
            for feature in features
        ],
        "reason": "All admitted features pass still review.",
        "temporal_review": "not_performed",
    }


def test_one_eye_and_mouth_remain_eligible_when_other_eye_is_hidden() -> None:
    data = admission()
    data["features"][0].update(route="hidden", source_state="unknown", reason="opaque_fully_hidden")
    original = deepcopy(data)
    result = review.validate_admission(data, FEATURES)
    assert result["eligible_features"] == ["canvas_right_eye", "mouth"]
    assert data == original
    assert review.validate_admission(data, ["mouth"])["eligible_features"] == ["mouth"]


def test_readable_eye_admission_preserves_minor_hair_limitations() -> None:
    data = admission()
    evidence = (
        "A fine hair crosses a peripheral lash tip. The main opening and lid path "
        "remain readable and can be localized without replacing foreground hair."
    )
    data["features"][0].update(evidence=evidence, confidence="medium")
    result = review.validate_admission(data, FEATURES)
    assert result["eligible_features"] == FEATURES
    assert result["features"][0]["evidence"] == evidence
    assert result["features"][0]["confidence"] == "medium"


@pytest.mark.parametrize("reason", ["partial_occlusion", "uncertain_boundary", "low_confidence"])
def test_valid_unsupported_feature_is_terminal_data(reason: str) -> None:
    data = admission()
    data["features"][0].update(route="unsupported", reason=reason, confidence="low")
    result = review.validate_admission(data, FEATURES)
    assert result["features"][0]["route"] == "unsupported"
    assert result["eligible_features"] == ["canvas_right_eye", "mouth"]


@pytest.mark.parametrize("ambiguous", [False, True])
def test_global_refusals_are_retained_without_eligible_features(ambiguous: bool) -> None:
    data = admission()
    reason = "ambiguous_subject" if ambiguous else "insufficient_resolution"
    data.update(subject_count=2 if ambiguous else 1, subject_unambiguous=not ambiguous)
    data["image_readable"] = False
    for feature in data["features"]:
        feature.update(route="unsupported", source_state="unknown", reason=reason)
    assert review.validate_admission(data, FEATURES)["eligible_features"] == []
    data["features"][0].update(route="direct", source_state="open", reason="clear_feature")
    with pytest.raises(ValueError, match="every feature unsupported"):
        review.validate_admission(data, FEATURES)


@pytest.mark.parametrize("requested", [[], ["mouth", "mouth"], ["jaw"], "mouth"])
def test_requested_features_are_strict_unique_and_nonempty(requested: object) -> None:
    with pytest.raises(ValueError):
        review.validate_admission(admission(), cast(Any, requested))


@pytest.mark.parametrize(
    "change",
    [
        {"route": "cleanup"},
        {"route": "bald"},
        {"confidence": "low"},
        {"source_state": "closed"},
        {"route": "hidden", "reason": "opaque_fully_hidden", "source_state": "open"},
    ],
)
def test_inconsistent_or_out_of_scope_admission_raises(change: dict[str, Any]) -> None:
    data = admission()
    data["features"][0].update(change)
    with pytest.raises(ValueError):
        review.validate_admission(data, FEATURES)


def test_duplicate_admission_ids_and_implicit_coercion_are_rejected() -> None:
    data = admission()
    data["features"][1] = deepcopy(data["features"][0])
    with pytest.raises(ValueError, match="exactly once"):
        review.validate_admission(data, FEATURES)
    for key, value in [("subject_count", "1"), ("image_readable", 1), ("schema_version", True)]:
        data = admission()
        data[key] = value
        with pytest.raises(ValueError):
            review.validate_admission(data, FEATURES)


def test_geometry_refusal_is_valid_but_cannot_smuggle_a_polygon() -> None:
    data = geometry(["canvas_right_eye"])
    data.update(
        status="cannot_segment",
        features=[],
        reason="An opaque hair lock covers the required lid path and eye opening.",
    )
    assert review.validate_geometry(data, ["canvas_right_eye"])["status"] == "cannot_segment"
    data["features"] = geometry(["canvas_right_eye"])["features"]
    with pytest.raises(ValueError, match="no geometry"):
        review.validate_geometry(data, ["canvas_right_eye"])


def test_geometry_requires_exact_dynamic_feature_ids() -> None:
    admitted = ["canvas_right_eye", "mouth"]
    data = geometry(list(reversed(admitted)))
    assert [
        f["feature_id"] for f in review.validate_geometry(data, admitted)["features"]
    ] == admitted
    with pytest.raises(ValueError, match="exactly once"):
        review.validate_geometry(geometry(FEATURES), admitted)
    with pytest.raises(ValueError, match="exactly once"):
        review.validate_geometry(geometry(["mouth", "mouth"]), admitted)


@pytest.mark.parametrize(
    "point", [[512, 0], [511.5, 0], [-1, 0], [0, 768], [float("nan"), 0], [True, 1]]
)
def test_geometry_rejects_invalid_panel_coordinates(point: list[Any]) -> None:
    data = geometry(["mouth"])
    data["features"][0]["points"][0] = point
    with pytest.raises(ValueError):
        review.validate_geometry(data, ["mouth"])


def test_geometry_rejects_repeated_closing_vertex() -> None:
    data = geometry(["mouth"])
    data["features"][0]["points"].append([10, 10])
    with pytest.raises(ValueError, match="unique"):
        review.validate_geometry(data, ["mouth"])


def test_quality_failure_remains_terminal_without_partial_acceptance() -> None:
    data = quality(FEATURES)
    data["features"][0].update(status="fail", reason="The closed state retains the original iris.")
    data.update(status="fail", reason="One admitted eye contradicts the required closed state.")
    result = review.validate_quality(data, FEATURES)
    assert result["status"] == "fail"
    assert "eligible_features" not in result
    data["status"] = "pass"
    with pytest.raises(ValueError, match="overall quality"):
        review.validate_quality(data, FEATURES)


@pytest.mark.parametrize(
    "limitation",
    [
        "The lip detail is modestly softer at atlas resolution; the A state remains readable.",
        "One isolated lash tip remains; the closed eye has no surviving iris or opening.",
    ],
)
def test_passing_quality_retains_observed_baseline_limitations(limitation: str) -> None:
    data = quality(FEATURES)
    data["features"][0]["reason"] = limitation
    original = deepcopy(data)
    result = review.validate_quality(data, FEATURES)
    assert result["status"] == "pass"
    assert result["features"][0]["reason"] == limitation
    assert result["temporal_review"] == "not_performed"
    assert data == original


def test_baseline_policy_does_not_reinterpret_a_retained_quality_refusal() -> None:
    data = quality(["mouth"])
    data["features"][0].update(status="fail", reason="Lip detail is softer than the original.")
    data.update(status="fail", reason="The previous review refused atlas softness.")
    assert review.validate_quality(data, ["mouth"]) == data


def test_quality_requires_all_admitted_ids_and_never_claims_playback() -> None:
    with pytest.raises(ValueError, match="exactly once"):
        review.validate_quality(quality(["mouth"]), FEATURES)
    data = quality(FEATURES)
    data["temporal_review"] = "passed"
    with pytest.raises(ValueError):
        review.validate_quality(data, FEATURES)
    data = quality(FEATURES)
    data["animation_accepted"] = True
    with pytest.raises(ValueError):
        review.validate_quality(data, FEATURES)


def test_schema_objects_are_strict_and_fresh() -> None:
    def inspect(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                assert value["additionalProperties"] is False
                assert set(value["required"]) == set(value["properties"])
            for nested in value.values():
                inspect(nested)
        elif isinstance(value, list):
            for nested in value:
                inspect(nested)

    for make_schema in [review.admission_schema, review.geometry_schema, review.quality_schema]:
        schema = make_schema()
        inspect(schema)
        json.dumps(schema, allow_nan=False)
        schema["properties"].clear()
        assert make_schema()["properties"]


def test_prompts_bind_dynamic_states_and_expose_acceptance_limits() -> None:
    geometry_prompt = review.geometry_prompt(STATES, ["mouth"], (640, 800))
    assert "640 by 800" in geometry_prompt
    assert 'Admitted feature IDs: ["mouth"]' in geometry_prompt
    assert "UNION of the main ORIGINAL artwork and corresponding new artwork" in geometry_prompt
    assert "OUTER LASH TIPS" in geometry_prompt
    assert "OUTSIDE the opaque\ncore only" in geometry_prompt
    assert "THREE-panel-pixel" not in geometry_prompt
    assert "cannot_segment" in geometry_prompt
    quality_prompt = review.quality_prompt(STATES, ["canvas_right_eye"])
    assert 'Admitted feature IDs: ["canvas_right_eye"]' in quality_prompt
    assert "temporal_review MUST be not_performed" in quality_prompt
    assert "redrawn crossing HAIR" in quality_prompt
    assert "report it in the feature reason even when passing" in quality_prompt
    with pytest.raises(ValueError):
        review.geometry_prompt(STATES, ["mouth"], (0, 800))
    with pytest.raises(ValueError):
        review.quality_prompt([STATES[0], STATES[0]], ["mouth"])
