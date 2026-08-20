"""Engine- and genre-neutral sequential recipe runner."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path

from stage_gen.config import parse_transparency_mode
from stage_gen.recipes.base import RunOptions, RunSummary, StageContext, StageResult
from stage_gen.reliability import (
    assert_safe_path_segment,
    atomic_write_json,
    redact_secrets,
)
from stage_gen.tags import tag_for_transparency_mode


async def run_recipe(options: RunOptions) -> RunSummary:
    mode = parse_transparency_mode(
        options.input.get("transparencyMode", options.config.transparency_mode),
        "input.transparencyMode",
    )
    input_value = {**options.input, "transparencyMode": mode}
    stages = options.recipe.stages_for(input_value)
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
                    )
                )
            stage_results.append(
                StageResult(
                    stage=stage.name,
                    ok=True,
                    duration_ms=round((time.perf_counter() - start) * 1_000),
                    artifacts=tuple(str(path) for path in paths),
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
            message = redact_secrets(
                str(_actionable_exception(error)),
                tuple(
                    secret
                    for secret in (run_config.open_router_api_key, run_config.fal_key)
                    if secret is not None
                ),
            )
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
