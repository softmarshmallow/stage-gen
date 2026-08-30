"""Engine- and genre-neutral sequential recipe runner."""

from __future__ import annotations

import asyncio
import stat
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from gnode import assert_safe_path_segment, atomic_write_json, redact_secrets
from stage_gen.config import parse_transparency_mode
from stage_gen.contracts import validate_run_artifact_ref
from stage_gen.recipes.base import (
    RunOptions,
    RunSummary,
    StageContext,
    StageResult,
    resolve_force_stage_plan,
)
from stage_gen.tags import tag_for_transparency_mode


async def run_recipe(options: RunOptions) -> RunSummary:
    if "transparencyMode" in options.input:
        raise ValueError("recipe input must not declare legacy transparencyMode")
    mode = parse_transparency_mode(
        options.input.get("transparency_mode", options.config.transparency_mode),
        "input.transparency_mode",
    )
    input_value = {**options.input, "transparency_mode": mode.value}
    stages = options.recipe.stages_for(input_value)
    force_plan = resolve_force_stage_plan(stages, options.force_stages)
    run_config = options.config.model_copy(update={"transparency_mode": mode})
    log = options.log or print
    computed_tag = tag_for_transparency_mode(options.recipe.tag_for(input_value), mode)
    tag = assert_safe_path_segment(options.tag or computed_tag, "recipe tag")
    output_root = await asyncio.to_thread(Path(options.config.out_dir).resolve)
    run_dir = output_root / tag
    await asyncio.to_thread(run_dir.mkdir, parents=True, exist_ok=True)

    started = datetime.now(UTC)
    stage_results: list[StageResult] = []
    failed_stage: str | None = None
    cancelled: asyncio.CancelledError | None = None

    log(f"stage-gen: recipe={options.recipe.id}")
    log(f"stage-gen: tag={tag}")
    log(f"stage-gen: out={run_dir}")

    for stage in stages:
        start = time.perf_counter()
        wave = int(stage.wave) if stage.wave.is_integer() else stage.wave
        log(f"  [wave {wave}] {stage.name} - {stage.description}")
        try:
            if options.cancellation is not None:
                options.cancellation.raise_if_cancelled()
            async with asyncio.timeout(run_config.stage_timeout_ms / 1_000):
                paths = await stage.run(
                    StageContext(
                        input=input_value,
                        tag=tag,
                        run_dir=run_dir,
                        config=run_config,
                        runtime=options.runtime,
                        cancellation=options.cancellation,
                        force_stages=force_plan.requested,
                        affected_stages=force_plan.affected,
                    )
                )
            stage_results.append(
                StageResult(
                    stage=stage.name,
                    ok=True,
                    duration_ms=round((time.perf_counter() - start) * 1_000),
                    artifacts=_portable_stage_artifacts(paths, run_dir),
                )
            )
        except asyncio.CancelledError as error:
            failed_stage = stage.name
            cancelled = error
            stage_results.append(
                StageResult(
                    stage=stage.name,
                    ok=False,
                    duration_ms=round((time.perf_counter() - start) * 1_000),
                    artifacts=(),
                    error="cancelled",
                )
            )
            break
        except TimeoutError:
            failed_stage = stage.name
            stage_results.append(
                StageResult(
                    stage=stage.name,
                    ok=False,
                    duration_ms=round((time.perf_counter() - start) * 1_000),
                    artifacts=(),
                    error=f"stage {stage.name} timed out after {run_config.stage_timeout_ms}ms",
                )
            )
            break
        except Exception as error:
            failed_stage = stage.name
            actionable = _actionable_exception(error)
            actionable_message = str(actionable).strip() or type(actionable).__name__
            message = (
                redact_secrets(
                    actionable_message,
                    tuple(
                        secret
                        for secret in (run_config.open_router_api_key, run_config.fal_key)
                        if secret is not None
                    ),
                )
                .replace("\x00", "[NUL]")
                .strip()
            )
            if not message:  # Defensive if a future redactor removes the entire message.
                message = type(actionable).__name__
            stage_results.append(
                StageResult(
                    stage=stage.name,
                    ok=False,
                    duration_ms=round((time.perf_counter() - start) * 1_000),
                    artifacts=(),
                    error=message,
                )
            )
            break

    ended = datetime.now(UTC)
    summary = RunSummary(
        recipe=options.recipe.id,
        input=input_value,
        tag=tag,
        run_dir=str(run_dir),
        started_at=started.isoformat().replace("+00:00", "Z"),
        ended_at=ended.isoformat().replace("+00:00", "Z"),
        duration_ms=round((ended - started).total_seconds() * 1_000),
        ok=failed_stage is None,
        failed_stage=failed_stage,
        stages=tuple(stage_results),
    )
    await asyncio.to_thread(atomic_write_json, run_dir / "run.json", summary.to_dict())
    if cancelled is not None:
        raise cancelled
    return summary


def _actionable_exception(error: Exception) -> Exception:
    if isinstance(error, ExceptionGroup):
        for child in error.exceptions:
            if isinstance(child, Exception):
                return _actionable_exception(child)
    return error


def _portable_stage_artifacts(paths: Sequence[str | Path], run_dir: Path) -> tuple[str, ...]:
    try:
        run_root = run_dir.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError("run directory is not a readable real directory") from error
    if run_root != run_dir:
        raise ValueError("run directory must not be a symlink")
    portable: list[str] = []
    for raw_path in paths:
        value = str(raw_path)
        path = Path(value)
        if path.is_absolute():
            if (
                value != value.strip()
                or "\x00" in value
                or "\\" in value
                or value.startswith("//")
                or "//" in value[1:]
                or any(part in {".", ".."} for part in path.parts)
            ):
                raise ValueError("stage artifact absolute path is ambiguous")
            try:
                relative = path.relative_to(run_dir)
            except ValueError as error:
                raise ValueError("stage artifact escapes the run directory") from error
            reference = relative.as_posix()
        else:
            reference = validate_run_artifact_ref(value)
            relative = Path(*reference.split("/"))
        reference = validate_run_artifact_ref(reference)
        lexical = run_dir / relative
        try:
            resolved = lexical.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise ValueError("stage artifact does not resolve to an existing file") from error
        if resolved != lexical:
            raise ValueError("stage artifact must not be a symlink or use symlinked parents")
        try:
            resolved.relative_to(run_root)
        except ValueError as error:
            raise ValueError("stage artifact escapes the run directory") from error
        try:
            artifact_mode = lexical.lstat().st_mode
        except OSError as error:
            raise ValueError("stage artifact metadata is not readable") from error
        if not stat.S_ISREG(artifact_mode):
            raise ValueError("stage artifact must be a regular file")
        if reference in portable:
            raise ValueError("stage artifacts must be unique")
        portable.append(reference)
    return tuple(portable)
