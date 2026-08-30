#!/usr/bin/env python3
"""Refresh one completed scrolling-preview manifest without rerunning generation stages.

This is a narrow offline maintenance harness for a run whose canonical artifacts were changed by
an explicit, separately validated workflow.  It reconstructs the recipe context from ``run.json``
and calls only ``ScrollingPreviewExecutor``'s manifest handler.  Provider services are replaced by
sentinels that fail if the manifest path unexpectedly attempts generation.

The ordinary ``generate --force-stage manifest`` command is intentionally not used here: the
generic recipe runner still visits every upstream stage, and those stages are allowed to reject or
replace artifacts whose prompt-bound cache identity changed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import stat
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gnode import assert_safe_path_segment, redact_secrets, sanitize_for_persistence
from stage_gen.config import StageGenConfig, load_config, parse_transparency_mode
from stage_gen.contracts import load_recipe_run_summary
from stage_gen.recipes.base import StageContext
from stage_gen.recipes.scrolling_preview.cache import valid_artifact_pair
from stage_gen.recipes.scrolling_preview.executor import ScrollingPreviewExecutor

_KIND = "scrolling_preview_manifest_refresh"


@dataclass(frozen=True, slots=True)
class RefreshPlan:
    run_dir: Path
    tag: str
    context: StageContext
    previous_manifest_path: Path
    previous_manifest_provenance_path: Path


class ManifestStageRunner(Protocol):
    async def run_scrolling_preview_stage(
        self, stage_name: str, context: StageContext
    ) -> Sequence[str]: ...


class _OfflineOnlyService:
    """Explode if a future manifest change accidentally reaches a provider service."""

    def __getattr__(self, name: str) -> Any:
        raise RuntimeError(f"manifest-only refresh attempted provider operation: {name}")


def prepare_refresh(run_dir: Path, config: StageGenConfig) -> RefreshPlan:
    """Validate that ``run_dir`` is one complete, previously manifested recipe run."""

    resolved_run_dir = _validated_existing_directory(run_dir, "run directory")
    summary_path = _validated_regular_file_within(
        resolved_run_dir,
        resolved_run_dir / "run.json",
        "run summary",
    )
    summary = load_recipe_run_summary(summary_path)
    if summary.recipe != "scrolling-preview":
        raise ValueError("run summary is not for scrolling-preview")
    if not summary.ok:
        raise ValueError("manifest refresh requires a completed successful run")

    tag = assert_safe_path_segment(summary.tag, "run tag")
    if resolved_run_dir.name != tag:
        raise ValueError("run directory name does not match the run tag")
    if summary.run_dir != resolved_run_dir.name:
        raise ValueError("run summary run_dir does not match the requested run directory")

    if not summary.stages:
        raise ValueError("run summary must contain completed stages")
    manifest_stages = [stage for stage in summary.stages if stage.stage == "manifest"]
    if len(manifest_stages) != 1 or not manifest_stages[0].ok:
        raise ValueError("run summary does not contain one successful manifest stage")
    if any(not stage.ok for stage in summary.stages):
        raise ValueError("run summary contains an incomplete stage")

    raw_input = summary.input
    mode = parse_transparency_mode(
        raw_input.get("transparency_mode"),
        "run input.transparency_mode",
    )
    if "game" in raw_input and config.game_library_root is None:
        raise ValueError("game-directed manifest refresh requires game_library_root")
    game_library_root = config.game_library_root
    if game_library_root is not None:
        game_library_root = _validated_existing_directory(
            game_library_root,
            "game library root",
        )

    manifest_path = resolved_run_dir / f"manifest_{tag}.json"
    manifest_provenance_path = Path(f"{manifest_path}.meta.json")
    _validated_regular_file_within(resolved_run_dir, manifest_path, "existing manifest")
    _validated_regular_file_within(
        resolved_run_dir,
        manifest_provenance_path,
        "existing manifest provenance",
    )
    if not valid_artifact_pair(manifest_path, force=False):
        raise ValueError("existing manifest artifact pair is stale or invalid")

    run_config = config.model_copy(
        update={
            "out_dir": resolved_run_dir.parent,
            "transparency_mode": mode,
            "game_library_root": game_library_root,
        }
    )
    context = StageContext(
        input=cast(dict[str, Any], dict(raw_input)),
        tag=tag,
        run_dir=resolved_run_dir,
        config=run_config,
    )
    return RefreshPlan(
        run_dir=resolved_run_dir,
        tag=tag,
        context=context,
        previous_manifest_path=manifest_path,
        previous_manifest_provenance_path=manifest_provenance_path,
    )


async def refresh_manifest(
    plan: RefreshPlan,
    runner: ManifestStageRunner | None = None,
) -> dict[str, object]:
    """Run only the deterministic manifest handler and verify its output pair."""

    if runner is None:
        unavailable = _OfflineOnlyService()
        runner = ScrollingPreviewExecutor(
            image_service=cast(Any, unavailable),
            structured_service=cast(Any, unavailable),
            background_service=cast(Any, unavailable),
        )
    artifacts = tuple(await runner.run_scrolling_preview_stage("manifest", plan.context))
    manifest_path = plan.run_dir / f"manifest_{plan.tag}.json"
    manifest_provenance_path = Path(f"{manifest_path}.meta.json")
    _validated_regular_file_within(plan.run_dir, manifest_path, "refreshed manifest")
    _validated_regular_file_within(
        plan.run_dir,
        manifest_provenance_path,
        "refreshed manifest provenance",
    )
    if not valid_artifact_pair(manifest_path, force=False):
        raise ValueError("refreshed manifest artifact pair is stale or invalid")
    manifest = _read_json_object(manifest_path, "refreshed manifest")
    if manifest.get("recipe") != "scrolling-preview" or manifest.get("tag") != plan.tag:
        raise ValueError("refreshed manifest identity does not match the run")
    repeat = manifest.get("image_repeat")
    if not isinstance(repeat, dict):
        raise ValueError("refreshed manifest does not declare image_repeat")
    repeat_artifacts = repeat.get("artifacts")
    if not isinstance(repeat_artifacts, list):
        raise ValueError("refreshed manifest image_repeat.artifacts must be a list")
    return {
        "schema_version": 1,
        "kind": _KIND,
        "ok": True,
        "tag": plan.tag,
        "run_dir": str(plan.run_dir),
        "manifest": manifest_path.name,
        "manifest_provenance": manifest_provenance_path.name,
        "image_repeat_status": repeat.get("status"),
        "image_repeat_artifacts": len(repeat_artifacts),
        "returned_artifacts": [Path(path).name for path in artifacts],
    }


def _validated_existing_directory(path_value: str | Path, label: str) -> Path:
    path = Path(path_value).absolute()
    cursor = Path(path.anchor)
    try:
        metadata = cursor.lstat()
    except FileNotFoundError as error:  # pragma: no cover - platform invariant
        raise ValueError(f"{label} does not exist") from error
    for part in path.parts[1:]:
        cursor /= part
        try:
            metadata = cursor.lstat()
        except FileNotFoundError as error:
            raise ValueError(f"{label} does not exist") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"{label} contains a symlink")
        if cursor != path and not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(f"{label} parent is not a directory")
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"{label} must be a directory")
    if path.resolve(strict=True) != path:
        raise ValueError(f"{label} escapes its lexical path")
    return path


def _validated_regular_file_within(root: Path, path: Path, label: str) -> Path:
    lexical_root = root.absolute()
    lexical_path = path.absolute()
    try:
        lexical_path.relative_to(lexical_root)
    except ValueError as error:
        raise ValueError(f"{label} escapes its root") from error
    try:
        metadata = lexical_path.lstat()
    except FileNotFoundError as error:
        raise ValueError(f"{label} does not exist") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{label} must be a regular non-symlink file")
    if lexical_path.resolve(strict=True) != lexical_path:
        raise ValueError(f"{label} escapes its root")
    return lexical_path


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not readable JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, Any], value)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--game-library-root",
        type=Path,
        help="Workspace root used to revalidate a portable authored game binding.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    options = _parse_args(argv)
    secrets: tuple[str, ...] = ()
    plan: RefreshPlan | None = None
    try:
        config = load_config()
        if options.game_library_root is not None:
            config = config.model_copy(
                update={"game_library_root": options.game_library_root.absolute()}
            )
        secrets = tuple(value for value in (config.open_router_api_key, config.fal_key) if value)
        plan = prepare_refresh(options.run_dir, config)
        report = asyncio.run(refresh_manifest(plan))
    except Exception as error:
        report = {
            "schema_version": 1,
            "kind": _KIND,
            "ok": False,
            "error": {
                "type": type(error).__name__,
                "message": redact_secrets(str(error), secrets)[:2000],
            },
            **({"tag": plan.tag, "run_dir": str(plan.run_dir)} if plan is not None else {}),
        }
    safe = sanitize_for_persistence(report, secrets)
    if not isinstance(safe, dict):  # pragma: no cover - fixed report shapes
        safe = {
            "schema_version": 1,
            "kind": _KIND,
            "ok": False,
            "error": {"type": "TypeError", "message": "report sanitization failed"},
        }
    print(json.dumps(safe, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if safe.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
