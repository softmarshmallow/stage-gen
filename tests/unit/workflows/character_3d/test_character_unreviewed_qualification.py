"""Unreviewed output remains visible in reports without contributing success."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from stage_gen.components.character_3d.io import write_json
from stage_gen.recipes.character_3d.qualification import Trial, collect_qualification


def fixture(tmp_path: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    run = tmp_path / "run"
    run.mkdir()
    write_json(
        run / "experiment.json",
        {
            "experiment_id": "unreviewed_fixture",
            "agent_route": "fixture@fixture",
            "profile": {"path": "profile.json", "sha256": "a" * 64},
            "pipeline_mode": "brief_to_rig",
            "review_mode": "none",
            "limits": {"max_usd": "1"},
        },
    )
    outcome = {
        "status": "completed_unreviewed",
        "qualification_eligible": False,
        "unattended": True,
    }
    summary = {
        "ok": True,
        "graph_sha256": "b" * 64,
        "nodes": [
            {"node_id": node, "status": "succeeded", "cache": "miss"}
            for node in ("assembly_admit", "rig_admit")
        ],
    }
    write_json(run / "graph.json", {"graph_sha256": "b" * 64})
    return run, outcome, summary


def collect(run: Path, outcome: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    write_json(run / "outcome.json", outcome)
    write_json(run / "summary.json", summary)
    return collect_qualification(run.parent, [Trial("fixture", run.name, "fresh")])


def test_unreviewed_completion_is_terminal_but_never_accepted_or_a_safe_failure(
    tmp_path: Path,
) -> None:
    run, outcome, summary = fixture(tmp_path)
    report = collect(run, outcome, summary)
    assert report["result_counts"] == {"completed_unreviewed": 1}
    assert report["terminal_trial_count"] == 1
    assert report["fresh_accepted_trial_count"] == 0
    assert report["fresh_accepted_character_count"] == 0
    assert report["safe_failure_count"] == 0
    row = report["rows"][0]
    assert row["review_mode"] == "none" and row["qualification_eligible"] is False
    assert row["accepted"] is False and row["fresh_accepted"] is False
    assert row["admissions"] == {} and row["errors"] == []


@pytest.mark.parametrize(
    "fault", ["claimed_acceptance", "wrong_status", "failed_summary", "eligible"]
)
def test_unreviewed_policy_cannot_supply_accepted_or_inconsistent_evidence(
    tmp_path: Path, fault: str
) -> None:
    run, outcome, summary = fixture(tmp_path)
    if fault == "claimed_acceptance":
        outcome["accepted"] = True
    elif fault == "wrong_status":
        outcome["status"] = "accepted"
    elif fault == "failed_summary":
        summary["ok"] = False
    else:
        outcome["qualification_eligible"] = True
    report = collect(run, outcome, summary)
    assert report["result_counts"] == {"invalid_evidence": 1}
    assert report["fresh_accepted_trial_count"] == report["safe_failure_count"] == 0


def test_failed_unreviewed_run_keeps_failure_without_claiming_semantic_admissions(
    tmp_path: Path,
) -> None:
    run, outcome, summary = fixture(tmp_path)
    outcome["status"] = "failed"
    summary["ok"] = False
    summary["nodes"][-1]["status"] = "failed"
    report = collect(run, outcome, summary)
    assert report["result_counts"] == {"failed": 1}
    assert report["safe_failure_count"] == report["fresh_accepted_trial_count"] == 0
    assert report["rows"][0]["errors"] == []
