"""The designed map, every check that can be made against a profile, and its persisted form.

Nothing here knows a game. Every threshold comes from the :class:`PlatformerProfile` it is
handed, which is what lets one designer serve a fixed-rise ground-founded platformer and a
chained-shaft metroidvania without a branch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import Field, ValidationError

from stage_gen.components._game_input import canonical_contract_json
from stage_gen.components.platformer_map_design.capabilities import PlatformerProfile
from stage_gen.contracts.artifacts import PersistedContractModel

PLATFORMER_MAP_DESIGN_SCHEMA_VERSION = 1
PLATFORMER_MAP_DESIGN_KIND = "platformer-chunk-map-v1"


@dataclass(frozen=True)
class Climbable:
    climbable_id: str
    variant_id: str
    foot_column: int
    #: Tiles this climbable spans. The profile decides which rises are legal.
    rise_tiles: int
    #: Height of the surface this climbable stands on. Two climbables can share a column at
    #: different heights, and no amount of inference can tell them apart, so it is declared.
    foot_height_tiles: int | None = None


@dataclass(frozen=True)
class Surface:
    """A contiguous walkable run at one height: either the floor or a platform."""

    surface_id: str
    start_column: int
    end_column: int
    height_tiles: int
    grounded: bool

    @property
    def width(self) -> int:
        return self.end_column - self.start_column


@dataclass
class DesignedMap:
    """A map as a grid of role symbols, bottom row first, plus its climbables."""

    profile_id: str
    columns: int
    rows: int
    #: ``rows`` strings of ``columns`` symbols, index 0 is the BOTTOM row.
    grid: list[str]
    climbables: list[Climbable] = field(default_factory=list)
    design_notes: str = ""
    #: One tag per column, or None when the format does not speak the biome channel.
    column_biomes: list[str] | None = None

    def symbol_at(self, column: int, height: int) -> str:
        """Symbol at a column and a height measured up from the floor (1 = lowest tile)."""

        return self.grid[height - 1][column]

    def ground_depth(self, column: int, profile: PlatformerProfile) -> int:
        """Unbroken floor tiles rising from the bottom. The only 'grounded' definition there is."""

        ground = profile.ground_role.symbol
        depth = 0
        for height in range(1, self.rows + 1):
            if self.symbol_at(column, height) != ground:
                break
            depth += 1
        return depth

    def surfaces(self, profile: PlatformerProfile) -> list[Surface]:
        """Every walkable run. Floors and platforms are the same thing to a traversal check."""

        ground_depths = [self.ground_depth(column, profile) for column in range(self.columns)]
        walkable = {role.symbol for role in profile.roles if role.walkable or role.grounded}
        empty = profile.empty_role.symbol
        found: list[Surface] = []
        for height in range(1, self.rows + 1):
            column = 0
            while column < self.columns:
                symbol = self.symbol_at(column, height)
                above = self.symbol_at(column, height + 1) if height < self.rows else empty
                is_top = symbol in walkable and above == empty
                if not is_top:
                    column += 1
                    continue
                start = column
                grounded = ground_depths[column] == height
                while column < self.columns:
                    here = self.symbol_at(column, height)
                    over = self.symbol_at(column, height + 1) if height < self.rows else empty
                    if here not in walkable or over != empty:
                        break
                    if (ground_depths[column] == height) != grounded:
                        break
                    column += 1
                found.append(Surface(f"s-h{height}-c{start}", start, column, height, grounded))
        return found


def _gap(a: Surface, b: Surface) -> int:
    """Columns of clear air between two surfaces, and zero wherever their spans overlap."""

    left, right = (a, b) if a.start_column <= b.start_column else (b, a)
    return max(0, right.start_column - (left.start_column + left.width))


def check(designed: DesignedMap, profile: PlatformerProfile) -> list[str]:
    """Every profile-driven rule. Returns human-readable problems, empty when the map is sound."""

    problems: list[str] = []
    geometry, movement = profile.geometry, profile.movement
    known = {role.symbol for role in profile.roles}
    ground = profile.ground_role.symbol
    empty = profile.empty_role.symbol

    # --- shape -------------------------------------------------------------------------------
    if len(designed.grid) != designed.rows:
        problems.append(f"grid has {len(designed.grid)} rows, expected {designed.rows}")
        return problems
    for index, row in enumerate(designed.grid):
        if len(row) != designed.columns:
            problems.append(f"row {index} has {len(row)} cells, expected {designed.columns}")
        unknown = sorted(set(row) - known)
        if unknown:
            problems.append(f"row {index} uses symbols outside the alphabet: {unknown}")
    if problems:
        return problems

    # --- floor -------------------------------------------------------------------------------
    low, high = geometry.ground_depth_tiles
    depths = [designed.ground_depth(column, profile) for column in range(designed.columns)]
    for column, depth in enumerate(depths):
        if not low <= depth <= high:
            problems.append(
                f"column {column} floor is {depth} tiles, outside the profile's {low}..{high}"
            )
            break
    for column in range(designed.columns - 1):
        step = abs(depths[column + 1] - depths[column])
        if step > movement.max_step_up_tiles:
            problems.append(
                f"columns {column}-{column + 1} step {step} tiles, above the profile's "
                f"unassisted maximum of {movement.max_step_up_tiles}"
            )
            break

    # --- role honesty: a declared role must match the geometry --------------------------------
    # The outer loop stops on this scan's OWN verdict. Inspecting ``problems[-1]`` instead would
    # read the floor-depth and step checks above, whose messages also begin "column", and this
    # scan would then never run on any map that already had a floor problem.
    mislabelled = False
    for height in range(1, designed.rows + 1):
        for column in range(designed.columns):
            symbol = designed.symbol_at(column, height)
            if symbol == empty:
                continue
            is_grounded = height <= depths[column]
            if symbol == ground and not is_grounded:
                problems.append(
                    f"column {column} height {height} is labelled ground but does not reach "
                    "the floor"
                )
                mislabelled = True
                break
            if symbol != ground and is_grounded:
                problems.append(
                    f"column {column} height {height} is labelled {symbol!r} but is part of "
                    "the floor stack"
                )
                mislabelled = True
                break
        if mislabelled:
            break

    # --- biomes: annotation only; membership and paintable span, never physics -----------------
    column_biomes = designed.column_biomes
    if column_biomes is not None:
        undeclared = sorted(set(column_biomes) - set(profile.biomes))
        if undeclared:
            problems.append(f"undeclared biome tag(s): {undeclared}")
        span_start = 0
        for column in range(1, designed.columns + 1):
            if column < designed.columns and (column_biomes[column] == column_biomes[span_start]):
                continue
            width = column - span_start
            if width < profile.biome_min_span_tiles:
                problems.append(
                    f"biome region {column_biomes[span_start]!r} at column "
                    f"{span_start} is only {width} wide; the consumer needs at least "
                    f"{profile.biome_min_span_tiles} to paint a region"
                )
                break
            span_start = column

    surfaces = designed.surfaces(profile)

    # --- framing -------------------------------------------------------------------------------
    for surface in surfaces:
        if surface.height_tiles > geometry.max_walkable_height_tiles:
            problems.append(
                f"surface {surface.surface_id} sits at {surface.height_tiles} tiles, above the "
                f"profile's walkable ceiling of {geometry.max_walkable_height_tiles}"
            )
            break

    # --- platform thickness --------------------------------------------------------------------
    if geometry.platforms_single_thickness:
        for surface in surfaces:
            if surface.grounded or surface.height_tiles < 2:
                continue
            below = [
                designed.symbol_at(column, surface.height_tiles - 1)
                for column in range(surface.start_column, surface.end_column)
            ]
            if any(symbol != empty for symbol in below):
                problems.append(
                    f"platform {surface.surface_id} is more than one tile thick; the profile "
                    "says only its top surface would carry collision"
                )
                break

    # --- climbables ----------------------------------------------------------------------------
    low_count, high_count = profile.climbable_count
    if not low_count <= len(designed.climbables) <= high_count:
        problems.append(
            f"{len(designed.climbables)} climbables, outside the profile's "
            f"{low_count}..{high_count}"
        )
    # Two climbables collide only when they occupy the same column at the SAME height. Keying
    # on column alone is a ground-footed game's rule: where the profile allows platform footing,
    # stacking climbables in one column is how a shaft chains upward, not a mistake.
    seen: set[tuple[int, int]] = set()
    for climb in designed.climbables:
        if climb.variant_id not in profile.climbable_variants:
            problems.append(f"climbable {climb.climbable_id} names an undeclared variant")
            continue
        if climb.rise_tiles not in movement.climbable_rise_tiles:
            problems.append(
                f"climbable {climb.climbable_id} rises {climb.rise_tiles}, and the profile "
                f"permits {list(movement.climbable_rise_tiles)}"
            )
            continue
        if not 0 <= climb.foot_column < designed.columns:
            problems.append(f"climbable {climb.climbable_id} is outside the grid")
            continue

        foot = _foot_surface(designed, profile, climb)
        if foot is not None:
            key = (climb.foot_column, foot.height_tiles)
            if key in seen:
                problems.append(
                    f"two climbables stand at column {climb.foot_column} height {foot.height_tiles}"
                )
            seen.add(key)
        if foot is None:
            problems.append(
                f"climbable {climb.climbable_id} has no {movement.climbable_footing} surface "
                f"to stand on at column {climb.foot_column}"
            )
            continue
        if movement.climbable_needs_flat_footing:
            neighbour = climb.foot_column + 1
            if neighbour >= designed.columns:
                problems.append(
                    f"climbable {climb.climbable_id} is on the last column and the profile "
                    "needs a right-hand neighbour"
                )
            elif depths[neighbour] != depths[climb.foot_column]:
                problems.append(
                    f"climbable {climb.climbable_id} needs level footing: columns "
                    f"{climb.foot_column} and {neighbour} differ"
                )
        target = foot.height_tiles + climb.rise_tiles
        landing = [
            surface
            for surface in surfaces
            if surface.height_tiles == target
            and surface.start_column <= climb.foot_column < surface.end_column
        ]
        if not landing:
            problems.append(
                f"climbable {climb.climbable_id} rises to {target} tiles where there is no "
                "surface to step onto"
            )

    # --- traversal: nothing may be stranded -----------------------------------------------------
    stranded = unreachable(designed, profile, surfaces)
    if stranded:
        problems.append(f"{len(stranded)} surface(s) cannot be reached: {', '.join(stranded[:3])}")
    return problems


def _foot_surface(
    designed: DesignedMap, profile: PlatformerProfile, climb: Climbable
) -> Surface | None:
    """Which surface this climbable stands on.

    Taking the lowest candidate is a ground-footed game's answer: where a profile permits
    platform footing, several climbables share a column at different heights and every one of
    them would resolve to the floor. Prefer the lowest candidate whose rise actually lands on a
    surface, so a chained shaft resolves the way it was drawn, and fall back to the lowest so an
    unlandable climbable still reports a foot to complain about.
    """

    surfaces = designed.surfaces(profile)
    if climb.foot_height_tiles is not None:
        for surface in surfaces:
            if (
                surface.height_tiles == climb.foot_height_tiles
                and surface.start_column <= climb.foot_column < surface.end_column
                and (profile.movement.climbable_footing == "any" or surface.grounded)
            ):
                return surface
        return None
    candidates = sorted(
        (
            surface
            for surface in surfaces
            if surface.start_column <= climb.foot_column < surface.end_column
            and (profile.movement.climbable_footing == "any" or surface.grounded)
        ),
        key=lambda surface: surface.height_tiles,
    )
    if not candidates:
        return None
    for candidate in candidates:
        target = candidate.height_tiles + climb.rise_tiles
        if any(
            surface.height_tiles == target
            and surface.start_column <= climb.foot_column < surface.end_column
            for surface in surfaces
        ):
            return candidate
    return candidates[0]


def unreachable(
    designed: DesignedMap,
    profile: PlatformerProfile,
    surfaces: list[Surface] | None = None,
) -> list[str]:
    """Surfaces no player can arrive at, by climbable or by jump, from the floor."""

    surfaces = surfaces if surfaces is not None else designed.surfaces(profile)
    reached = {surface.surface_id for surface in surfaces if surface.grounded}
    by_id = {surface.surface_id: surface for surface in surfaces}
    climb_targets: dict[str, list[str]] = {}
    for climb in designed.climbables:
        foot = _foot_surface(designed, profile, climb)
        if foot is None:
            continue
        target_height = foot.height_tiles + climb.rise_tiles
        for surface in surfaces:
            if (
                surface.height_tiles == target_height
                and surface.start_column <= climb.foot_column < surface.end_column
            ):
                climb_targets.setdefault(foot.surface_id, []).append(surface.surface_id)

    changed = True
    while changed:
        changed = False
        for source_id in list(reached):
            for target_id in climb_targets.get(source_id, []):
                if target_id not in reached:
                    reached.add(target_id)
                    changed = True
            source = by_id[source_id]
            for target in surfaces:
                if target.surface_id in reached:
                    continue
                rise = target.height_tiles - source.height_tiles
                if profile.movement.reachable(rise, _gap(source, target)):
                    reached.add(target.surface_id)
                    changed = True
    return [surface.surface_id for surface in surfaces if surface.surface_id not in reached]


class PlatformerMapDesignLoadError(ValueError):
    """Raised when a persisted platformer chunk-map design cannot be accepted."""


class PlatformerChunkMapDesign(PersistedContractModel):
    """The chunk sentence as persisted: re-expandable, and never an expanded grid.

    Storing the sentence rather than the grid is the point of the grammar. A grid is a
    derivative that any profile change invalidates; the sentence is what the designer actually
    composed, and re-expanding it against a profile reproduces the grid exactly.
    """

    schema_version: Literal[1]
    kind: Literal["platformer-chunk-map-v1"]
    profile_id: str = Field(min_length=1, max_length=96)
    columns: int = Field(ge=1)
    start_height_tiles: int = Field(ge=1)
    design_notes: str
    chunks: list[dict[str, object]]
    brief: str = ""


def load_platformer_chunk_map_design_bytes(data: bytes) -> PlatformerChunkMapDesign:
    """Validate one persisted chunk-map design from its canonical JSON bytes."""

    try:
        return PlatformerChunkMapDesign.model_validate_json(data)
    except ValidationError as error:
        raise PlatformerMapDesignLoadError(
            f"invalid platformer chunk map design: {error}"
        ) from error


def canonical_platformer_chunk_map_design_json(design: PlatformerChunkMapDesign) -> bytes:
    return canonical_contract_json(design)


__all__ = [
    "PLATFORMER_MAP_DESIGN_KIND",
    "PLATFORMER_MAP_DESIGN_SCHEMA_VERSION",
    "Climbable",
    "DesignedMap",
    "PlatformerChunkMapDesign",
    "PlatformerMapDesignLoadError",
    "Surface",
    "canonical_platformer_chunk_map_design_json",
    "check",
    "load_platformer_chunk_map_design_bytes",
    "unreachable",
]
