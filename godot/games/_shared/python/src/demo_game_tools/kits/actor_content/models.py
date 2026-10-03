"""Shared drawn-actor contract blocks: references, motion playback, closures."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Annotated, Literal, Protocol

from pydantic import Field, field_validator, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    SHA256_PATTERN,
    SNAKE_ID_PATTERN,
    normalized_text,
    portable_relative_path,
    unique_values,
)

MotionPlaybackMode = Literal["hold", "loop", "once", "gameplay_driven"]
CanonicalFrameIndex = Annotated[int, Field(ge=0, le=63)]

#: Which edge of its cell a motion's frames register against. Vertical only: horizontal placement is
#: unconditionally centered by both the repacker and the runtime origin.
#:
#: `center` is deliberately not admitted. The repacker supports it, but the runtime origin is
#: correct only for these two, so admitting it would publish a value that does not work.
MotionAnchor = Literal["bottom", "top"]
DEFAULT_MOTION_ANCHOR: MotionAnchor = "bottom"


class MotionPresentation(PersistedContractModel):
    """Authored runtime playback for one independently generated motion state."""

    state: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    playback_mode: MotionPlaybackMode
    canonical_frame_indices: list[CanonicalFrameIndex] = Field(min_length=1, max_length=64)
    frames_per_second: int | None = Field(default=None, ge=1, le=60)
    #: Which edge every frame of this motion registers against.
    #:
    #: Authored rather than recipe-owned because, unlike facing, it is not knowable before
    #: generation. Facing follows from the camera and is decided up front; the anchor depends on
    #: what the model actually drew - whether a climb tucked to hip height or to the chest, whether
    #: the feet left the bounding box's extreme. That is a per-artifact property, so it needs a knob
    #: at the point where a human has seen the output.
    #:
    #: A grounded actor registers on its feet, which is why the default is `bottom` and why nothing
    #: needed this until now. An actor hanging from its hands does not: bottom-anchoring pins its
    #: feet and throws its head up and down instead, which reads as bouncing.
    #:
    #: This is a deliberate stopgap. It pins a bounding-box extreme, so it cannot express a
    #: registration point inside the figure, and it is one value for the whole motion rather than
    #: one per frame. `TODO.md` `## Sprite anchoring` owns the replacement; when that lands this
    #: field is renamed or retired rather than extended.
    anchor: MotionAnchor = DEFAULT_MOTION_ANCHOR

    @field_validator("canonical_frame_indices")
    @classmethod
    def validate_frame_indices(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("canonical frame indices must be unique")
        return value

    @model_validator(mode="after")
    def validate_playback_shape(self) -> MotionPresentation:
        if self.playback_mode == "hold":
            if len(self.canonical_frame_indices) != 1:
                raise ValueError("hold playback requires exactly one canonical frame index")
            if self.frames_per_second is not None:
                raise ValueError("hold playback must not declare frames_per_second")
        elif self.playback_mode in {"loop", "once"}:
            if self.frames_per_second is None:
                raise ValueError(f"{self.playback_mode} playback requires frames_per_second")
        elif self.frames_per_second is not None:
            raise ValueError("gameplay_driven playback must not declare frames_per_second")
        return self


def validate_motion_states(
    motions: Sequence[MotionPresentation],
    *,
    allowed_states: set[str],
    label: str,
) -> None:
    states = [entry.state for entry in motions]
    unique_values(states, f"{label} motion state")
    unknown = sorted(set(states) - allowed_states)
    if unknown:
        raise ValueError(f"{label} declares unsupported motion states: " + ", ".join(unknown))


class ContentReference(PersistedContractModel):
    reference_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    source: str
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    rights_status: Literal["unreviewed", "restricted", "redistribution-approved"]
    rights_basis: list[str] = Field(min_length=1, max_length=16)

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        source = portable_relative_path(value, "content reference source")
        if not source.startswith("references/"):
            raise ValueError("content references must live under references/")
        if PurePosixPath(source).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("content references must use PNG, JPEG, or WebP")
        return source

    @field_validator("rights_basis")
    @classmethod
    def validate_rights_basis(cls, value: list[str]) -> list[str]:
        normalized = [normalized_text(entry, "content reference rights basis") for entry in value]
        unique_values(normalized, "content reference rights basis")
        return normalized


class ReferencesContent(Protocol):
    reference_ids: list[str]


def validate_reference_closure(
    references: Sequence[ContentReference],
    entries: Sequence[ReferencesContent],
) -> None:
    unique_values((entry.reference_id for entry in references), "content reference_id")
    unique_values((entry.source for entry in references), "content reference source")
    declared = {entry.reference_id for entry in references}
    selected = {reference_id for entry in entries for reference_id in entry.reference_ids}
    unknown = sorted(selected - declared)
    if unknown:
        raise ValueError("content entries reference unknown IDs: " + ", ".join(unknown))
    unused = sorted(declared - selected)
    if unused:
        raise ValueError("content declares unused reference IDs: " + ", ".join(unused))


__all__ = [
    "DEFAULT_MOTION_ANCHOR",
    "CanonicalFrameIndex",
    "ContentReference",
    "MotionAnchor",
    "MotionPlaybackMode",
    "MotionPresentation",
    "ReferencesContent",
    "validate_motion_states",
    "validate_reference_closure",
]
