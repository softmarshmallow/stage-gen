"""Small synthetic worlds for the component tests. Nothing here names a game."""

from __future__ import annotations

from stage_gen.components.worldgen import (
    AttachedProcess,
    Bump,
    ClusterProcess,
    Coast,
    EdgeSpec,
    HabitatSpec,
    ObjectSpec,
    PoissonProcess,
    Quota,
    RegionField,
    SetPieceMember,
    SetPieceSpec,
    SpacedProcess,
    ValueNoise,
    WorldFields,
    WorldSpec,
    placement_order,
    plate_cells,
)

SIZE = 128.0
SEED = 7
ANALYSIS = 64

EVERYWHERE = HabitatSpec(((-1, 1.0), (0, 1.0), (1, 1.0)))
BASE_ONLY = HabitatSpec(((-1, 1.0),))
REGION_MIX = HabitatSpec(((-1, 1.0), (0, 0.2), (1, 0.6)))
SHORE = HabitatSpec(((-1, 1.0), (0, 1.0), (1, 1.0)), edge=EdgeSpec("water", 4.0, 2.0, 0.0))


def regions(seed: int = SEED, *, size: float = SIZE) -> RegionField:
    return RegionField(
        seed=seed,
        shares=[0.25, 0.15],
        islet_lattice=14,
        islet_share=0.3,
        clear=(0.5, 0.5, 5.0 * 2.5 / size),
    )


def coast(seed: int = SEED, *, size: float = SIZE, land_share: float = 0.6) -> Coast:
    return Coast(
        seed=seed,
        size_meters=size,
        land_share=land_share,
        lattice=6,
        crinkle_weight=0.3,
        bumps=[Bump(0.0, 0.0, 12.0, 1.5)],
    )


def fresh_fields(seed: int = SEED, *, size: float = SIZE, land_share: float = 0.6) -> WorldFields:
    """A new fields object every call: ``plan_world`` adds clearings to the one it is given."""

    return WorldFields.build(
        size_meters=size,
        plate_cells=plate_cells(size),
        regions=regions(seed, size=size),
        coast=coast(seed, size=size, land_share=land_share),
        height_octave=ValueNoise(seed * 31 + 5, 12),
        height_octave_weight=0.25,
        shore_margin_meters=1.5,
        analysis_cells=ANALYSIS,
    )


def flat_fields(seed: int = SEED, *, size: float = SIZE) -> WorldFields:
    """Almost all land, one region: the null the pattern statistics are proven on."""

    return WorldFields.build(
        size_meters=size,
        plate_cells=plate_cells(size),
        regions=RegionField(seed=seed, shares=[]),
        coast=coast(seed, size=size, land_share=0.97),
        height_octave=None,
        height_octave_weight=0.0,
        shore_margin_meters=0.5,
        analysis_cells=ANALYSIS,
    )


CAMP = SetPieceSpec(
    "camp",
    (SetPieceMember("tent", -2.2, -1.4), SetPieceMember("fire", 1.4, 0.9)),
    5.0,
    1,
    "origin",
    (0.0, 0.0),
    frozenset({-1}),
)
RING = SetPieceSpec(
    "ring",
    tuple(
        SetPieceMember("stone", dx, dz)
        for dx, dz in ((0.0, -2.0), (1.9, -0.6), (1.2, 1.6), (-1.2, 1.6), (-1.9, -0.6))
    ),
    3.0,
    2,
    "band",
    (20.0, 50.0),
    frozenset(),
)


def objects(*, tree_density: float = 0.4, tree_chance: float = 0.9) -> tuple[ObjectSpec, ...]:
    return placement_order(
        [
            ObjectSpec(
                "tree",
                ClusterProcess(tree_density, 8.0, 5.0),
                REGION_MIX,
                chance=tree_chance,
                spacing_meters=1.6,
                footprint_radius_meters=0.4,
                quota=Quota(10, 400),
            ),
            ObjectSpec(
                "stone",
                PoissonProcess(0.5),
                EVERYWHERE,
                spacing_meters=1.2,
                footprint_radius_meters=0.6,
            ),
            ObjectSpec(
                "reed",
                PoissonProcess(2.0),
                SHORE,
                spacing_meters=0.8,
            ),
            ObjectSpec("grass", SpacedProcess(2.5), EVERYWHERE),
            ObjectSpec(
                "fern",
                AttachedProcess("tree", 2.0, 1.5, 0.6),
                EVERYWHERE,
                spacing_meters=0.5,
            ),
            ObjectSpec(
                "rare",
                PoissonProcess(0.08),
                BASE_ONLY,
                spacing_meters=4.0,
                footprint_radius_meters=0.5,
                quota=Quota(2, 2),
            ),
        ]
    )


def spec(seed: int = SEED, *, size: float = SIZE, **kwargs: float) -> WorldSpec:
    return WorldSpec(
        seed,
        size,
        (CAMP, RING),
        objects(**kwargs),
        (("tent", 1.2), ("fire", 1.0), ("stone", 0.6)),
    )
