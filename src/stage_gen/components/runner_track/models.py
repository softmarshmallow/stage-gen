"""The runner's track contract: authored tiled segments over the shared side-view stage.

A track reuses the platformer map's view, continuity, digest-locked references,
and parallax vocabulary, and selects a closed ground-presentation mode: the
shared 47-mask atlas or one structural painting per segment. Both modes serve
AUTHORED occupancy chunks; neither owns geometry. The camera is the runner's
own: `auto_run_x_v1` advances on its own rather than following input.

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

from typing import Annotated, Literal

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
from stage_gen.components.sideview_stage import (
    PreparedMapContinuity,
    PreparedMapGround,
    PreparedMapLayer,
    PreparedMapReference,
    PreparedMapView,
    bottom_contiguous_surface_row,
)

RUNNER_TRACK_SCHEMA_VERSION = 4

MIN_SEGMENT_COLUMNS = 8
MAX_SEGMENT_COLUMNS = 64


class RunnerCamera(PersistedContractModel):
    """The runner's camera advances on its own; nothing here reaches the image model."""

    mode: Literal["auto_run_x_v1"]


class RunnerHazard(PersistedContractModel):
    """One authored obstacle anchored to a supported column of its chunk.

    A `surface` hazard stands on the column's ground and is cleared by a jump;
    an `overhead` hazard hangs above it with `clearance_rows` of open air
    beneath its underside, measured up from the same surface, and is cleared
    by a slide. Both anchors demand support: an obstacle over a pit answers
    to no verb. The anchor carries no default on purpose - every placement
    states which half of the vertical axis it occupies.
    """

    prop_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    column: int = Field(ge=0, le=MAX_SEGMENT_COLUMNS - 1)
    anchor: Literal["surface", "overhead"]
    clearance_rows: float | None = Field(default=None, ge=0.5, le=16.0)

    @model_validator(mode="after")
    def validate_anchor(self) -> RunnerHazard:
        if self.anchor == "overhead" and self.clearance_rows is None:
            raise ValueError(f"overhead hazard {self.prop_id} must declare clearance_rows")
        if self.anchor == "surface" and self.clearance_rows is not None:
            raise ValueError(f"surface hazard {self.prop_id} must not declare clearance_rows")
        return self


class RunnerPickup(PersistedContractModel):
    """One authored pickup occupying an empty cell of its chunk."""

    item_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    column: int = Field(ge=0, le=MAX_SEGMENT_COLUMNS - 1)
    row: int = Field(ge=0, le=63)


#: What a chunk is for.
#:
#: `run` is the ordinary chunk the difficulty band draws from. `arena` is the
#: flat floor an encounter is fought over: it is never drawn by the selector,
#: it is streamed on demand while an encounter runs, and it carries nothing to
#: react to, because during the fight the reacting is done to the boss.
SegmentRole = Literal["run", "arena"]


def seam_profile(rows: int, walk_surface_row: int) -> list[str]:
    """The one column profile every chunk's first and last column must equal.

    Empty above the shared walk surface, solid from it down. Declared here
    rather than in the validator that enforces it because an arena chunk must
    hold this profile in EVERY column, and two places spelling out one datum
    is how the seam rule quietly acquires two meanings.
    """

    return ["0" if row < walk_surface_row else "1" for row in range(rows)]


class RunnerSegmentChunk(PersistedContractModel):
    segment_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    difficulty: int = Field(ge=1, le=10)
    #: Defaulted, because every chunk authored before encounters existed is a
    #: run chunk and says so by saying nothing.
    role: SegmentRole = "run"
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
        if self.role == "arena":
            # The fight is the demand. A hazard here would be a second thing to
            # read at the moment the player is reading a salvo, and a pickup
            # line would sit in the lane the salvo has to leave open.
            if self.hazards:
                raise ValueError(f"segment {self.segment_id} is an arena and carries no hazards")
            if self.pickups:
                raise ValueError(f"segment {self.segment_id} is an arena and carries no pickups")
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
            if hazard.anchor == "overhead":
                surface = bottom_contiguous_surface_row(self.occupancy, hazard.column)
                assert surface is not None  # refused above
                clearance = hazard.clearance_rows
                assert clearance is not None  # refused by the hazard model
                if surface - clearance < 0:
                    raise ValueError(
                        f"segment {self.segment_id} hangs {hazard.prop_id} above the grid"
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
        expected = seam_profile(self.rows, self.walk_surface_row)
        for chunk in self.chunks:
            if len(chunk.occupancy) != self.rows:
                raise ValueError(
                    f"segment {chunk.segment_id} has {len(chunk.occupancy)} rows; "
                    f"the track grid declares {self.rows}"
                )
            if chunk.role != "arena":
                continue
            # An arena is the seam profile all the way across: it may be
            # entered and left at any column and repeated back to back, which
            # is what lets one authored chunk hold an encounter of any length.
            width = len(chunk.occupancy[0])
            for column in range(width):
                if [row[column] for row in chunk.occupancy] != expected:
                    raise ValueError(
                        f"segment {chunk.segment_id} is an arena; every column must be empty "
                        f"above and solid from walk_surface_row {self.walk_surface_row} down, "
                        f"but column {column} is not"
                    )
        return self

    def arena_chunks(self) -> list[RunnerSegmentChunk]:
        return [chunk for chunk in self.chunks if chunk.role == "arena"]


GroundProjectionMode = Literal["orthographic_v1"]


class GroundProjection(PersistedContractModel):
    """How the ground's form is flattened onto the picture plane.

    A side-scroller's ground must be drawn in a PARALLEL projection - one whose
    receding edges never converge, so it has no vanishing point. That is a
    correctness rule rather than art direction: a vanishing point encodes a
    fixed camera position, and `auto_run_x_v1` scrolls the ground past the
    camera while chunks repeat in arbitrary order. Parallel projection is the
    only projection invariant under horizontal translation, so a converging
    tile has its vanishing point slide along with it and has no repeat unit at
    all.

    Orthographic and oblique are both parallel, and which one a package uses is
    the author's taste. `orthographic_v1` - a pure front elevation showing no
    top face - is the truthful default for a strict side view and the only
    member served today.

    `oblique_v1` is the reserved second member. It would carry
    `receding_angle_degrees` and `depth_ratio` (cabinet is 0.5, cavalier 1.0),
    and it is not merely unimplemented: `_validate_alpha_geometry` requires
    every published cell to be exactly opaque or exactly transparent against
    the authored occupancy, and oblique depth spills into neighbouring cells.
    Serving it means a projection-aware expected mask and a canvas margin
    beyond `columns x 64` first.
    """

    mode: GroundProjectionMode


#: What an absent `[ground.projection]` block means. Field presence is not
#: identity, so a package written before this block existed declares nothing
#: and means exactly this.
DEFAULT_GROUND_PROJECTION: GroundProjectionMode = "orthographic_v1"


class RunnerStructuralGround(PersistedContractModel):
    """One bespoke transparent painting per authored runner segment.

    The painting is presentation only. ``RunnerSegmentChunk.occupancy`` stays
    the geometry authority, and the local canonicalizer masks every generated
    raster back to that exact binary silhouette before publication.
    """

    mode: Literal["runner-structural-ground-v1"]
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    vertical_fit: Literal["floor_to_screen_bottom"]
    #: Absent means `orthographic_v1`. Declaring it is how an author states a
    #: projection deliberately rather than inheriting one.
    projection: GroundProjection | None = None
    prompt: str

    def projection_mode(self) -> GroundProjectionMode:
        """The declared projection, or the default an absent block means."""

        if self.projection is None:
            return DEFAULT_GROUND_PROJECTION
        return self.projection.mode

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "runner structural ground reference_id")
        return value

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "runner structural ground prompt", multiline=True)


type RunnerGround = Annotated[
    PreparedMapGround | RunnerStructuralGround,
    Field(discriminator="mode"),
]


class RunnerTrack(PersistedContractModel):
    schema_version: Literal[4]
    kind: Literal["runner-track-v4"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    track_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    display_name: str
    view: PreparedMapView
    camera: RunnerCamera
    continuity: PreparedMapContinuity
    references: list[PreparedMapReference] = Field(min_length=1, max_length=16)
    layers: list[PreparedMapLayer] = Field(min_length=1, max_length=8)
    ground: RunnerGround
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
    "DEFAULT_GROUND_PROJECTION",
    "MAX_SEGMENT_COLUMNS",
    "MIN_SEGMENT_COLUMNS",
    "RUNNER_TRACK_SCHEMA_VERSION",
    "RunnerCamera",
    "RunnerHazard",
    "RunnerPickup",
    "GroundProjection",
    "GroundProjectionMode",
    "RunnerGround",
    "RunnerSegmentChunk",
    "RunnerSegments",
    "RunnerStructuralGround",
    "RunnerTrack",
    "canonical_runner_track_json",
    "load_runner_track_bytes",
    "runner_track_sha256",
]
