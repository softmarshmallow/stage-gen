"""Read-only collection of enrolled qualification trials; no execution or admission.

Call ``collect_qualification(input_root, [Trial(...)])`` with the same input root
used by the runner (normally ``spikes``). Run paths are relative to that root.
Enroll trials before evaluating results: missing and invalid runs remain in the
denominator. Select a resume explicitly with ``outcome_path``; never enroll the
same run twice. ``decision_kind`` is an evaluator declaration, not a fact inferred
from a successful exit or a nonzero bill. Mock and resume evidence prevent a run
from counting as a fresh success even when it was enrolled as fresh.

The collector checks recorded outcome/summary agreement, accounting, and exact
admission -> review -> rendered evidence / final artifact hashes. It reports
existing acceptance; it cannot supply a missing semantic review, prove absence
of operator intervention, or establish generalization. A safe failure is a
reported unattended terminal failure with reconciled, within-budget accounting;
it never counts as an accepted character. Caller owns report persistence.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

from stage_gen.components.character_3d.io import canonical_digest
from stage_gen.components.character_3d.tool_views import (
    RENDER_VIEW_PROJECTION,
    render_view,
)

JsonObject = dict[str, Any]
NodeRecords = dict[str, JsonObject]
ReviewGrid = set[tuple[str, str | None, float, int]]
_ID = re.compile("[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\\Z")
_SHA = re.compile("[0-9a-f]{64}\\Z")
_SUCCESS = {"accepted", "accepted_assembly", "offline_fixture_complete"}
_MODES = {"assembly", "rig", "parts_to_rig", "brief_to_rig"}
_VIEWS = {
    "front": "positive_z",
    "back": "negative_z",
    "left": "negative_x",
    "right": "positive_x",
    "top": "positive_y",
    "bottom": "negative_y",
    "three_quarter": "three_quarter",
}


class EvidenceError(ValueError):
    """A recorded qualification claim is unsupported or inconsistent."""


@dataclass(frozen=True)
class Trial:
    trial_id: str
    run_path: str
    decision_kind: str
    cohort: str = "unspecified"
    outcome_path: str = "outcome.json"

    def __post_init__(self) -> None:
        for value in (self.trial_id, self.cohort):
            if not isinstance(value, str) or not _ID.fullmatch(value):
                raise ValueError("Trial and cohort identities must be portable identifiers")
        if self.decision_kind not in {"fresh", "saved_decision_replay", "unknown"}:
            raise ValueError("Declare fresh, saved_decision_replay, or unknown decisions")
        _relative(self.run_path)
        _relative(self.outcome_path)
        if Path(self.outcome_path).name != "outcome.json":
            raise ValueError("Select the original or an invocation's outcome.json")


def _relative(value: object) -> Path:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or ("\x00" in value)
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise EvidenceError("nonportable_path")
    return Path(value)


def _path(root: Path, value: object) -> Path:
    path = (root / _relative(value)).resolve()
    if not path.is_relative_to(root):
        raise EvidenceError("path_outside_declared_root")
    return path


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _json(path: Path) -> JsonObject:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise EvidenceError("record_must_be_an_object")
    return value


def _reference(root: Path, path: Path) -> dict[str, str]:
    return {"path": path.relative_to(root).as_posix(), "sha256": _sha(path)}


def _verified(root: Path, reference: object, *, path_key: str = "path") -> Path:
    if not isinstance(reference, dict) or not _SHA.fullmatch(str(reference.get("sha256"))):
        raise EvidenceError("invalid_artifact_reference")
    path = _path(root, reference.get(path_key))
    if not path.is_file() or _sha(path) != reference["sha256"]:
        raise EvidenceError("artifact_missing_or_hash_mismatch")
    if "bytes" in reference and path.stat().st_size != reference["bytes"]:
        raise EvidenceError("artifact_size_mismatch")
    return path


def _money(value: object) -> Decimal:
    if type(value) not in {str, int, float}:
        raise EvidenceError("invalid_accounting_amount")
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise EvidenceError("invalid_accounting_amount") from None
    if not amount.is_finite() or amount < 0:
        raise EvidenceError("invalid_accounting_amount")
    return amount


def _count(value: object) -> int:
    if type(value) is not int or value < 0:
        raise EvidenceError("invalid_accounting_count")
    return value


def _accounting(run: Path, outcome: JsonObject, experiment: JsonObject) -> JsonObject:
    reported = outcome.get("accounting", {})
    dispatches = _count(reported.get("dispatch_count", 0))
    known = _money(reported.get("known_cost_usd", "0"))
    liability = _money(reported.get("liability_usd", str(known) if dispatches == 0 else None))
    unknown = _count(reported.get("unknown_charge_count", 0 if dispatches == 0 else None))
    if liability < known:
        raise EvidenceError("liability_below_known_cost")
    ledger_path = _path(run, "ledger/ledger.json")
    if dispatches:
        if not ledger_path.is_file():
            raise EvidenceError("dispatches_without_durable_ledger")
        ledger = _json(ledger_path)
        attempts = ledger.get("attempts", [])
        if (
            _count(ledger.get("dispatch_count")) != dispatches
            or len(attempts) != dispatches
            or _money(ledger.get("known_cost_usd")) != known
            or (_money(ledger.get("liability_usd")) != liability)
            or (sum(item.get("charge_status") != "reported" for item in attempts) != unknown)
            or (
                sum((_money(item.get("known_cost_usd") or "0") for item in attempts), Decimal(0))
                != known
            )
            or (
                sum((_money(item.get("liability_usd")) for item in attempts), Decimal(0))
                != liability
            )
        ):
            raise EvidenceError("outcome_ledger_disagreement")
    inclusive = reported.get("inclusive_run_budget")
    unsettled_agent_known = Decimal(0)
    settled_inclusive_known: Decimal | None = None
    if inclusive is not None:
        inclusive_known = _money(inclusive.get("known_actual_usd"))
        settled_inclusive_known = inclusive_known
        inclusive_liability = _money(inclusive.get("liability_usd"))
        allocation = inclusive.get("reservations", {}).get("agent_loop")
        if (
            outcome.get("status") == "development_checkpoint_stopped"
            and inclusive.get("closed") is False
            and (allocation is not None)
            and (allocation.get("status") != "settled")
        ):
            control_path = _verified(run, outcome["development_control"])
            control = _json(control_path)
            checkpoint_path = _verified(run, outcome["stop_checkpoint"])
            checkpoint = _json(checkpoint_path)
            identity = _json(_path(run, "recovery/identity.json"))
            receipt = checkpoint["state"]["records"]["rig_submit_01"]
            if (
                control_path != _path(run, "recovery/development-stop.json")
                or control.get("kind") != "stop_after_committed_provider_submit"
                or control.get("target_node_id") != "rig_submit_01"
                or (control.get("qualification_eligible") is not False)
                or (control.get("experiment_sha256") != canonical_digest(experiment))
                or (
                    control.get("runtime_sha256") != _reference(run, run / "runtime.json")["sha256"]
                )
                or (control.get("graph_sha256") != identity.get("graph_sha256"))
                or (
                    control.get("graph_sha256")
                    != _json(_path(run, "graph.json")).get("graph_sha256")
                )
                or (checkpoint.get("identity_sha256") != canonical_digest(identity))
                or (
                    checkpoint.get("payload_sha256")
                    != canonical_digest(
                        {key: value for key, value in checkpoint.items() if key != "payload_sha256"}
                    )
                )
                or (checkpoint_path != _path(run, "recovery/rig_submit_01.completed.json"))
                or (checkpoint.get("node_id") != "rig_submit_01")
                or (receipt.get("task_id") != outcome["stop_checkpoint"].get("task_id"))
                or (
                    receipt.get("plan", {}).get("plan_sha256")
                    != outcome["stop_checkpoint"].get("plan_sha256")
                )
                or (allocation.get("status") != "running")
                or (allocation.get("dispatch_started") is not True)
                or (allocation.get("settlement") is not None)
                or (allocation.get("identity_sha256") != canonical_digest(experiment))
                or (_money(allocation.get("amount_usd")) < liability)
                or (_money(allocation.get("liability_usd")) < liability)
            ):
                raise EvidenceError("development_stop_agent_hold_does_not_cover_ledger")
            unsettled_agent_known = known
            inclusive_known += unsettled_agent_known
        if (
            inclusive_known < known
            or inclusive_liability < liability
            or inclusive_liability < inclusive_known
            or (inclusive.get("over_ceiling") is True)
        ):
            raise EvidenceError("inclusive_accounting_inconsistent_or_over_budget")
        known, liability = (inclusive_known, inclusive_liability)
    ceiling = _money(experiment["limits"]["max_usd"])
    return {
        "dispatch_count": dispatches,
        "known_cost_usd": str(known),
        "liability_usd": str(liability),
        "unknown_charge_count": unknown,
        "within_budget": liability <= ceiling,
        "reconciled": unknown == 0 and liability == known,
        "closed": inclusive is None or inclusive.get("closed") is True,
        "settled_inclusive_known_cost_usd": str(settled_inclusive_known)
        if settled_inclusive_known is not None
        else None,
        "unsettled_agent_known_cost_usd": str(unsettled_agent_known),
    }


def _node_record(run: Path, node_id: object, nodes: NodeRecords) -> tuple[JsonObject, Path]:
    if not isinstance(node_id, str) or not _ID.fullmatch(node_id):
        raise EvidenceError("invalid_admission_node_identity")
    node = nodes.get(node_id)
    if not node or node.get("status") != "succeeded":
        raise EvidenceError("admission_or_review_node_not_succeeded")
    refs = {item["artifact_ref"]: item for item in node.get("artifacts", [])}
    relative = "nodes/" + node_id + ".json"
    if relative not in refs or relative + ".meta.json" not in refs:
        raise EvidenceError("summary_missing_node_artifact_or_sidecar")
    path = _verified(run, refs[relative], path_key="artifact_ref")
    meta_path = _verified(run, refs[relative + ".meta.json"], path_key="artifact_ref")
    metadata = _json(meta_path)
    if (
        metadata.get("artifact", {}).get("sha256") != refs[relative]["sha256"]
        or metadata.get("artifact", {}).get("bytes") != path.stat().st_size
    ):
        raise EvidenceError("sidecar_artifact_disagreement")
    return (_json(path), path)


def _review_origin(
    run: Path, kind: str, review_id: str, review: JsonObject, nodes: NodeRecords, agent_route: str
) -> tuple[JsonObject, Path, JsonObject, JsonObject]:
    """Resolve unchanged-hash reuse to its original provider-reviewed record."""
    while True:
        original, path = _node_record(run, review_id, nodes)
        metadata = _json(path.with_name(path.name + ".meta.json"))
        if metadata.get("provider") == "openrouter":
            if cast(str, metadata.get("model")) + "@openrouter" != agent_route:
                raise EvidenceError("review_provider_identity_disagreement")
            prompt = metadata.get("prompt")
            if not isinstance(prompt, str):
                raise EvidenceError("missing_review_instructions")
            instruction_hash = hashlib.sha256(prompt.encode()).hexdigest()
            if (
                metadata.get("prompt_sha256") != instruction_hash
                or metadata.get("params", {}).get("instructions_sha256") != instruction_hash
            ):
                raise EvidenceError("review_instructions_hash_mismatch")
            contract = json.loads(prompt)
            if (
                contract.get("stage") != ("assembly" if kind == "assembly" else "rigging")
                or contract.get("source_sha256") != review.get("source_sha256")
                or contract.get("asset_id") != review.get("asset_id")
            ):
                raise EvidenceError("review_instructions_candidate_disagreement")
            if (
                original.get("review_context_sha256") is not None
                and contract.get("review_context_sha256") != original["review_context_sha256"]
            ):
                raise EvidenceError("review_context_differs_from_provider_instructions")
            return (original, path, metadata, contract)
        if (
            metadata.get("provider") != "local"
            or original.get("review_reused_for_unchanged_hash") is not True
        ):
            raise EvidenceError("review_not_bound_to_provider_verdict")
        match = re.fullmatch(kind + "_review_(\\d+)", review_id)
        if not match or int(match[1]) <= 1:
            raise EvidenceError("review_reuse_has_no_origin")
        previous_id = original.get(
            "review_reused_from_node", f"{kind}_review_{int(match[1]) - 1:02d}"
        )
        previous_match = re.fullmatch(kind + "_review_(\\d+)", str(previous_id))
        if not previous_match or not 0 < int(previous_match[1]) < int(match[1]):
            raise EvidenceError("review_reuse_has_invalid_origin_pointer")
        previous, _ = _node_record(run, previous_id, nodes)

        def comparable(value: JsonObject) -> JsonObject:
            return {
                key: item
                for key, item in value.items()
                if key not in {"review_reused_for_unchanged_hash", "review_reused_from_node"}
            }

        if comparable(original) != comparable(previous):
            raise EvidenceError("review_reuse_changed_the_original_verdict")
        review_id = previous_id


def _required_criteria(
    run: Path, experiment: JsonObject, contract: JsonObject, kind: str
) -> list[str]:
    criteria = contract.get("required_criteria")
    if (
        not isinstance(criteria, list)
        or not criteria
        or any(not isinstance(item, str) or not item for item in criteria)
        or (len(set(criteria)) != len(criteria))
    ):
        raise EvidenceError("invalid_retained_review_criteria")
    profile = contract.get("profile", {})
    frozen_profile = _path(run, "code/" + experiment["profile"]["path"])
    if frozen_profile.is_file():
        _verified(run / "code", experiment["profile"])
        if _json(frozen_profile) != profile:
            raise EvidenceError("review_profile_differs_from_frozen_profile")
    stage_criteria = profile.get("review", {}).get(kind + "_criteria")
    if stage_criteria is not None and stage_criteria != criteria:
        raise EvidenceError("review_criteria_differ_from_retained_profile")
    return criteria


def _required_grid(contract: JsonObject, kind: str) -> tuple[list[str], ReviewGrid]:
    """Current retained review contract: every declared view, pose and size tier."""
    profile = contract["profile"]["review"]
    poses: list[tuple[str | None, float]]
    views = [_VIEWS[view] for view in profile["required_views"]]
    if not views or len(set(views)) != len(views):
        raise EvidenceError("invalid_required_review_views")
    if kind == "assembly":
        poses = [(None, 0)]
    else:
        durations = {
            clip["name"]: _money(clip["duration_seconds"])
            for clip in contract["exported_rig_report"]["clips"]
        }
        required = [*profile["required_diagnostics"], profile["required_motion"]]
        optional = [name for name in profile.get("optional_diagnostics", []) if name in durations]
        poses = [
            (None, 0) if name == "rest" else (name, float(durations[name] * Decimal("0.375")))
            for name in dict.fromkeys([*required, *optional])
        ]
    expected = {
        ("inspection", clip, seconds, profile["inspection_height_pixels"])
        for clip, seconds in poses
    }
    gameplay = next((pose for pose in poses if pose[0] == profile["required_motion"]), (None, 0))
    expected.update(
        ("gameplay", *gameplay, size) for size in profile["target_character_height_pixels"]
    )
    return (views, expected)


def _review_pose_timing(pose: object) -> None:
    """Check the renderer's imported-frame clock, including nonzero clip starts."""

    def number(value: object, *, nonnegative: bool = True) -> Decimal:
        if type(value) not in {int, float}:
            raise EvidenceError("review_pose_timing_inconsistent")
        result = Decimal(str(value))
        if not result.is_finite() or (nonnegative and result < 0):
            raise EvidenceError("review_pose_timing_inconsistent")
        return result

    if not isinstance(pose, dict):
        raise EvidenceError("review_pose_timing_inconsistent")
    seconds = number(pose.get("time_seconds"))
    frame = number(pose.get("frame"), nonnegative=False)
    fps = number(pose.get("effective_fps_after_import"))
    frame_range = pose.get("frame_range")
    if fps <= 0 or not isinstance(frame_range, list) or len(frame_range) != 2:
        raise EvidenceError("review_pose_timing_inconsistent")
    start, end = [number(value, nonnegative=False) for value in frame_range]
    if pose.get("clip") is None:
        if seconds != 0 or frame != 0 or start != 0 or (end != 0):
            raise EvidenceError("review_pose_timing_inconsistent")
        return
    if not isinstance(pose["clip"], str) or not pose["clip"]:
        raise EvidenceError("review_pose_timing_inconsistent")
    tolerance = Decimal("0.00001")
    if (
        end < start
        or frame < start - tolerance
        or frame > end + tolerance
        or (abs(frame - (start + seconds * fps)) > tolerance)
    ):
        raise EvidenceError("review_pose_timing_inconsistent")


def _review_evidence(
    run: Path,
    review: JsonObject,
    source_hash: str,
    contract: JsonObject,
    metadata: JsonObject,
    kind: str,
) -> int:
    evidence = review.get("initial_evidence")
    retained = contract.get("final_render_evidence" if kind == "assembly" else "initial_evidence")
    expected = evidence
    if "initial_evidence_projection" in contract:
        if (
            contract["initial_evidence_projection"] != RENDER_VIEW_PROJECTION
            or kind != "rig"
            or (not isinstance(evidence, list))
        ):
            raise EvidenceError("unsupported_review_evidence_projection")
        if not all(isinstance(record, dict) for record in evidence):
            raise EvidenceError("missing_or_stale_review_evidence")
        expected = [render_view(record) for record in evidence]
    if expected != retained:
        raise EvidenceError("review_evidence_differs_from_retained_instructions")
    records = evidence if isinstance(evidence, list) else [evidence]
    if not records or not all(isinstance(record, dict) for record in records):
        raise EvidenceError("missing_or_stale_review_evidence")
    modern = isinstance(evidence, list)
    if not modern and kind != "assembly":
        raise EvidenceError("rig_review_missing_declared_evidence_grid")
    expected_views, expected_grid = _required_grid(contract, kind) if modern else ([], set())
    observed_grid = []
    submitted = {item["ref"]: item for item in metadata.get("inputs", [])}
    image_count = 0
    for record in records:
        if not isinstance(record, dict) or record.get("source_sha256") != source_hash:
            raise EvidenceError("missing_or_stale_review_evidence")
        report_path = _path(run, record["report"])
        manifest = _json(report_path.with_name("manifest.json"))
        if manifest.get("source", {}).get("sha256") != source_hash:
            raise EvidenceError("render_manifest_source_disagreement")
        artifacts = {item["path"]: item for item in manifest.get("artifacts", [])}
        if report_path.name not in artifacts:
            raise EvidenceError("render_manifest_missing_report")
        for item in artifacts.values():
            _verified(report_path.parent, {**item, "bytes": item["size_bytes"]})
        report = _json(report_path)
        if report.get("request", {}).get("source", {}).get("sha256") != source_hash:
            raise EvidenceError("rendered_different_candidate")
        if record.get("pose") != report.get("pose"):
            raise EvidenceError("review_pose_disagrees_with_render")
        _review_pose_timing(record.get("pose"))
        images = record.get("images", [])
        if not images:
            raise EvidenceError("review_has_no_images")
        actual_views = [image["view"] for image in images]
        if len(set(actual_views)) != len(actual_views):
            raise EvidenceError("duplicate_review_view")
        cameras = {image["name"]: image for image in report.get("result", {}).get("images", [])}
        if set(actual_views) != set(cameras):
            raise EvidenceError("review_views_differ_from_render")
        if modern:
            pose = record["pose"]
            size = record["character_height_pixels"]
            observed_grid.append((record["review_tier"], pose["clip"], pose["time_seconds"], size))
            if set(actual_views) != set(expected_views):
                raise EvidenceError("review_missing_required_views")
            if report["request"]["options"].get("character_height_pixels") != size:
                raise EvidenceError("render_size_disagrees_with_review_tier")
        for reference in images:
            image_path = _verified(run, reference)
            camera = cameras[reference["view"]]
            if (
                image_path != _path(report_path.parent, camera["image"])
                or artifacts.get(camera["image"], {}).get("sha256") != reference["sha256"]
            ):
                raise EvidenceError("review_image_disagrees_with_render_manifest")
            sent = submitted.get("run://" + reference["path"])
            if not sent or sent.get("sha256") != reference["sha256"]:
                raise EvidenceError("review_image_not_supplied_to_provider")
            _verified(run, {**sent, "path": reference["path"]})
            if reference.get("camera") != camera:
                raise EvidenceError("review_camera_disagrees_with_render")
            if modern:
                camera = reference["camera"]
                if (
                    camera.get("requested_character_height_pixels") != size
                    or abs(_money(camera["projected_geometry"]["height_pixels"]) - _money(size))
                    > Decimal("1")
                    or camera["projected_geometry"].get("fully_in_frame") is not True
                ):
                    raise EvidenceError("review_has_invalid_projection_or_clipped_character")
            image_count += 1
    if modern and (len(observed_grid) != len(expected_grid) or set(observed_grid) != expected_grid):
        raise EvidenceError("review_missing_or_duplicate_pose_size_tiers")
    return image_count


def _admission(
    root: Path, run: Path, kind: str, nodes: NodeRecords, experiment: JsonObject
) -> JsonObject:
    node_id = kind + "_admit"
    record, path = _node_record(run, node_id, nodes)
    if record.get("status") != kind + "_admitted":
        raise EvidenceError("admission_status_disagreement")
    source = _verified(root, record.get("source"))
    if not source.is_relative_to(run) or source.stat().st_size == 0:
        raise EvidenceError("admitted_output_not_authored_in_this_run")
    review_id = record.get("review_node")
    if not isinstance(review_id, str) or not review_id.startswith(kind + "_review_"):
        raise EvidenceError("wrong_review_stage")
    review, review_path = _node_record(run, review_id, nodes)
    if review.get("accepted") is not True:
        raise EvidenceError("admission_without_accepted_review")
    if review.get("source_sha256") != record["source"]["sha256"]:
        raise EvidenceError("reviewed_different_candidate")
    original, original_path, metadata, contract = _review_origin(
        run, kind, review_id, review, nodes, experiment["agent_route"]
    )
    _reject_verdict_reroll(
        run, kind, original_path.stem, original, contract, metadata, nodes, experiment
    )
    required = _required_criteria(run, experiment, contract, kind)
    if kind == "rig" and (
        contract.get("required_but_missing_weights") or contract.get("numeric_findings")
    ):
        raise EvidenceError("rig_admitted_despite_retained_numeric_blockers")
    criteria = review.get("criteria")
    if (
        not criteria
        or len(criteria) != len(required)
        or {item.get("criterion") for item in criteria} != set(required)
        or any(item.get("passed") is not True for item in criteria)
    ):
        raise EvidenceError("accepted_review_has_failed_or_missing_criteria")
    if any(issue.get("severity") == "blocking" for issue in review.get("issues", [])):
        raise EvidenceError("accepted_review_has_blocking_issues")
    image_count = _review_evidence(
        run, original, record["source"]["sha256"], contract, metadata, kind
    )
    return {
        "status": "accepted",
        "admission": _reference(root, path),
        "review": _reference(root, review_path),
        "original_provider_review": _reference(root, original_path),
        "source": _reference(root, source),
        "verified_initial_review_images": image_count,
    }


def _reject_verdict_reroll(
    run: Path,
    kind: str,
    current_id: str,
    current: JsonObject,
    contract: JsonObject,
    metadata: JsonObject,
    nodes: NodeRecords,
    experiment: JsonObject,
) -> None:
    """A second same-context opinion cannot erase a valid earlier rejection."""
    current_round = int(current_id.rsplit("_", 1)[1])

    def context(value: JsonObject, meta: JsonObject) -> tuple[JsonObject, list[tuple[Any, Any]]]:
        return (
            {
                key: value.get(key)
                for key in (
                    "stage",
                    "profile",
                    "required_criteria",
                    "required_but_missing_weights",
                    "numeric_findings",
                )
            },
            sorted(
                (item.get("role", item.get("source", "reference")), item.get("sha256"))
                for item in meta.get("inputs", [])
                if str(item.get("ref", "")).startswith("input://")
            ),
        )

    for node_id, node in nodes.items():
        match = re.fullmatch(kind + "_review_(\\d+)", node_id)
        if not match or int(match[1]) >= current_round or node.get("status") != "succeeded":
            continue
        prior, _ = _node_record(run, node_id, nodes)
        if (
            prior.get("accepted") is not False
            or prior.get("source_sha256") != current["source_sha256"]
        ):
            continue
        original, _, prior_meta, prior_contract = _review_origin(
            run, kind, node_id, prior, nodes, experiment["agent_route"]
        )
        if context(prior_contract, prior_meta) != context(contract, metadata):
            continue
        required = _required_criteria(run, experiment, prior_contract, kind)
        criteria = original.get("criteria", [])
        if len(criteria) != len(required) or {item.get("criterion") for item in criteria} != set(
            required
        ):
            raise EvidenceError("prior_same_artifact_rejection_has_invalid_criteria")
        if not any(item.get("passed") is False for item in criteria) and (
            not any(item.get("severity") == "blocking" for item in original.get("issues", []))
        ):
            raise EvidenceError("prior_same_artifact_rejection_has_no_failed_criterion")
        _review_evidence(run, original, current["source_sha256"], prior_contract, prior_meta, kind)
        raise EvidenceError("accepted_after_rejected_unchanged_artifact")


def _collect(root: Path, trial: Trial) -> JsonObject:
    row: JsonObject = {
        "trial_id": trial.trial_id,
        "run_path": trial.run_path,
        "cohort": trial.cohort,
        "declared_decision_kind": trial.decision_kind,
        "decision_kind": trial.decision_kind,
        "result": "missing_terminal_evidence",
        "accepted": False,
        "fresh_accepted": False,
        "safe_failure": False,
        "started_evidence": False,
        "terminal_record": False,
        "admissions": {},
        "evidence": {},
        "errors": [],
    }
    try:
        run = _path(root, trial.run_path)
        outcome_path = _path(run, trial.outcome_path)
        trace = outcome_path.with_name("trace.jsonl")
        row["started_evidence"] = outcome_path.is_file() or (
            trace.is_file() and trace.stat().st_size > 0
        )
        if not outcome_path.is_file():
            return row
        outcome = _json(outcome_path)
        row["terminal_record"] = outcome.get("status") in _SUCCESS | {
            "failed",
            "interrupted",
            "terminal_pending_reconciliation",
        }
        row["evidence"]["outcome"] = _reference(root, outcome_path)
        experiment_path = _path(run, "experiment.json")
        experiment = _json(experiment_path)
        row["evidence"]["experiment"] = _reference(root, experiment_path)
        row["experiment_id"] = experiment["experiment_id"]
        row["agent_route"] = experiment["agent_route"]
        row["profile"] = experiment["profile"]
        mode = experiment.get("pipeline_mode", "assembly")
        if mode not in _MODES:
            raise EvidenceError("unknown_pipeline_mode")
        row["pipeline_mode"] = mode
        row["reported_status"] = outcome.get("status")
        row["unattended_reported"] = outcome.get("unattended") is True
        row["resumed"] = outcome.get("resumed") is True or trial.outcome_path != "outcome.json"
        original_outcome = _json(_path(run, "outcome.json"))
        row["development_controlled"] = (
            _path(run, "recovery/development-stop.json").exists()
            or bool(original_outcome.get("development_control"))
            or original_outcome.get("status") == "development_checkpoint_stopped"
            or bool(outcome.get("development_control"))
        )
        context = experiment.get("budget_context", {})
        replay = context.get("mock_transport_only") is True or "saved_decisions" in context
        regression_path = _path(run, "regression.json")
        if regression_path.is_file():
            regression = _json(regression_path)
            replay |= regression.get("fresh_agent_decisions") is False
            row["evidence"]["regression"] = _reference(root, regression_path)
        if replay or trial.decision_kind == "saved_decision_replay":
            row["decision_kind"] = "saved_decision_replay"
        elif row["resumed"]:
            row["decision_kind"] = "resumed"
        elif row["development_controlled"]:
            row["decision_kind"] = "development_controlled"
        row["accounting"] = _accounting(run, outcome, experiment)
        runtime = _path(run, "runtime.json")
        if runtime.is_file():
            row["evidence"]["runtime_snapshot"] = _reference(root, runtime)
        summary_path = outcome_path.with_name("summary.json")
        if not summary_path.is_file():
            row["result"] = (
                "failed_without_summary"
                if outcome.get("status") == "failed"
                else "interrupted"
                if outcome.get("status") == "interrupted"
                else "missing_summary"
            )
            return row
        summary = _json(summary_path)
        row["evidence"]["summary"] = _reference(root, summary_path)
        row["duration_ms"] = summary.get("duration_ms")
        row["graph_sha256"] = summary.get("graph_sha256")
        graph_path = _path(run, "graph.json")
        graph = _json(graph_path)
        if graph.get("graph_sha256") != summary.get("graph_sha256"):
            raise EvidenceError("summary_graph_disagreement")
        nodes = {item["node_id"]: item for item in summary["nodes"]}
        if len(nodes) != len(summary["nodes"]):
            raise EvidenceError("duplicate_summary_node")
        row["failed_nodes"] = [key for key, node in nodes.items() if node["status"] == "failed"]
        row["review_statuses"] = {
            key: node["status"] for key, node in nodes.items() if "_review_" in key
        }
        row["cached_decision_nodes"] = [
            key
            for key, node in nodes.items()
            if node.get("cache") == "hit"
            and re.fullmatch(
                (
                    "(?:assemble|assembly_review|rig|rig_review|references|referenc"
                    "es_review|generate_[a-z0-9_]+|part_review_[a-z0-9_]+)_\\d+"
                ),
                key,
            )
        ]
        if row["decision_kind"] == "fresh" and row["cached_decision_nodes"]:
            row["decision_kind"] = "checkpoint_reuse"
        row["recorded_review_verdicts"] = {}
        for key, node_status in row["review_statuses"].items():
            if node_status == "succeeded":
                review, review_path = _node_record(run, key, nodes)
                if type(review.get("accepted")) is not bool:
                    raise EvidenceError("review_missing_boolean_verdict")
                row["recorded_review_verdicts"][key] = {
                    "accepted": review["accepted"],
                    "source_sha256": review.get("source_sha256"),
                    "record": _reference(root, review_path),
                    "issue_count": len(review.get("issues", [])),
                    "issues": [
                        {
                            field: str(issue.get(field, ""))[:320]
                            for field in ("severity", "region", "description")
                        }
                        for issue in review.get("issues", [])[:6]
                    ],
                }
        status = outcome.get("status")
        if status == "development_checkpoint_stopped":
            if summary.get("ok") is not True or not row["development_controlled"]:
                raise EvidenceError("development_stop_disagrees_with_summary_or_control")
            row["result"] = "development_checkpoint_stopped"
            return row
        if status == "prepared":
            if summary.get("ok") is not True:
                raise EvidenceError("prepared_outcome_disagrees_with_summary")
            row["result"] = "prepared"
            return row
        for kind in ("assembly", "rig"):
            if kind + "_admit" in nodes and nodes[kind + "_admit"]["status"] == "succeeded":
                row["admissions"][kind] = _admission(root, run, kind, nodes, experiment)
        if status in _SUCCESS:
            if summary.get("ok") is not True or row["failed_nodes"]:
                raise EvidenceError("accepted_outcome_disagrees_with_summary")
            required = {"assembly"} if mode == "assembly" else {"rig"}
            if mode in {"parts_to_rig", "brief_to_rig"}:
                required.add("assembly")
            if not required <= row["admissions"].keys():
                raise EvidenceError("missing_required_admission")
            if mode == "brief_to_rig":
                from stage_gen.recipes.character_3d.brief_evidence import (
                    collect_brief_evidence,
                )

                row["upstream"] = collect_brief_evidence(root, run, nodes, experiment)
            if (
                not row["accounting"]["within_budget"]
                or not row["accounting"]["reconciled"]
                or (not row["accounting"]["closed"])
            ):
                raise EvidenceError("accepted_with_unreconciled_or_over_budget_accounting")
            row["accepted"] = True
            row["result"] = "accepted_assembly" if mode == "assembly" else "accepted_character"
            row["fresh_accepted"] = (
                row["decision_kind"] == "fresh"
                and (not row["development_controlled"])
                and row["unattended_reported"]
                and (row["accounting"]["dispatch_count"] > 0)
                and (status != "offline_fixture_complete")
            )
        elif status in {"failed", "interrupted", "terminal_pending_reconciliation"}:
            if summary.get("ok") is True:
                raise EvidenceError("failed_outcome_disagrees_with_summary")
            row["result"] = status
            row["safe_failure"] = (
                status == "failed"
                and row["unattended_reported"]
                and row["accounting"]["within_budget"]
                and row["accounting"]["reconciled"]
                and row["accounting"]["closed"]
                and (not outcome.get("recovery"))
            )
            if row["safe_failure"]:
                row["result"] = "safe_failure"
        else:
            raise EvidenceError("unknown_terminal_outcome")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        row["result"] = "invalid_evidence"
        row["accepted"] = row["fresh_accepted"] = row["safe_failure"] = False
        row["errors"].append(
            str(error) if isinstance(error, EvidenceError) else type(error).__name__
        )
    return row


def collect_qualification(input_root: Path, trials: Sequence[Trial]) -> JsonObject:
    """Return a portable JSON report with one row per explicitly enrolled trial."""
    root = input_root.resolve()
    if len({trial.trial_id for trial in trials}) != len(trials):
        raise ValueError("Duplicate trial identity would distort the denominator")
    if len({(root / trial.run_path).resolve() for trial in trials}) != len(trials):
        raise ValueError("Enroll each run once; a resume is not another cold trial")
    rows = [_collect(root, trial) for trial in trials]
    return {
        "schema_version": 1,
        "claim": ("Recorded trial outcomes, not semantic admission or general reliability proof."),
        "trial_count": len(rows),
        "enrolled_trial_count": len(rows),
        "started_trial_count": sum(row["started_evidence"] for row in rows),
        "terminal_trial_count": sum(row["terminal_record"] for row in rows),
        "not_started_trial_count": sum(not row["started_evidence"] for row in rows),
        "result_counts": dict(Counter(row["result"] for row in rows)),
        "fresh_declared_trial_count": sum(t.decision_kind == "fresh" for t in trials),
        "fresh_accepted_trial_count": sum(row["fresh_accepted"] for row in rows),
        "fresh_accepted_character_count": sum(
            row["fresh_accepted"] and row["result"] == "accepted_character" for row in rows
        ),
        "safe_failure_count": sum(row["safe_failure"] for row in rows),
        "known_cost_usd_lower_bound": str(
            sum(
                (
                    _money(row["accounting"]["known_cost_usd"])
                    for row in rows
                    if "accounting" in row
                ),
                Decimal(0),
            )
        ),
        "accounting_missing_trial_count": sum("accounting" not in row for row in rows),
        "rows": rows,
    }
