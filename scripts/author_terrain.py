#!/usr/bin/env python3
"""Compile a declarative level plan into authored map terrain and climbable placements.

Terrain shape is authored, not generated: the image model paints only the 47-mask material
atlas, and `occupancy` is excluded from that atlas's cache identity. Reshaping a level therefore
costs no provider operation. What it does cost is correctness, because the occupancy matrix has
to satisfy several contracts at once that are easy to violate by hand:

  - adjacent walkable surfaces differ by at most `MAX_UNASSISTED_TERRAIN_RISE_TILES`
  - every climbable stands on bottom-supported terrain with an exposed deck exactly its rise
    above, and nothing directly on top of that deck
  - `walk_surface_row` exposes real terrain
  - floating platform interiors never intersect
  - every deck stays inside the runtime's vertical camera range

This turns a level into a small declaration and checks all of that before anything is written.

    uv run python scripts/author_terrain.py --plan crowncrag-road --check
    uv run python scripts/author_terrain.py --plan crowncrag-road --emit-toml
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stage_gen.components.game_map.prepared import (
    MAX_UNASSISTED_TERRAIN_RISE_TILES,
    bottom_contiguous_surface_row,
    normalized_terrain_column,
)

#: web/lib/runtime/prepared-scene.ts TILE_PX and VIEW_H; vertical.ts camera clamp.
TILE_PX = 64
VIEW_H = 720
VERTICAL_CAMERA_MIN_SCROLL_Y = -512
#: Every climbable spans exactly this many tiles until the tiled-band work lands (see TODO.md).
CLIMBABLE_RISE_TILES = 4
MAX_CLIMBABLE_PLACEMENTS = 8
#: Highest walkable surface that still holds the player inside the camera deadzone at zoom 1.
#: `verticalCameraScrollY` pins the feet at screen y 420 only while footY >= -92; above that the
#: level still loads and the player slides up the frame. The hard failure is at 19 tiles, which
#: `VERTICAL_CAMERA_MIN_SCROLL_Y` enforces for ledges only.
MAX_FRAMED_SURFACE_TILES = 12


@dataclass(frozen=True)
class Ledge:
    """A floating deck: one occupied row spanning a half-open column range."""

    ledge_id: str
    row: int
    start_column: int
    end_column: int


@dataclass(frozen=True)
class Climb:
    """A climbable rising from the ground at `column` to the ledge directly above it."""

    climbable_id: str
    variant_id: str
    column: int


@dataclass(frozen=True)
class LevelPlan:
    """One level's shape, as a declaration rather than a hand-drawn matrix."""

    map_id: str
    columns: int
    rows: int
    #: Ground thickness per column, from the bottom row upward. Length must equal `columns`.
    ground_heights: list[int]
    ledges: list[Ledge] = field(default_factory=list)
    climbs: list[Climb] = field(default_factory=list)
    walk_surface_row: int | None = None

    def occupancy(self) -> list[str]:
        grid = [["0"] * self.columns for _ in range(self.rows)]
        for column, height in enumerate(self.ground_heights):
            for offset in range(height):
                grid[self.rows - 1 - offset][column] = "1"
        for ledge in self.ledges:
            for column in range(ledge.start_column, ledge.end_column):
                grid[ledge.row][column] = "1"
        return ["".join(row) for row in grid]

    def surface_row(self, column: int) -> int:
        return self.rows - self.ground_heights[column]

    def normalized_x(self, column: int) -> float:
        """A position that lands mid-column, so it survives rounding in both directions."""

        return round((column + 0.5) / self.columns, 6)


def _deck_world_y(plan: LevelPlan, row: int) -> int:
    """World Y of a row's top edge, matching `vertical_fit = floor_to_screen_bottom`."""

    return VIEW_H - (plan.rows - row) * TILE_PX


def validate(plan: LevelPlan) -> list[str]:
    problems: list[str] = []
    if len(plan.ground_heights) != plan.columns:
        problems.append("ground_heights length must equal columns")
        return problems
    if not 2 <= plan.rows <= 64:
        problems.append(f"rows {plan.rows} outside the authored 2-64 range")
    if not 8 <= plan.columns <= 512:
        problems.append(f"columns {plan.columns} outside the authored 8-512 range")
    if any(height < 1 for height in plan.ground_heights):
        problems.append(
            "every column needs at least one ground tile; a hole is not authorable here"
        )

    for index in range(plan.columns - 1):
        delta = abs(plan.ground_heights[index + 1] - plan.ground_heights[index])
        if delta > MAX_UNASSISTED_TERRAIN_RISE_TILES:
            problems.append(
                f"columns {index}-{index + 1} rise {delta} tiles, above the unassisted maximum "
                f"{MAX_UNASSISTED_TERRAIN_RISE_TILES}; a step that large needs a climbable"
            )

    occupancy = plan.occupancy()
    for ledge in plan.ledges:
        if not 0 <= ledge.row < plan.rows:
            problems.append(f"ledge {ledge.ledge_id} row {ledge.row} is outside the matrix")
            continue
        if ledge.start_column >= ledge.end_column:
            problems.append(f"ledge {ledge.ledge_id} spans no columns")
            continue
        for column in range(ledge.start_column, ledge.end_column):
            if ledge.row >= plan.surface_row(column):
                problems.append(
                    f"ledge {ledge.ledge_id} column {column} sits inside the ground stack"
                )
                break
        deck_y = _deck_world_y(plan, ledge.row)
        if deck_y < VERTICAL_CAMERA_MIN_SCROLL_Y:
            problems.append(
                f"ledge {ledge.ledge_id} deck at world y {deck_y} is above the camera's "
                f"{VERTICAL_CAMERA_MIN_SCROLL_Y} limit; the player would climb out of frame"
            )

    for first in range(len(plan.ledges)):
        for second in range(first + 1, len(plan.ledges)):
            a, b = plan.ledges[first], plan.ledges[second]
            if a.row == b.row and a.start_column < b.end_column and b.start_column < a.end_column:
                problems.append(f"ledges {a.ledge_id} and {b.ledge_id} overlap on row {a.row}")

    if len(plan.climbs) > MAX_CLIMBABLE_PLACEMENTS:
        problems.append(
            f"{len(plan.climbs)} climbables exceeds the {MAX_CLIMBABLE_PLACEMENTS} placement bound"
        )
    seen_positions: set[float] = set()
    for climb in plan.climbs:
        if not 0 <= climb.column < plan.columns:
            problems.append(f"climbable {climb.climbable_id} column is outside the matrix")
            continue
        position = plan.normalized_x(climb.column)
        if position in seen_positions:
            problems.append(f"climbable {climb.climbable_id} shares a normalized_x with another")
        seen_positions.add(position)
        # Re-derive the column exactly as the contract and the runtime both do.
        if normalized_terrain_column(position, plan.columns) != climb.column:
            problems.append(
                f"climbable {climb.climbable_id} normalized_x does not resolve to column "
                f"{climb.column}"
            )
            continue
        # The runtime additionally requires a flat right neighbour, and throws
        # "ladder requires a flat lower terrain endpoint" if it is missing. Nothing in the
        # authored Python contract checks it, so a plan can pass validation and fail in the
        # browser. Catch it here, offline.
        if climb.column + 1 >= plan.columns:
            problems.append(
                f"climbable {climb.climbable_id} sits on the last column; the runtime needs a "
                "right terrain neighbour"
            )
        elif plan.ground_heights[climb.column] != plan.ground_heights[climb.column + 1]:
            problems.append(
                f"climbable {climb.climbable_id} needs a flat right terrain neighbour: column "
                f"{climb.column} is {plan.ground_heights[climb.column]} tiles and column "
                f"{climb.column + 1} is {plan.ground_heights[climb.column + 1]}"
            )
        lower = bottom_contiguous_surface_row(occupancy, climb.column)
        if lower is None:
            problems.append(
                f"climbable {climb.climbable_id} does not stand on bottom-supported terrain"
            )
            continue
        upper = lower - CLIMBABLE_RISE_TILES
        if upper < 0 or occupancy[upper][climb.column] != "1":
            problems.append(
                f"climbable {climb.climbable_id} has no deck exactly {CLIMBABLE_RISE_TILES} "
                f"tiles above its footing (needs an occupied cell at row {upper})"
            )
            continue
        if upper > 0 and occupancy[upper - 1][climb.column] != "0":
            problems.append(
                f"climbable {climb.climbable_id} deck at row {upper} is not exposed; "
                "the cell above it must be empty"
            )

    # Only ledge decks were bounded before. A ground stack taller than the framing budget walks
    # the player off the top of the frame with no error anywhere in the pipeline.
    tallest_ground = max(plan.ground_heights)
    if tallest_ground > MAX_FRAMED_SURFACE_TILES:
        problems.append(
            f"ground reaches {tallest_ground} tiles, above the {MAX_FRAMED_SURFACE_TILES}-tile "
            "framing budget; the player would slide out of the camera deadzone"
        )
    for ledge in plan.ledges:
        surface_tiles = (VIEW_H - _deck_world_y(plan, ledge.row)) // TILE_PX
        if surface_tiles > MAX_FRAMED_SURFACE_TILES:
            problems.append(
                f"ledge {ledge.ledge_id} deck sits {surface_tiles} tiles up, above the "
                f"{MAX_FRAMED_SURFACE_TILES}-tile framing budget"
            )

    if plan.walk_surface_row is not None:
        row = plan.walk_surface_row
        if not 0 <= row < plan.rows:
            problems.append("walk_surface_row is outside the matrix")
        else:
            above = occupancy[row - 1] if row > 0 else "0" * plan.columns
            if not any(
                cell == "1" and above[column] == "0" for column, cell in enumerate(occupancy[row])
            ):
                problems.append("walk_surface_row exposes no terrain surface")
    return problems


def emit_toml(plan: LevelPlan) -> str:
    occupancy = plan.occupancy()
    rows = "\n".join(f'  "{row}",' for row in occupancy)
    lines = [f"occupancy = [\n{rows}\n]"]
    if plan.walk_surface_row is not None:
        lines.append(f"walk_surface_row = {plan.walk_surface_row}")
    placements = []
    for climb in plan.climbs:
        placements.append(
            "[[climbable.placements]]\n"
            f'climbable_id = "{climb.climbable_id}"\n'
            f'variant_id = "{climb.variant_id}"\n'
            f"normalized_x = {plan.normalized_x(climb.column)}\n"
            'bottom_surface = "terrain"\n'
            f"rise_tiles = {CLIMBABLE_RISE_TILES}"
        )
    return "\n".join(lines) + "\n\n" + "\n\n".join(placements) + "\n"


def describe(plan: LevelPlan) -> str:
    occupancy = plan.occupancy()
    deck_rows = sorted({ledge.row for ledge in plan.ledges})
    return (
        f"{plan.map_id}: {plan.rows} rows x {plan.columns} columns "
        f"-> world {plan.columns * TILE_PX}x{plan.rows * TILE_PX}px\n"
        f"  ground heights {min(plan.ground_heights)}-{max(plan.ground_heights)} tiles\n"
        f"  {len(plan.ledges)} ledges on rows {deck_rows} "
        f"(deck world y {[_deck_world_y(plan, r) for r in deck_rows]})\n"
        f"  {len(plan.climbs)} climbables at columns "
        f"{[c.column for c in plan.climbs]}\n"
        f"  occupancy rows: {len(occupancy)}, width {len(occupancy[0])}"
    )


def crowncrag_road() -> LevelPlan:
    """Crowncrag Road as a climbing route rather than a flat walk.

    The ground rolls in steps no larger than the unassisted maximum, so every real height change
    is a climbable rather than a wall the player cannot read. Three tiers stack four tiles apart,
    which is the only rise a climbable spans today, and every deck stays inside the camera range.
    """

    columns, rows = 96, 16
    heights = [3] * columns

    def slope(start: int, end: int, height: int) -> None:
        for column in range(start, end):
            heights[column] = height

    # A rolling ground line: gentle rises the player can walk, plus two deeper basins that make
    # the upper tiers worth climbing to.
    slope(12, 20, 4)
    slope(20, 26, 5)
    slope(26, 34, 4)
    slope(34, 44, 3)
    slope(44, 52, 4)
    slope(52, 60, 5)
    slope(60, 68, 4)
    slope(68, 78, 3)
    slope(78, 88, 4)
    slope(88, 96, 3)

    ledges = [
        # Tier one, reachable from the opening flat.
        Ledge("river_shelf", row=rows - 3 - CLIMBABLE_RISE_TILES, start_column=4, end_column=14),
        # Tier two, above the first basin.
        Ledge("root_gallery", row=rows - 5 - CLIMBABLE_RISE_TILES, start_column=20, end_column=30),
        # Tier three, the highest deck on the route.
        Ledge("bell_landing", row=rows - 5 - CLIMBABLE_RISE_TILES, start_column=52, end_column=62),
        # A late shelf so the route ends on a climb rather than a walk.
        Ledge(
            "crown_approach", row=rows - 4 - CLIMBABLE_RISE_TILES, start_column=78, end_column=88
        ),
    ]
    climbs = [
        Climb("river_ladder", "bellroot_ladder", column=6),
        Climb("root_rope_ladder", "shrine_rope_ladder", column=22),
        Climb("bell_rope", "bellrope_climb", column=54),
        Climb("crown_ladder", "bellroot_ladder", column=80),
        Climb("crown_rope", "bellrope_climb", column=84),
    ]
    return LevelPlan(
        map_id="crowncrag-road",
        columns=columns,
        rows=rows,
        ground_heights=heights,
        ledges=ledges,
        climbs=climbs,
        walk_surface_row=rows - 3,
    )


PLANS = {"crowncrag-road": crowncrag_road}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", choices=sorted(PLANS), required=True)
    parser.add_argument("--emit-toml", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    plan = PLANS[args.plan]()
    problems = validate(plan)
    if problems:
        print(describe(plan))
        print("\nREJECTED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(describe(plan))
    print("\nplan satisfies every authored and runtime terrain contract")
    if args.emit_toml:
        print()
        print(emit_toml(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
