"""The agnostic authored contract: what an object is to the generator.

An object is an id, a process (how its points are drawn), a habitat (where
they may fall), a rarity, a spacing, a footprint, some avoidances and a
quota. Regions are integers. Nothing in here knows what any of it depicts:
a caller binds its own vocabulary (a prop, a mob, a sheet cell) to these
records, and this package never reads a name it did not receive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Literal

#: How many hashed marks a placed point carries (an instance seed, a look, a
#: turn, a scale). Callers derive what they need from these unit floats.
DEFAULT_MARKS: Final = 4


class SpecError(ValueError):
    """An authored world that cannot be generated as written."""


@dataclass(frozen=True, slots=True)
class PoissonProcess:
    """Independent points: ``density_per_100m2`` where the habitat weight is 1,
    proportionally fewer where it is lower, none where it is 0."""

    density_per_100m2: float


@dataclass(frozen=True, slots=True)
class ClusterProcess:
    """A Matérn cluster process: invisible parents, children in a disc around each.

    ``parents_per_100m2`` is the parent density where the habitat weight is 1
    (the habitat thins the parents, so groves stand where the object likes),
    ``mean_size`` the Poisson mean of children per parent, ``radius_meters``
    the disc. The expected density is the product of the first two.
    """

    parents_per_100m2: float
    mean_size: float
    radius_meters: float


@dataclass(frozen=True, slots=True)
class AttachedProcess:
    """Children around the final points of another object (the host)."""

    host_object_id: str
    radius_meters: float
    mean_size: float
    chance: float


@dataclass(frozen=True, slots=True)
class SpacedProcess:
    """A jittered grid: even cover at ``spacing_meters``, thinned by the habitat."""

    spacing_meters: float
    jitter: float = 0.8


type Process = PoissonProcess | ClusterProcess | AttachedProcess | SpacedProcess


@dataclass(frozen=True, slots=True)
class EdgeSpec:
    """A preference for the band near a distance field's zero set."""

    field: str
    peak_meters: float
    falloff_meters: float
    outside: float


@dataclass(frozen=True, slots=True)
class HeightBand:
    """A preference for a band of the height field, in [0, 1]."""

    low: float
    high: float
    falloff: float


@dataclass(frozen=True, slots=True)
class HabitatSpec:
    """Where an object may stand: region weights, an optional edge band, an
    optional height band, and how far from the water it must keep."""

    region_weights: tuple[tuple[int, float], ...]
    edge: EdgeSpec | None = None
    height: HeightBand | None = None
    land_margin_meters: float = 0.0
    #: Distance fields the object keeps a minimum distance from (a road band).
    keep_out: tuple[tuple[str, float], ...] = ()
    #: Whether the object may stand inside a clearing (litter may; a trunk may not).
    in_clearings: bool = False

    def weight(self, region: int) -> float:
        for index, value in self.region_weights:
            if index == region:
                return value
        return 0.0


@dataclass(frozen=True, slots=True)
class Quota:
    min_per_world: int = 0
    max_per_world: int | None = None


@dataclass(frozen=True, slots=True)
class AvoidRule:
    object_id: str
    radius_meters: float


@dataclass(frozen=True, slots=True)
class ObjectSpec:
    object_id: str
    process: Process
    habitat: HabitatSpec
    #: Rarity: per parent for a cluster, per point otherwise. 1 keeps all.
    chance: float = 1.0
    #: The object's own hard core: two of its points are never closer than this.
    spacing_meters: float = 0.0
    #: The physical footprint, the cross-object hard core: two points of any
    #: objects are never closer than the sum of their footprints.
    footprint_radius_meters: float = 0.0
    avoid: tuple[AvoidRule, ...] = ()
    quota: Quota = field(default_factory=Quota)
    #: Space the object keeps free around itself, entered into the fields as a
    #: clearing after it is placed, so later objects stay out.
    clearing_radius_meters: float = 0.0
    mark_count: int = DEFAULT_MARKS


@dataclass(frozen=True, slots=True)
class SetPieceMember:
    object_id: str
    dx: float
    dz: float
    mark: int = 0


@dataclass(frozen=True, slots=True)
class SetPieceSpec:
    """An authored composition, sited whole: at the origin, or in an annulus."""

    set_piece_id: str
    members: tuple[SetPieceMember, ...]
    clearing_radius_meters: float
    count_per_world: int = 1
    at: Literal["origin", "band"] = "band"
    band_meters: tuple[float, float] = (0.0, 0.0)
    required_regions: frozenset[int] = frozenset()


@dataclass(frozen=True, slots=True)
class WorldSpec:
    seed: int
    size_meters: float
    set_pieces: tuple[SetPieceSpec, ...]
    objects: tuple[ObjectSpec, ...]
    #: Footprints of set-piece members by object id, for the shared hard core.
    member_footprints: tuple[tuple[str, float], ...] = ()

    def object(self, object_id: str) -> ObjectSpec:
        for entry in self.objects:
            if entry.object_id == object_id:
                return entry
        raise SpecError(f"unknown object {object_id!r}")


def placement_order(
    objects: tuple[ObjectSpec, ...] | list[ObjectSpec], *, also_known: frozenset[str] = frozenset()
) -> tuple[ObjectSpec, ...]:
    """Hosts before what attaches to them, avoided before avoiders, then by id.

    A topological order over the ``near`` and ``avoid`` edges. A cycle is
    refused by name: two objects that each avoid the other have no order in
    which the second can see the first's final points. ``also_known`` names
    ids that stand in the world before any object (set-piece members): an
    ``avoid`` may name one, a ``near`` may not.
    """

    by_id: dict[str, ObjectSpec] = {}
    for entry in objects:
        if entry.object_id in by_id:
            raise SpecError(f"object id {entry.object_id!r} is declared twice")
        by_id[entry.object_id] = entry
    before: dict[str, set[str]] = {oid: set() for oid in by_id}
    for entry in objects:
        needs: list[str] = [rule.object_id for rule in entry.avoid]
        if isinstance(entry.process, AttachedProcess):
            needs.append(entry.process.host_object_id)
        for other in needs:
            if other == entry.object_id:
                raise SpecError(f"{entry.object_id} refers to itself")
            if other in by_id:
                before[entry.object_id].add(other)
            elif other not in also_known:
                raise SpecError(f"{entry.object_id} refers to unknown object {other!r}")
        if isinstance(entry.process, AttachedProcess) and entry.process.host_object_id not in by_id:
            raise SpecError(
                f"{entry.object_id} attaches to {entry.process.host_object_id!r}, "
                "which is not a placed object"
            )
    ordered: list[ObjectSpec] = []
    done: set[str] = set()
    remaining = sorted(by_id)
    while remaining:
        ready = [oid for oid in remaining if before[oid] <= done]
        if not ready:
            raise SpecError(f"placement order has a cycle among {remaining}")
        for oid in ready:
            ordered.append(by_id[oid])
            done.add(oid)
        remaining = [oid for oid in remaining if oid not in done]
    return tuple(ordered)
