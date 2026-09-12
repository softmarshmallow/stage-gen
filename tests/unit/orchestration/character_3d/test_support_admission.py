"""Ordinary use must be bound to a host-reviewed, exact qualification target."""

from __future__ import annotations

import copy
from typing import Any, Literal, TypedDict

import pytest

from gnode import Binding, ModelRef
from stage_gen.orchestration.character_3d import support_admission as MODULE


class SupportInputs(TypedDict):
    package_closure_sha256: str
    blender_executable_sha256: str
    python_version: str
    runtime_dependencies: dict[str, str]
    experiment: dict[str, Any]
    profile: dict[str, Any]
    routes: tuple[Binding, ...]


def inputs() -> SupportInputs:
    return {
        "package_closure_sha256": "a" * 64,
        "blender_executable_sha256": "b" * 64,
        "python_version": "3.12.9",
        "runtime_dependencies": {"numpy": "2.0.0", "Pillow": "11.0.0"},
        "experiment": {
            "profile": {"sha256": "c" * 64},
            "pricing": {"sha256": "f" * 64},
            "agent_route": "review@fixture",
            "pipeline_mode": "brief_to_rig",
            "partition_preset": "whole",
            "upstream": {"mesh_params": {"face_limit": 10000}},
            "rigging": {"preservation": "restore_normals"},
            "limits": {"max_review_rounds": 2},
            "brief": {"description": "An original short-haired SD human"},
            "experiment_id": "original_name",
        },
        "profile": {"profile_id": "sd_human_fixed_hands_v1"},
        "routes": (Binding("body_rig", ModelRef("rig", "fixture"), "rig", 1, 0, 0.25),),
    }


def record(target: dict[str, Any]) -> dict[str, Any]:
    # A synthetic host decision tests admission only, never a visual-success fixture.
    return {
        "schema_version": 1,
        "decision": "qualified_for_support",
        "qualification_id": "synthetic_host_test",
        "target": copy.deepcopy(target),
        "evidence": {
            key: "d" * 64
            for key in (
                "cohort_manifest",
                "qualification_report",
                "calibration_report",
                "release_review",
            )
        },
    }


def test_default_supported_request_requires_host_record() -> None:
    target = MODULE.support_target(**inputs())
    with pytest.raises(ValueError, match="reviewed host support record"):
        MODULE.admit_support(mode="supported", target=target)
    admitted = MODULE.admit_support(mode="supported", target=target, support_record=record(target))
    assert admitted["support_qualified"] is True
    assert len(admitted["support_record_sha256"]) == 64


@pytest.mark.parametrize("mode", ["development", "qualification"])
def test_experimental_modes_never_claim_support(
    mode: Literal["development", "qualification"],
) -> None:
    target = MODULE.support_target(**inputs())
    result = MODULE.admit_support(mode=mode, target=target)
    assert result["support_qualified"] is False
    assert result["support_record_sha256"] is None
    with pytest.raises(ValueError):
        MODULE.admit_support(mode=mode, target=target, support_record=record(target))


@pytest.mark.parametrize(
    "field",
    [
        "package",
        "blender",
        "python",
        "dependencies",
        "profile",
        "partition",
        "policy",
        "route",
        "pricing",
    ],
)
def test_changed_execution_identity_is_not_covered_by_prior_qualification(field: str) -> None:
    parameters = inputs()
    original = MODULE.support_target(**parameters)
    if field == "package":
        parameters["package_closure_sha256"] = "e" * 64
    elif field == "blender":
        parameters["blender_executable_sha256"] = "e" * 64
    elif field == "python":
        parameters["python_version"] = "3.13.0"
    elif field == "dependencies":
        parameters["runtime_dependencies"]["Pillow"] = "12.0.0"
    elif field == "profile":
        parameters["experiment"]["profile"]["sha256"] = "e" * 64
    elif field == "pricing":
        parameters["experiment"]["pricing"]["sha256"] = "e" * 64
    elif field == "partition":
        parameters["experiment"]["partition_preset"] = "head_body_hair"
    elif field == "policy":
        parameters["experiment"]["limits"]["max_review_rounds"] = 1
    else:
        parameters["experiment"]["agent_route"] = "different@fixture"
    changed = MODULE.support_target(**parameters)
    with pytest.raises(ValueError, match="does not match"):
        MODULE.admit_support(mode="supported", target=changed, support_record=record(original))


def test_character_brief_and_input_order_can_change_without_changing_qualified_policy() -> None:
    parameters = inputs()
    original = MODULE.support_target(**parameters)
    parameters["experiment"]["brief"]["description"] = "Another original short-haired human"
    parameters["experiment"]["experiment_id"] = "new_name"
    parameters["runtime_dependencies"] = dict(
        reversed(list(parameters["runtime_dependencies"].items()))
    )
    assert MODULE.support_target(**parameters) == original


@pytest.mark.parametrize(
    "fault", ["missing_review", "false_version", "unqualified", "unknown_key", "bad_hash"]
)
def test_incomplete_or_malformed_support_decision_is_refused(fault: str) -> None:
    target = MODULE.support_target(**inputs())
    decision = record(target)
    if fault == "missing_review":
        decision["evidence"].pop("release_review")
    elif fault == "false_version":
        decision["schema_version"] = True
    elif fault == "unqualified":
        decision["decision"] = "pending"
    elif fault == "unknown_key":
        decision["bypass"] = True
    else:
        decision["evidence"]["release_review"] = "unverified"
    with pytest.raises(ValueError):
        MODULE.admit_support(mode="supported", target=target, support_record=decision)
