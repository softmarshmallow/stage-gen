"""Climbable atlas layout, request sizing, and per-role admission envelopes.

One provider image carries every climbable a map declares. Layout is expressed in world tiles and
converted to pixels exactly once, so it survives a change of supersample factor or runtime tile
size. The request size must satisfy the provider's own limits, which is what bounds how many
variants can share a sheet.

A ladder carries crosswise rungs; a rope is a continuous strand. Their silhouettes differ by
roughly a factor of four, so each role is admitted against its own aspect envelope. The role is
authored in ``maps/<map_id>.toml`` and never inferred from pixels.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

ClimbableRole = Literal["ladder", "rope"]

#: web/lib/sideview-platformer/prepared-scene.ts TILE_PX
RUNTIME_TILE_PX = 64
#: web/lib/sideview-platformer/vertical.ts LADDER_VISUAL_WIDTH / LADDER_VISUAL_OVERSHOOT, in tiles.
CLIMBABLE_WIDTH_TILES = Fraction(1)
CLIMBABLE_OVERSHOOT_TILES = Fraction(1, 2)
GUTTER_TILES = Fraction(1)
PAD_TILES = Fraction(1, 2)

#: Source pixels per world tile. Fixed rather than derived from the variant count: it is the one
#: factor legal across the whole supported range, so no map needs adaptive sizing, and every
#: variant gets the same source cell whatever the count. A single climbable at 3x falls under the
#: provider's pixel floor. The runtime draws a climbable 64px wide, so 4x is already generous and
#: further headroom has diminishing value.
CLIMBABLE_SUPERSAMPLE = 4

#: src/gnode/providers/openai/image.py::_validate_gpt_image_2_size
EDGE_MULTIPLE = 16
EDGE_MAX = 3840
ASPECT_MAX = Fraction(3)
PIXELS_MIN = 655_360
PIXELS_MAX = 8_294_400

#: Measured across two art styles and nineteen sheets: ladders land at 4.0-4.4 height over width,
#: ropes at 14.7-16.2. One shared band cannot admit both. Widened to leave regeneration headroom
#: without admitting a silhouette that is not the declared role.
ROLE_ASPECT_ENVELOPE: dict[ClimbableRole, tuple[float, float]] = {
    "ladder": (2.0, 9.0),
    "rope": (8.0, 40.0),
}

#: All variants share one world scale, so their trimmed heights must agree closely.
MAX_HEIGHT_PARITY = 1.25


@dataclass(frozen=True, slots=True)
class ClimbableAtlasPlan:
    """The resolved sheet geometry for one map's declared climbables."""

    variants: int
    unit_px: int
    width_px: int
    height_px: int
    cell_px: tuple[int, int]

    @property
    def size(self) -> str:
        return f"{self.width_px}x{self.height_px}"

    @property
    def pixels(self) -> int:
        return self.width_px * self.height_px


def _round_up_multiple(value: int, multiple: int) -> int:
    return -(-value // multiple) * multiple


def provider_size_violations(width: int, height: int) -> list[str]:
    """Every reason the provider would reject this request size."""

    problems: list[str] = []
    if width % EDGE_MULTIPLE or height % EDGE_MULTIPLE:
        problems.append(f"edges must be multiples of {EDGE_MULTIPLE}")
    if width > EDGE_MAX or height > EDGE_MAX:
        problems.append(f"edges must not exceed {EDGE_MAX}px")
    long_edge, short_edge = max(width, height), min(width, height)
    if Fraction(long_edge, short_edge) > ASPECT_MAX:
        problems.append(f"aspect {long_edge / short_edge:.2f}:1 exceeds {ASPECT_MAX}:1")
    if not PIXELS_MIN <= width * height <= PIXELS_MAX:
        problems.append(f"{width * height} pixels outside [{PIXELS_MIN}, {PIXELS_MAX}]")
    return problems


def plan_climbable_atlas(variants: int, *, rise_tiles: int = 4) -> ClimbableAtlasPlan:
    """Lay one tile-wide column out per variant, then convert once to a legal request size."""

    if variants < 1:
        raise ValueError("climbable atlas must carry at least one variant")
    unit_px = RUNTIME_TILE_PX * CLIMBABLE_SUPERSAMPLE
    cell_h = Fraction(rise_tiles) + CLIMBABLE_OVERSHOOT_TILES * 2
    width_tiles = PAD_TILES * 2 + CLIMBABLE_WIDTH_TILES * variants + GUTTER_TILES * (variants - 1)
    height_tiles = PAD_TILES * 2 + cell_h
    width_px = _round_up_multiple(round(width_tiles * unit_px), EDGE_MULTIPLE)
    height_px = _round_up_multiple(round(height_tiles * unit_px), EDGE_MULTIPLE)
    problems = provider_size_violations(width_px, height_px)
    if problems:
        raise ValueError(
            f"climbable atlas for {variants} variants is not requestable at "
            f"{width_px}x{height_px}: " + "; ".join(problems)
        )
    return ClimbableAtlasPlan(
        variants=variants,
        unit_px=unit_px,
        width_px=width_px,
        height_px=height_px,
        cell_px=(
            round(CLIMBABLE_WIDTH_TILES * unit_px),
            round(cell_h * unit_px),
        ),
    )


def nominal_cell_box(plan: ClimbableAtlasPlan, index: int) -> tuple[int, int, int, int]:
    """Where a variant is asked to sit, used to prove one subject occupies each column."""

    if not 0 <= index < plan.variants:
        raise ValueError("climbable atlas column index is outside the plan")
    pad = round(PAD_TILES * plan.unit_px)
    gutter = round(GUTTER_TILES * plan.unit_px)
    cell_w, cell_h = plan.cell_px
    left = pad + index * (cell_w + gutter)
    return left, pad, left + cell_w, pad + cell_h


def role_aspect_admits(role: ClimbableRole, width: int, height: int) -> bool:
    if width <= 0 or height <= 0:
        return False
    low, high = ROLE_ASPECT_ENVELOPE[role]
    return low <= height / width <= high


__all__ = [
    "CLIMBABLE_SUPERSAMPLE",
    "MAX_HEIGHT_PARITY",
    "ROLE_ASPECT_ENVELOPE",
    "RUNTIME_TILE_PX",
    "ClimbableAtlasPlan",
    "ClimbableRole",
    "nominal_cell_box",
    "plan_climbable_atlas",
    "provider_size_violations",
    "role_aspect_admits",
]
