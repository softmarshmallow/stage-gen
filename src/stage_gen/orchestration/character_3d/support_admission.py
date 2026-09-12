"""Host-owned support decisions, separate from character quality judgments.

A support record is a reviewed deployment input outside a run's writable tree.
It is not authored by the producer/reviewer model. Development and qualification
may execute without a record; neither mode claims the preset is supported.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from gnode import Binding

type JsonObject = dict[str, Any]
type AdmissionMode = Literal["supported", "development", "qualification"]
_EVIDENCE = {"cohort_manifest", "qualification_report", "calibration_report", "release_review"}
_POLICY_FIELDS = ("pipeline_mode", "partition_preset", "upstream", "rigging", "limits")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _sha(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("Support admission requires exact SHA-256 identities")
    return value


def support_target(
    *,
    package_closure_sha256: str,
    blender_executable_sha256: str,
    python_version: str,
    runtime_dependencies: Mapping[str, str],
    experiment: JsonObject,
    profile: JsonObject,
    routes: Sequence[Binding],
) -> JsonObject:
    """Bind support to executable/resources, runtime, profile, policy and routes.

    Brief/character identity and artifact locations may vary. Budget and repair
    policies remain part of the qualification configuration, not caller guesses.
    No package record embeds its own digest, avoiding a circular hash dependency.
    """
    if (
        not python_version
        or not runtime_dependencies
        or not all(
            isinstance(name, str) and name and isinstance(version, str) and version
            for name, version in runtime_dependencies.items()
        )
    ):
        raise ValueError("Support admission requires the declared runtime dependency versions")
    policy = {name: experiment.get(name) for name in _POLICY_FIELDS}
    return {
        "package_closure_sha256": _sha(package_closure_sha256),
        "blender_executable_sha256": _sha(blender_executable_sha256),
        "python_version": python_version,
        "runtime_dependencies": dict(sorted(runtime_dependencies.items())),
        "profile": {
            "profile_id": profile["profile_id"],
            "source_sha256": _sha(experiment["profile"]["sha256"]),
        },
        "partition_preset": experiment.get("partition_preset"),
        "pricing_sha256": _sha(experiment["pricing"]["sha256"]),
        "policy_sha256": _digest(policy),
        "routes_sha256": _digest(
            {
                "agent_route": experiment["agent_route"],
                "providers": [
                    {
                        "operation": route.operation,
                        "model": route.model.model + "@" + route.model.provider,
                        "features": sorted(route.features),
                    }
                    for route in sorted(routes, key=lambda item: item.operation)
                ],
            }
        ),
    }


def admit_support(
    *, mode: AdmissionMode, target: JsonObject, support_record: JsonObject | None = None
) -> JsonObject:
    """Refuse ordinary use without the exact host-reviewed qualification decision."""
    if mode not in {"supported", "development", "qualification"}:
        raise ValueError("Unknown character admission mode")
    if mode != "supported":
        if support_record is not None:
            raise ValueError("Support records apply only to supported execution")
        return {
            "schema_version": 1,
            "mode": mode,
            "support_qualified": False,
            "target": target,
            "support_record_sha256": None,
        }
    if not isinstance(support_record, dict) or set(support_record) != {
        "schema_version",
        "decision",
        "qualification_id",
        "target",
        "evidence",
    }:
        raise ValueError("Supported execution requires a reviewed host support record")
    if (
        type(support_record["schema_version"]) is not int
        or support_record["schema_version"] != 1
        or support_record["decision"] != "qualified_for_support"
        or not isinstance(support_record["qualification_id"], str)
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,95}", support_record["qualification_id"]) is None
    ):
        raise ValueError("Support decision is invalid or not qualified")
    if support_record["target"] != target:
        raise ValueError("Support decision does not match the installed character configuration")
    evidence = support_record["evidence"]
    if not isinstance(evidence, dict) or set(evidence) != _EVIDENCE:
        raise ValueError("Support decision requires the complete reviewed qualification evidence")
    for value in evidence.values():
        _sha(value)
    return {
        "schema_version": 1,
        "mode": mode,
        "support_qualified": True,
        "target": target,
        "support_record_sha256": _digest(support_record),
        "qualification_id": support_record["qualification_id"],
    }
