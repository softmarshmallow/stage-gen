"""Six-phase stage graph for the scrolling-preview recipe."""

from __future__ import annotations

from collections.abc import Sequence

from stage_gen.recipes.base import StageContext, StageSpec
from stage_gen.recipes.scrolling_preview.manifest import write_scrolling_preview_manifest


async def _delegate(stage_name: str, context: StageContext) -> Sequence[str]:
    if context.runtime is None:
        raise RuntimeError(
            f"scrolling-preview stage {stage_name} requires a composed recipe runtime"
        )
    return await context.runtime.run_scrolling_preview_stage(stage_name, context)


async def _concept(context: StageContext) -> Sequence[str]:
    return await _delegate("concept", context)


async def _world_spec(context: StageContext) -> Sequence[str]:
    return await _delegate("world-spec", context)


async def _wave_a(context: StageContext) -> Sequence[str]:
    # The composed runtime owns the TaskGroup fan-out so component failures
    # cancel siblings and all provider calls share the stage cancellation scope.
    return await _delegate("wave-a", context)


async def _wave_b(context: StageContext) -> Sequence[str]:
    return await _delegate("wave-b", context)


async def _post_split(context: StageContext) -> Sequence[str]:
    return await _delegate("post-split", context)


async def _manifest(context: StageContext) -> Sequence[str]:
    # A runtime may generate/normalize per-run music before assembly.  When it
    # handles this stage it is authoritative; otherwise use the deterministic
    # repository fallback + manifest assembler directly.
    if context.runtime is not None:
        try:
            return await context.runtime.run_scrolling_preview_stage("manifest", context)
        except NotImplementedError:
            pass
    result = await write_scrolling_preview_manifest(
        run_dir=context.run_dir,
        tag=context.tag,
        transparency_mode=context.config.transparency_mode,
    )
    return result.artifacts


STAGES: tuple[StageSpec, ...] = (
    StageSpec(
        name="concept",
        wave=1,
        description="world concept image (style root)",
        run=_concept,
    ),
    StageSpec(
        name="world-spec",
        wave=1.5,
        description="world bible JSON via vision LLM",
        run=_world_spec,
        depends_on=("concept",),
    ),
    StageSpec(
        name="wave-a",
        wave=2,
        description=(
            "Wave A fan-out: layers, tileset, character, mobs, obstacles, items, inventory, portal"
        ),
        run=_wave_a,
        depends_on=("world-spec",),
    ),
    StageSpec(
        name="wave-b",
        wave=3,
        description=(
            "Wave B fan-out: character master sheet, character attack, per-mob idle + hurt strips"
        ),
        run=_wave_b,
        depends_on=("wave-a",),
    ),
    StageSpec(
        name="post-split",
        wave=4,
        description="split master sheet into per-state strips",
        run=_post_split,
        depends_on=("wave-b",),
    ),
    StageSpec(
        name="manifest",
        wave=5,
        description="write per-tag artifact manifest and resolve preview music",
        run=_manifest,
        depends_on=("post-split",),
    ),
)
