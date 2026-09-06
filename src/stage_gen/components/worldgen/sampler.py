"""The placement pipeline: candidates, two hard cores, quotas, and the plan.

Per object, in topological order:

1. candidates from its process, each flagged by whether it survived the
   random thins (the rest are the reserve);
2. sorted by hashed priority, so acceptance never depends on the order the
   generator happened to produce them;
3. **tier 1**, the object's own hard core, greedy in that order;
4. the quota, on the tier-1 set: the maximum truncates the priority order (a
   spatially unbiased subsample), the minimum tops up from the reserve by
   intensity, still clearing tier 1, and refuses when the reserve runs out;
5. **tier 2**, the cross-object hard core (footprints and ``avoid`` rules),
   which only ever deletes. A drop never promotes a candidate, so an edit to
   one object cannot cascade through the others: its reach is one footprint.

Points are emitted sorted by their stable address, never by acceptance order,
so a flipped acceptance moves one row of the record and not the numbering.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal

from .fields import Clearing, WorldFields
from .hashing import Stream
from .processes import Candidate, HostPoint, candidates_for
from .setpieces import SetPieceSite, place_set_pieces
from .spec import AttachedProcess, ObjectSpec, WorldSpec

#: The bucket is at least this many metres, whatever the radii.
MIN_BUCKET_METERS: Final = 1.0


@dataclass(frozen=True, slots=True)
class Placed:
    object_id: str
    x: float
    z: float
    key: tuple[int, ...]
    parent: tuple[int, ...] | None
    host: tuple[int, ...] | None
    #: Hashed unit floats the caller derives instance attributes from.
    marks: tuple[float, ...]
    origin: Literal["process", "quota_topup", "set_piece"]

    @property
    def cluster_id(self) -> str | None:
        """A stable name for the parent or host this point belongs to."""

        if self.parent is not None:
            return f"{self.object_id}/c{'.'.join(str(v) for v in self.parent)}"
        if self.host is not None:
            return f"host/{'.'.join(str(v) for v in self.host)}"
        return None


@dataclass(frozen=True, slots=True)
class ObjectTally:
    candidates: int
    reserve: int
    dropped_own_core: int
    truncated: int
    topped_up: int
    dropped_neighbour: int
    placed: int


class PointIndex:
    """Placed points bucketed on a grid, so a reach test reads nine buckets.

    The bucket is at least twice the largest radius it will ever be asked
    about, so two points that could touch are never more than one bucket
    apart. Same answer as the full scan, which is what byte identity needs.
    """

    def __init__(self, bucket_meters: float) -> None:
        self.bucket = max(MIN_BUCKET_METERS, bucket_meters)
        self.buckets: dict[tuple[int, int], list[tuple[float, float, float, str]]] = {}
        self.count = 0
        #: The largest radius added so far: bounds how far a reach test reads.
        self.widest = 0.0

    def add(self, x: float, z: float, radius: float, object_id: str = "") -> None:
        key = (int(x // self.bucket), int(z // self.bucket))
        self.buckets.setdefault(key, []).append((x, z, radius, object_id))
        self.count += 1
        if radius > self.widest:
            self.widest = radius

    def hits(
        self,
        x: float,
        z: float,
        radius: float,
        *,
        only: Callable[[str], bool] | None = None,
        reach_override: float | None = None,
    ) -> bool:
        """Whether anything within ``radius + its radius`` (or ``reach_override``) is here."""

        cx = int(x // self.bucket)
        cz = int(z // self.bucket)
        # One ring covers a reach up to the bucket; a wider reach reads more.
        widest = radius + self.widest if reach_override is None else reach_override
        rings = max(1, math.ceil(widest / self.bucket))
        for dx in range(-rings, rings + 1):
            for dz in range(-rings, rings + 1):
                for px, pz, pr, oid in self.buckets.get((cx + dx, cz + dz), ()):
                    if only is not None and not only(oid):
                        continue
                    reach = radius + pr if reach_override is None else reach_override
                    if (x - px) ** 2 + (z - pz) ** 2 < reach * reach:
                        return True
        return False

    def nearest_distance(self, x: float, z: float, *, rings: int) -> float:
        """The distance to the nearest point within ``rings`` buckets, else inf."""

        cx = int(x // self.bucket)
        cz = int(z // self.bucket)
        best = math.inf
        for dx in range(-rings, rings + 1):
            for dz in range(-rings, rings + 1):
                for px, pz, _pr, _oid in self.buckets.get((cx + dx, cz + dz), ()):
                    d = math.hypot(x - px, z - pz)
                    if 0.0 < d < best:
                        best = d
        return best

    def pairs_closer_than(
        self, gap: Callable[[str, str], float]
    ) -> Iterator[tuple[tuple[float, float, str], tuple[float, float, str]]]:
        """Every pair of points closer than ``gap(object_a, object_b)``, each once."""

        # Each unordered pair of buckets is visited once: the bucket itself
        # (later entries only) and the four neighbours in the forward half.
        forward = ((1, 0), (-1, 1), (0, 1), (1, 1))
        for (cx, cz), entries in self.buckets.items():
            for index, (ax, az, _ar, aid) in enumerate(entries):
                for bx, bz, _br, bid in entries[index + 1 :]:
                    if math.hypot(ax - bx, az - bz) < gap(aid, bid):
                        yield (ax, az, aid), (bx, bz, bid)
                for dx, dz in forward:
                    for bx, bz, _br, bid in self.buckets.get((cx + dx, cz + dz), ()):
                        if math.hypot(ax - bx, az - bz) < gap(aid, bid):
                            yield (ax, az, aid), (bx, bz, bid)


def accept_own(cands: Sequence[Candidate], spacing_meters: float) -> tuple[list[Candidate], int]:
    """Tier 1: greedy in the given order; returns the kept list and how many the core dropped."""

    if spacing_meters <= 0.0:
        return list(cands), 0
    index = PointIndex(spacing_meters)
    kept: list[Candidate] = []
    dropped = 0
    for cand in cands:
        if index.hits(cand.x, cand.z, 0.0, reach_override=spacing_meters):
            dropped += 1
            continue
        index.add(cand.x, cand.z, 0.0)
        kept.append(cand)
    return kept, dropped


def apply_quota(
    kept: list[Candidate],
    reserve: Sequence[Candidate],
    *,
    min_per_world: int,
    max_per_world: int | None,
    spacing_meters: float,
) -> tuple[list[Candidate], int, int]:
    """The maximum truncates, the minimum tops up. Returns (kept, truncated, topped_up)."""

    truncated = 0
    if max_per_world is not None and len(kept) > max_per_world:
        truncated = len(kept) - max_per_world
        kept = kept[:max_per_world]
    topped = 0
    if len(kept) < min_per_world:
        index = PointIndex(max(spacing_meters, MIN_BUCKET_METERS))
        for cand in kept:
            index.add(cand.x, cand.z, 0.0)
        for cand in sorted(reserve, key=lambda c: (-c.intensity, c.priority, c.key)):
            if len(kept) >= min_per_world:
                break
            if spacing_meters > 0.0 and index.hits(
                cand.x, cand.z, 0.0, reach_override=spacing_meters
            ):
                continue
            index.add(cand.x, cand.z, 0.0)
            kept.append(cand)
            topped += 1
    return kept, truncated, topped


def _is(object_id: str) -> Callable[[str], bool]:
    def predicate(candidate: str) -> bool:
        return candidate == object_id

    return predicate


def drop_neighbours(
    kept: Sequence[Candidate],
    index: PointIndex,
    obj: ObjectSpec,
    *,
    footprint_of: Callable[[str], float],
) -> tuple[list[Candidate], int]:
    """Tier 2: drop against every earlier object's footprint and the avoid rules. Never promotes."""

    avoid = {rule.object_id: rule.radius_meters for rule in obj.avoid}
    final: list[Candidate] = []
    dropped = 0
    for cand in kept:
        if index.hits(cand.x, cand.z, obj.footprint_radius_meters):
            dropped += 1
            continue
        blocked = False
        for other, radius in avoid.items():
            if index.hits(
                cand.x,
                cand.z,
                0.0,
                only=_is(other),
                reach_override=radius,
            ):
                blocked = True
                break
        if blocked:
            dropped += 1
            continue
        final.append(cand)
    return final, dropped


@dataclass(frozen=True, slots=True)
class WorldPlan:
    points: Mapping[str, tuple[Placed, ...]]
    sites: tuple[SetPieceSite, ...]
    tallies: Mapping[str, ObjectTally]
    refusals: tuple[str, ...]

    def all_points(self) -> Iterator[Placed]:
        for object_id in sorted(self.points):
            yield from self.points[object_id]


def _bucket_for(spec: WorldSpec) -> float:
    radii = [obj.footprint_radius_meters for obj in spec.objects]
    radii += [radius for _oid, radius in spec.member_footprints]
    radii += [rule.radius_meters for obj in spec.objects for rule in obj.avoid]
    return 2.0 * max(radii, default=0.0) + MIN_BUCKET_METERS


def _marks(stream: Stream, key: tuple[int, ...], count: int) -> tuple[float, ...]:
    cell = stream.cell(*key)
    return tuple(cell.unit(m) for m in range(count))


def plan_world(spec: WorldSpec, fields: WorldFields) -> WorldPlan:
    """Site the set pieces, then place every object in order. Pure in (spec, fields)."""

    sites, refusals = place_set_pieces(spec, fields)
    fields.add_clearings([site.clearing for site in sites])
    index = PointIndex(_bucket_for(spec))
    member_footprint = dict(spec.member_footprints)
    for site in sites:
        for member in site.members:
            index.add(
                member.x, member.z, member_footprint.get(member.object_id, 0.0), member.object_id
            )
    footprints = {obj.object_id: obj.footprint_radius_meters for obj in spec.objects}
    footprints.update(member_footprint)

    def footprint_of(object_id: str) -> float:
        return footprints.get(object_id, 0.0)

    points: dict[str, tuple[Placed, ...]] = {}
    tallies: dict[str, ObjectTally] = {}
    for obj in spec.objects:
        hosts: list[HostPoint] = []
        if isinstance(obj.process, AttachedProcess):
            hosts = [HostPoint(p.x, p.z, p.key) for p in points.get(obj.process.host_object_id, ())]
        cands = candidates_for(obj, fields, spec.seed, hosts)
        passed = [c for c in cands if c.passed]
        reserve = [c for c in cands if not c.passed]
        passed.sort(key=lambda c: (c.priority, c.key))
        kept, own_dropped = accept_own(passed, obj.spacing_meters)
        kept, truncated, topped = apply_quota(
            kept,
            reserve,
            min_per_world=obj.quota.min_per_world,
            max_per_world=obj.quota.max_per_world,
            spacing_meters=obj.spacing_meters,
        )
        topped_keys = {c.key for c in kept[len(kept) - topped :]} if topped else set()
        final, neighbour_dropped = drop_neighbours(kept, index, obj, footprint_of=footprint_of)
        final.sort(key=lambda c: c.key)
        mark_s = Stream.of(spec.seed, obj.object_id, "mark")
        placed = tuple(
            Placed(
                object_id=obj.object_id,
                x=round(c.x, 3),
                z=round(c.z, 3),
                key=c.key,
                parent=c.parent,
                host=c.host,
                marks=_marks(mark_s, c.key, obj.mark_count),
                origin="quota_topup" if c.key in topped_keys else "process",
            )
            for c in final
        )
        for p in placed:
            index.add(p.x, p.z, obj.footprint_radius_meters, obj.object_id)
        if obj.clearing_radius_meters > 0.0 and placed:
            fields.add_clearings([Clearing(p.x, p.z, obj.clearing_radius_meters) for p in placed])
        points[obj.object_id] = placed
        tallies[obj.object_id] = ObjectTally(
            candidates=len(cands),
            reserve=len(reserve),
            dropped_own_core=own_dropped,
            truncated=truncated,
            topped_up=topped,
            dropped_neighbour=neighbour_dropped,
            placed=len(placed),
        )
        if len(placed) < obj.quota.min_per_world:
            refusals.append(
                f"{obj.object_id}: {len(placed)} placed, below min_per_world "
                f"{obj.quota.min_per_world} "
                f"({neighbour_dropped} dropped by neighbours, {len(reserve)} in the reserve)"
            )
    return WorldPlan(points=points, sites=sites, tallies=tallies, refusals=tuple(refusals))
