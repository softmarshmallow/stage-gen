"""Six-phase core stage graph plus the optional game, theme, style, profile and village stages."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from stage_gen.recipes.base import StageContext, StageSpec
from stage_gen.recipes.scrolling_preview.manifest import write_scrolling_preview_manifest
from stage_gen.recipes.scrolling_preview.village import village_enabled


async def _delegate(stage_name: str, context: StageContext) -> Sequence[str]:
    if context.runtime is None:
        raise RuntimeError(
            f"scrolling-preview stage {stage_name} requires a composed recipe runtime"
        )
    return await context.runtime.run_recipe_stage("scrolling-preview", stage_name, context)


async def _concept(context: StageContext) -> Sequence[str]:
    return await _delegate("concept", context)


async def _theme_compile(context: StageContext) -> Sequence[str]:
    return await _delegate("theme-compile", context)


async def _profile_resolve(context: StageContext) -> Sequence[str]:
    return await _delegate("profile-resolve", context)


async def _game_resolve(context: StageContext) -> Sequence[str]:
    return await _delegate("game-resolve", context)


async def _soundtrack_resolve(context: StageContext) -> Sequence[str]:
    return await _delegate("soundtrack-resolve", context)


async def _soundtrack_generate(context: StageContext) -> Sequence[str]:
    return await _delegate("soundtrack-generate", context)


async def _map_book_resolve(context: StageContext) -> Sequence[str]:
    return await _delegate("map-book-resolve", context)


async def _style_select(context: StageContext) -> Sequence[str]:
    return await _delegate("style-select", context)


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


async def _village_spec(context: StageContext) -> Sequence[str]:
    return await _delegate("village-spec", context)


async def _village_concepts(context: StageContext) -> Sequence[str]:
    return await _delegate("village-concepts", context)


async def _village_stills(context: StageContext) -> Sequence[str]:
    return await _delegate("village-stills", context)


async def _village_strips(context: StageContext) -> Sequence[str]:
    return await _delegate("village-strips", context)


async def _manifest(context: StageContext) -> Sequence[str]:
    # A runtime may generate/normalize per-run music before assembly.  When it
    # handles this stage it is authoritative; otherwise use the deterministic
    # repository fallback + manifest assembler directly.
    if context.runtime is not None:
        try:
            return await context.runtime.run_recipe_stage("scrolling-preview", "manifest", context)
        except NotImplementedError:
            pass
    if "game" in context.input:
        # A directed manifest depends on the resolved contract's resident render shape and full
        # mob state set as well as its identity. Only the composed executor revalidates and derives
        # those values, so the direct assembler must fail closed instead of publishing a downgraded
        # directed run.
        raise RuntimeError("game-directed scrolling manifest requires a composed recipe runtime")
    result = await write_scrolling_preview_manifest(
        run_dir=context.run_dir,
        tag=context.tag,
        transparency_mode=context.config.transparency_mode,
        character_profile="character_profile" in context.input,
        village=village_enabled(context.input),
        soundtrack="soundtrack" in context.input,
        map_book="map_book" in context.input,
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

THEME_COMPILE_STAGE = StageSpec(
    name="theme-compile",
    wave=0.5,
    description="compile numeric theme controls into stage-scoped prose",
    run=_theme_compile,
)

STYLE_SELECT_STAGE = StageSpec(
    name="style-select",
    wave=0.75,
    description="select and locally materialize one canonical image style anchor",
    run=_style_select,
)

STYLE_SELECT_AFTER_THEME_STAGE = StageSpec(
    name="style-select",
    wave=0.75,
    description="select and locally materialize one canonical image style anchor",
    run=_style_select,
    depends_on=("theme-compile",),
)

PROFILE_RESOLVE_STAGE = StageSpec(
    name="profile-resolve",
    wave=0.25,
    description="resolve and canonically bind the authored player character profile",
    run=_profile_resolve,
)

#: Placed ahead of every other opt-in resolver, at the very front of the graph.
#:
#: The game contract directs the stages that follow it - it supplies the art-direction clause the
#: concept prompt carries, the build the player turnaround is drawn to, and the vocabulary the
#: village roster is generated against - so nothing that consumes it can run first. It is also the
#: cheapest stage in the graph and the one most likely to reject a request: it reads one local
#: file, checks two digests, and refuses a world authored for a camera this recipe cannot draw. A
#: run whose direction is wrong should discover that before it has paid for a concept image.
GAME_RESOLVE_STAGE = StageSpec(
    name="game-resolve",
    wave=0.1,
    description="resolve and canonically bind the authored game contract",
    run=_game_resolve,
)

SOUNDTRACK_RESOLVE_STAGE = StageSpec(
    name="soundtrack-resolve",
    wave=0.2,
    description="resolve and canonically bind the authored game soundtrack",
    run=_soundtrack_resolve,
    depends_on=("game-resolve",),
)

SOUNDTRACK_GENERATE_STAGE = StageSpec(
    name="soundtrack-generate",
    wave=4.5,
    description="generate or reuse every game-global soundtrack track",
    run=_soundtrack_generate,
    depends_on=("post-split", "soundtrack-resolve"),
)

MAP_BOOK_RESOLVE_STAGE = StageSpec(
    name="map-book-resolve",
    wave=0.3,
    description="resolve and canonically bind the authored ordered game map book",
    run=_map_book_resolve,
    depends_on=("game-resolve", "soundtrack-resolve"),
)


#: The village stages, placed after the whole hunting graph and before the manifest.
#:
#: Their dependencies would allow them much earlier - `village-spec` needs only `concept`, and
#: the strips need only their own turnarounds - but `orchestration/runner.py` walks the stage
#: tuple strictly sequentially and breaks on the first failure. There is no cross-stage
#: concurrency for an earlier wave to overlap with, so an earlier placement buys no wall-clock
#: time and costs the run its core artwork: a village-spec failure at wave 1.6 would abort
#: before Wave A ever ran, and an optional feature would have destroyed the mandatory one.
#:
#: Last-but-one is therefore the only correct position. Every hunting artifact is already on
#: disk and cache-valid before the first village call is made, so the worst a village failure
#: can now do is leave the run without a village - which is exactly the blast radius an opt-in
#: feature is allowed to have.
VILLAGE_STAGES: tuple[StageSpec, ...] = (
    StageSpec(
        name="village-spec",
        wave=4.1,
        description="village hub bible JSON via vision LLM",
        run=_village_spec,
        # `concept` is the only artifact it reads; `post-split` is named so the DAG itself
        # records that the mandatory graph completes first, rather than leaving that to the
        # wave number alone.
        depends_on=("concept", "post-split"),
    ),
    StageSpec(
        name="village-concepts",
        wave=4.2,
        description="village fan-out: per-resident turnarounds and the village fixture sheet",
        run=_village_concepts,
        depends_on=("village-spec",),
    ),
    StageSpec(
        name="village-strips",
        wave=4.3,
        description="village fan-out: per-resident idle strips",
        run=_village_strips,
        depends_on=("village-concepts",),
    ),
)

#: The village graph a game contract directs. Identical to `VILLAGE_STAGES` except that the
#: last stage draws stills instead of strips, which is the whole of the resident render profile
#: as the graph sees it. Substituted rather than added: a run draws each resident once, and a
#: graph carrying both would generate a strip and a still of the same person and publish one.
DIRECTED_VILLAGE_STAGES: tuple[StageSpec, ...] = (
    *VILLAGE_STAGES[:-1],
    StageSpec(
        name="village-stills",
        wave=4.3,
        description="village fan-out: per-resident forward-facing stills",
        run=_village_stills,
        depends_on=("village-concepts",),
    ),
)


def _stages_after_style() -> tuple[StageSpec, ...]:
    concept, *remaining = STAGES
    styled_concept = StageSpec(
        name=concept.name,
        wave=concept.wave,
        description=concept.description,
        run=concept.run,
        depends_on=("style-select",),
    )
    return (styled_concept, *remaining)


def _stages_after_theme() -> tuple[StageSpec, ...]:
    concept, *remaining = STAGES
    themed_concept = StageSpec(
        name=concept.name,
        wave=concept.wave,
        description=concept.description,
        run=concept.run,
        depends_on=("theme-compile",),
    )
    return (themed_concept, *remaining)


def _stages_with_village(
    configured: tuple[StageSpec, ...],
    *,
    directed: bool = False,
) -> tuple[StageSpec, ...]:
    """Splice the village stages into an already-composed graph, in wave order.

    Composition is a merge rather than a prefix or a suffix because, unlike the theme, style and
    profile stages, the village stages do not all run before the graph they join - they interleave
    with it. Sorting the union by wave keeps the tuple in the order it executes, which is the
    order every other branch here already leaves it in, and is stable for the existing stages
    because each of those branches already emits its stages in ascending wave order.

    `manifest` gains the dependency instead of the village stages gaining one on it: the manifest
    enumerates published artifacts, so it has to run after the last village artifact exists, and
    a village stage that ran after the manifest would leave its artwork out of the very file the
    runtime reads to find it.
    """

    village_stages = DIRECTED_VILLAGE_STAGES if directed else VILLAGE_STAGES
    terminal = village_stages[-1].name
    village_bound = tuple(
        StageSpec(
            name=stage.name,
            wave=stage.wave,
            description=stage.description,
            run=stage.run,
            depends_on=(*stage.depends_on, terminal),
        )
        if stage.name == "manifest"
        else stage
        for stage in configured
    )
    return tuple(sorted((*village_bound, *village_stages), key=lambda stage: stage.wave))


def _stages_with_soundtrack(configured: tuple[StageSpec, ...]) -> tuple[StageSpec, ...]:
    soundtrack_bound = tuple(
        StageSpec(
            name=stage.name,
            wave=stage.wave,
            description=stage.description,
            run=stage.run,
            depends_on=(*stage.depends_on, "soundtrack-generate"),
        )
        if stage.name == "manifest"
        else stage
        for stage in configured
    )
    return tuple(
        sorted(
            (*soundtrack_bound, SOUNDTRACK_RESOLVE_STAGE, SOUNDTRACK_GENERATE_STAGE),
            key=lambda stage: stage.wave,
        )
    )


def _stages_with_map_book(configured: tuple[StageSpec, ...]) -> tuple[StageSpec, ...]:
    map_bound = tuple(
        StageSpec(
            name=stage.name,
            wave=stage.wave,
            description=stage.description,
            run=stage.run,
            depends_on=(*stage.depends_on, "map-book-resolve"),
        )
        if stage.name == "manifest"
        else stage
        for stage in configured
    )
    return tuple(sorted((*map_bound, MAP_BOOK_RESOLVE_STAGE), key=lambda stage: stage.wave))


def scrolling_preview_stages(input_value: Mapping[str, Any]) -> tuple[StageSpec, ...]:
    """Keep the base graph exact unless an explicit feature is enabled."""

    has_theme = "theme" in input_value
    has_style = "style_anchor" in input_value
    has_profile = "character_profile" in input_value
    has_game = "game" in input_value
    has_soundtrack = "soundtrack" in input_value
    has_map_book = "map_book" in input_value
    has_village = village_enabled(input_value)
    if (
        not has_theme
        and not has_style
        and not has_profile
        and not has_village
        and not has_game
        and not has_soundtrack
        and not has_map_book
    ):
        return STAGES
    if has_theme and not has_style:
        configured = (THEME_COMPILE_STAGE, *_stages_after_theme())
    elif has_style:
        style_stage = STYLE_SELECT_AFTER_THEME_STAGE if has_theme else STYLE_SELECT_STAGE
        prefix = (THEME_COMPILE_STAGE, style_stage) if has_theme else (style_stage,)
        configured = (*prefix, *_stages_after_style())
    else:
        configured = STAGES
    if has_profile:
        profile_bound = tuple(
            StageSpec(
                name=stage.name,
                wave=stage.wave,
                description=stage.description,
                run=stage.run,
                depends_on=(*stage.depends_on, "profile-resolve"),
            )
            if stage.name == "wave-a"
            else stage
            for stage in configured
        )
        configured = (PROFILE_RESOLVE_STAGE, *profile_bound)
    if has_game:
        # Every stage that draws reads the contract, so the whole graph waits on it. Bound to
        # `concept` alone rather than to each consumer: `concept` is the first stage of the core
        # graph and everything else already depends on it transitively, so one edge states the
        # ordering without repeating it eight times.
        game_bound = tuple(
            StageSpec(
                name=stage.name,
                wave=stage.wave,
                description=stage.description,
                run=stage.run,
                depends_on=(*stage.depends_on, "game-resolve"),
            )
            if stage.name == "concept"
            else stage
            for stage in configured
        )
        configured = (GAME_RESOLVE_STAGE, *game_bound)
    if has_soundtrack:
        if not has_game:
            raise ValueError("scrolling-preview soundtrack requires a game contract binding")
        if not has_map_book:
            raise ValueError("scrolling-preview soundtrack requires a map_book binding")
        configured = _stages_with_soundtrack(configured)
    if has_map_book:
        if not has_game or not has_soundtrack:
            raise ValueError("scrolling-preview map_book requires game and soundtrack bindings")
        configured = _stages_with_map_book(configured)
    if not has_village:
        return configured
    return _stages_with_village(configured, directed=has_game)
