"""Exact-current compound map-generation contract (``game-map-v7``)."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field, field_validator, model_validator

from stage_gen.components._game_input import (
    GAME_ID_PATTERN,
    KEBAB_ID_PATTERN,
    SHA256_PATTERN,
    SNAKE_ID_PATTERN,
    canonical_contract_json,
    normalized_text,
    parse_toml_contract,
    portable_relative_path,
    unique_values,
)
from stage_gen.contracts.artifacts import PersistedContractModel

PREPARED_GAME_MAP_SCHEMA_VERSION = 7
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
    profile: Literal["side_view_2d"]
    gameplay_space: Literal["side_plane"]
    camera_behavior: Literal["scrolling"]
    scroll_axis: Literal["x"]


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
    loop_construction: Literal["mirror_repeat", "generated_bridge"]


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
    occupancy: list[str] = Field(min_length=2, max_length=64)
    # Where the authored occupancy grid sits vertically. This is an enum rather than a coordinate:
    # the deepest row bottoms out at the viewport edge, which makes a gap below the world
    # impossible instead of merely unlikely. The consumer derives its own baseline; no map
    # declares pixels.
    vertical_fit: Literal["floor_to_screen_bottom"]
    # The occupancy row whose top edge is the main ground plane, used as the datum for layers that
    # must meet the visible terrain rather than the buried world floor. This is an index into
    # authored geometry, not a prediction about generated art, so it stays stable across
    # regeneration.
    walk_surface_row: int = Field(ge=0, le=63)
    prompt: str

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "map ground reference_id")
        return value

    @field_validator("occupancy")
    @classmethod
    def validate_occupancy(cls, value: list[str]) -> list[str]:
        width = len(value[0])
        if width < 8 or width > 512:
            raise ValueError("map ground occupancy width must be between 8 and 512 cells")
        if any(len(row) != width for row in value):
            raise ValueError("map ground occupancy must be rectangular")
        if any(not row or set(row) - {"0", "1"} for row in value):
            raise ValueError("map ground occupancy rows may contain only zero and one")
        if "1" not in value[-1]:
            raise ValueError(
                "map ground occupancy must contain terrain supported by the bottom row"
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

    @model_validator(mode="after")
    def validate_walk_surface_row(self) -> PreparedMapGround:
        if self.walk_surface_row >= len(self.occupancy):
            raise ValueError("map ground walk_surface_row must index an authored occupancy row")
        row = self.occupancy[self.walk_surface_row]
        above = (
            self.occupancy[self.walk_surface_row - 1]
            if self.walk_surface_row > 0
            else "0" * len(row)
        )
        if not any(cell == "1" and above[column] == "0" for column, cell in enumerate(row)):
            raise ValueError(
                "map ground walk_surface_row must expose a terrain surface in at least one column"
            )
        return self

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "map ground prompt", multiline=True)


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
    placements: list[PreparedMapClimbablePlacement] = Field(min_length=1, max_length=8)

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "map climbable reference_id")
        return value

    @field_validator("placements")
    @classmethod
    def validate_placements(
        cls, value: list[PreparedMapClimbablePlacement]
    ) -> list[PreparedMapClimbablePlacement]:
        unique_values((entry.climbable_id for entry in value), "map climbable_id")
        positions = [entry.normalized_x for entry in value]
        if len(set(positions)) != len(positions):
            raise ValueError("map climbable normalized_x values must be unique")
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
        declared = {entry.variant_id for entry in variants}
        unknown = sorted({entry.variant_id for entry in self.placements} - declared)
        if unknown:
            raise ValueError(
                "map climbable placements reference undeclared variants: " + ", ".join(unknown)
            )
        unplaced = sorted(declared - {entry.variant_id for entry in self.placements})
        if unplaced:
            raise ValueError("map climbable declares unplaced variants: " + ", ".join(unplaced))
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


class PreparedGameMap(PersistedContractModel):
    schema_version: Literal[7]
    kind: Literal["game-map-v7"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    map_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    display_name: str
    view: PreparedMapView
    continuity: PreparedMapContinuity
    references: list[PreparedMapReference] = Field(min_length=1, max_length=32)
    layers: list[PreparedMapLayer] = Field(min_length=1, max_length=8)
    ground: PreparedMapGround
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
        opaque_layers = [layer for layer in self.layers if layer.alpha_mode == "opaque"]
        if len(opaque_layers) != 1:
            raise ValueError("map must declare exactly one opaque layer")
        base = opaque_layers[0]
        if base.plane != "background" or base.order != 0 or base.parallax != 0.0:
            raise ValueError("the opaque map base must be background order zero with parallax zero")
        if any(layer.alpha_mode != "transparent" for layer in self.layers if layer is not base):
            raise ValueError("every non-base map layer must use transparent alpha")
        occupancy = self.ground.occupancy
        width = len(occupancy[0])
        if self.climbable is not None:
            for placement in self.climbable.placements:
                column = normalized_terrain_column(placement.normalized_x, width)
                lower_surface = bottom_contiguous_surface_row(occupancy, column)
                if lower_surface is None:
                    raise ValueError(
                        f"map climbable {placement.climbable_id} must stand on "
                        "bottom-supported terrain"
                    )
                upper_surface = lower_surface - placement.rise_tiles
                if (
                    upper_surface < 0
                    or occupancy[upper_surface][column] != "1"
                    or (upper_surface > 0 and occupancy[upper_surface - 1][column] != "0")
                ):
                    raise ValueError(
                        f"map climbable {placement.climbable_id} requires an exposed upper deck "
                        f"exactly {placement.rise_tiles} tiles above its lower surface"
                    )
        if self.portal is not None:
            for endpoint in self.portal.endpoints:
                column = normalized_terrain_column(endpoint.normalized_x, width)
                if bottom_contiguous_surface_row(occupancy, column) is None:
                    raise ValueError(
                        f"map portal endpoint {endpoint.anchor} must stand on "
                        "bottom-supported terrain"
                    )
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


def load_prepared_game_map_bytes(data: bytes) -> PreparedGameMap:
    return parse_toml_contract(data, model=PreparedGameMap, label="prepared game map")


def canonical_prepared_game_map_json(game_map: PreparedGameMap) -> bytes:
    return canonical_contract_json(game_map)


__all__ = [
    "MAX_CLIMBABLE_VARIANTS_PER_ROLE",
    "PREPARED_GAME_MAP_SCHEMA_VERSION",
    "PreparedGameMap",
    "PreparedMapContinuity",
    "PreparedMapGround",
    "PreparedMapClimbable",
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
