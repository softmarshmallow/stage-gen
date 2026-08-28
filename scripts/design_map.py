#!/usr/bin/env python3
"""Compose a Bellweather map as a chunk sentence and compile it into the shipped map contract.

`stage_gen.components.platformer_map_design` knows how to compose and validate a platformer map
against a declared capability profile, and nothing else. It deliberately contains no game. This
script is the Bellweather side of that boundary: it owns the game's `PlatformerProfile`, drives
the offline checks, and adapts an accepted design into the authored `LevelPlan` that
`scripts/author_terrain.py` already compiles into the occupancy rows and climbable placements
`maps/<map_id>.toml` carries. `author_terrain` emits those blocks; `apply` below is what puts
them into a map document.

What this is NOT. It is not a second map generator: the grammar, the expander, and every
profile-driven rule live in the component. It is not a terrain art pipeline: `occupancy` is
excluded from the ground atlas's cache identity, so reshaping a level costs no provider
operation there. It is not free of provider cost either, though: the climbable atlas node
digests the whole authored `[climbable]` block, placements included, so an `apply` that moves a
placement re-bills that one image until the cache split tracked in TODO.md lands. It is not a
TOML writer: `apply` performs narrow text surgery on the exact blocks `author_terrain.emit_toml()`
owns plus the map's own `revision = N` line, and leaves every other byte of the map, including
the `[portal]` table, untouched. It is not a tool that picks its own target: `apply` requires
`--library-root`, because rewriting the digest-pinned shipped library is a deliberate,
separately authorized edit. And it is not a live tool by default: only `design` reaches a
provider, and only behind an explicit double opt-in.

    uv run python scripts/design_map.py check --example
    uv run python scripts/design_map.py check --design out/crowncrag.json
    uv run python scripts/design_map.py render --example --out out/crowncrag.png
    uv run python scripts/design_map.py apply --design out/crowncrag.json \
        --map-id crowncrag-road --library-root library/games --dry-run
    STAGE_GEN_RUN_LIVE=1 uv run python scripts/design_map.py design --live \
        --brief "a rising pilgrim road" --out out/crowncrag.json
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import itertools
import json
import os
import re
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import NamedTuple

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw

from scripts.author_terrain import (
    CLIMBABLE_RISE_TILES,
    MAX_CLIMBABLE_PLACEMENTS,
    MAX_FRAMED_SURFACE_TILES,
    Climb,
    Ledge,
    LevelPlan,
    emit_toml,
    validate,
)
from stage_gen.components._game_input import sha256_bytes
from stage_gen.components.game_map.prepared import MAX_UNASSISTED_TERRAIN_RISE_TILES
from stage_gen.components.platformer_map_design import (
    PLATFORMER_MAP_DESIGN_KIND,
    PLATFORMER_MAP_DESIGN_SCHEMA_VERSION,
    STANDARD_TILE_ROLES,
    DesignBrief,
    DesignedMap,
    GeometryProfile,
    MovementProfile,
    PlatformerChunkMapDesign,
    PlatformerMapDesignLoadError,
    PlatformerProfile,
    canonical_platformer_chunk_map_design_json,
    check,
    design_chunks,
    expand_chunks,
    load_platformer_chunk_map_design_bytes,
    translate,
)
from stage_gen.orchestration.game_package import (
    GamePackageValidationError,
    resolve_game_package,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
#: The shipped, digest-pinned library. `apply` has no default target; naming this one is a
#: deliberate, separately authorized edit, so it only warns. Tests and experiments pass a copy.
REPOSITORY_LIBRARY_ROOT = REPOSITORY_ROOT / "library" / "games"
#: The environment opt-in that, together with `--live`, permits a provider call.
LIVE_ENVIRONMENT_FLAG = "STAGE_GEN_RUN_LIVE"

BELLWEATHER_SIDE_VIEW = PlatformerProfile(
    profile_id="bellweather-side-view",
    movement=MovementProfile(
        # Every traversal number below is the game's, not the designer's.
        max_step_up_tiles=MAX_UNASSISTED_TERRAIN_RISE_TILES,
        #: Measured from the runtime's own jump arc: rise 1 clears 8 columns, rise 2 clears 6,
        #: and nothing higher is jumpable at any gap. See web/lib/runtime/player.ts.
        jump_reach={1: 8, 2: 6},
        climbable_rise_tiles=(CLIMBABLE_RISE_TILES,),
        #: A level or downward move stays crossable only this far; treating any drop as free
        #: silently connects surfaces a screen apart.
        level_gap_tiles=8,
        climbable_footing="ground",
        #: The runtime throws "ladder requires a flat lower terrain endpoint" without it.
        climbable_needs_flat_footing=True,
    ),
    geometry=GeometryProfile(
        # 96x16 is the shipped crowncrag-road grid; author_terrain.validate bounds rows to
        # 2..64 and columns to 8..512, so both sit well inside what the contract accepts.
        columns=96,
        rows=16,
        ground_depth_tiles=(1, 8),
        max_walkable_height_tiles=MAX_FRAMED_SURFACE_TILES,
        platforms_single_thickness=True,
    ),
    roles=STANDARD_TILE_ROLES,
    climbable_variants=("bellroot_ladder", "shrine_rope_ladder", "bellrope_climb"),
    climbable_count=(3, MAX_CLIMBABLE_PLACEMENTS),
    # Biomes are deliberately OFF for this game: game-map-v7 has no per-region style surface,
    # so nothing downstream could consume a per-column biome tag. The profile gates the channel
    # rather than the designer inventing one, and turning it on means adding that surface first.
    biomes=(),
    biome_min_span_tiles=0,
    notes=(
        "Bellweather side-view platformer. Terrain shape is authored rather than generated, so "
        "reshaping a level costs no provider operation."
    ),
)

PROFILES: dict[str, PlatformerProfile] = {BELLWEATHER_SIDE_VIEW.profile_id: BELLWEATHER_SIDE_VIEW}

#: A hand-composed sentence that satisfies every profile rule and every authored terrain
#: contract, so `check`, `render`, and `apply` can be exercised with no external file.
EXAMPLE_CHUNKS: list[dict[str, object]] = [
    {"kind": "run", "len": 8},
    {"kind": "perch", "platform_width": 6, "climb_rise": 4, "variant": "bellroot_ladder"},
    {"kind": "stairs", "steps": 2, "step_h": 1, "tread": 4, "dir": "up"},
    {"kind": "run", "len": 6},
    {"kind": "perch", "platform_width": 8, "climb_rise": 4, "variant": "shrine_rope_ladder"},
    {"kind": "hollow", "width": 6, "depth": 2},
    {"kind": "stairs", "steps": 1, "step_h": 2, "tread": 4, "dir": "down"},
    {"kind": "run", "len": 6},
    {"kind": "hop_chain", "count": 3, "jump_rise": 1, "gap": 3, "platform_width": 4, "dir": "up"},
    {"kind": "perch", "platform_width": 6, "climb_rise": 4, "variant": "bellrope_climb"},
    {"kind": "run", "len": 8},
]


def persisted_design(
    *,
    profile: PlatformerProfile,
    start_height_tiles: int,
    design_notes: str,
    chunks: list[dict[str, object]],
    brief: str,
) -> PlatformerChunkMapDesign:
    """Build the persisted sentence.

    The model pins `schema_version` and `kind` as literal types, so they are written literally
    here and cross-checked against the component's own constants. If the component ever revs the
    contract this raises rather than silently writing a stale discriminator.
    """

    if (PLATFORMER_MAP_DESIGN_SCHEMA_VERSION, PLATFORMER_MAP_DESIGN_KIND) != (
        1,
        "platformer-chunk-map-v1",
    ):
        raise MapAdapterError(
            "the persisted platformer chunk-map contract has moved; update scripts/design_map.py"
        )
    return PlatformerChunkMapDesign(
        schema_version=1,
        kind="platformer-chunk-map-v1",
        profile_id=profile.profile_id,
        columns=profile.geometry.columns,
        start_height_tiles=start_height_tiles,
        design_notes=design_notes,
        chunks=chunks,
        brief=brief,
    )


def example_design() -> PlatformerChunkMapDesign:
    """The canned sentence, in the same persisted form a live run would write."""

    return persisted_design(
        profile=BELLWEATHER_SIDE_VIEW,
        start_height_tiles=3,
        design_notes=(
            "A pilgrim road that climbs in three acts: a ladder-fed river shelf, a rope-fed "
            "root gallery over a hollow, a stepped hop chain to the ridge, and a final rope "
            "onto the crown approach."
        ),
        chunks=EXAMPLE_CHUNKS,
        brief="offline example",
    )


class MapAdapterError(ValueError):
    """Raised when a designed map cannot be expressed as an authored level plan."""


class MapSurgeryError(ValueError):
    """Raised when a shipped map document does not have the exact shape the surgery expects."""


# ---------------------------------------------------------------------------------------------
# Loading and expansion
# ---------------------------------------------------------------------------------------------


def load_design(path: Path) -> PlatformerChunkMapDesign:
    return load_platformer_chunk_map_design_bytes(path.read_bytes())


def expand(
    design: PlatformerChunkMapDesign, profile: PlatformerProfile
) -> tuple[DesignedMap, list[str]]:
    """Re-expand the persisted sentence and return the map plus every problem, translated."""

    if design.profile_id != profile.profile_id:
        raise MapAdapterError(
            f"design was composed for profile {design.profile_id!r}, not {profile.profile_id!r}"
        )
    # The persisted `columns` is the width the sentence was composed against, not a width the
    # design gets to choose. A design that disagrees with its own profile's geometry would expand
    # onto a grid no map in this game has, so it is refused here rather than compiled.
    if design.columns != profile.geometry.columns:
        raise MapAdapterError(
            f"design declares {design.columns} columns, but profile {profile.profile_id!r} is "
            f"{profile.geometry.columns} columns wide; a design may not resize the grid"
        )
    value: dict[str, object] = {
        "start_height": design.start_height_tiles,
        "chunks": design.chunks,
        "design_notes": design.design_notes,
    }
    designed, chunk_errors, spans = expand_chunks(value, profile, design.columns)
    return designed, chunk_errors + translate(check(designed, profile), spans)


def describe(designed: DesignedMap, profile: PlatformerProfile) -> str:
    depths = [designed.ground_depth(column, profile) for column in range(designed.columns)]
    surfaces = designed.surfaces(profile)
    platforms = [surface for surface in surfaces if not surface.grounded]
    return (
        f"{designed.profile_id}: {designed.rows} rows x {designed.columns} columns\n"
        f"  ground {min(depths)}-{max(depths)} tiles\n"
        f"  {len(platforms)} floating platform(s) at heights "
        f"{sorted({surface.height_tiles for surface in platforms})}\n"
        f"  {len(designed.climbables)} climbable(s) at columns "
        f"{[climb.foot_column for climb in designed.climbables]}"
    )


# ---------------------------------------------------------------------------------------------
# The adapter: a designed map becomes an authored level plan, or fails loudly
# ---------------------------------------------------------------------------------------------


def to_level_plan(designed: DesignedMap, profile: PlatformerProfile, map_id: str) -> LevelPlan:
    """Translate an accepted design into `author_terrain`'s declaration.

    The two formats do not describe the same set of maps. `LevelPlan` is a heightfield plus
    single-row decks plus fixed-rise terrain-footed climbables; a `DesignedMap` can express
    holes, thick platforms, other rises, and platform-footed climbables. Everything the plan
    cannot say is collected and reported at once rather than silently flattened.
    """

    empty = profile.empty_role.symbol
    problems: list[str] = []
    depths = [designed.ground_depth(column, profile) for column in range(designed.columns)]

    for column, depth in enumerate(depths):
        if depth == 0:
            problems.append(
                f"column {column} has no ground tile; a hole is not expressible as an authored "
                "level plan, whose ground_heights must be at least 1 everywhere"
            )
            break

    ledges: list[Ledge] = []
    for surface in designed.surfaces(profile):
        if surface.grounded:
            continue
        if surface.height_tiles >= 2:
            thick = [
                column
                for column in range(surface.start_column, surface.end_column)
                if designed.symbol_at(column, surface.height_tiles - 1) != empty
            ]
            if thick:
                problems.append(
                    f"platform {surface.surface_id} is more than one row thick at column(s) "
                    f"{thick[:4]}; an authored ledge is exactly one occupied row"
                )
                continue
        ledges.append(
            Ledge(
                ledge_id=surface.surface_id,
                row=designed.rows - surface.height_tiles,
                start_column=surface.start_column,
                end_column=surface.end_column,
            )
        )

    climbs: list[Climb] = []
    for climb in designed.climbables:
        if not 0 <= climb.foot_column < designed.columns:
            problems.append(
                f"climbable {climb.climbable_id} foot column {climb.foot_column} is outside "
                f"the {designed.columns}-column grid"
            )
            continue
        if climb.rise_tiles != CLIMBABLE_RISE_TILES:
            problems.append(
                f"climbable {climb.climbable_id} rises {climb.rise_tiles} tiles; every authored "
                f"placement spans exactly {CLIMBABLE_RISE_TILES} until the tiled-band work lands"
            )
            continue
        foot_height = (
            climb.foot_height_tiles
            if climb.foot_height_tiles is not None
            else depths[climb.foot_column]
        )
        if foot_height != depths[climb.foot_column]:
            problems.append(
                f"climbable {climb.climbable_id} is footed at {foot_height} tiles on a platform, "
                f"but column {climb.foot_column} has {depths[climb.foot_column]} ground tiles; "
                'an authored placement is always bottom_surface = "terrain"'
            )
            continue
        climbs.append(
            Climb(
                climbable_id=climb.climbable_id,
                variant_id=climb.variant_id,
                column=climb.foot_column,
            )
        )

    if problems:
        raise MapAdapterError(_listed("this design cannot be expressed as a level plan", problems))

    plan = LevelPlan(
        map_id=map_id,
        columns=designed.columns,
        rows=designed.rows,
        ground_heights=depths,
        ledges=ledges,
        climbs=climbs,
        # The walk surface is where the player starts, which is the left edge's floor. It is
        # also what `vertical_anchor = "walk_surface"` layers are pinned to.
        walk_surface_row=designed.rows - depths[0],
    )
    _assert_same_occupancy(plan, designed, profile)
    return plan


def _assert_same_occupancy(
    plan: LevelPlan, designed: DesignedMap, profile: PlatformerProfile
) -> None:
    """The plan must reproduce the designed grid cell for cell, or the translation lost a tile."""

    empty = profile.empty_role.symbol
    expected = [
        "".join("0" if symbol == empty else "1" for symbol in designed.grid[height - 1])
        for height in range(designed.rows, 0, -1)
    ]
    produced = plan.occupancy()
    for index, (want, got) in enumerate(zip(expected, produced, strict=True)):
        if want != got:
            raise MapAdapterError(
                "the authored level plan does not reproduce the designed grid at occupancy row "
                f"{index}:\n  designed: {want}\n  authored: {got}"
            )


def _listed(headline: str, problems: Sequence[str]) -> str:
    body = "\n".join(f"  - {problem}" for problem in problems)
    return f"{headline}:\n{body}"


# ---------------------------------------------------------------------------------------------
# Text surgery on the shipped map document
# ---------------------------------------------------------------------------------------------

#: The exact `occupancy = [` spelling and row formatting `emit_toml` already ships.
_OCCUPANCY_BLOCK = re.compile(r'^occupancy = \[\n(?:  "[01]+",\n)+\]$', re.MULTILINE)
_WALK_SURFACE_ROW = re.compile(r"^walk_surface_row = \d+$", re.MULTILINE)
_PLACEMENT_BLOCK = re.compile(
    r"^\[\[climbable\.placements\]\]\n(?:[a-z_]+ = [^\n]*\n)+", re.MULTILINE
)
_MAP_REVISION = re.compile(r"^revision = (\d+)$", re.MULTILINE)


def shipped_occupancy_shape(text: str) -> tuple[int, int]:
    """The `(rows, columns)` of the occupancy matrix the surgery would overwrite.

    Read from the block that is actually replaced, not from the parsed document, so the shape
    asserted against is the shape being edited.
    """

    block = _OCCUPANCY_BLOCK.search(text)
    if block is None:
        raise MapSurgeryError("the map document has no recognizable `occupancy = [` block")
    rows = re.findall(r'"([01]+)"', block.group(0))
    widths = {len(row) for row in rows}
    if len(widths) != 1:
        raise MapSurgeryError(
            f"the shipped occupancy matrix is ragged: its rows are {sorted(widths)} columns wide"
        )
    return len(rows), widths.pop()


def assert_fits_shipped_map(plan: LevelPlan, text: str, map_id: str) -> None:
    """Refuse a plan whose grid is not the exact shape of the map being rewritten.

    Every normalized coordinate already in the document -- portal endpoints, parallax placement --
    is expressed against the shipped grid. Resizing the matrix under them silently moves every one
    of those to a different world position, and the digest re-lock would then pin the result.
    """

    shipped = shipped_occupancy_shape(text)
    if (plan.rows, plan.columns) != shipped:
        raise MapSurgeryError(
            f"the compiled plan is {plan.rows} rows x {plan.columns} columns, but the shipped map "
            f"{map_id!r} is {shipped[0]} rows x {shipped[1]} columns; a design cannot change the "
            "dimensions of a map it was not composed for"
        )


def _emitted_sections(plan: LevelPlan) -> tuple[str, str, str]:
    """Split `author_terrain.emit_toml` output into the three blocks the map document owns."""

    emitted = emit_toml(plan)
    head, separator, placements = emitted.partition("\n\n")
    if not separator or not placements.strip():
        raise MapSurgeryError("emit_toml produced no climbable placements to write")
    occupancy_block, newline, walk_line = head.rpartition("\n")
    if not newline or not walk_line.startswith("walk_surface_row = "):
        raise MapSurgeryError("emit_toml did not emit a walk_surface_row line")
    return occupancy_block, walk_line, placements


def rewrite_map_document(text: str, plan: LevelPlan) -> str:
    """Replace only the compiled blocks, and bump the map revision. Everything else survives."""

    occupancy_block, walk_line, placements = _emitted_sections(plan)

    text, replaced = _OCCUPANCY_BLOCK.subn(lambda _: occupancy_block, text, count=1)
    if replaced != 1:
        raise MapSurgeryError("the map document has no recognizable `occupancy = [` block")
    text, replaced = _WALK_SURFACE_ROW.subn(lambda _: walk_line, text, count=1)
    if replaced != 1:
        raise MapSurgeryError("the map document has no recognizable `walk_surface_row` line")

    blocks = list(_PLACEMENT_BLOCK.finditer(text))
    if not blocks:
        raise MapSurgeryError("the map document has no `[[climbable.placements]]` blocks")
    for current, following in itertools.pairwise(blocks):
        if text[current.end() : following.start()] != "\n":
            raise MapSurgeryError(
                "the `[[climbable.placements]]` blocks are not one contiguous run; refusing to "
                "rewrite a region that holds something else"
            )
    text = text[: blocks[0].start()] + placements + text[blocks[-1].end() :]

    revisions = list(_MAP_REVISION.finditer(text))
    if len(revisions) != 1:
        raise MapSurgeryError(
            f"expected exactly one `revision = N` line in the map document, found {len(revisions)}"
        )
    revision = revisions[0]
    bumped = int(revision.group(1)) + 1
    return text[: revision.start()] + f"revision = {bumped}" + text[revision.end() :]


def _maps_entry_digest(map_id: str) -> re.Pattern[str]:
    """Anchored on the map's own `map_id`, never on its position in the `[[maps]]` array."""

    return re.compile(
        rf'(\[\[maps\]\]\nmap_id = "{re.escape(map_id)}"\nsource = "[^"\n]+"\n'
        rf'source_sha256 = ")[a-f0-9]{{64}}(")'
    )


def _selector_digest(package_ref: str) -> re.Pattern[str]:
    return re.compile(
        rf'(package_ref = "{re.escape(package_ref)}"\npackage_sha256 = ")[a-f0-9]{{64}}(")'
    )


def _substitute(pattern: re.Pattern[str], text: str, digest: str, label: str) -> str:
    updated, replacements = pattern.subn(
        lambda match: f"{match.group(1)}{digest}{match.group(2)}", text, count=1
    )
    if replacements != 1:
        raise MapSurgeryError(f"could not re-lock {label}: no anchored digest matched")
    return updated


# ---------------------------------------------------------------------------------------------
# Library package addressing
# ---------------------------------------------------------------------------------------------


class PackageTarget(NamedTuple):
    """Where one map, its game contract, and the selector that binds them actually live.

    A `NamedTuple` rather than a dataclass so this module stays importable under every loader:
    `@dataclass` resolves its own annotations through `sys.modules[cls.__module__]`, which is
    `None` when a test execs the file with `importlib` without registering it first.
    """

    library_root: Path
    game_id: str
    package_ref: str
    package_dir: Path
    selector_path: Path
    game_path: Path
    map_path: Path


def locate_package(library_root: Path, map_id: str) -> PackageTarget:
    selector_path = library_root / "main.toml"
    if not selector_path.is_file():
        raise MapSurgeryError(f"no game package selector at {selector_path}")
    selector = tomllib.loads(selector_path.read_text(encoding="utf-8"))
    game_id = str(selector["game_id"])
    package_ref = str(selector["package_ref"])
    package_dir = library_root / game_id
    if PurePosixPath(package_ref).parent.name != game_id:
        raise MapSurgeryError(
            f"selector package_ref {package_ref!r} does not name the {game_id!r} package"
        )
    game_path = package_dir / "game.toml"
    game = tomllib.loads(game_path.read_text(encoding="utf-8"))
    sources = {str(entry["map_id"]): str(entry["source"]) for entry in game.get("maps", [])}
    if map_id not in sources:
        raise MapSurgeryError(
            f"game {game_id} declares no map {map_id!r}; it has {sorted(sources)}"
        )
    return PackageTarget(
        library_root=library_root,
        game_id=game_id,
        package_ref=package_ref,
        package_dir=package_dir,
        selector_path=selector_path,
        game_path=game_path,
        map_path=package_dir.joinpath(*PurePosixPath(sources[map_id]).parts),
    )


def _changed_on_disk(path: Path, before: str) -> bool:
    """Whether a write that raised left `path` holding anything other than what it was read with.

    `Path.write_text` truncates before it writes, so a failure at the open leaves the document
    untouched while a failure partway through leaves it short. Only the second one needs a restore,
    and reading the bytes back is the only thing that tells the two apart. A document that cannot
    be read is treated as changed, because that is the direction that reports rather than hides.
    """

    try:
        return path.read_bytes() != before.encode("utf-8")
    except OSError:
        return True


def _restore(written: Sequence[tuple[Path, str]]) -> None:
    """Put back the documents this run actually wrote, and report which state the package is in.

    Only written paths are passed in, and that is the whole point: a document the aborted run
    never reached still holds the bytes it was read with, so rewriting it can only manufacture a
    failure. Restoring all three unconditionally meant an untouched-but-unwritable file was
    reported as a broken digest chain over a package nothing had touched.

    Every written path is still attempted even when one fails, so a single unwritable file cannot
    strand the others. This never raises: the caller either prints the original cause or re-raises
    it, and a rollback report may not displace the reason the rewrite stopped.

    `stage_gen.reliability.atomic.atomic_write_bundle` is the repository's rollback-safe multi-file
    commit, but it requires every file to share one directory and installs at mode 0o600; the map,
    its `game.toml`, and `main.toml` live in three directories and are committed source, so the
    restore is explicit here instead.
    """

    if not written:
        print("nothing had been written; every document still holds its pre-apply bytes")
        return
    failures: list[str] = []
    for path, before in written:
        try:
            path.write_text(before, encoding="utf-8")
        except OSError as error:
            failures.append(f"{path}: {error}")
    if failures:
        print(
            _listed(
                "documents this run had already written could not be put back; this package's "
                "digest chain is broken and needs a manual checkout",
                failures,
            )
        )
        return
    print("every document was restored to its pre-apply bytes; nothing was left half-written")


def _diff(label: str, before: str, after: str) -> str:
    lines = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{label}",
        tofile=f"b/{label}",
    )
    return "".join(lines)


# ---------------------------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------------------------

_BACKGROUND = (250, 248, 244)
_INK = (20, 20, 20)
_GROUND = (110, 86, 60)
_PLATFORM = (176, 148, 104)
_LADDER = (198, 60, 52)
_ROPE = (150, 80, 190)


def _refuse_docs_destination(path: Path) -> None:
    if "docs" in path.resolve().parts:
        raise MapSurgeryError(
            f"refusing to write {path}: anything under docs/ is published media and needs a "
            "provenance sidecar and a rights basis. Write the diagnostic elsewhere."
        )


def render(designed: DesignedMap, profile: PlatformerProfile, out: Path, title: str) -> None:
    """A flat diagnostic of the compiled grid: ground, platforms, and climbable bars."""

    cell, pad, label = 8, 12, 34
    width = designed.columns * cell + pad * 2
    height = designed.rows * cell + label + pad * 2 + 16
    image = Image.new("RGB", (width, height), _BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.text((pad, pad), title, fill=_INK)

    legend = ((_GROUND, "ground"), (_PLATFORM, "platform"), (_LADDER, "ladder"), (_ROPE, "rope"))
    x = pad
    for color, name in legend:
        draw.rectangle([x, pad + 14, x + 9, pad + 23], fill=color)
        draw.text((x + 13, pad + 14), name, fill=_INK)
        x += 13 + 7 * len(name) + 14

    top = pad + label
    ground_symbol = profile.ground_role.symbol
    empty_symbol = profile.empty_role.symbol
    for tile_height in range(1, designed.rows + 1):
        y = top + (designed.rows - tile_height) * cell
        for column in range(designed.columns):
            symbol = designed.symbol_at(column, tile_height)
            if symbol == empty_symbol:
                continue
            color = _GROUND if symbol == ground_symbol else _PLATFORM
            x0 = pad + column * cell
            draw.rectangle([x0, y, x0 + cell - 1, y + cell - 1], fill=color)

    for climb in designed.climbables:
        if not 0 <= climb.foot_column < designed.columns:
            continue
        foot = climb.foot_height_tiles or designed.ground_depth(climb.foot_column, profile)
        # The design names a variant, not a role; the map contract is what actually sorts a
        # variant into [[climbable.ladders]] or [[climbable.ropes]]. This is a naming heuristic
        # for the diagnostic only, and "rope ladder" is a ladder.
        ropelike = "ladder" not in climb.variant_id and "rope" in climb.variant_id
        color = _ROPE if ropelike else _LADDER
        x0 = pad + climb.foot_column * cell + 2
        x1 = pad + climb.foot_column * cell + cell - 3
        y0 = top + (designed.rows - foot - climb.rise_tiles) * cell
        y1 = top + (designed.rows - foot) * cell - 1
        draw.rectangle([x0, y0, x1, y1], fill=color)

    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)


# ---------------------------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------------------------


def _resolve_design(design_path: Path | None, use_example: bool) -> PlatformerChunkMapDesign:
    if use_example:
        return example_design()
    if design_path is None:
        raise MapAdapterError("pass either --design <path> or --example")
    return load_design(design_path)


def run_check(args: argparse.Namespace) -> int:
    profile = PROFILES[str(args.profile)]
    design = _resolve_design(args.design, bool(args.example))
    designed, problems = expand(design, profile)
    print(describe(designed, profile))
    if problems:
        print("\nREJECTED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\ndesign satisfies every rule the bellweather-side-view profile declares")
    return 0


def run_render(args: argparse.Namespace) -> int:
    profile = PROFILES[str(args.profile)]
    design = _resolve_design(args.design, bool(args.example))
    out = Path(args.out)
    _refuse_docs_destination(out)
    designed, problems = expand(design, profile)
    render(
        designed,
        profile,
        out,
        f"{design.profile_id} - {designed.columns}x{designed.rows} - "
        f"{'PASS' if not problems else f'{len(problems)} problem(s)'}",
    )
    print(describe(designed, profile))
    for problem in problems:
        print(f"  - {problem}")
    print(f"\nrendered: {out}")
    return 0


def run_apply(args: argparse.Namespace) -> int:
    profile = PROFILES[str(args.profile)]
    design = _resolve_design(args.design, bool(args.example))
    map_id = str(args.map_id)
    library_root = Path(args.library_root).resolve()
    dry_run = bool(args.dry_run)

    designed, problems = expand(design, profile)
    if problems:
        print(_listed("the design does not satisfy its own profile", problems))
        return 1

    plan = to_level_plan(designed, profile, map_id)
    consumer_problems = validate(plan)
    if consumer_problems:
        print(_listed("author_terrain rejected the compiled level plan", consumer_problems))
        return 1

    target = locate_package(library_root, map_id)
    if library_root.is_relative_to(REPOSITORY_LIBRARY_ROOT) and not dry_run:
        print(
            "WARNING: writing to the real repository library at "
            f"{REPOSITORY_LIBRARY_ROOT}. The shipped map TOMLs are digest-pinned; review the "
            "diff and the regenerated media before committing.\n"
        )

    map_before = target.map_path.read_text(encoding="utf-8")
    assert_fits_shipped_map(plan, map_before, map_id)
    map_after = rewrite_map_document(map_before, plan)
    map_bytes = map_after.encode("utf-8")

    game_before = target.game_path.read_text(encoding="utf-8")
    game_after = _substitute(
        _maps_entry_digest(map_id),
        game_before,
        sha256_bytes(map_bytes),
        f"the [[maps]] entry for {map_id}",
    )
    game_bytes = game_after.encode("utf-8")

    selector_before = target.selector_path.read_text(encoding="utf-8")
    selector_after = _substitute(
        _selector_digest(target.package_ref),
        selector_before,
        sha256_bytes(game_bytes),
        "the selector package_sha256",
    )

    writes = (
        (target.map_path, map_before, map_after),
        (target.game_path, game_before, game_after),
        (target.selector_path, selector_before, selector_after),
    )
    if dry_run:
        for path, before, after in writes:
            print(_diff(str(path.relative_to(library_root)), before, after), end="")
        print("\n--dry-run: nothing was written")
        return 0

    # The three documents are one digest chain, so a half-written set is a broken package. Every
    # original was read above; anything that goes wrong from the first write onward puts back the
    # documents this run actually wrote -- and only those -- before it returns. The cause is always
    # printed first, or re-raised unchanged; the rollback only ever adds what state disk is in.
    written: list[tuple[Path, str]] = []
    try:
        for path, before, after in writes:
            try:
                path.write_text(after, encoding="utf-8")
            except OSError:
                if _changed_on_disk(path, before):
                    written.append((path, before))
                raise
            written.append((path, before))
        resolved = resolve_game_package(target.package_dir)
        if resolved.package_sha256 != sha256_bytes(game_bytes):
            raise MapSurgeryError("package digest chain is inconsistent after the rewrite")
    except GamePackageValidationError as error:
        print(f"package no longer resolves after the rewrite: {error.code}: {error}")
        _restore(written)
        return 1
    except OSError as error:
        print(f"writing the rewritten documents failed: {error}")
        _restore(written)
        return 1
    except BaseException:
        # An interrupt is as capable of breaking the chain as an exception is, and it is never
        # traded for a MapSurgeryError: the documents go back, then the original propagates.
        _restore(written)
        raise
    print(
        json.dumps(
            {
                **resolved.identity(),
                "map_id": map_id,
                "climbables": len(plan.climbs),
                "ledges": len(plan.ledges),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


async def _design_samples(
    profile: PlatformerProfile, brief: DesignBrief, samples: int, seed: int, attempts_dir: Path
) -> list[tuple[int, Path, list[str]]]:
    from stage_gen.config import load_config
    from stage_gen.orchestration.runtime import create_structured_service

    config = load_config()
    service = create_structured_service(
        api_key=config.open_router_api_key or "",
        model=config.text_model,
        base_url=config.open_router_base_url or "https://openrouter.ai/api/v1",
    )
    try:
        runs = await asyncio.gather(
            *(
                design_chunks(
                    service,
                    profile,
                    brief,
                    seed=seed + index,
                    artifact_dir=_sample_dir(attempts_dir, index),
                )
                for index in range(1, samples + 1)
            )
        )
    finally:
        await service.aclose()
    results: list[tuple[int, Path, list[str]]] = []
    for index, attempts in enumerate(runs, 1):
        last = attempts[-1]
        artifact = _sample_dir(attempts_dir, index) / f"attempt-{last.attempt:02d}.json"
        results.append((index, artifact, last.problems))
    return results


def _sample_dir(attempts_dir: Path, index: int) -> Path:
    directory = attempts_dir / f"s{index}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def run_design(args: argparse.Namespace) -> int:
    live_env = os.environ.get(LIVE_ENVIRONMENT_FLAG) == "1"
    if not (bool(args.live) and live_env):
        print(
            "design is the only live subcommand and needs BOTH opt-ins: pass --live and set "
            f"{LIVE_ENVIRONMENT_FLAG}=1. No provider call was made.\n"
            "  check, render, and apply are fully offline."
        )
        return 1

    profile = PROFILES[str(args.profile)]
    out = Path(args.out)
    _refuse_docs_destination(out)
    brief = DesignBrief(intent=str(args.brief), shape=str(args.shape or ""))
    attempts_dir = out.parent / f"{out.stem}.attempts"
    results = asyncio.run(
        _design_samples(profile, brief, int(args.samples), int(args.seed), attempts_dir)
    )

    accepted = next((entry for entry in results if not entry[2]), None)
    for index, artifact, problems in results:
        print(f"sample {index}: {'PASS' if not problems else 'FAIL'} ({artifact})")
        for problem in problems[:4]:
            print(f"  - {problem}")
    if accepted is None:
        print("\nno sample satisfied the profile; nothing was written")
        return 1

    payload = json.loads(accepted[1].read_text(encoding="utf-8"))
    design = persisted_design(
        profile=profile,
        start_height_tiles=int(payload["start_height"]),
        design_notes=str(payload.get("design_notes", "")),
        chunks=[dict(chunk) for chunk in payload["chunks"]],
        brief=brief.intent,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(canonical_platformer_chunk_map_design_json(design))
    print(f"\nwrote: {out}")
    return 0


# ---------------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------------


def _add_source_arguments(parser: argparse.ArgumentParser) -> None:
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--design", type=Path, help="a persisted chunk-sentence design JSON")
    source.add_argument(
        "--example", action="store_true", help="use the canned in-script example design"
    )
    parser.add_argument(
        "--profile", choices=sorted(PROFILES), default=BELLWEATHER_SIDE_VIEW.profile_id
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="design_map.py",
        description=(
            "Compose a Bellweather map as a chunk sentence and compile it into the shipped "
            "map contract."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    checker = subparsers.add_parser(
        "check", help="offline: expand a design and validate it against the profile"
    )
    _add_source_arguments(checker)
    checker.set_defaults(handler=run_check)

    renderer = subparsers.add_parser(
        "render", help="offline: write a diagnostic PNG of the expanded grid"
    )
    _add_source_arguments(renderer)
    renderer.add_argument("--out", type=Path, required=True, help="PNG destination (never docs/)")
    renderer.set_defaults(handler=run_render)

    designer = subparsers.add_parser(
        "design", help="LIVE: compose a new design with the structured-generation service"
    )
    designer.add_argument("--brief", required=True, help="what the level should feel like")
    designer.add_argument("--shape", default="", help="optional silhouette, e.g. 'two peaks'")
    designer.add_argument("--out", type=Path, required=True, help="design JSON destination")
    designer.add_argument("--samples", type=int, default=1)
    designer.add_argument("--seed", type=int, default=1)
    designer.add_argument(
        "--live",
        action="store_true",
        help=f"required, together with {LIVE_ENVIRONMENT_FLAG}=1, to reach a provider",
    )
    designer.add_argument(
        "--profile", choices=sorted(PROFILES), default=BELLWEATHER_SIDE_VIEW.profile_id
    )
    designer.set_defaults(handler=run_design)

    applier = subparsers.add_parser(
        "apply", help="offline: compile a design into a shipped map and re-lock the digest chain"
    )
    _add_source_arguments(applier)
    applier.add_argument("--map-id", required=True, help="the map to rewrite, e.g. crowncrag-road")
    applier.add_argument(
        "--library-root",
        type=Path,
        required=True,
        help=(
            "directory holding main.toml and the game packages. Required and never defaulted: "
            f"naming the shipped library at {REPOSITORY_LIBRARY_ROOT} rewrites digest-pinned "
            "source and is a deliberate, separately authorized edit"
        ),
    )
    applier.add_argument("--dry-run", action="store_true", help="print the diff without writing")
    applier.set_defaults(handler=run_apply)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler = args.handler
    try:
        result = handler(args)
    except (MapAdapterError, MapSurgeryError, PlatformerMapDesignLoadError) as error:
        print(str(error))
        return 1
    return int(result)


if __name__ == "__main__":
    raise SystemExit(main())
