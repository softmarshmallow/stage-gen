from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from stage_gen.contracts import (
    MAX_JSON_SAFE_INTEGER,
    RecipeRunSummaryLoadError,
    load_recipe_run_summary,
    parse_recipe_run_summary,
)


def _valid_summary() -> dict[str, object]:
    return {
        "schema_version": 3,
        "kind": "recipe_run_v3",
        "recipe": "scrolling-preview",
        "input": {"prompt": "original moonlit ruins", "transparency_mode": "chroma"},
        "tag": "original-moonlit-ruins-chroma",
        "run_dir": "original-moonlit-ruins-chroma",
        "started_at": "2026-08-25T01:02:03.123456Z",
        "ended_at": "2026-08-25T01:02:04.123456Z",
        "duration_ms": 1000,
        "ok": True,
        "stages": [
            {
                "stage": "concept",
                "ok": True,
                "duration_ms": 1000,
                "artifacts": ["concept.png"],
            }
        ],
    }


def test_run_summary_accepts_and_round_trips_only_the_exact_current_shape() -> None:
    value = _valid_summary()

    summary = parse_recipe_run_summary(value)

    assert summary.to_dict() == value
    assert summary.failed_stage is None


def test_run_summary_normalizes_semantically_integral_json_numbers() -> None:
    value = _valid_summary()
    value["duration_ms"] = 1000.0
    stages = value["stages"]
    assert isinstance(stages, list)
    stage = stages[0]
    assert isinstance(stage, dict)
    stage["duration_ms"] = 1000.0

    summary = parse_recipe_run_summary(value)

    assert summary.duration_ms == 1000
    assert summary.stages[0].duration_ms == 1000
    assert summary.to_dict()["duration_ms"] == 1000


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update(schema_version=2), "literal_error"),
        (lambda value: value.update(kind="dialogue_run_v2"), "literal_error"),
        (lambda value: value.update(runDir=value.pop("run_dir")), "run_dir"),
        (lambda value: value.update(unexpected=True), "extra_forbidden"),
        (lambda value: value.update(stages=[]), "too_short"),
        (
            lambda value: value.update(run_dir="/tmp/original-moonlit-ruins-chroma"),
            "portable safe path segment",
        ),
        (lambda value: value.update(run_dir="another-run"), "run_dir must equal tag"),
        (
            lambda value: value["input"].update(mapBook={}),  # type: ignore[union-attr]
            "lower_snake_case",
        ),
        (
            lambda value: value["input"].update(  # type: ignore[union-attr]
                transparencyMode="chroma"
            ),
            "legacy transparencyMode",
        ),
        (lambda value: value.update(duration_ms=MAX_JSON_SAFE_INTEGER + 1), "less_than_equal"),
        (
            lambda value: value["input"].update(  # type: ignore[union-attr]
                seed=MAX_JSON_SAFE_INTEGER + 1
            ),
            "outside the JSON safe range",
        ),
        (
            lambda value: value["input"].update(seed=1e20),  # type: ignore[union-attr]
            "outside the JSON safe range",
        ),
        (
            lambda value: value.update(started_at="2026-08-25T01:02:03.1234567Z"),
            "at most six fractional digits",
        ),
        (
            lambda value: value["stages"][0].update(  # type: ignore[index,union-attr]
                durationMs=value["stages"][0].pop("duration_ms")  # type: ignore[index,union-attr]
            ),
            "duration_ms",
        ),
        (lambda value: value.update(failed_stage=None), "must omit failed_stage"),
        (
            lambda value: value["stages"][0].update(error=None),  # type: ignore[index,union-attr]
            "must omit error",
        ),
        (
            lambda value: value["stages"][0].update(  # type: ignore[index,union-attr]
                error="bad\x00error"
            ),
            "must not contain NUL",
        ),
        (
            lambda value: value["stages"][0].update(  # type: ignore[index,union-attr]
                artifacts=["/tmp/private.png"]
            ),
            "portable relative POSIX reference",
        ),
        (
            lambda value: value["stages"][0].update(  # type: ignore[index,union-attr]
                artifacts=["../escape.png"]
            ),
            "portable relative POSIX reference",
        ),
        (
            lambda value: value["stages"][0].update(  # type: ignore[index,union-attr]
                artifacts=["captures/bad%20name.png"]
            ),
            "portable relative POSIX reference",
        ),
    ],
)
def test_run_summary_rejects_legacy_aliases_missing_semantics_and_extras(
    mutation: object,
    message: str,
) -> None:
    value = deepcopy(_valid_summary())
    assert callable(mutation)
    mutation(value)

    with pytest.raises(RecipeRunSummaryLoadError, match=message):
        parse_recipe_run_summary(value)


def test_run_summary_requires_one_final_failed_stage_and_no_failed_artifacts() -> None:
    value = _valid_summary()
    value.update(ok=False, failed_stage="manifest")
    stages = value["stages"]
    assert isinstance(stages, list)
    stages.append(
        {
            "stage": "manifest",
            "ok": False,
            "duration_ms": 2,
            "artifacts": [],
            "error": "manifest validation failed",
        }
    )

    summary = parse_recipe_run_summary(value)

    assert summary.failed_stage == "manifest"
    assert summary.to_dict() == value

    stages[-1]["artifacts"] = ["untrusted.json"]
    with pytest.raises(RecipeRunSummaryLoadError, match="must not publish artifacts"):
        parse_recipe_run_summary(value)


def test_run_summary_loader_rejects_duplicate_keys_and_nonfinite_json(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    path.write_text('{"schema_version":3,"schema_version":3}', encoding="utf-8")
    with pytest.raises(RecipeRunSummaryLoadError, match="duplicate JSON key"):
        load_recipe_run_summary(path)

    value = _valid_summary()
    value["input"] = {"weight": float("nan")}
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(RecipeRunSummaryLoadError, match="invalid JSON constant"):
        load_recipe_run_summary(path)
