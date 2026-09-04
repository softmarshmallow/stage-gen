"""The side-view stage: the map blocks every side-scrolling genre shares.

A side-view game, whatever its genre, presents one horizontal plane the camera
travels along: a view profile, a continuity rule for the layers that loop past
it, the references those layers are drawn from, the layers themselves, and the
ground the actors stand on. The platformer authors these blocks in its map
document and the runner in its track segments; both read them from here, so
neither genre component imports the other.

Persisted ``kind``/``mode`` strings are unchanged by this home: module paths
are never persisted, so a rehome costs no run.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field, field_validator, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    SHA256_PATTERN,
    SNAKE_ID_PATTERN,
    normalized_text,
    portable_relative_path,
    unique_values,
)
from stage_gen.media import LOOP_METHODS, LoopConstruction


class PreparedMapView(PersistedContractModel):
    """What the artwork is. Every field here directs generation and enters the image cache key."""

    profile: Literal["side_view_2d"]
    gameplay_space: Literal["side_plane"]


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
