"""The runner's track contract: authored tiled segments over the shared side-view stage.

A track reuses the platformer map's generation vocabulary verbatim - the view,
the continuity/loop block, digest-locked references, parallax layers, and the
47-mask ground atlas request - and replaces the platformer's generated terrain
with AUTHORED occupancy chunks. The camera is the runner's own: `auto_run_x_v1`
advances on its own rather than following input.

Segments are the genre fact. Every chunk shares one grid height and one
`walk_surface_row`, and the SEAM RULE - every chunk's first and last columns
are bottom-supported with their surface exactly at `walk_surface_row` - is what
makes the track infinite: any chunk may follow any chunk in any order, so no
cross-chunk geometry check ever exists. Pits (bottom-row `0` runs) are legal
here; the platformer family's bottom-supported-escape-floor rule is exactly
the rule this family drops. Whether a pit is CLEARABLE is a cross-member fact
proved at package resolution against the gameplay contract's jump profile.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    GAME_ID_PATTERN,
    KEBAB_ID_PATTERN,
    SNAKE_ID_PATTERN,
    canonical_contract_json,
    normalized_text,
    parse_toml_contract,
    sha256_bytes,
    unique_values,
)
from stage_gen.components.platformer_map import (
    PreparedMapContinuity,
    PreparedMapGround,
    PreparedMapLayer,
    PreparedMapReference,
    PreparedMapView,
    bottom_contiguous_surface_row,
)

RUNNER_TRACK_SCHEMA_VERSION = 1

MIN_SEGMENT_COLUMNS = 8
MAX_SEGMENT_COLUMNS = 64


class RunnerCamera(PersistedContractModel):
    """The runner's camera advances on its own; nothing here reaches the image model."""

    mode: Literal["auto_run_x_v1"]


class RunnerHazard(PersistedContractModel):
    """One authored obstacle standing on a supported column of its chunk."""

    prop_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    column: int = Field(ge=0, le=MAX_SEGMENT_COLUMNS - 1)


class RunnerPickup(PersistedContractModel):
    """One authored pickup occupying an empty cell of its chunk."""

    item_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    column: int = Field(ge=0, le=MAX_SEGMENT_COLUMNS - 1)
    row: int = Field(ge=0, le=63)


class RunnerSegmentChunk(PersistedContractModel):
    segment_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    difficulty: int = Field(ge=1, le=10)
    occupancy: list[str] = Field(min_length=1, max_length=64)
    hazards: list[RunnerHazard] = Field(default_factory=list, max_length=16)
    pickups: list[RunnerPickup] = Field(default_factory=list, max_length=32)

    @field_validator("occupancy")
    @classmethod
    def validate_occupancy(cls, value: list[str]) -> list[str]:
        width = len(value[0])
        if width < MIN_SEGMENT_COLUMNS or width > MAX_SEGMENT_COLUMNS:
            raise ValueError(
                f"segment occupancy must be {MIN_SEGMENT_COLUMNS}-{MAX_SEGMENT_COLUMNS} "
                "columns wide"
            )
        for row in value:
            if len(row) != width:
                raise ValueError("segment occupancy must be rectangular")
            if set(row) - {"0", "1"}:
                raise ValueError("segment occupancy rows must contain only 0 and 1")
        return value

    @model_validator(mode="after")
    def validate_placements(self) -> RunnerSegmentChunk:
        width = len(self.occupancy[0])
        unique_values(
            (f"{entry.column}" for entry in self.hazards),
            f"segment {self.segment_id} hazard column",
        )
        unique_values(
            (f"{entry.column}:{entry.row}" for entry in self.pickups),
            f"segment {self.segment_id} pickup cell",
        )
        for hazard in self.hazards:
            if hazard.column >= width:
                raise ValueError(
                    f"segment {self.segment_id} hazard column {hazard.column} is outside the chunk"
                )
            if bottom_contiguous_surface_row(self.occupancy, hazard.column) is None:
                raise ValueError(
                    f"segment {self.segment_id} places hazard {hazard.prop_id} over a pit"
                )
        for pickup in self.pickups:
            if pickup.column >= width or pickup.row >= len(self.occupancy):
                raise ValueError(
                    f"segment {self.segment_id} pickup {pickup.item_id} is outside the chunk"
                )
            if self.occupancy[pickup.row][pickup.column] != "0":
                raise ValueError(
                    f"segment {self.segment_id} pickup {pickup.item_id} occupies solid terrain"
                )
        return self

    def max_pit_run(self) -> int:
        """The widest contiguous unsupported bottom-row run in this chunk."""

        widest = 0
        run = 0
        for column in range(len(self.occupancy[0])):
            if bottom_contiguous_surface_row(self.occupancy, column) is None:
                run += 1
                widest = max(widest, run)
            else:
                run = 0
        return widest


class RunnerSegments(PersistedContractModel):
    """The shared chunk grid: one height, one seam datum, many interchangeable chunks."""

    rows: int = Field(ge=6, le=32)
    #: The seam datum: the top row of every chunk's first and last supported
    #: column, and the datum a `walk_surface`-anchored layer registers against.
    walk_surface_row: int = Field(ge=1, le=31)
    chunks: list[RunnerSegmentChunk] = Field(min_length=1, max_length=64)

    @field_validator("chunks")
    @classmethod
    def validate_chunk_ids(cls, value: list[RunnerSegmentChunk]) -> list[RunnerSegmentChunk]:
        unique_values((entry.segment_id for entry in value), "segment_id")
        return value

    @model_validator(mode="after")
    def validate_grid(self) -> RunnerSegments:
        if self.walk_surface_row >= self.rows:
            raise ValueError("walk_surface_row must sit inside the segment grid")
        for chunk in self.chunks:
            if len(chunk.occupancy) != self.rows:
                raise ValueError(
                    f"segment {chunk.segment_id} has {len(chunk.occupancy)} rows; "
                    f"the track grid declares {self.rows}"
                )
        return self


class RunnerTrack(PersistedContractModel):
    schema_version: Literal[1]
    kind: Literal["runner-track-v1"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    track_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    display_name: str
    view: PreparedMapView
    camera: RunnerCamera
    continuity: PreparedMapContinuity
    references: list[PreparedMapReference] = Field(min_length=1, max_length=16)
    layers: list[PreparedMapLayer] = Field(min_length=1, max_length=8)
    ground: PreparedMapGround
    segments: RunnerSegments

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str, info: ValidationInfo) -> str:
        return normalized_text(value, f"track {info.field_name}")

    @model_validator(mode="after")
    def validate_composition(self) -> RunnerTrack:
        unique_values((entry.reference_id for entry in self.references), "track reference_id")
        unique_values((entry.source for entry in self.references), "track reference source")
        unique_values((entry.layer_id for entry in self.layers), "track layer_id")
        unique_values(
            (f"{entry.plane}:{entry.order}" for entry in self.layers), "track layer order"
        )
        opaque = [entry for entry in self.layers if entry.alpha_mode == "opaque"]
        if len(opaque) != 1:
            raise ValueError("a track declares exactly one opaque base layer")
        declared = {entry.reference_id for entry in self.references}
        selected = {
            *(reference_id for entry in self.layers for reference_id in entry.reference_ids),
            *self.ground.reference_ids,
        }
        unknown = sorted(selected - declared)
        if unknown:
            raise ValueError("track selects unknown reference IDs: " + ", ".join(unknown))
        unused = sorted(declared - selected)
        if unused:
            raise ValueError("track declares unused reference IDs: " + ", ".join(unused))
        return self


def load_runner_track_bytes(data: bytes) -> RunnerTrack:
    return parse_toml_contract(data, model=RunnerTrack, label="runner track contract")


def canonical_runner_track_json(contract: RunnerTrack) -> bytes:
    return canonical_contract_json(contract)


def runner_track_sha256(contract: RunnerTrack) -> str:
    return sha256_bytes(canonical_runner_track_json(contract))


__all__ = [
    "MAX_SEGMENT_COLUMNS",
    "MIN_SEGMENT_COLUMNS",
    "RUNNER_TRACK_SCHEMA_VERSION",
    "RunnerCamera",
    "RunnerHazard",
    "RunnerPickup",
    "RunnerSegmentChunk",
    "RunnerSegments",
    "RunnerTrack",
    "canonical_runner_track_json",
    "load_runner_track_bytes",
    "runner_track_sha256",
]
