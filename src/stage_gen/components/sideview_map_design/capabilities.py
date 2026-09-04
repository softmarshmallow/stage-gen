"""What a game can express, stated as data rather than assumed.

Every constant a map designer is tempted to treat as universal turns out to be one game's
tuning: a 2-tile unassisted step, a 4-tile climbable, ground-only climbable footing, a 12-tile
framing budget. None of that belongs in a map designer. It belongs here, supplied by whoever is
designing a map.

Everything is in TILES. This module never sees pixels, a camera, an engine, or an art pipeline;
converting tiles to a viewport is the consumer's job, and it is exactly that conversion which
makes a movement envelope game-specific in the first place.

The module deliberately contains no game. It declares the vocabulary a caller uses to describe
one, and the three standard tile roles so a caller need not redeclare the alphabet.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

#: Where a climbable may plant its foot.
#:   "ground"  - only on terrain connected to the world floor
#:   "any"     - on any walkable surface, which permits ladder-chained storeys
ClimbableFooting = Literal["ground", "any"]


@dataclass(frozen=True)
class TileRole:
    """One symbol in the map alphabet, and what the consumer will do with it.

    The alphabet is declared rather than fixed because it is the one thing that must match the
    consumer exactly. A role the consumer cannot render is a lie the designer would be free to
    tell, so a caller should declare only roles it can actually build.
    """

    symbol: str
    name: str
    description: str
    #: True when a player can stand on this role's top surface.
    walkable: bool = True
    #: True when this role must rest on the world floor (a heightfield, not a platform).
    grounded: bool = False

    def __post_init__(self) -> None:
        if len(self.symbol) != 1:
            raise ValueError("a tile role symbol must be exactly one character")


@dataclass(frozen=True)
class MovementProfile:
    """What the player can traverse, in tiles. Measured from the game, never guessed."""

    #: Largest height increase a player can clear between adjacent walkable columns.
    max_step_up_tiles: int
    #: rise_tiles -> the widest horizontal gap that rise is still reachable across.
    #: Absent rises are unreachable. Derive this from the game's own jump simulation.
    jump_reach: Mapping[int, int]
    #: Exact rises a climbable may span. A single-valued tuple pins it, as a fixed-rise
    #: contract does; a range lets the designer choose.
    climbable_rise_tiles: tuple[int, ...]
    #: Widest horizontal gap crossable when the target is level with or below the source.
    #: Treating any drop or level move as crossable at ANY gap silently connects surfaces a
    #: whole screen apart; that rule was measured accepting a stranded platform.
    level_gap_tiles: int = 0
    climbable_footing: ClimbableFooting = "ground"
    #: True when a climbable's foot needs the next column at the same height.
    climbable_needs_flat_footing: bool = False

    def __post_init__(self) -> None:
        if self.max_step_up_tiles < 0:
            raise ValueError("max_step_up_tiles cannot be negative")
        if not self.climbable_rise_tiles:
            raise ValueError("a profile must permit at least one climbable rise")
        if any(rise < 1 for rise in self.climbable_rise_tiles):
            raise ValueError("climbable rises must be positive")

    def reachable(self, rise_tiles: int, gap_tiles: int) -> bool:
        """Can a player cross from one surface to another that is ``rise_tiles`` higher?"""

        if rise_tiles <= 0:
            return gap_tiles <= self.level_gap_tiles
        limit = self.jump_reach.get(rise_tiles)
        return limit is not None and gap_tiles <= limit

    @property
    def max_jumpable_rise(self) -> int:
        return max(self.jump_reach, default=0)


@dataclass(frozen=True)
class GeometryProfile:
    """The bounds of the grid the consumer can accept."""

    columns: int
    rows: int
    #: Depth of solid floor under every column. The lower bound is what the consumer needs to
    #: render a floor at all; the upper bound stops the floor eating the playable space.
    ground_depth_tiles: tuple[int, int]
    #: Highest walkable surface the consumer can keep on screen. This is a framing budget, not a
    #: grid bound, and it is usually well below ``rows``.
    max_walkable_height_tiles: int
    #: True when a floating platform must be exactly one tile thick.
    platforms_single_thickness: bool = True
    #: Narrowest deck that counts as standing room rather than a stepping stone. Only the words
    #: that promise room to stand and fight are held to it; a stepping-stone word is allowed to
    #: be narrow on purpose. Schema minimums are advisory under strict output, so this is a
    #: validated rule, not a hint.
    shelf_min_width_tiles: int = 2

    def __post_init__(self) -> None:
        if self.shelf_min_width_tiles < 1:
            raise ValueError("a shelf needs at least one tile to stand on")
        low, high = self.ground_depth_tiles
        if low < 1:
            raise ValueError("every column needs at least one floor tile")
        if high < low:
            raise ValueError("ground depth range is inverted")
        if self.max_walkable_height_tiles > self.rows:
            raise ValueError("the framing budget cannot exceed the grid height")


@dataclass(frozen=True)
class PlatformerProfile:
    """A complete description of what one game will accept from the designer."""

    profile_id: str
    movement: MovementProfile
    geometry: GeometryProfile
    roles: tuple[TileRole, ...]
    #: Named climbable kinds the consumer can draw. Empty disables climbables entirely.
    climbable_variants: tuple[str, ...] = ()
    climbable_count: tuple[int, int] = (0, 0)
    #: True when a design must place every declared variant at least once. A consumer that draws
    #: each declared variant into an atlas cell has no use for a variant the map never stands up,
    #: and would reject the geometry after the fact; declaring it here lets the validator say so
    #: while the design can still be re-composed.
    climbable_variants_each_placed: bool = False
    #: Physics-neutral appearance tags the design may paint terrain with; empty disables the
    #: channel. The designer chooses the tag, exactly as it chooses a climbable variant by
    #: name; resolving a tag to actual art is the consumer's later step.
    biomes: tuple[str, ...] = ()
    #: Narrowest contiguous biome region the consumer can paint (transitions need room).
    biome_min_span_tiles: int = 0
    notes: str = ""

    def __post_init__(self) -> None:
        symbols = [role.symbol for role in self.roles]
        if len(set(symbols)) != len(symbols):
            raise ValueError("tile role symbols must be unique")
        if not any(role.grounded for role in self.roles):
            raise ValueError("a profile needs one grounded role for the floor")
        if self.climbable_variants_each_placed and not self.climbable_variants:
            raise ValueError("a profile cannot require placing variants it does not declare")

    @property
    def empty_role(self) -> TileRole:
        for role in self.roles:
            if not role.walkable and not role.grounded:
                return role
        raise ValueError("a profile needs one empty role")

    @property
    def ground_role(self) -> TileRole:
        return next(role for role in self.roles if role.grounded)

    @property
    def platform_roles(self) -> tuple[TileRole, ...]:
        return tuple(role for role in self.roles if role.walkable and not role.grounded)

    @property
    def solid_symbols(self) -> frozenset[str]:
        return frozenset(role.symbol for role in self.roles if role.walkable or role.grounded)


#: The three standard roles. A caller may declare its own alphabet instead; these exist so the
#: common case does not have to.
EMPTY_TILE_ROLE = TileRole(".", "empty", "open air the player moves through", walkable=False)
GROUND_TILE_ROLE = TileRole(
    "#", "ground", "solid terrain connected down to the world floor", grounded=True
)
PLATFORM_TILE_ROLE = TileRole("=", "platform", "a floating platform's walkable top surface")

STANDARD_TILE_ROLES: tuple[TileRole, ...] = (
    EMPTY_TILE_ROLE,
    GROUND_TILE_ROLE,
    PLATFORM_TILE_ROLE,
)

__all__ = [
    "EMPTY_TILE_ROLE",
    "GROUND_TILE_ROLE",
    "PLATFORM_TILE_ROLE",
    "STANDARD_TILE_ROLES",
    "ClimbableFooting",
    "GeometryProfile",
    "MovementProfile",
    "PlatformerProfile",
    "TileRole",
]
