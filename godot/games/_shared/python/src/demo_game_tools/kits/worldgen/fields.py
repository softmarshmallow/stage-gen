"""The scalar layer: noise, regions, the coast, distances, height, intensity.

Everything a placement rule can read lives here as a field over the world
square, and every field is deterministic in the seed. Regions are integers
(-1 is the base region, 0.. are the others in declaration order); what a
region *is* -- a forest floor, a bog -- is the caller's vocabulary and never
appears in this package.

Two resolutions. The **plate** grid is the one the masks are rasterised at
(1024 cells for a 256 m or a 512 m world), and point queries about land and
region read it directly so a placed thing and the drawn mask never disagree.
The **analysis** grid (256 cells) carries the distance and height fields and
the per-object support scans; those are smooth, so 2 m cells are enough.

Memory is streamed where it matters: a noise field is produced row by row and
the region rows zip the octaves as they go, so a million-cell plate never
holds six float grids at once.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Final

from .spec import HabitatSpec

#: Value-noise lattice resolution for the region continents. Small enough that
#: regions are continents, not speckle.
REGION_LATTICE: Final = 8
#: Rounds of threshold adjustment when solving the region shares.
SHARE_SOLVE_ROUNDS: Final = 16
#: Samples per axis when solving a threshold to a share.
SOLVE_SAMPLES: Final = 48
#: Cells per axis of the analysis grid.
ANALYSIS_CELLS: Final = 256
#: The slack on the measured peak intensity: the grid can miss the true
#: supremum, and an acceptance ratio above one would under-populate a band.
PEAK_SLACK: Final = 1.10
#: Points sampled around a circle when a clearing is tested for land.
CLEARING_SAMPLES: Final = 12

_INF: Final = float("inf")


def smoothstep(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


@dataclass(frozen=True, slots=True)
class GridSpec:
    """A square grid of ``cells`` x ``cells`` over a world ``size_meters`` across, centred."""

    size_meters: float
    cells: int

    @property
    def cell_meters(self) -> float:
        return self.size_meters / self.cells

    @property
    def half(self) -> float:
        return self.size_meters / 2.0

    def centre(self, i: int, j: int) -> tuple[float, float]:
        cell = self.cell_meters
        return (i + 0.5) * cell - self.half, (j + 0.5) * cell - self.half

    def index(self, x: float, z: float) -> tuple[int, int]:
        cell = self.cell_meters
        i = int((x + self.half) / cell)
        j = int((z + self.half) / cell)
        last = self.cells - 1
        return min(last, max(0, i)), min(last, max(0, j))


class ValueNoise:
    """Tileable bilinear value noise on a small lattice. Pure Python, no numpy.

    ``at`` answers one point; ``rows`` streams the field at every cell centre
    of a plate with the row's vertical blend hoisted out of the inner loop.
    """

    def __init__(self, seed: int, lattice: int) -> None:
        from .hashing import Stream

        stream = Stream.of(seed, "value_noise")
        self.lattice = lattice
        self.values = [
            [stream.unit(row, column) for column in range(lattice)] for row in range(lattice)
        ]

    def at(self, u: float, v: float) -> float:
        """``u`` and ``v`` are in [0, 1) over the world; the field wraps."""

        n = self.lattice
        x = (u % 1.0) * n
        y = (v % 1.0) * n
        x0, y0 = math.floor(x), math.floor(y)
        fx, fy = smoothstep(x - x0), smoothstep(y - y0)
        x0 %= n
        y0 %= n
        x1, y1 = (x0 + 1) % n, (y0 + 1) % n
        top: float = self.values[y0][x0] * (1.0 - fx) + self.values[y0][x1] * fx
        bottom: float = self.values[y1][x0] * (1.0 - fx) + self.values[y1][x1] * fx
        return top * (1.0 - fy) + bottom * fy

    def rows(self, cells: int) -> Iterator[list[float]]:
        n = self.lattice
        columns: list[tuple[int, int, float]] = []
        for column in range(cells):
            x = ((column + 0.5) / cells % 1.0) * n
            x0 = math.floor(x)
            columns.append((x0 % n, (x0 + 1) % n, smoothstep(x - x0)))
        for row in range(cells):
            y = ((row + 0.5) / cells % 1.0) * n
            y0 = math.floor(y)
            fy = smoothstep(y - y0)
            above = self.values[y0 % n]
            below = self.values[(y0 + 1) % n]
            line = [above[i] * (1.0 - fy) + below[i] * fy for i in range(n)]
            yield [line[x0] * (1.0 - fx) + line[x1] * fx for x0, x1, fx in columns]

    def grid(self, cells: int) -> list[list[float]]:
        return list(self.rows(cells))


def solve_threshold(samples: Sequence[float], share: float) -> float:
    """The level above which a ``share`` of the samples lie."""

    ordered = sorted(samples)
    return ordered[int((1.0 - share) * (len(ordered) - 1))]


class ScalarGrid:
    """A float per cell, read bilinearly between cell centres."""

    def __init__(self, spec: GridSpec, rows: list[list[float]]) -> None:
        self.spec = spec
        self.rows = rows

    def cell(self, i: int, j: int) -> float:
        return self.rows[j][i]

    def at(self, x: float, z: float) -> float:
        spec = self.spec
        cell = spec.cell_meters
        fx = (x + spec.half) / cell - 0.5
        fz = (z + spec.half) / cell - 0.5
        last = spec.cells - 1
        i0 = min(last, max(0, math.floor(fx)))
        j0 = min(last, max(0, math.floor(fz)))
        i1 = min(last, i0 + 1)
        j1 = min(last, j0 + 1)
        tx = min(1.0, max(0.0, fx - i0))
        tz = min(1.0, max(0.0, fz - j0))
        rows = self.rows
        top = rows[j0][i0] * (1.0 - tx) + rows[j0][i1] * tx
        bottom = rows[j1][i0] * (1.0 - tx) + rows[j1][i1] * tx
        return top * (1.0 - tz) + bottom * tz


class IndexGrid:
    """An int per cell, read at the nearest cell. Regions, or land as 0 / -1."""

    def __init__(self, spec: GridSpec, rows: list[list[int]]) -> None:
        self.spec = spec
        self.rows = rows

    def at(self, x: float, z: float) -> int:
        i, j = self.spec.index(x, z)
        return self.rows[j][i]

    def share(self, value: int) -> float:
        total = self.spec.cells * self.spec.cells
        return sum(row.count(value) for row in self.rows) / total


class RegionField:
    """One value-noise field per non-base region, each thresholded to its share.

    Where two fields both clear their thresholds the one further above its own
    wins, so every boundary is a wobbly curve between two continents rather
    than a band of the base. A second, finer octave per region adds islets:
    patches a few metres across inside the others, taking ``islet_share`` of
    the region's share. Both thresholds are solved together on a sampled grid,
    so the authored shares hold whatever the lattices produce. ``clear``
    fades every region out around a unit-square point, so the set piece the
    player spawns on stands on the base region by rule, not by luck.
    """

    def __init__(
        self,
        *,
        seed: int,
        shares: Sequence[float],
        lattice: int = REGION_LATTICE,
        islet_lattice: int = 0,
        islet_share: float = 0.0,
        clear: tuple[float, float, float] | None = None,
    ) -> None:
        self.shares_authored = tuple(shares)
        self.clear = clear
        self.fields = [
            ValueNoise(seed * 7919 + 13 + 1009 * index, lattice) for index in range(len(shares))
        ]
        self.islet_share = islet_share if islet_lattice > 0 and islet_share > 0.0 else 0.0
        self.islets = (
            [
                ValueNoise(seed * 6007 + 29 + 1013 * index, islet_lattice)
                for index in range(len(shares))
            ]
            if self.islet_share > 0.0
            else []
        )
        grid = [
            (i / SOLVE_SAMPLES, j / SOLVE_SAMPLES)
            for i in range(SOLVE_SAMPLES)
            for j in range(SOLVE_SAMPLES)
        ]
        self.thresholds = [0.0] * len(shares)
        self.islet_thresholds = [0.0] * len(shares)
        for index, (share, field) in enumerate(zip(shares, self.fields, strict=True)):
            samples = [field.at(u, v) for u, v in grid]
            continent = share * (1.0 - self.islet_share)
            self.thresholds[index] = solve_threshold(samples, continent)
            if self.islets:
                fine = [self.islets[index].at(u, v) for u, v in grid]
                self.islet_thresholds[index] = solve_threshold(fine, share * self.islet_share)
        for _ in range(SHARE_SOLVE_ROUNDS):
            counts = [0] * len(shares)
            for u, v in grid:
                index = self.index_at_unit(u, v)
                if index >= 0:
                    counts[index] += 1
            for index, share in enumerate(shares):
                actual = counts[index] / len(grid)
                # Field units and share units are both [0, 1]; a half-step
                # converges without overshooting on these lattices.
                self.thresholds[index] += (actual - share) * 0.5
                self.islet_thresholds[index] += (actual - share) * 0.5
        counts = [0] * len(shares)
        for u, v in grid:
            index = self.index_at_unit(u, v)
            if index >= 0:
                counts[index] += 1
        self.shares: dict[int, float] = {
            index: counts[index] / len(grid) for index in range(len(shares))
        }
        self.shares[-1] = 1.0 - sum(self.shares.values())

    def _clear_gain(self, u: float, v: float) -> float:
        if self.clear is None:
            return 1.0
        cu, cv, radius = self.clear
        if radius <= 0.0:
            return 1.0
        return smoothstep((math.hypot(u - cu, v - cv) - radius) / (radius * 0.6))

    def index_at_unit(self, u: float, v: float) -> int:
        best, excess = -1, 0.0
        gain = self._clear_gain(u, v)
        for index, field in enumerate(self.fields):
            margin = (field.at(u, v) - self.thresholds[index]) * gain
            if self.islets:
                margin = max(
                    margin, (self.islets[index].at(u, v) - self.islet_thresholds[index]) * gain
                )
            if margin > excess:
                best, excess = index, margin
        return best

    def index_rows(self, cells: int) -> Iterator[list[int]]:
        """The region at every cell centre of a plate, one row at a time."""

        streams = [field.rows(cells) for field in self.fields]
        fine_streams = [islet.rows(cells) for islet in self.islets]
        thresholds = self.thresholds
        fine_thresholds = self.islet_thresholds
        for row in range(cells):
            lines = [next(stream) for stream in streams]
            fine_lines = [next(stream) for stream in fine_streams]
            v = (row + 0.5) / cells
            out: list[int] = []
            for column in range(cells):
                best, excess = -1, 0.0
                gain = self._clear_gain((column + 0.5) / cells, v)
                for index, values in enumerate(lines):
                    margin = (values[column] - thresholds[index]) * gain
                    if fine_lines:
                        margin = max(
                            margin, (fine_lines[index][column] - fine_thresholds[index]) * gain
                        )
                    if margin > excess:
                        best, excess = index, margin
                out.append(best)
            yield out


@dataclass(frozen=True, slots=True)
class Bump:
    """A raised patch of the coast field: land is guaranteed around a point."""

    x: float
    z: float
    radius_meters: float
    strength: float


class Coast:
    """The land: noise plus a radial falloff, solved to the authored share.

    A bump keeps a set piece on land whatever the noise says, and a water ring
    inside the square means the player never sees the square's edge. ``field``
    includes the bumps and decides land; ``relief`` omits them, so a height
    read off it does not make the spawn the summit.
    """

    def __init__(
        self,
        *,
        seed: int,
        size_meters: float,
        land_share: float,
        lattice: int,
        crinkle_weight: float,
        bumps: Sequence[Bump] = (),
    ) -> None:
        self.size = size_meters
        self.half = size_meters / 2.0
        self.land_share = land_share
        self.bumps = tuple(bumps)
        self.coast = ValueNoise(seed * 104729 + 7, lattice)
        # A second octave crinkles the coast at a few metres, the hand-torn
        # look of the reference; the shader tears it again below a metre.
        self.crinkle = ValueNoise(seed * 7 + 3, lattice * 4)
        self.crinkle_weight = crinkle_weight
        n = 96
        samples = [
            self.field(
                (i + 0.5) / n * size_meters - self.half, (j + 0.5) / n * size_meters - self.half
            )
            for i in range(n)
            for j in range(n)
        ]
        self.threshold = solve_threshold(samples, land_share)
        self.solved_share = sum(1 for value in samples if value > self.threshold) / len(samples)

    def _relief(self, x: float, z: float, coast: float, crinkle: float) -> float:
        if max(abs(x), abs(z)) / self.half > 0.94:
            return -10.0
        radial = math.hypot(x, z) / self.half
        return coast * 0.55 + (crinkle - 0.5) * self.crinkle_weight + (1.0 - radial * radial) * 0.9

    def _bumps(self, x: float, z: float) -> float:
        total = 0.0
        for bump in self.bumps:
            total += (
                max(0.0, 1.0 - math.hypot(x - bump.x, z - bump.z) / bump.radius_meters)
                * bump.strength
            )
        return total

    def relief(self, x: float, z: float) -> float:
        u = (x + self.half) / self.size
        v = (z + self.half) / self.size
        return self._relief(x, z, self.coast.at(u, v), self.crinkle.at(u, v))

    def field(self, x: float, z: float) -> float:
        return self.relief(x, z) + self._bumps(x, z)

    def at(self, x: float, z: float) -> bool:
        return self.field(x, z) > self.threshold

    def rows(self, cells: int) -> Iterator[list[bool]]:
        coast = self.coast.rows(cells)
        crinkle = self.crinkle.rows(cells)
        cell = self.size / cells
        half = self.half
        threshold = self.threshold
        for row in range(cells):
            z = (row + 0.5) * cell - half
            coast_row = next(coast)
            crinkle_row = next(crinkle)
            yield [
                self._relief(
                    (column + 0.5) * cell - half, z, coast_row[column], crinkle_row[column]
                )
                + self._bumps((column + 0.5) * cell - half, z)
                > threshold
                for column in range(cells)
            ]


def chamfer_distance(spec: GridSpec, is_seed: Callable[[int, int], bool]) -> ScalarGrid:
    """Distance in metres from every cell to the nearest seed cell (3-4 chamfer, two passes)."""

    n = spec.cells
    rows = [[0.0 if is_seed(i, j) else _INF for i in range(n)] for j in range(n)]
    for j in range(n):
        row = rows[j]
        above = rows[j - 1] if j > 0 else None
        for i in range(n):
            best = row[i]
            if i > 0 and row[i - 1] + 3.0 < best:
                best = row[i - 1] + 3.0
            if above is not None:
                if above[i] + 3.0 < best:
                    best = above[i] + 3.0
                if i > 0 and above[i - 1] + 4.0 < best:
                    best = above[i - 1] + 4.0
                if i < n - 1 and above[i + 1] + 4.0 < best:
                    best = above[i + 1] + 4.0
            row[i] = best
    for j in range(n - 1, -1, -1):
        row = rows[j]
        below = rows[j + 1] if j < n - 1 else None
        for i in range(n - 1, -1, -1):
            best = row[i]
            if i < n - 1 and row[i + 1] + 3.0 < best:
                best = row[i + 1] + 3.0
            if below is not None:
                if below[i] + 3.0 < best:
                    best = below[i] + 3.0
                if i < n - 1 and below[i + 1] + 4.0 < best:
                    best = below[i + 1] + 4.0
                if i > 0 and below[i - 1] + 4.0 < best:
                    best = below[i - 1] + 4.0
            row[i] = best
    scale = spec.cell_meters / 3.0
    limit = spec.size_meters * 2.0
    return ScalarGrid(
        spec,
        [[min(limit, value * scale) if value != _INF else limit for value in row] for row in rows],
    )


def patch_chord_meters(spec: GridSpec, inside: Callable[[int, int], bool]) -> float:
    """Twice the mean distance from an inside cell to the outside: the mean chord of the patches."""

    distance = chamfer_distance(spec, lambda i, j: not inside(i, j))
    total, count = 0.0, 0
    for j in range(spec.cells):
        row = distance.rows[j]
        for i in range(spec.cells):
            if inside(i, j):
                total += row[i]
                count += 1
    return 0.0 if count == 0 else 2.0 * total / count


def band(distance: float, *, peak_meters: float, falloff_meters: float, outside: float) -> float:
    """1 within ``peak_meters``, ``outside`` beyond the falloff, a smooth step between."""

    if distance <= peak_meters:
        return 1.0
    if falloff_meters <= 0.0 or distance >= peak_meters + falloff_meters:
        return outside
    t = smoothstep((distance - peak_meters) / falloff_meters)
    return 1.0 + (outside - 1.0) * t


def trapezoid(value: float, *, low: float, high: float, falloff: float) -> float:
    """1 inside [low, high], 0 beyond the falloff on either side, linear between."""

    if low <= value <= high:
        return 1.0
    if falloff <= 0.0:
        return 0.0
    if value < low:
        return max(0.0, 1.0 - (low - value) / falloff)
    return max(0.0, 1.0 - (value - high) / falloff)


@dataclass(frozen=True, slots=True)
class Clearing:
    x: float
    z: float
    radius_meters: float


class WorldFields:
    """Every field a placement rule may read, and the intensity that combines them.

    Built once per world from the plate-resolution land and region grids, the
    analysis-resolution height and distance grids, and the shore margin. Then
    the caller adds clearings (set pieces) and polyline distances (a road) as
    the world takes shape; intensities read the state at the time they are
    evaluated, which is why the population is placed in a fixed order.
    """

    def __init__(
        self,
        *,
        plate: GridSpec,
        analysis: GridSpec,
        land: IndexGrid,
        regions: IndexGrid,
        height: ScalarGrid,
        shore_margin_meters: float,
    ) -> None:
        if land.spec != plate or regions.spec != plate:
            raise ValueError("land and regions must be plate-resolution grids")
        if height.spec != analysis:
            raise ValueError("height must be an analysis-resolution grid")
        self.plate = plate
        self.analysis = analysis
        self.land = land
        self.regions = regions
        self.height = height
        self.shore_margin_meters = shore_margin_meters
        self.distances: dict[str, ScalarGrid] = {}
        self.clearings: list[Clearing] = []
        self._scan_cache: dict[tuple[HabitatSpec, int], list[float]] = {}
        self._state = 0
        self.add_distance("water", lambda i, j: land.at(*analysis.centre(i, j)) < 0)
        region_rows = regions.rows
        cells = plate.cells

        def region_edge(i: int, j: int) -> bool:
            # The analysis cell is an edge if the plate cell under its centre
            # differs from any of its four plate neighbours a cell away.
            x, z = analysis.centre(i, j)
            pi, pj = plate.index(x, z)
            own = region_rows[pj][pi]
            step = max(1, round(analysis.cell_meters / plate.cell_meters / 2))
            for di, dj in ((step, 0), (-step, 0), (0, step), (0, -step)):
                ni, nj = pi + di, pj + dj
                if 0 <= ni < cells and 0 <= nj < cells and region_rows[nj][ni] != own:
                    return True
            return False

        self.add_distance("region_edge", region_edge)

    @classmethod
    def build(
        cls,
        *,
        size_meters: float,
        plate_cells: int,
        regions: RegionField,
        coast: Coast,
        height_octave: ValueNoise | None,
        height_octave_weight: float,
        shore_margin_meters: float,
        analysis_cells: int = ANALYSIS_CELLS,
    ) -> WorldFields:
        plate = GridSpec(size_meters, plate_cells)
        analysis = GridSpec(size_meters, analysis_cells)
        land_rows = [[0 if flag else -1 for flag in row] for row in coast.rows(plate_cells)]
        region_rows = list(regions.index_rows(plate_cells))
        # The height: the coast's relief (no bumps) with the solved threshold
        # at zero and the 99th percentile of the land at one, plus one finer
        # octave so a band is not just "distance from the coast".
        relief: list[list[float]] = []
        octave_rows = height_octave.rows(analysis_cells) if height_octave is not None else None
        for j in range(analysis_cells):
            octave = next(octave_rows) if octave_rows is not None else None
            row: list[float] = []
            for i in range(analysis_cells):
                x, z = analysis.centre(i, j)
                value = coast.relief(x, z) - coast.threshold
                if octave is not None:
                    value += (octave[i] - 0.5) * height_octave_weight
                row.append(value)
            relief.append(row)
        on_land: list[float] = []
        for j in range(analysis_cells):
            for i in range(analysis_cells):
                pi, pj = plate.index(*analysis.centre(i, j))
                if land_rows[pj][pi] >= 0:
                    on_land.append(relief[j][i])
        on_land.sort()
        top = on_land[int(0.99 * (len(on_land) - 1))] if on_land else 1.0
        scale = 1.0 / top if top > 1e-9 else 0.0
        height = ScalarGrid(
            analysis, [[min(1.0, max(0.0, value * scale)) for value in row] for row in relief]
        )
        return cls(
            plate=plate,
            analysis=analysis,
            land=IndexGrid(plate, land_rows),
            regions=IndexGrid(plate, region_rows),
            height=height,
            shore_margin_meters=shore_margin_meters,
        )

    # -- mutation as the world takes shape -------------------------------

    def add_distance(self, name: str, is_seed: Callable[[int, int], bool]) -> None:
        self.distances[name] = chamfer_distance(self.analysis, is_seed)
        self._state += 1

    def add_polyline_distance(self, name: str, points: Sequence[tuple[float, float]]) -> None:
        """Distance to a polyline, seeded by the analysis cells it crosses."""

        if not points:
            self.distances[name] = ScalarGrid(
                self.analysis,
                [
                    [self.analysis.size_meters * 2.0] * self.analysis.cells
                    for _ in range(self.analysis.cells)
                ],
            )
            return
        seeds: set[tuple[int, int]] = set()
        step = self.analysis.cell_meters * 0.5
        for index in range(len(points)):
            ax, az = points[index]
            bx, bz = points[min(index + 1, len(points) - 1)]
            length = math.hypot(bx - ax, bz - az)
            count = max(1, int(length / step))
            for k in range(count + 1):
                t = k / count
                seeds.add(self.analysis.index(ax + (bx - ax) * t, az + (bz - az) * t))
        self.add_distance(name, lambda i, j: (i, j) in seeds)

    def add_clearings(self, clearings: Sequence[Clearing]) -> None:
        self.clearings.extend(clearings)
        centres = [(c.x, c.z) for c in self.clearings]
        self.add_distance(
            "set_piece",
            lambda i, j: any(
                math.hypot(self.analysis.centre(i, j)[0] - x, self.analysis.centre(i, j)[1] - z)
                <= self.analysis.cell_meters * 0.75
                for x, z in centres
            ),
        )
        self._state += 1

    # -- point queries ---------------------------------------------------

    def on_land(self, x: float, z: float, margin_meters: float) -> bool:
        """Land here and at four points ``margin`` metres away: a cheap shore distance."""

        half = self.plate.half
        if abs(x) > half or abs(z) > half:
            return False
        land = self.land
        if land.at(x, z) < 0:
            return False
        if margin_meters <= 0.0:
            return True
        m = margin_meters
        return (
            land.at(x + m, z) >= 0
            and land.at(x - m, z) >= 0
            and land.at(x, z + m) >= 0
            and land.at(x, z - m) >= 0
        )

    def in_clearing(self, x: float, z: float, extra_meters: float = 0.0) -> bool:
        for clearing in self.clearings:
            if math.hypot(x - clearing.x, z - clearing.z) < clearing.radius_meters + extra_meters:
                return True
        return False

    def clearing_on_land(self, x: float, z: float, radius_meters: float) -> bool:
        if not self.on_land(x, z, self.shore_margin_meters):
            return False
        for k in range(CLEARING_SAMPLES):
            a = math.tau * k / CLEARING_SAMPLES
            if not self.on_land(
                x + math.cos(a) * radius_meters,
                z + math.sin(a) * radius_meters,
                self.shore_margin_meters,
            ):
                return False
        return True

    def region_at(self, x: float, z: float) -> int:
        return self.regions.at(x, z)

    def distance(self, name: str, x: float, z: float) -> float:
        grid = self.distances.get(name)
        if grid is None:
            raise KeyError(f"no distance field {name!r}; have {sorted(self.distances)}")
        return grid.at(x, z)

    def intensity(self, habitat: HabitatSpec, x: float, z: float) -> float:
        """In [0, 1]: how suitable this point is. Density is applied by the process."""

        margin = self.shore_margin_meters + habitat.land_margin_meters
        if not self.on_land(x, z, margin):
            return 0.0
        if not habitat.in_clearings and self.in_clearing(x, z):
            return 0.0
        weight = habitat.weight(self.regions.at(x, z))
        if weight <= 0.0:
            return 0.0
        for name, minimum in habitat.keep_out:
            if self.distance(name, x, z) < minimum:
                return 0.0
        edge = habitat.edge
        if edge is not None:
            weight *= band(
                self.distance(edge.field, x, z),
                peak_meters=edge.peak_meters,
                falloff_meters=edge.falloff_meters,
                outside=edge.outside,
            )
            if weight <= 0.0:
                return 0.0
        height = habitat.height
        if height is not None:
            weight *= trapezoid(
                self.height.at(x, z), low=height.low, high=height.high, falloff=height.falloff
            )
        return weight

    # -- per-object scans on the analysis grid ----------------------------

    def _scan(self, habitat: HabitatSpec) -> list[float]:
        """The intensity at every analysis cell centre, cached until the fields change."""

        key = (habitat, self._state)
        cached = self._scan_cache.get(key)
        if cached is not None:
            return cached
        cells = self.analysis.cells
        scan = [
            self.intensity(habitat, *self.analysis.centre(i, j))
            for j in range(cells)
            for i in range(cells)
        ]
        self._scan_cache[key] = scan
        return scan

    def peak_intensity(self, habitat: HabitatSpec) -> float:
        peak = max(self._scan(habitat), default=0.0)
        return min(1.0, peak * PEAK_SLACK) if peak > 0.0 else 0.0

    def support_area_m2(self, habitat: HabitatSpec) -> float:
        area = self.analysis.cell_meters**2
        return sum(1 for value in self._scan(habitat) if value > 0.0) * area

    def support_chord_meters(self, habitat: HabitatSpec) -> float:
        scan = self._scan(habitat)
        cells = self.analysis.cells
        return patch_chord_meters(self.analysis, lambda i, j: scan[j * cells + i] > 0.0)

    def support_cells(self, habitat: HabitatSpec) -> list[tuple[int, int]]:
        scan = self._scan(habitat)
        cells = self.analysis.cells
        return [(i, j) for j in range(cells) for i in range(cells) if scan[j * cells + i] > 0.0]
