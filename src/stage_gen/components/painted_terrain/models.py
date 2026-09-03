"""The authored half of the painted ground mode.

A map that names this mode is asking for its terrain to be painted rather than tiled. It
says what the material is and nothing about where the paint may go: the silhouette
tolerance is a property of the family, published so a consumer can reason about it, and
never a knob an author turns. That follows the same rule the spawn contract already
follows -- a package names a word, the consumer owns the numbers.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import normalized_text, unique_values
from stage_gen.components.painted_terrain.segments import PAINTED_TERRAIN_CELL_PX
from stage_gen.components.painted_terrain.silhouette import (
    PAINTED_TERRAIN_DILATE_PX,
    PAINTED_TERRAIN_ERODE_PX,
    PAINTED_TERRAIN_SURFACE_DILATE_PX,
)


class PaintedSilhouetteTolerance(PersistedContractModel):
    """How far the drawn edge may leave the authored one, in published pixels.

    Published rather than implied. Collision is computed from occupancy alone and nothing
    samples the image at any stage, so this band changes no rule of play -- but a consumer
    drawing a debug overlay, or a reviewer asking why the art does not sit on the grid,
    both need the number rather than a description of it.
    """

    cell_px: int = Field(ge=1)
    erode_px: int = Field(ge=0)
    dilate_px: int = Field(ge=0)
    surface_dilate_px: int = Field(ge=0)


def painted_silhouette_tolerance() -> PaintedSilhouetteTolerance:
    return PaintedSilhouetteTolerance(
        cell_px=PAINTED_TERRAIN_CELL_PX,
        erode_px=PAINTED_TERRAIN_ERODE_PX,
        dilate_px=PAINTED_TERRAIN_DILATE_PX,
        surface_dilate_px=PAINTED_TERRAIN_SURFACE_DILATE_PX,
    )


class PaintedTerrainGround(PersistedContractModel):
    """One bespoke transparent painting per derived segment of the map's occupancy.

    The painting is presentation only. Generated ``terrain.json`` occupancy stays the
    geometry authority, and publication masks every returned raster back into a bounded
    band around that exact silhouette before it ships.
    """

    mode: Literal["painted-terrain-v1"]
    reference_ids: list[str] = Field(min_length=1, max_length=16)
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


__all__ = [
    "PaintedSilhouetteTolerance",
    "PaintedTerrainGround",
    "painted_silhouette_tolerance",
]
