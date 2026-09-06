"""Algorithmic world layout: biome mask, scatter, camp clearing, splat plate.

Local and free. Nothing here calls a provider, and the same seed must produce
byte-identical JSON and identical splat bytes, because the layout is part of the
run's identity and a viewer reload must not shuffle the world.

The layout is deliberately dumb. Proving that an LLM can design a survival map
is not this spike's question; the platformer's map designer already answered the
shape of that problem, and porting it here is a later, separate piece of work.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from io import BytesIO
from typing import Final, TypedDict, cast

from PIL import Image

from stage_gen.recipes.oblique_survival.models import (
    CAMP_PROP_IDS,
    Clutter,
    Forage,
    Package,
    Plants,
    Prop,
)

#: Metres per splat cell, whatever the world's size. The road is 2.2 m wide
#: and needs more than four cells across it for its eroded edge to read as
#: torn rather than stepped; a 256 m world is a 1024-cell plate.
SPLAT_CELL_METERS: Final = 0.25

#: The layout's only source of randomness: ``mulberry32`` handed out as a
#: nullary draw in [0, 1). Every scatter takes its draws from one of these, in
#: one order, which is what makes a seed reproduce a world byte for byte.
type Rand = Callable[[], float]
#: ``(x, z, margin)`` -> land here and at four points ``margin`` metres away.
type LandTest = Callable[[float, float, float], bool]
#: ``(x, z, radius)`` -> whether anything already placed reaches this far.
type CollisionTest = Callable[[float, float, float], bool]
#: ``(x, z)`` -> the id of the biome that owns that point.
type BiomeLookup = Callable[[float, float], str]


class DecalPlacement(TypedDict):
    """One decal laid flat on the ground, as the layout record publishes it."""

    decal: str
    x: float
    z: float
    rotation_degrees: float
    scale: float


class GroundDecal(DecalPlacement, total=False):
    """A decal placement plus whichever of the two optional bindings it carries."""

    #: The entity a pad or a skirt belongs to. A viewer with no card for that
    #: entity draws no decal either, because a pad alone reads as a stain.
    under: str
    #: The weather condition that reveals a wet decal. Absent for the rest.
    condition: str


class GroundPiece(TypedDict):
    """One cell of a piece sheet (litter, forage, a standing plant) on the ground."""

    #: Index into the sheet's cells, in reading order.
    cell: int
    x: float
    z: float
    rotation_degrees: float
    scale: float


#: Metres per bucket of the placement hash. A bucket must be wider than the
#: largest scatter reach two props can have between them, so a collision is
#: always found in the 3x3 of buckets around a candidate.
def splat_cells(size: float) -> int:
    return max(16, round(size / SPLAT_CELL_METERS))


class PlacementHash:
    """Placed entities bucketed on a grid, so a collision test reads nine buckets, not all.

    The bucket is at least twice the largest scatter radius, so two entities
    that could touch are never more than one bucket apart. Same answer as the
    full scan, which is what byte-identity needs.
    """

    def __init__(self, bucket_meters: float) -> None:
        self.bucket = max(1.0, bucket_meters)
        self.buckets: dict[tuple[int, int], list[Placed]] = {}

    def add(self, placed: Placed) -> None:
        key = (int(placed.x // self.bucket), int(placed.z // self.bucket))
        self.buckets.setdefault(key, []).append(placed)

    def collides(self, x: float, z: float, radius: float) -> bool:
        cx = int(x // self.bucket)
        cz = int(z // self.bucket)
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for placed in self.buckets.get((cx + dx, cz + dz), ()):
                    reach = radius + placed.scatter_radius_meters
                    if (x - placed.x) ** 2 + (z - placed.z) ** 2 < reach * reach:
                        return True
        return False


#: Metres of feather across a biome boundary once the shader has eroded it.
BLEND_METERS: Final = 3.0
#: Value-noise lattice resolution. Small enough that biomes are continents,
#: not speckle.
NOISE_LATTICE: Final = 8


#: A piece lying on the ground (litter, a contact patch) carries its shadow
#: along its lower edge, so it is never spun and never mirrored: it turns at
#: most the look contract's jitter from facing the camera, and the viewer
#: re-aims it when the camera turns. Nothing is mirrored for variety anywhere.
def _ground_piece_jitter(package: Package, rand: Rand) -> float:
    turn: float = rand() * 2.0 - 1.0
    return round(turn * package.look.ground_piece_jitter_degrees, 2)


#: Rounds of threshold adjustment when solving the biome shares. Each biome's
#: field is thresholded to its share alone and then the overlaps are settled by
#: which field is further above its threshold, so the solved shares drift a
#: little; a few rounds of correction bring them back.
SHARE_SOLVE_ROUNDS: Final = 16


def mulberry32(seed: int) -> Rand:
    """The viewer runs the same generator, so a shared name is worth the note."""

    state = seed & 0xFFFFFFFF

    def rand() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        t = state
        t = (t ^ (t >> 15)) * (t | 1) & 0xFFFFFFFF
        t = (t ^ (t + ((t ^ (t >> 7)) * (t | 61) & 0xFFFFFFFF))) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0

    return rand


def _smoothstep(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


class ValueNoise:
    """Tileable bilinear value noise on a small lattice. Pure Python, no numpy."""

    def __init__(self, seed: int, lattice: int = NOISE_LATTICE) -> None:
        rand = mulberry32(seed)
        self.lattice = lattice
        self.values = [[rand() for _ in range(lattice)] for _ in range(lattice)]

    def at(self, u: float, v: float) -> float:
        """``u`` and ``v`` are in [0, 1) over the world; the field wraps."""

        n = self.lattice
        x = (u % 1.0) * n
        y = (v % 1.0) * n
        x0, y0 = math.floor(x), math.floor(y)
        fx, fy = _smoothstep(x - x0), _smoothstep(y - y0)
        x0 %= n
        y0 %= n
        x1, y1 = (x0 + 1) % n, (y0 + 1) % n
        top: float = self.values[y0][x0] * (1.0 - fx) + self.values[y0][x1] * fx
        bottom: float = self.values[y1][x0] * (1.0 - fx) + self.values[y1][x1] * fx
        return top * (1.0 - fy) + bottom * fy

    def grid(self, cells: int) -> list[list[float]]:
        """The field sampled at every cell centre of a ``cells`` x ``cells`` plate.

        The same bilinear blend as ``at``, with the row's vertical blend hoisted
        out of the inner loop: a million-cell plate is a few hundred
        milliseconds instead of a dozen seconds of ``at`` calls.
        """

        n = self.lattice
        columns: list[tuple[int, int, float]] = []
        for column in range(cells):
            x = ((column + 0.5) / cells % 1.0) * n
            x0 = math.floor(x)
            columns.append((x0 % n, (x0 + 1) % n, _smoothstep(x - x0)))
        rows: list[list[float]] = []
        for row in range(cells):
            y = ((row + 0.5) / cells % 1.0) * n
            y0 = math.floor(y)
            fy = _smoothstep(y - y0)
            above = self.values[y0 % n]
            below = self.values[(y0 + 1) % n]
            line = [above[i] * (1.0 - fy) + below[i] * fy for i in range(n)]
            rows.append([line[x0] * (1.0 - fx) + line[x1] * fx for x0, x1, fx in columns])
        return rows


@dataclass(frozen=True, slots=True)
class Placed:
    entity_id: str
    kind: str
    ref_id: str
    state: str | None
    x: float
    z: float
    seed: int
    footprint_radius_meters: float
    scatter_radius_meters: float


@dataclass(frozen=True, slots=True)
class Layout:
    seed: int
    size_meters: float
    player_spawn: tuple[float, float]
    camp_position: tuple[float, float]
    clear_radius_meters: float
    entities: tuple[Placed, ...]
    decals: tuple[GroundDecal, ...]
    road_id: str | None
    road_width_meters: float
    road: tuple[tuple[float, float], ...]
    clutter: tuple[GroundPiece, ...]
    #: The forage pieces, the same shape as the litter: the item each yields
    #: is the manifest's cell record, not repeated here.
    forage: tuple[GroundPiece, ...]
    #: The standing plants, the same shape again; the viewer stands them up.
    plants: tuple[GroundPiece, ...]
    land_share: float
    splat_png: bytes
    #: The biome-weight plate: R, G, B are the non-base biomes in declaration
    #: order, hard-edged; the base is whatever is left. Alpha is always opaque,
    #: because a browser premultiplies an image by its alpha on decode.
    biome_splat_png: bytes
    #: Share of the square each biome actually got, by id.
    biome_shares: dict[str, float]
    counts: dict[str, int]

    def as_record(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "size_meters": round(self.size_meters, 3),
            "player_spawn": {"x": self.player_spawn[0], "z": self.player_spawn[1]},
            "camp_position": {"x": self.camp_position[0], "z": self.camp_position[1]},
            "clear_radius_meters": round(self.clear_radius_meters, 3),
            "counts": dict(sorted(self.counts.items())),
            "entities": [
                {
                    "id": entity.entity_id,
                    "kind": entity.kind,
                    ("prop" if entity.kind == "prop" else "actor"): entity.ref_id,
                    **({"state": entity.state} if entity.state is not None else {}),
                    "x": entity.x,
                    "z": entity.z,
                    "seed": entity.seed,
                    "footprint_radius_meters": round(entity.footprint_radius_meters, 3),
                }
                for entity in self.entities
            ],
            "decals": [dict(decal) for decal in self.decals],
            "road": (
                {
                    "road_id": self.road_id,
                    "width_meters": round(self.road_width_meters, 3),
                    "points": [{"x": x, "z": z} for x, z in self.road],
                }
                if self.road
                else None
            ),
            "clutter": [dict(entry) for entry in self.clutter],
            "forage": [dict(entry) for entry in self.forage],
            "plants": [dict(entry) for entry in self.plants],
            "land_share": round(self.land_share, 4),
            "biome_shares": {
                key: round(value, 4) for key, value in sorted(self.biome_shares.items())
            },
        }


def _scatter_radius(package: Package, prop: Prop) -> float:
    """Separation is not collision: grass has no footprint but still must not stack."""

    footprint = package.meters(prop.footprint_radius_units)
    return max(footprint, 0.5 * package.meters(prop.shadow_width_units))


def _biome_weight(package: Package, prop: Prop, biome_id: str) -> float:
    """How much this prop likes this biome: the prop's own row, else its family's."""

    if prop.biome_weights is not None:
        value = prop.biome_weights.get(biome_id)
        return float(value) if value is not None else 0.0
    weights = package.world.get("biome_weights", {})
    entry = weights.get(prop.family)
    if not isinstance(entry, dict):
        return 1.0
    value = entry.get(biome_id)
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


class BiomeField:
    """One value-noise field per non-base biome, each thresholded to its share.

    Where two fields both clear their thresholds the one further above its own
    wins, so every boundary is a wobbly curve between two continents rather
    than a band of the base. The thresholds are solved on a sampled grid, not
    assumed, so the shares hold whatever the lattices happen to produce.
    """

    def __init__(
        self, package: Package, seed: int, *, camp_clear: tuple[float, float, float] | None = None
    ) -> None:
        # The camp stands on the base biome: inside `camp_clear` (unit-square
        # centre and radius) the islet octave is faded out, so the spawn is
        # never on a patch of scree or bog that the fine noise happened to
        # drop at the world's centre. The continents are untouched.
        self.camp_clear = camp_clear
        self.base = package.biomes[0].biome_id
        self.others = [biome for biome in package.biomes[1:]]
        # The first field keeps the seed the single second biome always had,
        # so a package that only ever had two biomes keeps its map.
        self.fields = [
            ValueNoise(seed * 7919 + 13 + 1009 * index, NOISE_LATTICE)
            for index, _ in enumerate(self.others)
        ]
        # The islets: a second, finer octave per biome, thresholded high, so a
        # biome is also a scatter of patches a few metres across inside the
        # others. The reference's turf is a patchwork at that scale, and a
        # screen at play zoom holds two or three materials because of it, not
        # because of anything inside a tile. `biome_islet_share` is the part
        # of each biome's share spent on islets; the continent keeps the rest.
        world = package.world
        islet_lattice = int(world.get("biome_islet_lattice", 0) or 0)
        self.islet_share = float(world.get("biome_islet_share", 0.0) or 0.0)
        if islet_lattice <= 0 or self.islet_share <= 0.0:
            self.islet_share = 0.0
        self.islets = (
            [
                ValueNoise(seed * 6007 + 29 + 1013 * index, islet_lattice)
                for index, _ in enumerate(self.others)
            ]
            if self.islet_share > 0.0
            else []
        )
        grid = [(i / 48.0, j / 48.0) for i in range(48) for j in range(48)]
        self.thresholds = [0.0] * len(self.others)
        self.islet_thresholds = [0.0] * len(self.others)
        for index, (biome, field) in enumerate(zip(self.others, self.fields, strict=True)):
            samples = sorted(field.at(u, v) for u, v in grid)
            continent = biome.share * (1.0 - self.islet_share)
            self.thresholds[index] = samples[int((1.0 - continent) * (len(samples) - 1))]
            if self.islets:
                fine = sorted(self.islets[index].at(u, v) for u, v in grid)
                islet = biome.share * self.islet_share
                self.islet_thresholds[index] = fine[int((1.0 - islet) * (len(fine) - 1))]
        for _ in range(SHARE_SOLVE_ROUNDS):
            counts = [0] * len(self.others)
            for u, v in grid:
                index = self._index_at(u, v)
                if index >= 0:
                    counts[index] += 1
            for index, biome in enumerate(self.others):
                actual = counts[index] / len(grid)
                # Field units and share units are both [0, 1]; a half-step
                # converges without overshooting on these lattices. Both
                # thresholds move together, so the continent-to-islet split
                # stays where it was authored.
                self.thresholds[index] += (actual - biome.share) * 0.5
                self.islet_thresholds[index] += (actual - biome.share) * 0.5
        self.shares: dict[str, float] = {}
        counts = [0] * len(self.others)
        for u, v in grid:
            index = self._index_at(u, v)
            if index >= 0:
                counts[index] += 1
        for index, biome in enumerate(self.others):
            self.shares[biome.biome_id] = counts[index] / len(grid)
        self.shares[self.base] = 1.0 - sum(self.shares.values())

    @classmethod
    def for_layout(cls, package: Package, layout: Layout) -> BiomeField:
        """The field exactly as ``build_layout`` solved it, camp clearing included."""

        return cls(
            package,
            layout.seed,
            camp_clear=(0.5, 0.5, layout.clear_radius_meters * 2.5 / layout.size_meters),
        )

    def _islet_gain(self, u: float, v: float) -> float:
        """1 away from the camp, 0 inside its clearing, a smooth step between."""

        if self.camp_clear is None:
            return 1.0
        cu, cv, radius = self.camp_clear
        if radius <= 0.0:
            return 1.0
        t = (math.hypot(u - cu, v - cv) - radius) / (radius * 0.6)
        t = min(1.0, max(0.0, t))
        return t * t * (3.0 - 2.0 * t)

    def _index_at(self, u: float, v: float) -> int:
        """Index into ``others`` of the biome at a unit-square point, or -1 for the base."""

        best, excess = -1, 0.0
        gain = self._islet_gain(u, v)
        for index, field in enumerate(self.fields):
            margin = field.at(u, v) - self.thresholds[index]
            if self.islets:
                margin = max(
                    margin, (self.islets[index].at(u, v) - self.islet_thresholds[index]) * gain
                )
            if margin > excess:
                best, excess = index, margin
        return best

    def index_at(self, x: float, z: float, size: float) -> int:
        half = size / 2.0
        return self._index_at((x + half) / size, (z + half) / size)

    def index_grid(self, cells: int) -> list[list[int]]:
        """``_index_at`` at every cell centre of a plate, from the hoisted noise grids."""

        grids = [field.grid(cells) for field in self.fields]
        fine_grids = [islet.grid(cells) for islet in self.islets]
        thresholds = self.thresholds
        fine_thresholds = self.islet_thresholds
        out: list[list[int]] = []
        for row in range(cells):
            lines = [grid[row] for grid in grids]
            fine_lines = [grid[row] for grid in fine_grids]
            line: list[int] = []
            v = (row + 0.5) / cells
            for column in range(cells):
                best, excess = -1, 0.0
                gain = self._islet_gain((column + 0.5) / cells, v) if fine_lines else 1.0
                for index, values in enumerate(lines):
                    margin = values[column] - thresholds[index]
                    if fine_lines:
                        margin = max(
                            margin, (fine_lines[index][column] - fine_thresholds[index]) * gain
                        )
                    if margin > excess:
                        best, excess = index, margin
                line.append(best)
            out.append(line)
        return out

    def biome_at(self, x: float, z: float, size: float) -> str:
        index = self.index_at(x, z, size)
        return self.base if index < 0 else self.others[index].biome_id


def _family_shares(package: Package) -> dict[str, float]:
    """Total density share per family, for splitting the family's budget."""

    totals: dict[str, float] = {}
    for prop in package.props:
        if prop.prop_id in CAMP_PROP_IDS:
            continue
        totals[prop.family] = totals.get(prop.family, 0.0) + prop.density_share
    return totals


def _prop_target(
    package: Package, prop: Prop, area_hundreds: float, shares: dict[str, float]
) -> int:
    """How many of this prop the world wants.

    `[world.density]` is a FAMILY budget, not a per-prop one. Before shares
    existed, a second conifer would simply have doubled the wood.
    """

    per_hundred = (package.world.get("density", {}) or {}).get(prop.family)
    if not isinstance(per_hundred, int | float) or isinstance(per_hundred, bool):
        return 0
    total = shares.get(prop.family, 0.0)
    if total <= 0.0:
        return 0
    return round(float(per_hundred) * area_hundreds * prop.density_share / total)


class Landmass:
    """The land: noise plus a radial falloff, solved to the authored share.

    A bump under the camp keeps the camp on land whatever the noise says, and
    a water ring inside the square means the player never sees the square's
    edge. Beyond the coast the ground is discarded and the water shows through.
    ``at`` answers one point (the scatter asks); ``grid`` answers a whole plate
    from the hoisted noise grids (the splat asks, a million times).
    """

    def __init__(
        self,
        package: Package,
        *,
        seed: int,
        size: float,
        camp: tuple[float, float],
        clear_radius: float,
    ) -> None:
        landmass = package.world.get("landmass", {})
        self.size = size
        self.half = size / 2.0
        self.camp = camp
        self.clear_radius = clear_radius
        self.land_share = float(landmass.get("land_share", 0.6))
        self.shore_margin = float(landmass.get("shore_margin_meters", 2.0))
        lattice = int(landmass.get("coast_noise_lattice", 6))
        self.coast = ValueNoise(seed * 104729 + 7, lattice)
        # A second octave crinkles the coast at a few metres, the hand-torn
        # look of the reference; the shader tears it again below a metre.
        self.crinkle = ValueNoise(seed * 7 + 3, lattice * 4)
        self.crinkle_weight = float(landmass.get("coast_crinkle", 0.30))
        samples = sorted(
            self.field(
                (i + 0.5) / 96.0 * size - self.half,
                (j + 0.5) / 96.0 * size - self.half,
            )
            for i in range(96)
            for j in range(96)
        )
        self.threshold = samples[int((1.0 - self.land_share) * (len(samples) - 1))]
        self.solved_share = sum(1 for value in samples if value > self.threshold) / len(samples)

    def _shape(self, x: float, z: float, coast: float, crinkle: float) -> float:
        half = self.half
        if max(abs(x), abs(z)) / half > 0.94:
            return -10.0
        radial = math.hypot(x, z) / half
        camp_bump = max(
            0.0, 1.0 - math.hypot(x - self.camp[0], z - self.camp[1]) / (self.clear_radius * 2.5)
        )
        return (
            coast * 0.55
            + (crinkle - 0.5) * self.crinkle_weight
            + (1.0 - radial * radial) * 0.9
            + camp_bump * 1.5
        )

    def field(self, x: float, z: float) -> float:
        u = (x + self.half) / self.size
        v = (z + self.half) / self.size
        return self._shape(x, z, self.coast.at(u, v), self.crinkle.at(u, v))

    def at(self, x: float, z: float) -> bool:
        return self.field(x, z) > self.threshold

    def grid(self, cells: int) -> list[list[bool]]:
        coast = self.coast.grid(cells)
        crinkle = self.crinkle.grid(cells)
        cell = self.size / cells
        half = self.half
        threshold = self.threshold
        shape = self._shape
        out: list[list[bool]] = []
        for row in range(cells):
            z = (row + 0.5) * cell - half
            coast_row = coast[row]
            crinkle_row = crinkle[row]
            out.append(
                [
                    shape((column + 0.5) * cell - half, z, coast_row[column], crinkle_row[column])
                    > threshold
                    for column in range(cells)
                ]
            )
        return out


def build_layout(package: Package) -> Layout:
    seed = int(package.world.get("seed", 1))
    size = float(package.world.get("size_meters", 64.0))
    clear_radius = float(package.world.get("camp_clear_radius_meters", 6.0))
    half = size / 2.0
    margin = 1.5
    # The islets fade out over the camp clearing and its surround (the same
    # reach the landmass bump has), so the camp stands on the base biome.
    field = BiomeField(package, seed, camp_clear=(0.5, 0.5, clear_radius * 2.5 / size))

    def biome_at(x: float, z: float) -> str:
        return field.biome_at(x, z, size)

    camp = (0.0, 0.0)

    landmass = Landmass(package, seed=seed, size=size, camp=camp, clear_radius=clear_radius)
    shore_margin = landmass.shore_margin
    land_at = landmass.at

    def on_land(x: float, z: float, margin: float) -> bool:
        """Land here and at four points ``margin`` away: a cheap shore distance."""

        if not land_at(x, z):
            return False
        return all(
            land_at(x + dx, z + dz)
            for dx, dz in ((margin, 0.0), (-margin, 0.0), (0.0, margin), (0.0, -margin))
        )

    rand = mulberry32(seed)
    entities: list[Placed] = []
    counts: dict[str, int] = {}
    widest = max(
        [_scatter_radius(package, prop) for prop in package.props]
        + [package.meters(package.mob.shadow_width_units) * 0.5],
    )
    placed_hash = PlacementHash(2.0 * widest + 0.5)
    collides = placed_hash.collides

    def place(
        *,
        kind: str,
        ref_id: str,
        state: str | None,
        x: float,
        z: float,
        footprint: float,
        scatter: float,
        variant_of: Prop | None = None,
    ) -> None:
        index = len(entities)
        prefix = {"prop": "p", "mob": "m"}.get(kind, "e")
        seed = int(rand() * 100000)
        # A prop with variants takes its look from the seed it already
        # publishes, not from another draw: props without variants land
        # exactly where they always did.
        if variant_of is not None and variant_of.variants is not None:
            state = variant_state(variant_of, seed)
        placed = Placed(
            entity_id=f"{prefix}{index:04d}",
            kind=kind,
            ref_id=ref_id,
            state=state,
            x=round(x, 3),
            z=round(z, 3),
            seed=seed,
            footprint_radius_meters=footprint,
            scatter_radius_meters=scatter,
        )
        entities.append(placed)
        placed_hash.add(placed)
        counts[ref_id] = counts.get(ref_id, 0) + 1

    # The camp is authored, not scattered: a tent and a cold firepit inside the
    # clearing, so the player always has one buildable landmark to stand next to.
    camp_props = [
        ("canvas_tent", "pitched", -2.2, -1.4, 1.35),
        ("campfire", "unlit", 1.4, 0.9, 1.0),
    ]
    pads: list[tuple[float, float, float, str]] = []
    for prop_id, state, dx, dz, pad_scale in camp_props:
        try:
            prop = package.prop(prop_id)
        except Exception:  # a scope may omit a prop; the camp degrades quietly
            continue
        if state not in prop.states:
            state = prop.baseline_state
        pads.append((camp[0] + dx, camp[1] + dz, pad_scale, f"p{len(entities):04d}"))
        place(
            kind="prop",
            ref_id=prop_id,
            state=state,
            x=camp[0] + dx,
            z=camp[1] + dz,
            footprint=package.meters(prop.footprint_radius_units),
            scatter=_scatter_radius(package, prop),
        )

    area_hundreds = (size * size) / 100.0
    shares = _family_shares(package)
    for prop in sorted(package.props, key=lambda entry: entry.prop_id):
        if prop.prop_id in CAMP_PROP_IDS:
            continue
        target = _prop_target(package, prop, area_hundreds, shares)
        if target <= 0:
            continue
        scatter = _scatter_radius(package, prop)
        footprint = package.meters(prop.footprint_radius_units)
        state = prop.baseline_state
        accepted = 0
        for _ in range(target * 40):
            if accepted >= target:
                break
            x = (rand() * 2.0 - 1.0) * (half - margin)
            z = (rand() * 2.0 - 1.0) * (half - margin)
            if math.hypot(x - camp[0], z - camp[1]) < clear_radius + scatter:
                continue
            if rand() > _biome_weight(package, prop, biome_at(x, z)):
                continue
            if not on_land(x, z, shore_margin):
                continue
            if collides(x, z, scatter):
                continue
            place(
                kind="prop",
                ref_id=prop.prop_id,
                state=state,
                x=x,
                z=z,
                footprint=footprint,
                scatter=scatter,
                variant_of=prop,
            )
            accepted += 1

    mob = package.mob
    mob_count = int(package.gameplay.get("mob_count", 1))
    mob_scatter = package.meters(mob.shadow_width_units) * 0.5
    placed_mobs = 0
    for _ in range(mob_count * 200):
        if placed_mobs >= mob_count:
            break
        x = (rand() * 2.0 - 1.0) * (half - margin)
        z = (rand() * 2.0 - 1.0) * (half - margin)
        if math.hypot(x - camp[0], z - camp[1]) < clear_radius + 4.0:
            continue
        if not on_land(x, z, shore_margin):
            continue
        if collides(x, z, mob_scatter):
            continue
        place(
            kind="mob",
            ref_id=mob.actor_id,
            state=None,
            x=x,
            z=z,
            footprint=package.meters(mob.footprint_radius_units),
            scatter=mob_scatter,
        )
        placed_mobs += 1

    decals = (
        _pad_decals(package, rand, pads=pads)
        + _skirt_decals(package, rand, entities=entities)
        + _wet_decals(
            package,
            rand,
            half=half,
            camp=camp,
            clear_radius=clear_radius,
            on_land=on_land,
            shore_margin=shore_margin,
            collides=collides,
        )
    )
    road_points = _road_polyline(
        package, rand, camp=camp, half=half, clear_radius=clear_radius, on_land=on_land
    )
    road_width = package.road.width_meters if package.road is not None else 0.0
    clutter = _scatter_pieces(
        package,
        rand,
        package.clutter,
        biome_at=biome_at,
        half=half,
        road_points=road_points,
        road_width=road_width,
        entities=entities,
        pads=pads,
        on_land=on_land,
    )
    # The forage keeps out of the camp clearing too: the spawn is a clean
    # floor, and the first twig is a few steps away, not underfoot.
    forage = _scatter_pieces(
        package,
        rand,
        package.forage,
        biome_at=biome_at,
        half=half,
        road_points=road_points,
        road_width=road_width,
        entities=entities,
        pads=pads,
        on_land=on_land,
        keep_out_circle=(camp[0], camp[1], clear_radius),
    )
    # The plants keep out of the clearing too, and off the road like the rest.
    plants = _scatter_pieces(
        package,
        rand,
        package.plants,
        biome_at=biome_at,
        half=half,
        road_points=road_points,
        road_width=road_width,
        entities=entities,
        pads=pads,
        on_land=on_land,
        keep_out_circle=(camp[0], camp[1], clear_radius),
    )
    cells = splat_cells(size)
    splat = _render_splat(
        package,
        size=size,
        entities=entities,
        road_points=road_points,
        road_width=road_width,
        land_rows=landmass.grid(cells),
    )
    biome_splat = _render_biome_splat(field, size=size)
    return Layout(
        seed=seed,
        size_meters=size,
        player_spawn=(0.0, 2.4),
        camp_position=camp,
        clear_radius_meters=clear_radius,
        entities=tuple(entities),
        decals=tuple(decals),
        road_id=package.road.road_id if package.road is not None and road_points else None,
        road_width_meters=road_width,
        road=tuple(road_points),
        clutter=tuple(clutter),
        forage=tuple(forage),
        plants=tuple(plants),
        land_share=landmass.solved_share,
        splat_png=splat,
        biome_splat_png=biome_splat,
        biome_shares=dict(field.shares),
        counts=counts,
    )


def _pad_decals(
    package: Package, rand: Rand, *, pads: list[tuple[float, float, float, str]]
) -> list[GroundDecal]:
    """A worn pad under each camp structure, the reference genre's base disc.

    The stamped path this replaced only ever read as a chain of stains; a pad
    under a thing that stands still reads as the thing having been there.
    """

    decal_id = package.world.get("pad_decal")
    if not decal_id or not any(
        decal.decal_id == decal_id and decal.use == "pad" for decal in package.decals
    ):
        return []
    # ``under`` names the structure the pad belongs to, so a viewer that has
    # no card for it draws no pad either: a pad alone reads as a stain.
    return [
        {
            "decal": decal_id,
            "under": entity_id,
            "x": round(x, 3),
            "z": round(z, 3),
            "rotation_degrees": _ground_piece_jitter(package, rand),
            "scale": round(scale, 3),
        }
        for x, z, scale, entity_id in pads
    ]


def _skirt_decals(package: Package, rand: Rand, *, entities: list[Placed]) -> list[GroundDecal]:
    """The seam, painted by the pipeline: one skirt under every prop of a family.

    Only when the package has chosen ``ground_contact = "skirt_decal"``; the
    choice is the author's, and this function never takes it for them.
    """

    if package.ground_contact != "skirt_decal":
        return []
    by_family = {
        family: decal
        for decal in package.decals
        if decal.use == "skirt"
        for family in decal.families
    }
    out: list[GroundDecal] = []
    for entity in entities:
        if entity.kind != "prop":
            continue
        prop = package.prop(entity.ref_id)
        decal = by_family.get(prop.family)
        if decal is None:
            continue
        laid = package.meters(prop.shadow_width_units) * decal.scale
        out.append(
            {
                "decal": decal.decal_id,
                "under": entity.entity_id,
                "x": entity.x,
                "z": entity.z,
                "rotation_degrees": _ground_piece_jitter(package, rand),
                "scale": round(laid / decal.width_meters, 3),
            }
        )
    return out


def _wet_decals(
    package: Package,
    rand: Rand,
    *,
    half: float,
    camp: tuple[float, float],
    clear_radius: float,
    on_land: LandTest,
    shore_margin: float,
    collides: CollisionTest,
) -> list[GroundDecal]:
    """Standing water for a weather condition, scattered once at world generation.

    A puddle is a decal that is only ever *seen* under rain: the runtime fades
    it with wetness, so a dry world shows none and a wet one shows the same
    hollows every time. Placed off the camp clearing, off the shore and clear
    of every prop's scatter radius, so no puddle sits under a trunk. Each
    entry names its condition, which is how the viewer knows what drives it.
    """

    out: list[GroundDecal] = []
    area_hundreds = ((half * 2.0) ** 2) / 100.0
    for condition in package.weather:
        wet = condition.wet
        if wet is None:
            continue
        decal = next((d for d in package.decals if d.decal_id == wet.decal_id), None)
        if decal is None:
            continue
        target = round(wet.per_100_sqm * area_hundreds)
        reach = max(decal.width_meters, decal.height_meters) * 0.6
        accepted = 0
        for _ in range(target * 30):
            if accepted >= target:
                break
            x = (rand() * 2.0 - 1.0) * (half - 1.5)
            z = (rand() * 2.0 - 1.0) * (half - 1.5)
            if math.hypot(x - camp[0], z - camp[1]) < clear_radius + reach:
                continue
            if not on_land(x, z, shore_margin):
                continue
            if collides(x, z, reach):
                continue
            out.append(
                {
                    "decal": decal.decal_id,
                    "condition": condition.condition_id,
                    "x": round(x, 3),
                    "z": round(z, 3),
                    "rotation_degrees": _ground_piece_jitter(package, rand),
                    "scale": round(0.8 + rand() * 0.6, 3),
                }
            )
            accepted += 1
    return out


def _segment_distance(px: float, pz: float, ax: float, az: float, bx: float, bz: float) -> float:
    dx = bx - ax
    dz = bz - az
    length_sq = dx * dx + dz * dz
    t = (
        0.0
        if length_sq <= 1e-9
        else max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / length_sq))
    )
    return math.hypot(px - (ax + dx * t), pz - (az + dz * t))


def polyline_distance(x: float, z: float, points: Sequence[tuple[float, float]]) -> float:
    if not points:
        return math.inf
    if len(points) == 1:
        return math.hypot(x - points[0][0], z - points[0][1])
    return min(
        _segment_distance(x, z, points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
        for i in range(len(points) - 1)
    )


def _road_polyline(
    package: Package,
    rand: Rand,
    *,
    camp: tuple[float, float],
    half: float,
    clear_radius: float,
    on_land: LandTest,
) -> list[tuple[float, float]]:
    """One wandering track out of the camp. It ends where the land does.

    It starts at the edge of the clearing, not at its centre, and it is pulled
    back toward its outbound heading so it wanders without doubling back. The
    road is a polyline here and a green mask in the splat; the shader tears its
    edge. Where a plank road would need a ribbon mesh with its texture aligned
    to travel, a dirt track does not, which is why v0 has a dirt track.
    """

    road = package.road
    if road is None:
        return []
    step = 1.5
    heading = rand() * math.tau
    outbound = heading
    x = camp[0] + math.cos(heading) * clear_radius * 0.75
    z = camp[1] + math.sin(heading) * clear_radius * 0.75
    points = [(round(x, 3), round(z, 3))]
    travelled = 0.0
    while travelled < road.length_meters:
        heading += (rand() - 0.5) * 0.5 + (outbound - heading) * 0.12
        x += math.cos(heading) * step
        z += math.sin(heading) * step
        if abs(x) > half - 3.0 or abs(z) > half - 3.0 or not on_land(x, z, 1.0):
            break
        points.append((round(x, 3), round(z, 3)))
        travelled += step
    return points


def _scatter_pieces(
    package: Package,
    rand: Rand,
    clutter: Clutter | Forage | Plants | None,
    *,
    biome_at: BiomeLookup,
    half: float,
    road_points: list[tuple[float, float]],
    road_width: float,
    entities: list[Placed],
    pads: list[tuple[float, float, float, str]],
    on_land: LandTest,
    keep_out_circle: tuple[float, float, float] | None = None,
) -> list[GroundPiece]:
    """Scatter a piece sheet's cells (the litter, the forage) flat on the
    ground at true size.

    Pieces keep off the road and off the camp pads, and out of prop
    footprints; they may sit under a bush, because litter does. The forage
    also keeps out of ``keep_out_circle``, the camp clearing.
    """

    if clutter is None or not clutter.density:
        return []
    top = max(clutter.density.values())
    if top <= 0.0:
        return []
    size = half * 2.0
    target = round(top * (size * size) / 100.0)
    keep_out = road_width / 2.0 + 0.25
    bucket_meters = 4.0
    buckets: dict[tuple[int, int], list[Placed]] = {}
    for entity in entities:
        if entity.kind != "prop":
            continue
        key = (int(entity.x // bucket_meters), int(entity.z // bucket_meters))
        buckets.setdefault(key, []).append(entity)

    def in_footprint(x: float, z: float) -> bool:
        cx = int(x // bucket_meters)
        cz = int(z // bucket_meters)
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for entity in buckets.get((cx + dx, cz + dz), ()):
                    if math.hypot(x - entity.x, z - entity.z) < entity.footprint_radius_meters:
                        return True
        return False

    out: list[GroundPiece] = []
    for _ in range(target * 12):
        if len(out) >= target:
            break
        x = (rand() * 2.0 - 1.0) * (half - 1.0)
        z = (rand() * 2.0 - 1.0) * (half - 1.0)
        weight = clutter.density.get(biome_at(x, z), 0.0) / top
        if rand() > weight:
            continue
        if not on_land(x, z, 0.6):
            continue
        if road_points and polyline_distance(x, z, road_points) < keep_out:
            continue
        if any(math.hypot(x - px, z - pz) < 1.4 * scale for px, pz, scale, _ in pads):
            continue
        if (
            keep_out_circle is not None
            and math.hypot(x - keep_out_circle[0], z - keep_out_circle[1]) < keep_out_circle[2]
        ):
            continue
        if in_footprint(x, z):
            continue
        allowed = clutter.cells_for(biome_at(x, z))
        if not allowed:
            continue
        # A piece carries its contact along its lower edge, so it is never
        # spun, and it is never mirrored either: jittered a little, no more.
        out.append(
            {
                "cell": allowed[int(rand() * len(allowed)) % len(allowed)],
                "x": round(x, 3),
                "z": round(z, 3),
                "rotation_degrees": _ground_piece_jitter(package, rand),
                "scale": round(0.8 + rand() * 0.35, 3),
            }
        )
    return out


def _render_splat(
    package: Package,
    *,
    size: float,
    entities: list[Placed],
    road_points: list[tuple[float, float]] | None = None,
    road_width: float = 0.0,
    land_rows: list[list[bool]] | None = None,
) -> bytes:
    """R is the road, G is under-canopy darkening, B is reserved, A is land.

    The biomes live on their own plate (`_render_biome_splat`); this one holds
    the world's structure. Row 0 is minimum z. The viewer loads this with
    ``flipY = false`` and samples it as data, never as colour, so it carries no
    colour space. ``land_rows`` is the landmass sampled on this plate's grid;
    absent, everything is land.
    """

    cells = splat_cells(size)
    half = size / 2.0

    # A soft disc of shade under anything with a canopy, painted at splat
    # resolution so the shader gets it for free with the biome sample.
    shade: list[list[float]] = [[0.0] * cells for _ in range(cells)]
    canopy = {
        entity.ref_id: package.prop(entity.ref_id) for entity in entities if entity.kind == "prop"
    }
    for entity in entities:
        prop = canopy.get(entity.ref_id)
        if prop is None or prop.family != "tree" or entity.state != "standing":
            continue
        radius = package.meters(prop.shadow_width_units) * 1.6
        cx = (entity.x + half) / size * cells
        cz = (entity.z + half) / size * cells
        cell_radius = radius / size * cells
        lo_x, hi_x = int(cx - cell_radius) - 1, int(cx + cell_radius) + 2
        lo_z, hi_z = int(cz - cell_radius) - 1, int(cz + cell_radius) + 2
        for row in range(max(0, lo_z), min(cells, hi_z)):
            for column in range(max(0, lo_x), min(cells, hi_x)):
                distance = math.hypot(column + 0.5 - cx, row + 0.5 - cz)
                if distance >= cell_radius or cell_radius <= 0:
                    continue
                falloff = 1.0 - (distance / cell_radius)
                shade[row][column] = min(0.62, shade[row][column] + falloff * falloff * 0.30)

    # Filled as bytes, not pixel by pixel: a 1024-cell plate is a million
    # writes, and PIL's per-pixel setter is the slow way to make them.
    raw = bytearray(cells * cells * 4)
    for row in range(cells):
        land_row = land_rows[row] if land_rows is not None else None
        shade_row = shade[row]
        base = row * cells * 4
        for column in range(cells):
            offset = base + column * 4
            raw[offset + 1] = round(shade_row[column] * 255)
            raw[offset + 3] = 255 if land_row is None or land_row[column] else 0
    image = Image.frombytes("RGBA", (cells, cells), bytes(raw))
    pixels = image.load()
    assert pixels is not None

    # The road, hard-edged like the biome mask, one segment's bounding box at a
    # time. The shader erodes it with a finer grain than it uses for biomes.
    if road_points and road_width > 0.0 and len(road_points) >= 2:
        reach = road_width / 2.0
        cell_meters = size / cells
        for index in range(len(road_points) - 1):
            ax, az = road_points[index]
            bx, bz = road_points[index + 1]
            lo_x = int((min(ax, bx) - reach + half) / cell_meters) - 1
            hi_x = int((max(ax, bx) + reach + half) / cell_meters) + 2
            lo_z = int((min(az, bz) - reach + half) / cell_meters) - 1
            hi_z = int((max(az, bz) + reach + half) / cell_meters) + 2
            for row in range(max(0, lo_z), min(cells, hi_z)):
                z = (row + 0.5) * cell_meters - half
                for column in range(max(0, lo_x), min(cells, hi_x)):
                    x = (column + 0.5) * cell_meters - half
                    if _segment_distance(x, z, ax, az, bx, bz) <= reach:
                        _r, g, b, a = cast("tuple[int, int, int, int]", pixels[column, row])
                        pixels[column, row] = (255, g, b, a)

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _render_biome_splat(field: BiomeField, *, size: float) -> bytes:
    """R, G, B are the non-base biomes in declaration order; the base is the rest.

    A hard mask, like the world splat: the shader erodes each channel with
    noise and feathers it, and feathering twice would only blur the boundary
    the noise is meant to break up. Alpha is opaque everywhere: it is not a
    channel, because an image's colour is premultiplied by its alpha on decode.
    """

    cells = splat_cells(size)
    raw = bytearray(cells * cells * 4)
    for row, line in enumerate(field.index_grid(cells)):
        base = row * cells * 4
        for column, index in enumerate(line):
            offset = base + column * 4
            if index >= 0:
                raw[offset + index] = 255
            raw[offset + 3] = 255
    image = Image.frombytes("RGBA", (cells, cells), bytes(raw))
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def variant_state(prop: Prop, seed: int) -> str:
    """Which of a prop's variant looks a placed instance takes, from its own seed.

    Pure: the same seed always gives the same look, the weights are honoured in
    proportion, and no random stream is consumed, so a variant edit moves a
    prop's looks and nothing else in the world.
    """

    if prop.variants is None:
        return prop.baseline_state
    total = sum(prop.variants.weights)
    point = ((seed % 100000) / 100000.0) * total
    running = 0.0
    for state, weight in zip(prop.variants.states, prop.variants.weights, strict=True):
        running += weight
        if point < running:
            return state
    return prop.variants.states[-1]


def check_layout(package: Package, layout: Layout) -> list[str]:
    """Refusals, not warnings. Every one of these means the world is unusable."""

    problems: list[str] = []
    for entity in layout.entities:
        if entity.kind == "prop" and entity.state is not None:
            try:
                declared = package.prop(entity.ref_id).states
            except Exception:
                continue
            if entity.state not in declared:
                problems.append(f"{entity.entity_id} stands as undeclared look {entity.state!r}")
    half = layout.size_meters / 2.0
    entities = layout.entities
    for index, first in enumerate(entities):
        if abs(first.x) > half or abs(first.z) > half:
            problems.append(f"{first.entity_id} lies outside the world square")
        for second in entities[index + 1 :]:
            reach = first.scatter_radius_meters + second.scatter_radius_meters
            distance = math.hypot(first.x - second.x, first.z - second.z)
            if distance < reach - 1e-6:
                problems.append(
                    f"{first.entity_id} and {second.entity_id} overlap: "
                    f"{distance:.3f} < {reach:.3f}"
                )
                break
    camp_x, camp_z = layout.camp_position
    for entity in entities:
        inside = math.hypot(entity.x - camp_x, entity.z - camp_z) < layout.clear_radius_meters
        camp_prop = entity.kind == "prop" and entity.ref_id in CAMP_PROP_IDS
        if inside and not camp_prop:
            problems.append(f"{entity.entity_id} stands inside the camp clearing")
    spawn_distance = math.hypot(layout.player_spawn[0] - camp_x, layout.player_spawn[1] - camp_z)
    if spawn_distance > layout.clear_radius_meters:
        problems.append("the player spawns outside the camp clearing")
    area_hundreds = (layout.size_meters**2) / 100.0
    shares = _family_shares(package)
    for prop in package.props:
        ceiling = _prop_target(package, prop, area_hundreds, shares)
        if ceiling <= 0:
            continue
        if layout.counts.get(prop.prop_id, 0) > ceiling:
            problems.append(
                f"{prop.prop_id} exceeds its density ceiling: "
                f"{layout.counts[prop.prop_id]} > {ceiling}"
            )
    return problems
