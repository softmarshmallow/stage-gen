"""Exact-current compound map-generation contract (``game-map-v10``).

The authored document states what a map should be: its art direction, its layers and
references, the climbable roster it can draw, and the terrain it wants generated. It carries
no geometry. Terrain shape is produced by a named generator into a ``map-terrain-v1``
artifact, exactly the way a layer's artwork is produced into a PNG, and the two are checked
against each other by :func:`validate_generated_terrain`.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import Field, ValidationError, field_validator, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    GAME_ID_PATTERN,
    KEBAB_ID_PATTERN,
    SHA256_PATTERN,
    SNAKE_ID_PATTERN,
    AuthoredContractLoadError,
    canonical_contract_json,
    normalized_text,
    parse_toml_contract,
    portable_relative_path,
    unique_values,
)
from stage_gen.components.painted_terrain import (
    PAINTED_TERRAIN_MAX_ROWS,
    PAINTED_TERRAIN_MIN_SEGMENT_COLUMNS,
    PaintedTerrainGround,
    painted_terrain_segments,
)
from stage_gen.media import LOOP_METHODS, LoopConstruction

PREPARED_GAME_MAP_SCHEMA_VERSION = 10
#: Generated terrain geometry is its own artifact contract, produced by a generator the map
#: names and never written back into the authored document.
PREPARED_MAP_TERRAIN_SCHEMA_VERSION = 1
MAX_UNASSISTED_TERRAIN_RISE_TILES = 2
#: Per role. Both roles together always fit one provider image, so a map never
#: schedules more than one climbable atlas.
MAX_CLIMBABLE_VARIANTS_PER_ROLE = 3


def _bottom_contiguous_heights(occupancy: list[str]) -> list[int]:
    """Return gameplay floor heights while ignoring disconnected upper platforms."""

    heights: list[int] = []
    for column in range(len(occupancy[0])):
        height = 0
        row = len(occupancy) - 1
        while row >= 0 and occupancy[row][column] == "1":
            height += 1
            row -= 1
        heights.append(height)
    return heights


class PreparedMapView(PersistedContractModel):
    """What the artwork is. Every field here directs generation and enters the image cache key."""

    profile: Literal["side_view_2d"]
    gameplay_space: Literal["side_plane"]


class PreparedMapCamera(PersistedContractModel):
    """What the runtime does with the artwork. Nothing here reaches the image model.

    This used to live in ``[view]`` as ``camera_behavior`` and ``scroll_axis``, which put a
    runtime fact inside the generation digest: editing the camera re-billed every map image even
    though no prompt changed. The art-direction half of that claim was always carried better by
    ``continuity.seamless_axis``, which states the concrete obligation -- every layer must be a
    verified horizontal repeat unit -- rather than restating the camera it follows from.

    ``follow_axes`` is the whole extension point. A side-scroller declares ``["x"]``, a map with
    routes stacked above one another ``["x", "y"]``, a climbing tower ``["y"]``, and a
    single-screen arena an empty list. Consumers that cannot honour an axis must reject the map
    rather than silently ignoring it.
    """

    mode: Literal["player_follow"]
    follow_axes: list[Literal["x", "y"]] = Field(max_length=2)

    @field_validator("follow_axes")
    @classmethod
    def validate_follow_axes(cls, value: list[str]) -> list[str]:
        unique_values(value, "camera follow_axes")
        if value != [axis for axis in ("x", "y") if axis in value]:
            raise ValueError("camera follow_axes must use canonical x, y order")
        return value


class PreparedMapContinuity(PersistedContractModel):
    seamless_axis: Literal["x"]
    # How a layer that does not already loop is made to loop. Admission runs first either way, so a
    # layer the image model already returned as a clean repeat unit costs nothing here.
    #
    # `mirror_repeat` is the baseline: appending a horizontal mirror makes every join a reflection,
    # which is continuous by definition, so it cannot fail and needs no provider. It doubles the
    # period and the content reads back on itself.
    #
    # `generated_bridge` appends one generated span that carries the tail into the head. It costs
    # one image operation per layer that needs it and produces no mirrored content.
    #
    # `seam_repaint` repaints the wrap itself after relocating it to the middle of the canvas the
    # provider sees. It costs one image operation, leaves the period unchanged, and is the only
    # construction whose join the provider paints through rather than meets.
    #
    # `fold_repaint` repaints a mirror's reflection axis so the content stops reading back on
    # itself, leaving the wrap fold untouched.
    #
    # The repaint constructions replace source pixels rather than appending, so the generated
    # layer is not recoverable from a map that selects them.
    loop_construction: LoopConstruction
    # Construction used when the selected one cannot be completed - a provider return that is not
    # a displaced copy of what we sent, so no single translation lands it. Must be deterministic:
    # a fallback that can itself fail is not a fallback.
    loop_fallback: LoopConstruction = "mirror_repeat"

    @field_validator("loop_fallback")
    @classmethod
    def validate_loop_fallback(cls, value: LoopConstruction) -> LoopConstruction:
        if LOOP_METHODS[value].is_generative:
            raise ValueError(
                "loop_fallback must be a deterministic construction; "
                f"{value} needs a provider operation and can fail the same way"
            )
        return value


class PreparedMapLayerPresentation(PersistedContractModel):
    """Consumer-only depth treatment applied without changing generated pixels."""

    contrast: float = Field(ge=0.25, le=2.0)
    saturation: float = Field(ge=0.0, le=2.0)
    atmosphere_color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    atmosphere_strength: float = Field(ge=0.0, le=1.0)
    detail_blur_screen_pixels: float = Field(ge=0.0, le=4.0)

    @field_validator("atmosphere_color")
    @classmethod
    def normalize_atmosphere_color(cls, value: str) -> str:
        return value.lower()


class PreparedMapReference(PersistedContractModel):
    reference_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    source: str
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    rights_status: Literal["unreviewed", "restricted", "redistribution-approved"]
    rights_basis: list[str] = Field(min_length=1, max_length=16)

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        source = portable_relative_path(value, "map reference source")
        if not source.startswith("references/"):
            raise ValueError("map references must live under references/")
        if PurePosixPath(source).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("map references must use PNG, JPEG, or WebP")
        return source

    @field_validator("rights_basis")
    @classmethod
    def validate_rights_basis(cls, value: list[str]) -> list[str]:
        normalized = [normalized_text(entry, "map reference rights basis") for entry in value]
        unique_values(normalized, "map reference rights basis")
        return normalized


class PreparedMapLayer(PersistedContractModel):
    layer_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    plane: Literal["background", "foreground"]
    order: int = Field(ge=0, le=7)
    parallax: float = Field(ge=0.0, le=8.0)
    alpha_mode: Literal["opaque", "transparent"]
    # Which edge of the layer's trimmed raster registers, and against which datum. `plane` stays
    # painter order only; conflating the two is how a layer ends up with no vertical intent at all.
    vertical_anchor: Literal["canvas_cover", "screen_top", "screen_bottom", "walk_surface"]
    # Optional author override, as a fraction of the layer's own trimmed height, positive pushing
    # the layer down. Omit it: the producer resolves the value from the raster it actually got,
    # because an authored fraction is a prediction about pixels that do not exist yet. An override
    # that is too small to seal a bottom-anchored layer is rejected with the measured minimum.
    vertical_offset: float | None = Field(default=None, ge=-1.0, le=1.0)
    # Optional per-layer override of the map's loop construction. Omit it to take the map default.
    # Layers within one map do not share a difficulty: a layer whose own ends already agree loops
    # under any construction, while one whose ends disagree in the source art fails under all of
    # them. Forcing a single construction across a map treats those as the same problem.
    loop_construction: LoopConstruction | None = None
    presentation: PreparedMapLayerPresentation
    prompt: str

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "map layer reference_id")
        return value

    @model_validator(mode="after")
    def validate_vertical_placement(self) -> PreparedMapLayer:
        if self.vertical_anchor == "canvas_cover":
            if self.alpha_mode != "opaque":
                raise ValueError(
                    "only the opaque base layer may claim the canvas_cover vertical anchor"
                )
            if self.vertical_offset not in (None, 0.0):
                raise ValueError("a canvas_cover layer cannot declare a vertical offset")
        elif self.alpha_mode == "opaque":
            raise ValueError("the opaque base layer must use the canvas_cover vertical anchor")
        return self

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "map layer prompt", multiline=True)


class PreparedMapGround(PersistedContractModel):
    mode: Literal["terrain-atlas-3x3-minimal-v1"]
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    # Where the generated grid sits vertically. This is an enum rather than a coordinate: the
    # deepest row bottoms out at the viewport edge, which makes a gap below the world impossible
    # instead of merely unlikely. The consumer derives its own baseline; no map declares pixels.
    vertical_fit: Literal["floor_to_screen_bottom"]
    prompt: str

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "map ground reference_id")
        return value

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "map ground prompt", multiline=True)


#: How a map's terrain is drawn. The tile atlas is the default and stays it: it is cheap,
#: it repeats forever, and every map that does not ask for anything else gets it. Painted
#: terrain is the opt-in for a map that wants custom, style-refined ground instead of
#: generic tiles, and it costs one image call per derived segment. Both modes are drawn
#: from the same generated occupancy and neither owns collision.
type PreparedGroundDirection = Annotated[
    PreparedMapGround | PaintedTerrainGround,
    Field(discriminator="mode"),
]


class PreparedMapClimbableVariant(PersistedContractModel):
    """One climbable appearance the map generates. Role is declared, never detected."""

    variant_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    prompt: str

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "map climbable variant prompt", multiline=True)


class PreparedMapClimbablePlacement(PersistedContractModel):
    climbable_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    variant_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    normalized_x: float = Field(gt=0.0, lt=1.0)
    bottom_surface: Literal["terrain"]
    rise_tiles: Literal[4]


class PreparedMapClimbable(PersistedContractModel):
    """One atlas of climbable appearances plus the instances that place them.

    A ladder carries crosswise rungs; a rope is a continuous strand. The two roles differ in
    silhouette by roughly a factor of four, so validation admits each against its own envelope
    rather than one shared band. Because the role is authored, nothing has to infer it.

    Both roles together are bounded at ``MAX_CLIMBABLE_VARIANTS_PER_ROLE * 2``, which always fits
    a single provider image, so no map ever schedules more than one climbable atlas.
    """

    mode: Literal["climbable-atlas-v1"]
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    ladders: list[PreparedMapClimbableVariant] = Field(
        default_factory=list, max_length=MAX_CLIMBABLE_VARIANTS_PER_ROLE
    )
    ropes: list[PreparedMapClimbableVariant] = Field(
        default_factory=list, max_length=MAX_CLIMBABLE_VARIANTS_PER_ROLE
    )

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "map climbable reference_id")
        return value

    @property
    def variants(self) -> list[PreparedMapClimbableVariant]:
        """Atlas order: every ladder left to right, then every rope.

        Column index is roster index; that binding is positional and unverified.
        """

        return [*self.ladders, *self.ropes]

    def role_of(self, variant_id: str) -> Literal["ladder", "rope"]:
        if any(entry.variant_id == variant_id for entry in self.ladders):
            return "ladder"
        if any(entry.variant_id == variant_id for entry in self.ropes):
            return "rope"
        raise KeyError(f"map climbable variant {variant_id} is not declared")

    @model_validator(mode="after")
    def validate_variants(self) -> PreparedMapClimbable:
        variants = self.variants
        if not variants:
            raise ValueError("map climbable must declare at least one ladder or rope variant")
        unique_values((entry.variant_id for entry in variants), "map climbable variant_id")
        return self


class PreparedMapPortalEndpoint(PersistedContractModel):
    anchor: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    normalized_x: float = Field(gt=0.0, lt=1.0)
    role: Literal["entry", "exit"]


class PreparedMapPortal(PersistedContractModel):
    mode: Literal["portal-pair-1x2-v1"]
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    prompt: str
    endpoints: list[PreparedMapPortalEndpoint] = Field(min_length=1, max_length=2)

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "map portal reference_id")
        return value

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "map portal prompt", multiline=True)

    @field_validator("endpoints")
    @classmethod
    def validate_endpoints(
        cls, value: list[PreparedMapPortalEndpoint]
    ) -> list[PreparedMapPortalEndpoint]:
        unique_values((entry.anchor for entry in value), "map portal anchor")
        unique_values((entry.role for entry in value), "map portal role")
        positions = [entry.normalized_x for entry in value]
        if len(set(positions)) != len(positions):
            raise ValueError("map portal normalized_x values must be unique")
        return value


class PreparedMapTerrainRequest(PersistedContractModel):
    """What the author asks for, not what was produced.

    Terrain shape is generated the way artwork is generated: the map states the generator and
    the intent, a graph node produces geometry, and the result is an artifact with its own
    provenance. Nothing generated is ever written back here, so this table stays small enough
    to read and stable enough to diff.
    """

    #: Which generator composes this map. A second dialect is a new mode, never a silent change.
    mode: Literal["platformer-chunk-map-v1"]
    #: The intent the map designer reads. This is the SHAPE brief and is deliberately separate
    #: from ``PreparedMapGround.prompt``, which directs the material atlas. A map may ask for a
    #: village layout painted in winter stone; the two prompts answer different questions.
    brief: str
    columns: int = Field(ge=8, le=512)
    rows: int = Field(ge=2, le=64)
    #: The row whose top edge is the main ground plane, and the datum for ``walk_surface``
    #: anchored layers. It is authored rather than derived precisely because painted scenery is
    #: pinned to it: a regenerated map must meet the existing art, not move it.
    walk_surface_row: int = Field(ge=0, le=63)

    @field_validator("brief")
    @classmethod
    def validate_brief(cls, value: str) -> str:
        return normalized_text(value, "map terrain brief", multiline=True)

    @model_validator(mode="after")
    def validate_datum(self) -> PreparedMapTerrainRequest:
        if self.walk_surface_row >= self.rows:
            raise ValueError("map terrain walk_surface_row must index a row inside the grid")
        return self


class PreparedGameMap(PersistedContractModel):
    schema_version: Literal[10]
    kind: Literal["game-map-v10"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    map_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    display_name: str
    view: PreparedMapView
    camera: PreparedMapCamera
    continuity: PreparedMapContinuity
    references: list[PreparedMapReference] = Field(min_length=1, max_length=32)
    layers: list[PreparedMapLayer] = Field(min_length=1, max_length=8)
    ground: PreparedGroundDirection
    terrain: PreparedMapTerrainRequest
    climbable: PreparedMapClimbable | None = None
    portal: PreparedMapPortal | None = None

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalized_text(value, "map display_name")

    @field_validator("references")
    @classmethod
    def validate_references(cls, value: list[PreparedMapReference]) -> list[PreparedMapReference]:
        unique_values((entry.reference_id for entry in value), "map reference_id")
        unique_values((entry.source for entry in value), "map reference source")
        return value

    @field_validator("layers")
    @classmethod
    def validate_layers(cls, value: list[PreparedMapLayer]) -> list[PreparedMapLayer]:
        unique_values((entry.layer_id for entry in value), "map layer_id")
        for plane in ("background", "foreground"):
            orders = sorted(entry.order for entry in value if entry.plane == plane)
            if orders and orders != list(range(len(orders))):
                raise ValueError(f"{plane} layer order must be contiguous from zero")
        return value

    @model_validator(mode="after")
    def validate_composition(self) -> PreparedGameMap:
        reference_ids = {entry.reference_id for entry in self.references}
        selected_ids = {
            reference_id for layer in self.layers for reference_id in layer.reference_ids
        } | set(self.ground.reference_ids)
        if self.climbable is not None:
            selected_ids.update(self.climbable.reference_ids)
        if self.portal is not None:
            selected_ids.update(self.portal.reference_ids)
        unknown = sorted(selected_ids - reference_ids)
        if unknown:
            raise ValueError("map generation references unknown IDs: " + ", ".join(unknown))
        unused = sorted(reference_ids - selected_ids)
        if unused:
            raise ValueError("map declares unused reference IDs: " + ", ".join(unused))
        if isinstance(self.ground, PaintedTerrainGround):
            # Painted terrain is one image call per derived segment, so a map it cannot serve
            # has to be refused while planning rather than discovered after the spend. The
            # row cap is the binding one and no partition can relieve it: a grid taller than
            # the guide canvas can carry at the publication cell loses native resolution
            # however its columns are cut.
            if self.terrain.rows > PAINTED_TERRAIN_MAX_ROWS:
                raise ValueError(
                    f"painted terrain needs at most {PAINTED_TERRAIN_MAX_ROWS} rows, "
                    f"and this map asks for {self.terrain.rows}"
                )
            if self.terrain.columns < PAINTED_TERRAIN_MIN_SEGMENT_COLUMNS:
                raise ValueError(
                    f"painted terrain needs at least {PAINTED_TERRAIN_MIN_SEGMENT_COLUMNS} "
                    f"columns, and this map asks for {self.terrain.columns}"
                )
            painted_terrain_segments(self.terrain.columns, self.terrain.rows)
        opaque_layers = [layer for layer in self.layers if layer.alpha_mode == "opaque"]
        if len(opaque_layers) != 1:
            raise ValueError("map must declare exactly one opaque layer")
        base = opaque_layers[0]
        if base.plane != "background" or base.order != 0 or base.parallax != 0.0:
            raise ValueError("the opaque map base must be background order zero with parallax zero")
        if any(layer.alpha_mode != "transparent" for layer in self.layers if layer is not base):
            raise ValueError("every non-base map layer must use transparent alpha")
        return self


def normalized_terrain_column(normalized_x: float, width: int) -> int:
    """Project a normalized map X coordinate onto its authored occupancy column."""

    if not 0.0 < normalized_x < 1.0 or width <= 0:
        raise ValueError("normalized terrain position and occupancy width are invalid")
    return min(width - 1, int(normalized_x * width))


def bottom_contiguous_surface_row(occupancy: list[str], column: int) -> int | None:
    """Return the top row of a column's solid bottom-connected terrain stack."""

    if not occupancy or column < 0 or column >= len(occupancy[0]):
        raise ValueError("terrain occupancy column is outside the authored rectangle")
    row = len(occupancy) - 1
    if occupancy[row][column] != "1":
        return None
    while row > 0 and occupancy[row - 1][column] == "1":
        row -= 1
    return row


class PreparedMapTerrain(PersistedContractModel):
    """Generated terrain geometry.

    This is an artifact, not authored input: a terrain generator produces it the way an image
    model produces a layer, and it is bound to its map by digest rather than by being pasted
    back into the map document. Every geometry rule the runtime depends on is enforced here,
    because here is where geometry now exists.
    """

    schema_version: Literal[1]
    kind: Literal["map-terrain-v1"]
    map_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    occupancy: list[str] = Field(min_length=2, max_length=64)
    walk_surface_row: int = Field(ge=0, le=63)
    climbable_placements: list[PreparedMapClimbablePlacement] = Field(
        default_factory=list, max_length=8
    )

    @field_validator("occupancy")
    @classmethod
    def validate_occupancy(cls, value: list[str]) -> list[str]:
        width = len(value[0])
        if width < 8 or width > 512:
            raise ValueError("map terrain occupancy width must be between 8 and 512 cells")
        if any(len(row) != width for row in value):
            raise ValueError("map terrain occupancy must be rectangular")
        if any(not row or set(row) - {"0", "1"} for row in value):
            raise ValueError("map terrain occupancy rows may contain only zero and one")
        if "1" not in value[-1]:
            raise ValueError(
                "map terrain occupancy must contain terrain supported by the bottom row"
            )
        if "0" in value[-1]:
            raise ValueError(
                "every gameplay terrain column must have a bottom-supported escape floor"
            )
        heights = _bottom_contiguous_heights(value)
        if any(
            abs(heights[index + 1] - heights[index]) > MAX_UNASSISTED_TERRAIN_RISE_TILES
            for index in range(len(heights) - 1)
        ):
            raise ValueError("adjacent gameplay terrain surfaces may differ by at most two tiles")
        return value

    @field_validator("climbable_placements")
    @classmethod
    def validate_placements(
        cls, value: list[PreparedMapClimbablePlacement]
    ) -> list[PreparedMapClimbablePlacement]:
        unique_values((entry.climbable_id for entry in value), "map climbable_id")
        positions = [entry.normalized_x for entry in value]
        if len(set(positions)) != len(positions):
            raise ValueError("map climbable normalized_x values must be unique")
        return value

    @model_validator(mode="after")
    def validate_walk_surface_row(self) -> PreparedMapTerrain:
        if self.walk_surface_row >= len(self.occupancy):
            raise ValueError("map terrain walk_surface_row must index a generated occupancy row")
        row = self.occupancy[self.walk_surface_row]
        above = (
            self.occupancy[self.walk_surface_row - 1]
            if self.walk_surface_row > 0
            else "0" * len(row)
        )
        if not any(cell == "1" and above[column] == "0" for column, cell in enumerate(row)):
            raise ValueError(
                "map terrain walk_surface_row must expose a terrain surface in at least one column"
            )
        return self


def validate_generated_terrain(game_map: PreparedGameMap, terrain: PreparedMapTerrain) -> None:
    """Check generated geometry against what its map asked for.

    Geometry is generated, so the authored document cannot check it at load time the way it once
    could. This is where the two meet: the artifact must be for this map, at the grid and datum
    the author requested, placing exactly the climbable roster the map declared, on terrain that
    can actually carry it.
    """

    if terrain.map_id != game_map.map_id:
        raise ValueError(f"terrain artifact belongs to map {terrain.map_id}, not {game_map.map_id}")
    request = game_map.terrain
    height, width = len(terrain.occupancy), len(terrain.occupancy[0])
    if (height, width) != (request.rows, request.columns):
        raise ValueError(
            f"map {game_map.map_id} asked for {request.rows}x{request.columns} terrain and the "
            f"generator produced {height}x{width}"
        )
    if terrain.walk_surface_row != request.walk_surface_row:
        raise ValueError(
            f"map {game_map.map_id} pins its walk surface to row {request.walk_surface_row} and "
            f"the generator returned {terrain.walk_surface_row}; painted scenery is anchored to "
            "that datum"
        )
    placements = terrain.climbable_placements
    if game_map.climbable is None:
        if placements:
            raise ValueError(
                f"map {game_map.map_id} declares no climbable atlas but terrain places "
                f"{len(placements)} climbable(s)"
            )
        return
    if not placements:
        raise ValueError(f"map {game_map.map_id} declares a climbable atlas that nothing places")
    declared = {entry.variant_id for entry in game_map.climbable.variants}
    unknown = sorted({entry.variant_id for entry in placements} - declared)
    if unknown:
        raise ValueError(
            "map climbable placements reference undeclared variants: " + ", ".join(unknown)
        )
    unplaced = sorted(declared - {entry.variant_id for entry in placements})
    if unplaced:
        raise ValueError("map climbable declares unplaced variants: " + ", ".join(unplaced))
    for placement in placements:
        column = normalized_terrain_column(placement.normalized_x, width)
        lower_surface = bottom_contiguous_surface_row(terrain.occupancy, column)
        if lower_surface is None:
            raise ValueError(
                f"map climbable {placement.climbable_id} must stand on bottom-supported terrain"
            )
        upper_surface = lower_surface - placement.rise_tiles
        if (
            upper_surface < 0
            or terrain.occupancy[upper_surface][column] != "1"
            or (upper_surface > 0 and terrain.occupancy[upper_surface - 1][column] != "0")
        ):
            raise ValueError(
                f"map climbable {placement.climbable_id} requires an exposed upper deck exactly "
                f"{placement.rise_tiles} tiles above its lower surface"
            )
    if game_map.portal is not None:
        for endpoint in game_map.portal.endpoints:
            column = normalized_terrain_column(endpoint.normalized_x, width)
            if bottom_contiguous_surface_row(terrain.occupancy, column) is None:
                raise ValueError(
                    f"map portal endpoint {endpoint.anchor} must stand on bottom-supported terrain"
                )


def load_prepared_game_map_bytes(data: bytes) -> PreparedGameMap:
    return parse_toml_contract(data, model=PreparedGameMap, label="prepared game map")


def canonical_prepared_game_map_json(game_map: PreparedGameMap) -> bytes:
    return canonical_contract_json(game_map)


def load_prepared_map_terrain_bytes(data: bytes) -> PreparedMapTerrain:
    try:
        return PreparedMapTerrain.model_validate_json(data)
    except ValidationError as error:
        raise AuthoredContractLoadError(f"prepared map terrain is invalid: {error}") from error


def canonical_prepared_map_terrain_json(terrain: PreparedMapTerrain) -> bytes:
    return canonical_contract_json(terrain)


__all__ = [
    "validate_generated_terrain",
    "load_prepared_map_terrain_bytes",
    "canonical_prepared_map_terrain_json",
    "PreparedMapTerrainRequest",
    "PreparedMapTerrain",
    "PREPARED_MAP_TERRAIN_SCHEMA_VERSION",
    "MAX_CLIMBABLE_VARIANTS_PER_ROLE",
    "PREPARED_GAME_MAP_SCHEMA_VERSION",
    "PreparedGameMap",
    "PreparedMapContinuity",
    "PreparedGroundDirection",
    "PreparedMapGround",
    "PreparedMapClimbable",
    "PreparedMapCamera",
    "PreparedMapClimbablePlacement",
    "PreparedMapClimbableVariant",
    "PreparedMapLayer",
    "PreparedMapLayerPresentation",
    "PreparedMapPortal",
    "PreparedMapPortalEndpoint",
    "PreparedMapReference",
    "PreparedMapView",
    "bottom_contiguous_surface_row",
    "canonical_prepared_game_map_json",
    "load_prepared_game_map_bytes",
    "normalized_terrain_column",
]
