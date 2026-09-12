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

from typing import Literal

from pydantic import Field, field_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    normalized_text,
    unique_values,
)
from stage_gen.components.sideview_layers.models import (
    LayerContinuity as PreparedMapContinuity,
)
from stage_gen.components.sideview_layers.models import (
    LayerPresentation as PreparedMapLayerPresentation,
)
from stage_gen.components.sideview_layers.models import (
    LayerReference as PreparedMapReference,
)
from stage_gen.components.sideview_layers.models import (
    LayerRequest as PreparedMapLayer,
)


class PreparedMapView(PersistedContractModel):
    """What the artwork is. Every field here directs generation and enters the image cache key."""

    profile: Literal["side_view_2d"]
    gameplay_space: Literal["side_plane"]


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


__all__ = [
    "PreparedMapContinuity",
    "PreparedMapLayerPresentation",
    "PreparedMapReference",
    "PreparedMapLayer",
    "PreparedMapView",
    "PreparedMapGround",
]
