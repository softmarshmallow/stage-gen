"""Algorithmic world layout: the recipe's binding of the world generator.

Local and free. Nothing here calls a provider, and the same seed must produce
byte-identical JSON and identical plate bytes, because the layout is part of
the run's identity and a host reload must not shuffle the world.

The generator (``stage_gen.components.worldgen``) knows regions as integers
and objects as ids. This module is where the recipe's words meet it: a biome
becomes a region index, a prop's ``placement`` block becomes an object spec,
a ``[[set_pieces]]`` entry becomes a composition, and what comes back is
turned into the layout record the manifest embeds and the hosts read.

The one random stream the first layouts consumed is gone. Every draw is
addressed by (seed, object, cell, index), so raising the pines' density moves
the pines and, within one footprint, nothing else. ``mulberry32`` stays here
only because the hosts run it for the sim and a test pins the port.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Protocol, TypedDict

from stage_gen.components import worldgen
from stage_gen.components.worldgen import (
    AttachedProcess,
    AvoidRule,
    Bump,
    ClusterProcess,
    Coast,
    EdgeSpec,
    HabitatSpec,
    HeightBand,
    ObjectSpec,
    PatternReport,
    Plate,
    PointIndex,
    PoissonProcess,
    Quota,
    RegionField,
    SetPieceMember,
    SetPieceSpec,
    SpacedProcess,
    Stream,
    ValueNoise,
    WorldFields,
    WorldPlan,
    WorldSpec,
    plate_cells,
    polyline_distance,
)
from stage_gen.recipes.oblique_survival.models import (
    Package,
    Placement,
    Prop,
    SourceError,
)

#: Metres per plate cell at the finest a plate is drawn; a plate caps at 1024
#: cells a side, so a 512 m world draws 0.5 m cells (``worldgen.plate_cells``).
SPLAT_CELL_METERS: Final = worldgen.PLATE_CELL_METERS
#: How far the spawn's land bump and region clearing reach, in clearing radii.
SPAWN_REACH: Final = 2.5
#: The canopy's shade: added per cell as ``gain * (1 - d/r)**2``, capped.
CANOPY_GAIN: Final = 0.30
CANOPY_CAP: Final = 0.62
#: Pieces keep this far off the road's edge.
ROAD_PIECE_MARGIN: Final = 0.25
#: A pad's keep-out, as a multiple of its authored scale.
PAD_REACH: Final = 1.4
#: The road's walk.
ROAD_STEP_METERS: Final = 1.5
#: How the recipe's edge words map to the generator's distance fields.
EDGE_FIELD: Final[Mapping[str, str]] = {
    "water": "water",
    "biome": "region_edge",
    "road": "road",
    "set_piece": "set_piece",
}
#: Sheet object ids, in the order the record lists them.
SHEET_NAMES: Final = ("clutter", "forage", "plants")

#: The hosts run this generator for the sim, seeded from the layout's seed.
type Rand = Callable[[], float]


def mulberry32(seed: int) -> Rand:
    """The hosts run the same generator, so a shared name is worth the note."""

    state = seed & 0xFFFFFFFF

    def rand() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        t = state
        t = (t ^ (t >> 15)) * (t | 1) & 0xFFFFFFFF
        t = (t ^ (t + ((t ^ (t >> 7)) * (t | 61) & 0xFFFFFFFF))) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0

    return rand


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
    #: The grove or the host this entity came with, or None for a lone one.
    cluster: str | None = None
    #: The set-piece instance this entity is a member of, or None.
    set_piece: str | None = None


@dataclass(frozen=True, slots=True)
class SetPieceRecord:
    instance_id: str
    set_piece_id: str
    x: float
    z: float
    clearing_radius_meters: float


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
    plate_cells: int
    splat_png: bytes
    #: The biome-weight plate: R, G, B are the non-base biomes in declaration
    #: order, hard-edged; the base is whatever is left. Alpha is always opaque,
    #: because a browser premultiplies an image by its alpha on decode.
    biome_splat_png: bytes
    #: Share of the square each biome actually got, by id.
    biome_shares: dict[str, float]
    counts: dict[str, int]
    set_pieces: tuple[SetPieceRecord, ...]
    #: Per object: the tally of the placement and the pattern measurement.
    report: dict[str, dict[str, object]]
    #: What the generator refused: a quota it could not meet, a set piece
    #: with no site, a cluster that did not cluster. ``check_layout`` repeats
    #: them, so a refused world never reaches the manifest.
    refusals: tuple[str, ...]

    @property
    def cell_meters(self) -> float:
        return self.size_meters / self.plate_cells

    def as_record(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "size_meters": round(self.size_meters, 3),
            "cell_meters": round(self.cell_meters, 4),
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
                    **({"cluster": entity.cluster} if entity.cluster is not None else {}),
                    **({"set_piece": entity.set_piece} if entity.set_piece is not None else {}),
                }
                for entity in self.entities
            ],
            "set_pieces": [
                {
                    "id": piece.instance_id,
                    "set_piece": piece.set_piece_id,
                    "x": piece.x,
                    "z": piece.z,
                    "clearing_radius_meters": piece.clearing_radius_meters,
                }
                for piece in self.set_pieces
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
            "report": {key: dict(value) for key, value in sorted(self.report.items())},
        }


# --- the binding ------------------------------------------------------------


def _scatter_radius(package: Package, prop: Prop) -> float:
    """Separation is not collision: grass has no footprint but still must not stack."""

    footprint = package.meters(prop.footprint_radius_units)
    return max(footprint, 0.5 * package.meters(prop.shadow_width_units))


def _region_index(package: Package) -> dict[str, int]:
    """The base biome is -1; the others are the plate channels in order."""

    return {
        biome.biome_id: (-1 if index == 0 else index - 1)
        for index, biome in enumerate(package.biomes)
    }


def _habitat(
    placement: Placement,
    regions: Mapping[str, int],
    *,
    keep_out: tuple[tuple[str, float], ...] = (),
    in_clearings: bool = False,
) -> HabitatSpec:
    edge = placement.edge
    height = placement.height
    return HabitatSpec(
        region_weights=tuple(
            (regions[biome_id], weight) for biome_id, weight in sorted(placement.habitat.items())
        ),
        edge=(
            EdgeSpec(
                field=EDGE_FIELD[edge.of],
                peak_meters=edge.within_meters,
                falloff_meters=edge.falloff_meters,
                outside=edge.outside,
            )
            if edge is not None
            else None
        ),
        height=(
            HeightBand(low=height.min, high=height.max, falloff=height.falloff)
            if height is not None
            else None
        ),
        keep_out=keep_out,
        in_clearings=in_clearings,
    )


def _process(
    placement: Placement,
) -> PoissonProcess | ClusterProcess | AttachedProcess | SpacedProcess:
    if placement.cluster is not None:
        return ClusterProcess(
            parents_per_100m2=placement.cluster.parents_per_100m2,
            mean_size=placement.cluster.mean_size,
            radius_meters=placement.cluster.radius_meters,
        )
    if placement.near is not None:
        return AttachedProcess(
            host_object_id=placement.near.host,
            radius_meters=placement.near.radius_meters,
            mean_size=placement.near.mean,
            chance=placement.near.chance,
        )
    if placement.density_per_100m2 is not None:
        return PoissonProcess(placement.density_per_100m2)
    assert placement.spacing_meters is not None
    return SpacedProcess(placement.spacing_meters)


def _object(
    object_id: str,
    placement: Placement,
    regions: Mapping[str, int],
    *,
    footprint: float,
    scatter: float,
    keep_out: tuple[tuple[str, float], ...] = (),
    in_clearings: bool = False,
) -> ObjectSpec:
    process = _process(placement)
    # The object's own core: twice its scatter radius (two of it never stack),
    # or the authored spacing when that is wider. A spaced object's grid is
    # its spacing already.
    spacing = 0.0 if isinstance(process, SpacedProcess) else 2.0 * scatter
    if placement.spacing_meters is not None and not isinstance(process, SpacedProcess):
        spacing = max(spacing, placement.spacing_meters)
    return ObjectSpec(
        object_id=object_id,
        process=process,
        habitat=_habitat(placement, regions, keep_out=keep_out, in_clearings=in_clearings),
        chance=placement.chance,
        spacing_meters=spacing,
        footprint_radius_meters=footprint,
        avoid=tuple(AvoidRule(rule.target, rule.radius_meters) for rule in placement.avoid),
        quota=Quota(placement.min_per_world, placement.max_per_world),
        clearing_radius_meters=placement.clearing_radius_meters,
    )


class _PlacedCell(Protocol):
    @property
    def placement(self) -> Placement | None: ...


class _Sheet(Protocol):
    @property
    def placement(self) -> Placement: ...

    @property
    def cells(self) -> Sequence[_PlacedCell]: ...

    def cells_for(self, biome_id: str) -> tuple[int, ...]: ...


def _sheets(package: Package) -> list[tuple[str, _Sheet]]:
    out: list[tuple[str, _Sheet]] = []
    if package.clutter is not None:
        out.append(("clutter", package.clutter))
    if package.forage is not None:
        out.append(("forage", package.forage))
    if package.plants is not None:
        out.append(("plants", package.plants))
    return out


def _objects(
    package: Package, regions: Mapping[str, int], road_keep_out: float
) -> list[ObjectSpec]:
    road: tuple[tuple[str, float], ...] = (("road", road_keep_out),) if package.road else ()
    objects: list[ObjectSpec] = []
    for prop in package.props:
        if prop.placement is None:
            continue
        footprint = package.meters(prop.footprint_radius_units)
        objects.append(
            _object(
                prop.prop_id,
                prop.placement,
                regions,
                footprint=footprint,
                scatter=_scatter_radius(package, prop),
                keep_out=(("road", road_keep_out + footprint),) if package.road else (),
            )
        )
    mob = package.mob
    if mob.placement is not None:
        objects.append(
            _object(
                mob.actor_id,
                mob.placement,
                regions,
                footprint=package.meters(mob.footprint_radius_units),
                scatter=package.meters(mob.shadow_width_units) * 0.5,
                keep_out=road,
            )
        )
    for name, sheet in _sheets(package):
        objects.append(
            _object(
                name,
                sheet.placement,
                regions,
                footprint=0.0,
                scatter=0.0,
                keep_out=road,
                in_clearings=name == "clutter",
            )
        )
        for index, cell in enumerate(sheet.cells):
            if cell.placement is None:
                continue
            objects.append(
                _object(
                    f"{name}/{index}",
                    cell.placement,
                    regions,
                    footprint=0.0,
                    scatter=0.0,
                    keep_out=road,
                    in_clearings=name == "clutter",
                )
            )
    return objects


def _ordered(package: Package, objects: list[ObjectSpec]) -> tuple[ObjectSpec, ...]:
    """The generator's order, then the author's where it says so, re-checked."""

    members = frozenset(
        member.prop for piece in package.world.set_pieces for member in piece.members
    )
    ordered = list(worldgen.placement_order(objects, also_known=members))
    authored = package.world.population_order
    if not authored:
        return tuple(ordered)
    rank = {object_id: index for index, object_id in enumerate(authored)}
    ordered.sort(key=lambda obj: rank.get(obj.object_id, len(rank)))
    seen: set[str] = set()
    for obj in ordered:
        needs = [rule.object_id for rule in obj.avoid]
        if isinstance(obj.process, AttachedProcess):
            needs.append(obj.process.host_object_id)
        for other in needs:
            if other not in seen and any(o.object_id == other for o in ordered):
                raise SourceError(
                    f"population.order places {obj.object_id} before {other}, which it needs"
                )
        seen.add(obj.object_id)
    return tuple(ordered)


def _set_pieces(package: Package, regions: Mapping[str, int]) -> tuple[SetPieceSpec, ...]:
    out: list[SetPieceSpec] = []
    for piece in package.world.set_pieces:
        out.append(
            SetPieceSpec(
                set_piece_id=piece.set_piece_id,
                members=tuple(
                    SetPieceMember(object_id=member.prop, dx=member.dx, dz=member.dz, mark=index)
                    for index, member in enumerate(piece.members)
                ),
                clearing_radius_meters=piece.clearing_radius_meters,
                count_per_world=piece.count,
                at=piece.at,
                band_meters=piece.band_meters,
                required_regions=(
                    frozenset({regions[piece.biome]}) if piece.biome is not None else frozenset()
                ),
            )
        )
    return tuple(out)


def _member_footprints(package: Package) -> tuple[tuple[str, float], ...]:
    """A member's reach in the shared core: its footprint, or its pad's, whichever is wider."""

    reach: dict[str, float] = {}
    for piece in package.world.set_pieces:
        for member in piece.members:
            prop = package.prop(member.prop)
            radius = package.meters(prop.footprint_radius_units)
            if member.pad_scale is not None and piece.pad_decal is not None:
                radius = max(radius, PAD_REACH * member.pad_scale)
            reach[member.prop] = max(reach.get(member.prop, 0.0), radius)
    return tuple(sorted(reach.items()))


def _road_polyline(
    package: Package, fields: WorldFields, *, clear_radius: float
) -> list[tuple[float, float]]:
    """One wandering track out of the spawn clearing. It ends where the land does.

    It starts at the edge of the clearing, not at its centre, and it is pulled
    back toward its outbound heading so it wanders without doubling back. The
    road is a polyline here and a red mask in the splat; the shader tears its
    edge. Where a plank road would need a ribbon mesh with its texture aligned
    to travel, a dirt track does not, which is why v0 has a dirt track.
    """

    road = package.road
    if road is None:
        return []
    stream = Stream.of(package.world.seed, "road", "walk")
    half = package.world.size_meters / 2.0
    heading = stream.unit(0) * math.tau
    outbound = heading
    x = math.cos(heading) * clear_radius * 0.75
    z = math.sin(heading) * clear_radius * 0.75
    points = [(round(x, 3), round(z, 3))]
    travelled = 0.0
    step = 1
    while travelled < road.length_meters:
        heading += (stream.unit(step) - 0.5) * 0.5 + (outbound - heading) * 0.12
        step += 1
        x += math.cos(heading) * ROAD_STEP_METERS
        z += math.sin(heading) * ROAD_STEP_METERS
        if abs(x) > half - 3.0 or abs(z) > half - 3.0 or not fields.on_land(x, z, 1.0):
            break
        points.append((round(x, 3), round(z, 3)))
        travelled += ROAD_STEP_METERS
    return points


def _jitter(package: Package, unit: float) -> float:
    """A ground piece turns at most the look contract's jitter from facing the camera."""

    return round((unit * 2.0 - 1.0) * package.look.ground_piece_jitter_degrees, 2)


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


def _fields(package: Package) -> tuple[WorldFields, RegionField, Coast]:
    world = package.world
    size = world.size_meters
    clearing = world.spawn.clearing_radius_meters
    regions = RegionField(
        seed=world.seed,
        shares=[biome.share for biome in package.biomes[1:]],
        lattice=worldgen.REGION_LATTICE,
        islet_lattice=world.biomes.islet_lattice,
        islet_share=world.biomes.islet_share,
        clear=(0.5, 0.5, clearing * SPAWN_REACH / size),
    )
    coast = Coast(
        seed=world.seed,
        size_meters=size,
        land_share=world.landmass.land_share,
        lattice=world.landmass.coast_noise_lattice,
        crinkle_weight=world.landmass.coast_crinkle,
        bumps=[Bump(0.0, 0.0, clearing * SPAWN_REACH, 1.5)],
    )
    octave = world.landmass.height_octave_lattice
    fields = WorldFields.build(
        size_meters=size,
        plate_cells=plate_cells(size),
        regions=regions,
        coast=coast,
        height_octave=ValueNoise(world.seed * 31 + 5, octave) if octave > 0 else None,
        height_octave_weight=world.landmass.height_octave_weight,
        shore_margin_meters=world.landmass.shore_margin_meters,
    )
    return fields, regions, coast


def build_layout(package: Package) -> Layout:
    world = package.world
    size = world.size_meters
    seed = world.seed
    spawn = world.spawn
    clearing = spawn.clearing_radius_meters
    fields, region_field, coast = _fields(package)
    regions = _region_index(package)

    road_points = _road_polyline(package, fields, clear_radius=clearing)
    road_width = package.road.width_meters if package.road is not None else 0.0
    fields.add_polyline_distance("road", road_points)

    objects = _ordered(package, _objects(package, regions, road_width / 2.0 + ROAD_PIECE_MARGIN))
    spec = WorldSpec(
        seed=seed,
        size_meters=size,
        set_pieces=_set_pieces(package, regions),
        objects=objects,
        member_footprints=_member_footprints(package),
    )
    refusals: list[str] = list(worldgen.check_spec(spec, fields))
    plan = worldgen.plan_world(spec, fields)
    refusals.extend(plan.refusals)

    entities, counts, set_pieces, pads = _entities(package, plan)
    clutter, forage, plants = _pieces(package, plan, fields, regions)
    decals = (
        _pad_decals(package, pads)
        + _skirt_decals(package, entities)
        + _wet_decals(package, fields, entities, clearing=clearing)
    )
    cells = fields.plate.cells
    splat = _render_splat(
        package, fields, entities=entities, road_points=road_points, road_width=road_width
    )
    biome_splat = _render_biome_splat(fields)

    reports = [
        worldgen.measure_object(spec, fields, obj, plan.points[obj.object_id]) for obj in objects
    ]
    refusals.extend(worldgen.refuse_patterns(spec, reports))
    report = _report(plan, reports)

    assert spawn.spawn is not None
    return Layout(
        seed=seed,
        size_meters=size,
        player_spawn=spawn.spawn,
        camp_position=(0.0, 0.0),
        clear_radius_meters=clearing,
        entities=tuple(entities),
        decals=tuple(decals),
        road_id=package.road.road_id if package.road is not None and road_points else None,
        road_width_meters=road_width,
        road=tuple(road_points),
        clutter=tuple(clutter),
        forage=tuple(forage),
        plants=tuple(plants),
        land_share=coast.solved_share,
        plate_cells=cells,
        splat_png=splat,
        biome_splat_png=biome_splat,
        biome_shares={
            biome.biome_id: region_field.shares[regions[biome.biome_id]] for biome in package.biomes
        },
        counts=counts,
        set_pieces=tuple(set_pieces),
        report=report,
        refusals=tuple(refusals),
    )


def _entities(
    package: Package, plan: WorldPlan
) -> tuple[
    list[Placed], dict[str, int], list[SetPieceRecord], list[tuple[float, float, float, str]]
]:
    """Set-piece members first, then every placed prop and mob, in object order."""

    entities: list[Placed] = []
    counts: dict[str, int] = {}
    pads: list[tuple[float, float, float, str]] = []
    set_pieces: list[SetPieceRecord] = []
    seed_s = Stream.of(package.world.seed, "entity", "seed")

    def place(
        *,
        kind: str,
        ref_id: str,
        state: str | None,
        x: float,
        z: float,
        seed: int,
        footprint: float,
        scatter: float,
        cluster: str | None = None,
        set_piece: str | None = None,
    ) -> Placed:
        prefix = {"prop": "p", "mob": "m"}.get(kind, "e")
        placed = Placed(
            entity_id=f"{prefix}{len(entities):04d}",
            kind=kind,
            ref_id=ref_id,
            state=state,
            x=round(x, 3),
            z=round(z, 3),
            seed=seed,
            footprint_radius_meters=footprint,
            scatter_radius_meters=scatter,
            cluster=cluster,
            set_piece=set_piece,
        )
        entities.append(placed)
        counts[ref_id] = counts.get(ref_id, 0) + 1
        return placed

    for site in plan.sites:
        piece = package.world.set_piece(site.set_piece_id)
        set_pieces.append(
            SetPieceRecord(
                instance_id=site.instance_id,
                set_piece_id=site.set_piece_id,
                x=site.x,
                z=site.z,
                clearing_radius_meters=site.clearing_radius_meters,
            )
        )
        for member, point in zip(piece.members, site.members, strict=True):
            prop = package.prop(member.prop)
            state = member.state or prop.baseline_state
            placed = place(
                kind="prop",
                ref_id=member.prop,
                state=state,
                x=point.x,
                z=point.z,
                seed=int(seed_s.unit(site.ordinal, point.mark, len(entities)) * 100000),
                footprint=package.meters(prop.footprint_radius_units),
                scatter=_scatter_radius(package, prop),
                set_piece=site.instance_id,
            )
            if member.pad_scale is not None and piece.pad_decal is not None:
                pads.append((point.x, point.z, member.pad_scale, placed.entity_id))
    props = {prop.prop_id: prop for prop in package.props}
    mob = package.mob
    for object_id, points in plan.points.items():
        if object_id in props:
            prop = props[object_id]
            footprint = package.meters(prop.footprint_radius_units)
            scatter = _scatter_radius(package, prop)
            for sample in points:
                instance_seed = int(sample.marks[0] * 100000)
                place(
                    kind="prop",
                    ref_id=object_id,
                    state=variant_state(prop, instance_seed),
                    x=sample.x,
                    z=sample.z,
                    seed=instance_seed,
                    footprint=footprint,
                    scatter=scatter,
                    cluster=sample.cluster_id,
                )
        elif object_id == mob.actor_id:
            for sample in points:
                place(
                    kind="mob",
                    ref_id=object_id,
                    state=None,
                    x=sample.x,
                    z=sample.z,
                    seed=int(sample.marks[0] * 100000),
                    footprint=package.meters(mob.footprint_radius_units),
                    scatter=package.meters(mob.shadow_width_units) * 0.5,
                    cluster=sample.cluster_id,
                )
    return entities, counts, set_pieces, pads


def _pieces(
    package: Package, plan: WorldPlan, fields: WorldFields, regions: Mapping[str, int]
) -> tuple[list[GroundPiece], list[GroundPiece], list[GroundPiece]]:
    """The sheets' points become cells: the sheet object draws a cell allowed on
    its biome (one with no placement of its own), a cell object is its cell."""

    by_region = {index: biome_id for biome_id, index in regions.items()}
    out: dict[str, list[GroundPiece]] = {name: [] for name in SHEET_NAMES}
    for name, sheet in _sheets(package):
        overridden = {index for index, cell in enumerate(sheet.cells) if cell.placement is not None}
        for object_id, points in plan.points.items():
            if object_id == name:
                fixed: int | None = None
            elif object_id.startswith(f"{name}/"):
                fixed = int(object_id.split("/", 1)[1])
            else:
                continue
            for point in points:
                if fixed is None:
                    biome_id = by_region[fields.region_at(point.x, point.z)]
                    allowed = [c for c in sheet.cells_for(biome_id) if c not in overridden]
                    if not allowed:
                        continue
                    cell = allowed[int(point.marks[1] * len(allowed)) % len(allowed)]
                else:
                    cell = fixed
                out[name].append(
                    {
                        "cell": cell,
                        "x": point.x,
                        "z": point.z,
                        "rotation_degrees": _jitter(package, point.marks[2]),
                        "scale": round(0.8 + point.marks[3] * 0.35, 3),
                    }
                )
        out[name].sort(key=lambda piece: (piece["z"], piece["x"], piece["cell"]))
    return out["clutter"], out["forage"], out["plants"]


def _pad_decals(package: Package, pads: list[tuple[float, float, float, str]]) -> list[GroundDecal]:
    """A worn pad under a set-piece member that asks for one: the reference genre's base disc."""

    stream = Stream.of(package.world.seed, "decal", "pad")
    out: list[GroundDecal] = []
    for index, (x, z, scale, entity_id) in enumerate(pads):
        piece = next(
            piece
            for piece in package.world.set_pieces
            if piece.pad_decal is not None
            and any(member.pad_scale is not None for member in piece.members)
        )
        decal_id = piece.pad_decal
        assert decal_id is not None
        out.append(
            {
                "decal": decal_id,
                "under": entity_id,
                "x": round(x, 3),
                "z": round(z, 3),
                "rotation_degrees": _jitter(package, stream.unit(index)),
                "scale": round(scale, 3),
            }
        )
    return out


def _skirt_decals(package: Package, entities: Sequence[Placed]) -> list[GroundDecal]:
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
    stream = Stream.of(package.world.seed, "decal", "skirt")
    out: list[GroundDecal] = []
    for index, entity in enumerate(entities):
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
                "rotation_degrees": _jitter(package, stream.unit(index)),
                "scale": round(laid / decal.width_meters, 3),
            }
        )
    return out


def _wet_decals(
    package: Package, fields: WorldFields, entities: Sequence[Placed], *, clearing: float
) -> list[GroundDecal]:
    """Standing water for a weather condition, scattered once at world generation.

    A puddle is a decal that is only ever *seen* under rain: the runtime fades
    it with wetness, so a dry world shows none and a wet one shows the same
    hollows every time. Placed off the spawn clearing, off the shore and clear
    of every prop's scatter radius, so no puddle sits under a trunk.
    """

    out: list[GroundDecal] = []
    size = package.world.size_meters
    half = size / 2.0
    area_hundreds = (size * size) / 100.0
    index = PointIndex(2.0 * max((e.scatter_radius_meters for e in entities), default=0.0) + 1.0)
    for entity in entities:
        index.add(entity.x, entity.z, entity.scatter_radius_meters, entity.ref_id)
    shore = package.world.landmass.shore_margin_meters
    for condition in package.weather:
        wet = condition.wet
        if wet is None:
            continue
        decal = next((d for d in package.decals if d.decal_id == wet.decal_id), None)
        if decal is None:
            continue
        stream = Stream.of(package.world.seed, "decal", "wet", condition.condition_id)
        target = round(wet.per_100_sqm * area_hundreds)
        reach = max(decal.width_meters, decal.height_meters) * 0.6
        accepted = 0
        for attempt in range(target * 30):
            if accepted >= target:
                break
            x = (stream.unit(attempt, 0) * 2.0 - 1.0) * (half - 1.5)
            z = (stream.unit(attempt, 1) * 2.0 - 1.0) * (half - 1.5)
            if math.hypot(x, z) < clearing + reach:
                continue
            if not fields.on_land(x, z, shore):
                continue
            if index.hits(x, z, reach):
                continue
            out.append(
                {
                    "decal": decal.decal_id,
                    "condition": condition.condition_id,
                    "x": round(x, 3),
                    "z": round(z, 3),
                    "rotation_degrees": _jitter(package, stream.unit(attempt, 2)),
                    "scale": round(0.8 + stream.unit(attempt, 3) * 0.6, 3),
                }
            )
            accepted += 1
    return out


def _render_splat(
    package: Package,
    fields: WorldFields,
    *,
    entities: Sequence[Placed],
    road_points: Sequence[tuple[float, float]],
    road_width: float,
) -> bytes:
    """R is the road, G is under-canopy darkening, B is reserved, A is land.

    The biomes live on their own plate; this one holds the world's structure.
    Row 0 is minimum z. A host loads this with ``flipY = false`` and samples it
    as data, never as colour, so it carries no colour space.
    """

    plate = Plate(fields.plate.cells, fields.plate.size_meters)
    plate.fill_channel(3, ((255 if value >= 0 else 0 for value in row) for row in fields.land.rows))
    # A soft disc of shade under anything with a canopy, painted at plate
    # resolution so the shader gets it for free with the biome sample. An
    # attribute of the prop, not a family rule, and only on the looks a
    # placed instance may start as: a stump casts none.
    props = {prop.prop_id: prop for prop in package.props}
    for entity in entities:
        prop = props.get(entity.ref_id)
        if prop is None or entity.kind != "prop" or prop.canopy_radius_meters <= 0.0:
            continue
        starts = set(prop.variants.states) if prop.variants is not None else {prop.baseline_state}
        if entity.state not in starts:
            continue
        plate.stamp_disc(
            1, entity.x, entity.z, prop.canopy_radius_meters, gain=CANOPY_GAIN, cap=CANOPY_CAP
        )
    if road_points and road_width > 0.0:
        plate.stamp_polyline(0, list(road_points), road_width, 255)
    return plate.png()


def _render_biome_splat(fields: WorldFields) -> bytes:
    """R, G, B are the non-base biomes in declaration order; the base is the rest.

    A hard mask, like the world splat: the shader erodes each channel with
    noise and feathers it, and feathering twice would only blur the boundary
    the noise is meant to break up. Alpha is opaque everywhere: it is not a
    channel, because an image's colour is premultiplied by its alpha on decode.
    """

    plate = Plate(fields.plate.cells, fields.plate.size_meters)
    for channel in range(3):
        plate.fill_channel(
            channel,
            ((255 if value == channel else 0 for value in row) for row in fields.regions.rows),
        )
    plate.fill_constant(3, 255)
    return plate.png()


def _report(plan: WorldPlan, reports: Sequence[PatternReport]) -> dict[str, dict[str, object]]:
    by_id = {report.object_id: report for report in reports}
    out: dict[str, dict[str, object]] = {}
    for object_id, tally in plan.tallies.items():
        report = by_id[object_id]
        out[object_id] = {
            "placed": tally.placed,
            "candidates": tally.candidates,
            "reserve": tally.reserve,
            "dropped_own_core": tally.dropped_own_core,
            "dropped_neighbour": tally.dropped_neighbour,
            "truncated": tally.truncated,
            "topped_up": tally.topped_up,
            "support_area_m2": round(report.support_area_m2, 1),
            "mean_nn_meters": report.mean_nn_meters,
            "null_mean_nn_meters": report.null_mean_nn_meters,
            "r_mc": report.r_mc,
            "k_ratio": report.k_ratio,
            "verdict": report.verdict,
        }
    return out


def check_layout(package: Package, layout: Layout) -> list[str]:
    """Refusals, not warnings. Every one of these means the world is unusable."""

    problems: list[str] = list(layout.refusals)
    props = {prop.prop_id: prop for prop in package.props}
    for entity in layout.entities:
        if entity.kind == "prop" and entity.state is not None:
            prop = props.get(entity.ref_id)
            if prop is not None and entity.state not in prop.states:
                problems.append(f"{entity.entity_id} stands as undeclared look {entity.state!r}")
    half = layout.size_meters / 2.0
    entities = layout.entities
    widest = max((e.scatter_radius_meters for e in entities), default=0.0)
    index = PointIndex(2.0 * widest + 1.0)
    by_key: dict[tuple[float, float, str], Placed] = {}
    for entity in entities:
        if abs(entity.x) > half or abs(entity.z) > half:
            problems.append(f"{entity.entity_id} lies outside the world square")
        index.add(entity.x, entity.z, entity.scatter_radius_meters, entity.entity_id)
        by_key[(entity.x, entity.z, entity.entity_id)] = entity
    footprints = {entity.entity_id: entity.footprint_radius_meters for entity in entities}
    refs = {entity.entity_id: entity.ref_id for entity in entities}
    spacing = {entity.entity_id: 2.0 * entity.scatter_radius_meters for entity in entities}

    def gap(a: str, b: str) -> float:
        # The generator's own rules: two of one object keep their spacing, two
        # of different objects keep their footprints apart.
        if refs[a] == refs[b]:
            return min(spacing[a], spacing[b])
        return footprints[a] + footprints[b]

    for (ax, az, aid), (bx, bz, bid) in index.pairs_closer_than(gap):
        a = by_key[(ax, az, aid)]
        b = by_key[(bx, bz, bid)]
        if a.set_piece is not None and a.set_piece == b.set_piece:
            continue  # authored offsets are the author's
        distance = math.hypot(ax - bx, az - bz)
        problems.append(f"{aid} and {bid} overlap: {distance:.3f} < {gap(aid, bid):.3f}")
        if len(problems) > 40:
            break
    clearings = [
        (piece.x, piece.z, piece.clearing_radius_meters, piece.instance_id)
        for piece in layout.set_pieces
    ]
    for entity in entities:
        for x, z, radius, instance in clearings:
            inside = math.hypot(entity.x - x, entity.z - z) < radius
            if inside and entity.set_piece != instance:
                problems.append(f"{entity.entity_id} stands inside the clearing of {instance}")
    spawn_distance = math.hypot(layout.player_spawn[0], layout.player_spawn[1])
    if spawn_distance > layout.clear_radius_meters:
        problems.append("the player spawns outside the spawn clearing")
    return problems


__all__ = [
    "SPLAT_CELL_METERS",
    "GroundDecal",
    "GroundPiece",
    "Layout",
    "Placed",
    "SetPieceRecord",
    "build_layout",
    "check_layout",
    "mulberry32",
    "polyline_distance",
    "variant_state",
]
