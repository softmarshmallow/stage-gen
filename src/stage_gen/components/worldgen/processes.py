"""Candidate generators: the four point processes, every draw addressed.

Each process yields ``Candidate`` records for one object from salted draws
addressed by the object, a cell and a running index, so the candidates of an
object depend on nothing but its own block, the seed and the fields. A
candidate that lost a random thin (the habitat's intensity, the rarity) is
still yielded, flagged ``passed=False``: those are the reserve a quota's
minimum tops up from, because they are legitimate sites that happened to
lose a coin toss, unlike a point off the land.

Cells are sized so a Poisson cell holds about eight expected points, and a
cell whose expectation would exceed ``LAMBDA_CELL_MAX`` is refused rather than
clamped: that is an authoring mistake, not a sampling problem.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Final

from .fields import WorldFields
from .hashing import Stream
from .spec import (
    AttachedProcess,
    ClusterProcess,
    ObjectSpec,
    PoissonProcess,
    SpacedProcess,
    SpecError,
    WorldSpec,
)

#: Expected points per Poisson cell; the cell side is chosen to hit it.
LAMBDA_CELL_TARGET: Final = 8.0
#: The refusal line for a cell's expectation.
LAMBDA_CELL_MAX: Final = 64.0
#: The smallest cell a process is divided into.
MIN_CELL_METERS: Final = 0.5
#: Above this fraction of the hexagonal packing limit the hard core, not the
#: cluster block, sets the pattern, and the measurement will not read as
#: clustered.
PACKING_FRACTION_MAX: Final = 0.35
#: Iteration guard for the inverse-CDF Poisson draw.
POISSON_K_MAX: Final = 4096


@dataclass(frozen=True, slots=True)
class Candidate:
    x: float
    z: float
    #: The stable address: which cell, which index, which child.
    key: tuple[int, ...]
    #: The parent's address for a cluster child, else None.
    parent: tuple[int, ...] | None
    #: The host's address for an attached child, else None.
    host: tuple[int, ...] | None
    priority: float
    #: The intensity at the point, in (0, 1].
    intensity: float
    #: Survived the intensity thin and the rarity. False means "in the reserve".
    passed: bool


def poisson_count(u: float, lam: float) -> int:
    """A Poisson variate by inverse CDF from one uniform in [0, 1)."""

    if lam <= 0.0:
        return 0
    if lam > LAMBDA_CELL_MAX:
        raise SpecError(f"a cell expectation of {lam:.1f} exceeds {LAMBDA_CELL_MAX:g}")
    p = math.exp(-lam)
    cdf = p
    k = 0
    while u >= cdf:
        k += 1
        if k > POISSON_K_MAX:
            raise SpecError(f"poisson_count did not converge at lambda {lam:g}")
        p *= lam / k
        cdf += p
    return k


def cell_meters_for(lam_per_m2: float, *, size_meters: float) -> float:
    """The cell side that puts about ``LAMBDA_CELL_TARGET`` expected points in a cell."""

    if lam_per_m2 <= 0.0:
        return size_meters
    side = math.sqrt(LAMBDA_CELL_TARGET / lam_per_m2)
    return min(size_meters, max(MIN_CELL_METERS, side))


def _cells(size_meters: float, cell: float) -> Iterator[tuple[int, int]]:
    count = max(1, math.ceil(size_meters / cell))
    for j in range(count):
        for i in range(count):
            yield i, j


def _inside(fields: WorldFields, x: float, z: float) -> bool:
    half = fields.plate.half
    return -half <= x < half and -half <= z < half


def poisson_candidates(obj: ObjectSpec, fields: WorldFields, seed: int) -> Iterator[Candidate]:
    process = obj.process
    if not isinstance(process, PoissonProcess):
        raise SpecError(f"{obj.object_id} is not a Poisson object")
    peak = fields.peak_intensity(obj.habitat)
    if peak <= 0.0:
        return
    lam_peak = process.density_per_100m2 / 100.0 * peak
    size = fields.plate.size_meters
    cell = cell_meters_for(lam_peak, size_meters=size)
    lam_cell = lam_peak * cell * cell
    half = size / 2.0
    count_s = Stream.of(seed, obj.object_id, "poisson", "count")
    site_s = Stream.of(seed, obj.object_id, "poisson", "site")
    thin_s = Stream.of(seed, obj.object_id, "poisson", "thin")
    chance_s = Stream.of(seed, obj.object_id, "chance")
    prio_s = Stream.of(seed, obj.object_id, "priority")
    for i, j in _cells(size, cell):
        n = poisson_count(count_s.unit(i, j), lam_cell)
        if n == 0:
            continue
        site_c = site_s.cell(i, j)
        for k in range(n):
            x = (i + site_c.unit(k, 0)) * cell - half
            z = (j + site_c.unit(k, 1)) * cell - half
            if not _inside(fields, x, z):
                continue
            lam = fields.intensity(obj.habitat, x, z)
            if lam <= 0.0:
                continue
            passed = thin_s.unit(i, j, k) * peak < lam and chance_s.unit(i, j, k) < obj.chance
            yield Candidate(
                x=x,
                z=z,
                key=(i, j, k),
                parent=None,
                host=None,
                priority=prio_s.unit(i, j, k),
                intensity=lam,
                passed=passed,
            )


def cluster_candidates(obj: ObjectSpec, fields: WorldFields, seed: int) -> Iterator[Candidate]:
    process = obj.process
    if not isinstance(process, ClusterProcess):
        raise SpecError(f"{obj.object_id} is not a cluster object")
    peak = fields.peak_intensity(obj.habitat)
    if peak <= 0.0:
        return
    lam_parent = process.parents_per_100m2 / 100.0 * peak
    size = fields.plate.size_meters
    cell = cell_meters_for(lam_parent, size_meters=size)
    lam_cell = lam_parent * cell * cell
    half = size / 2.0
    parents_s = Stream.of(seed, obj.object_id, "cluster", "parents")
    psite_s = Stream.of(seed, obj.object_id, "cluster", "parent_site")
    pthin_s = Stream.of(seed, obj.object_id, "cluster", "parent_thin")
    size_s = Stream.of(seed, obj.object_id, "cluster", "size")
    child_s = Stream.of(seed, obj.object_id, "cluster", "child")
    cthin_s = Stream.of(seed, obj.object_id, "cluster", "child_thin")
    chance_s = Stream.of(seed, obj.object_id, "chance")
    prio_s = Stream.of(seed, obj.object_id, "priority")
    for i, j in _cells(size, cell):
        n = poisson_count(parents_s.unit(i, j), lam_cell)
        if n == 0:
            continue
        psite_c = psite_s.cell(i, j)
        for q in range(n):
            px = (i + psite_c.unit(q, 0)) * cell - half
            pz = (j + psite_c.unit(q, 1)) * cell - half
            if not _inside(fields, px, pz):
                continue
            parent_lam = fields.intensity(obj.habitat, px, pz)
            if parent_lam <= 0.0 or pthin_s.unit(i, j, q) * peak >= parent_lam:
                continue
            rare = chance_s.unit(i, j, q) >= obj.chance
            m = poisson_count(size_s.unit(i, j, q), process.mean_size)
            child_c = child_s.cell(i, j, q)
            for c in range(m):
                a = child_c.unit(c, 0) * math.tau
                r = process.radius_meters * math.sqrt(child_c.unit(c, 1))
                x = px + math.cos(a) * r
                z = pz + math.sin(a) * r
                if not _inside(fields, x, z):
                    continue
                lam = fields.intensity(obj.habitat, x, z)
                if lam <= 0.0:
                    continue
                # The parent already paid the habitat; a child is thinned only
                # by how much worse its own ground is than the parent's, so a
                # grove on uniform ground keeps its whole mean size.
                relative = min(1.0, lam / parent_lam)
                passed = not rare and cthin_s.unit(i, j, q, c) < relative
                yield Candidate(
                    x=x,
                    z=z,
                    key=(i, j, q, c),
                    parent=(i, j, q),
                    host=None,
                    priority=prio_s.unit(i, j, q, c),
                    intensity=lam,
                    passed=passed,
                )


@dataclass(frozen=True, slots=True)
class HostPoint:
    """What an attached process needs of a host's final point."""

    x: float
    z: float
    key: tuple[int, ...]


def attached_candidates(
    obj: ObjectSpec, fields: WorldFields, seed: int, hosts: Sequence[HostPoint]
) -> Iterator[Candidate]:
    process = obj.process
    if not isinstance(process, AttachedProcess):
        raise SpecError(f"{obj.object_id} is not an attached object")
    chance_s = Stream.of(seed, obj.object_id, "attach", "chance")
    size_s = Stream.of(seed, obj.object_id, "attach", "size")
    child_s = Stream.of(seed, obj.object_id, "attach", "child")
    prio_s = Stream.of(seed, obj.object_id, "priority")
    for host in hosts:
        rare = chance_s.unit(*host.key) >= process.chance
        m = poisson_count(size_s.unit(*host.key), process.mean_size)
        child_c = child_s.cell(*host.key)
        for c in range(m):
            a = child_c.unit(c, 0) * math.tau
            r = process.radius_meters * math.sqrt(child_c.unit(c, 1))
            x = host.x + math.cos(a) * r
            z = host.z + math.sin(a) * r
            if not _inside(fields, x, z):
                continue
            lam = fields.intensity(obj.habitat, x, z)
            if lam <= 0.0:
                continue
            key = (*host.key, c)
            yield Candidate(
                x=x,
                z=z,
                key=key,
                parent=None,
                host=host.key,
                priority=prio_s.unit(*key),
                intensity=lam,
                passed=not rare,
            )


def spaced_candidates(obj: ObjectSpec, fields: WorldFields, seed: int) -> Iterator[Candidate]:
    process = obj.process
    if not isinstance(process, SpacedProcess):
        raise SpecError(f"{obj.object_id} is not a spaced object")
    spacing = process.spacing_meters
    size = fields.plate.size_meters
    half = size / 2.0
    jitter_s = Stream.of(seed, obj.object_id, "spaced", "jitter")
    thin_s = Stream.of(seed, obj.object_id, "spaced", "thin")
    chance_s = Stream.of(seed, obj.object_id, "chance")
    prio_s = Stream.of(seed, obj.object_id, "priority")
    for i, j in _cells(size, spacing):
        x = (i + 0.5 + (jitter_s.unit(i, j, 0) - 0.5) * process.jitter) * spacing - half
        z = (j + 0.5 + (jitter_s.unit(i, j, 1) - 0.5) * process.jitter) * spacing - half
        if not _inside(fields, x, z):
            continue
        lam = fields.intensity(obj.habitat, x, z)
        if lam <= 0.0:
            continue
        passed = thin_s.unit(i, j) < lam and chance_s.unit(i, j) < obj.chance
        yield Candidate(
            x=x,
            z=z,
            key=(i, j),
            parent=None,
            host=None,
            priority=prio_s.unit(i, j),
            intensity=lam,
            passed=passed,
        )


def candidates_for(
    obj: ObjectSpec, fields: WorldFields, seed: int, hosts: Sequence[HostPoint] = ()
) -> list[Candidate]:
    process = obj.process
    if isinstance(process, PoissonProcess):
        return list(poisson_candidates(obj, fields, seed))
    if isinstance(process, ClusterProcess):
        return list(cluster_candidates(obj, fields, seed))
    if isinstance(process, AttachedProcess):
        return list(attached_candidates(obj, fields, seed, hosts))
    return list(spaced_candidates(obj, fields, seed))


def packing_limit_per_100m2(spacing_meters: float) -> float:
    """Hexagonal packing of discs kept ``spacing`` apart, per 100 m²."""

    if spacing_meters <= 0.0:
        return math.inf
    return 100.0 * 2.0 / (math.sqrt(3.0) * spacing_meters * spacing_meters)


def check_spec(spec: WorldSpec, fields: WorldFields) -> list[str]:
    """Refusals, not warnings: an object that cannot be drawn as written.

    A cell expectation over the line, a grove packed denser than its hard
    core allows, a cluster radius wider than the patches its habitat comes in
    (the islet octave shatters a region into patches; a grove wider than a
    patch cannot exist there and would not measure as a grove), a quota that
    contradicts itself, a habitat with no ground at all.
    """

    problems: list[str] = []
    size = spec.size_meters
    for obj in spec.objects:
        name = obj.object_id
        if not 0.0 < obj.chance <= 1.0:
            problems.append(f"{name}: chance must be within (0, 1], got {obj.chance}")
        quota = obj.quota
        if quota.max_per_world is not None and quota.max_per_world < quota.min_per_world:
            problems.append(
                f"{name}: max_per_world {quota.max_per_world} is below min {quota.min_per_world}"
            )
        peak = fields.peak_intensity(obj.habitat)
        if peak <= 0.0:
            problems.append(f"{name}: no suitable ground anywhere in the world")
            continue
        process = obj.process
        if isinstance(process, PoissonProcess):
            lam = process.density_per_100m2 / 100.0 * peak
            cell = cell_meters_for(lam, size_meters=size)
            if lam * cell * cell > LAMBDA_CELL_MAX:
                problems.append(
                    f"{name}: density {process.density_per_100m2} per 100 m² is beyond the sampler"
                )
        elif isinstance(process, ClusterProcess):
            lam = process.parents_per_100m2 / 100.0 * peak
            cell = cell_meters_for(lam, size_meters=size)
            if lam * cell * cell > LAMBDA_CELL_MAX:
                problems.append(
                    f"{name}: {process.parents_per_100m2} parents per 100 m² is beyond the sampler"
                )
            if process.mean_size > LAMBDA_CELL_MAX:
                problems.append(
                    f"{name}: cluster mean_size {process.mean_size} is beyond the sampler"
                )
            if process.radius_meters <= 0.0:
                problems.append(f"{name}: cluster radius_meters must be positive")
            else:
                disc = math.pi * process.radius_meters**2 / 100.0
                grove = process.mean_size / disc
                limit = packing_limit_per_100m2(obj.spacing_meters)
                if grove > PACKING_FRACTION_MAX * limit:
                    problems.append(
                        f"{name}: a cluster of {process.mean_size:g} in "
                        f"{process.radius_meters:g} m is {grove:.1f} per 100 m², over "
                        f"{PACKING_FRACTION_MAX:.0%} of the {limit:.1f} its spacing allows; "
                        "the hard core, not the cluster, would set the pattern"
                    )
                chord = fields.support_chord_meters(obj.habitat)
                if chord > 0.0 and process.radius_meters > chord:
                    problems.append(
                        f"{name}: cluster radius {process.radius_meters:g} m is wider than the "
                        f"{chord:.1f} m patches its habitat comes in"
                    )
        elif isinstance(process, AttachedProcess):
            if process.mean_size > LAMBDA_CELL_MAX:
                problems.append(
                    f"{name}: attached mean_size {process.mean_size} is beyond the sampler"
                )
            if not 0.0 < process.chance <= 1.0:
                problems.append(f"{name}: attach chance must be within (0, 1]")
        elif isinstance(process, SpacedProcess):
            if process.spacing_meters < MIN_CELL_METERS:
                problems.append(f"{name}: spacing_meters must be at least {MIN_CELL_METERS:g}")
            if not 0.0 <= process.jitter <= 1.0:
                problems.append(f"{name}: jitter must be within [0, 1]")
    return problems
