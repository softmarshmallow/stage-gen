"""Point-pattern measurement against a Monte-Carlo null, and the refusals.

The textbook aggregation index (Clark and Evans' R: the mean nearest-
neighbour distance over its Poisson expectation) measures the support, not
the pattern, on a habitat like ours: a region shattered into islets has a
perimeter longer than its area can hide, and a plain Poisson process on it
reads as "regular" at R = 1.3 to 1.6. Donnelly's edge correction assumes a
convex region and a flat intensity and under-corrects here.

So the null is not a formula but the same world: the object's own intensity,
exclusions, hard core and realised count, with its process replaced by plain
Poisson, drawn nine times from a fixed measurement salt. ``r_mc`` is the
observed mean nearest-neighbour distance over the null's mean; ``k_ratio``
the observed neighbour count within the cluster radius over the null's.
Measured on the real fields: Poisson reads r_mc 0.86-1.07, a Matérn cluster
0.23-0.69 with k_ratio 1.9-12.7, a jittered grid 1.29-1.55. A cluster is
refused only when both statistics say it did not cluster, so one extreme
null replicate cannot refuse a clean world.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from .fields import WorldFields
from .hashing import Stream
from .sampler import Placed, PointIndex
from .spec import ClusterProcess, ObjectSpec, SpacedProcess, WorldSpec

NULL_REPLICATES: Final = 9
CLUSTER_R_MAX: Final = 0.85
CLUSTER_K_MIN: Final = 1.40
SPACED_R_MIN: Final = 1.15
#: Below this many points the statistics are noise; report, never refuse.
MEASURE_MIN_POINTS: Final = 30
#: Below this many neighbour pairs in the null the K ratio is noise.
MEASURE_MIN_PAIRS: Final = 200
#: Rejection-sampling tries per point when drawing a null replicate.
NULL_TRIES_PER_POINT: Final = 60
#: Above this many points three replicates are as good as nine: the null's
#: spread shrinks with the count, and the ninth costs what the first did.
LARGE_COUNT: Final = 2000
LARGE_REPLICATES: Final = 3

type Verdict = Literal["clustered", "random", "spaced", "unmeasurable"]


@dataclass(frozen=True, slots=True)
class PatternReport:
    object_id: str
    count: int
    support_area_m2: float
    mean_nn_meters: float
    null_mean_nn_meters: float
    r_mc: float
    radius_meters: float
    k_bar: float
    k_null: float
    k_ratio: float
    verdict: Verdict


def mean_nearest_neighbour(points: Sequence[tuple[float, float]]) -> float:
    """Mean distance to the nearest other point, bucketed; inf-free for n >= 2."""

    n = len(points)
    if n < 2:
        return 0.0
    # A bucket wide enough that the nearest neighbour is almost always within
    # one ring; the ring count grows when it is not.
    extent = max(max(abs(x), abs(z)) for x, z in points) * 2.0 + 1.0
    bucket = max(1.0, extent / math.sqrt(n))
    index = PointIndex(bucket)
    for x, z in points:
        index.add(x, z, 0.0)
    total = 0.0
    for x, z in points:
        rings = 1
        best = index.nearest_distance(x, z, rings=rings)
        # Every point closer than rings * bucket lies inside the rings read,
        # so the search widens until the best found is provably the nearest.
        while best > rings * bucket and rings * bucket < extent:
            rings += 1
            best = index.nearest_distance(x, z, rings=rings)
        total += 0.0 if best == math.inf else best
    return total / n


def neighbours_within(points: Sequence[tuple[float, float]], radius_meters: float) -> float:
    """Mean number of other points within ``radius_meters`` of a point."""

    n = len(points)
    if n < 2 or radius_meters <= 0.0:
        return 0.0
    index = PointIndex(radius_meters)
    for x, z in points:
        index.add(x, z, 0.0)
    total = 0
    r2 = radius_meters * radius_meters
    for x, z in points:
        cx = int(x // index.bucket)
        cz = int(z // index.bucket)
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for px, pz, _pr, _oid in index.buckets.get((cx + dx, cz + dz), ()):
                    d2 = (x - px) ** 2 + (z - pz) ** 2
                    if 0.0 < d2 < r2:
                        total += 1
    return total / n


def _null_replicate(
    obj: ObjectSpec, fields: WorldFields, seed: int, replicate: int, count: int
) -> list[tuple[float, float]]:
    """``count`` Poisson points from the object's own intensity and hard core."""

    stream = Stream.of(seed, "measure", obj.object_id, "null")
    peak = fields.peak_intensity(obj.habitat)
    half = fields.plate.half
    index = PointIndex(max(obj.spacing_meters, 1.0))
    out: list[tuple[float, float]] = []
    tries = count * NULL_TRIES_PER_POINT
    k = 0
    while len(out) < count and k < tries:
        x = (stream.unit(replicate, k, 0) * 2.0 - 1.0) * half
        z = (stream.unit(replicate, k, 1) * 2.0 - 1.0) * half
        u = stream.unit(replicate, k, 2)
        k += 1
        lam = fields.intensity(obj.habitat, x, z)
        if lam <= 0.0 or u * peak >= lam:
            continue
        if obj.spacing_meters > 0.0 and index.hits(x, z, 0.0, reach_override=obj.spacing_meters):
            continue
        index.add(x, z, 0.0)
        out.append((x, z))
    return out


def measure_object(
    spec: WorldSpec, fields: WorldFields, obj: ObjectSpec, placed: Sequence[Placed]
) -> PatternReport:
    points = [(p.x, p.z) for p in placed]
    count = len(points)
    area = fields.support_area_m2(obj.habitat)
    process = obj.process
    radius = (
        process.radius_meters
        if isinstance(process, ClusterProcess)
        else process.spacing_meters
        if isinstance(process, SpacedProcess)
        else 0.0
    )
    if count < MEASURE_MIN_POINTS or area <= 0.0:
        return PatternReport(
            obj.object_id, count, area, 0.0, 0.0, 0.0, radius, 0.0, 0.0, 0.0, "unmeasurable"
        )
    mean_nn = mean_nearest_neighbour(points)
    k_bar = neighbours_within(points, radius) if radius > 0.0 else 0.0
    null_nn: list[float] = []
    null_k: list[float] = []
    replicates = NULL_REPLICATES if count < LARGE_COUNT else LARGE_REPLICATES
    for replicate in range(replicates):
        null = _null_replicate(obj, fields, spec.seed, replicate, count)
        if len(null) < MEASURE_MIN_POINTS:
            continue
        null_nn.append(mean_nearest_neighbour(null))
        if radius > 0.0:
            null_k.append(neighbours_within(null, radius))
    if not null_nn:
        return PatternReport(
            obj.object_id, count, area, mean_nn, 0.0, 0.0, radius, k_bar, 0.0, 0.0, "unmeasurable"
        )
    null_mean = sum(null_nn) / len(null_nn)
    r_mc = mean_nn / null_mean if null_mean > 0.0 else 0.0
    k_null = sum(null_k) / len(null_k) if null_k else 0.0
    k_measurable = k_null * count >= MEASURE_MIN_PAIRS
    k_ratio = k_bar / k_null if k_null > 0.0 and k_measurable else 0.0
    verdict: Verdict
    if isinstance(process, ClusterProcess):
        clustered = r_mc <= CLUSTER_R_MAX or (k_measurable and k_ratio >= CLUSTER_K_MIN)
        verdict = "clustered" if clustered else "random"
    elif isinstance(process, SpacedProcess):
        verdict = "spaced" if r_mc >= SPACED_R_MIN else "random"
    elif r_mc <= CLUSTER_R_MAX:
        verdict = "clustered"
    elif r_mc >= SPACED_R_MIN:
        verdict = "spaced"
    else:
        verdict = "random"
    return PatternReport(
        object_id=obj.object_id,
        count=count,
        support_area_m2=area,
        mean_nn_meters=round(mean_nn, 4),
        null_mean_nn_meters=round(null_mean, 4),
        r_mc=round(r_mc, 4),
        radius_meters=radius,
        k_bar=round(k_bar, 4),
        k_null=round(k_null, 4),
        k_ratio=round(k_ratio, 4),
        verdict=verdict,
    )


def refuse_patterns(spec: WorldSpec, reports: Sequence[PatternReport]) -> list[str]:
    """A cluster block that did not cluster, a spacing that did not space."""

    problems: list[str] = []
    by_id = {report.object_id: report for report in reports}
    for obj in spec.objects:
        report = by_id.get(obj.object_id)
        if report is None or report.verdict == "unmeasurable":
            continue
        if isinstance(obj.process, ClusterProcess) and report.verdict != "clustered":
            problems.append(
                f"{obj.object_id}: authored as a cluster but came out random "
                f"(r_mc {report.r_mc:.2f} > {CLUSTER_R_MAX}, "
                f"k_ratio {report.k_ratio:.2f} < {CLUSTER_K_MIN})"
            )
        elif isinstance(obj.process, SpacedProcess) and report.verdict != "spaced":
            problems.append(
                f"{obj.object_id}: authored as spaced but came out random "
                f"(r_mc {report.r_mc:.2f} < {SPACED_R_MIN})"
            )
    return problems
