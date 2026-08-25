"""One anatomical reference per actor sheet, so every sprite renders the same apparent size.

An actor's states arrive as several separately generated sheets with unrelated cell geometry -
600x688 for the master states, 600x800 for attack, 64x128 for the ladder climb - and nothing in
the pixels ties their scale together. The runtime therefore has to reconstruct "how big is this
character" from each sheet independently.

Every deterministic attempt at that failed, and failed for one reason: silhouette height
conflates pose with draw scale. A crawling character is shorter than a standing one because of
the pose; a climbing character is shorter because the artwork is smaller. Measured across a full
run, erosion-based stroke thickness put a legitimately low crawl at 0.590 and a genuinely
mis-scaled attack at 0.580 - indistinguishable. A guard on "all frames the same height" fared
worse: it happened to hold on one run's climb loop (124px on all four frames) and failed on the
next (103, 109, 117, 109), because a climb cycle is supposed to move vertically.

The head does not have that problem. A crawling head, a lunging head, and a climbing head are
the same size, because a head is a fact about the character rather than about the pose. It is
not recoverable from alpha - which is exactly the boundary `actor-boundary-and-semantic-review.md`
draws between geometry and semantics - so it is measured once per sheet by a vision model and
recorded, and the runtime then scales every sheet so the heads agree.

For a creature with no distinguishable head - a slime is one dome - the model reports the whole
body instead, which is the same reference applied to a subject whose head is its body.
"""

from __future__ import annotations

from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from stage_gen.recipes.scrolling_preview.mob_states import (
    is_mob_strip_stage,
    mob_strip_state_for_stage,
)

ACTOR_SCALE_REFERENCE_SCHEMA_NAME = "scrolling_preview_actor_scale_reference_v1"
ACTOR_SCALE_REFERENCE_ERROR_CODE = "scrolling-actor-scale-reference-v1"

#: Smallest fraction of a frame the reference may occupy before the reading is treated as noise.
#: A head under a fiftieth of the frame cannot be located reliably enough to scale from, and a
#: bad reading here resizes the whole character rather than failing visibly.
MINIMUM_REFERENCE_FRACTION = 0.02
#: Largest fraction. A reference filling the frame means the model bounded the whole sprite
#: rather than the part asked for - except for a body reference, where that is the correct answer.
MAXIMUM_HEAD_FRACTION = 0.75

ScaleReferencePart = Literal["head", "body"]


class ActorScaleReference(BaseModel):
    """Where the scale reference sits, as fractions of the inspected frame."""

    model_config = ConfigDict(extra="forbid", strict=True)

    part: ScaleReferencePart = Field(
        description="head for a subject with a distinguishable head, body otherwise.",
    )
    top: float = Field(description="Top of the reference, as a fraction of frame height.")
    bottom: float = Field(description="Bottom of the reference, as a fraction of frame height.")
    left: float = Field(description="Left of the reference, as a fraction of frame width.")
    right: float = Field(description="Right of the reference, as a fraction of frame width.")
    confident: bool
    evidence: str = Field(min_length=1, max_length=300)

    def extent_pixels(self, *, frame_width: int, frame_height: int) -> float:
        """The reference's largest dimension in source pixels.

        Deliberately not its height. A head is measured shorter when it tilts, and a crawl pose
        tilts it hard: measured on a real run, the same character's head read 224px standing and
        162px crawling from artwork drawn at one scale. The largest dimension barely moves under
        rotation, so it survives the pose the way a vertical extent does not.
        """

        return max(
            (self.bottom - self.top) * frame_height,
            (self.right - self.left) * frame_width,
        )


class ActorScaleReferenceError(ValueError):
    """A sheet's scale reference could not be measured well enough to scale from."""

    def __init__(self, message: str) -> None:
        super().__init__(f"{ACTOR_SCALE_REFERENCE_ERROR_CODE}: {message}")
        self.code = ACTOR_SCALE_REFERENCE_ERROR_CODE


def actor_scale_reference_prompt(
    subject: str,
    frame_index: int,
    *,
    still: bool = False,
) -> str:
    """Ask for one measurable part, in frame-relative terms the answer can be checked against.

    The evaluator receives one cell's dimensions, so strip coordinates must be normalized to
    that selected cell rather than to the full sheet. A resident still is already one cell and
    must not be described to the reviewer as a strip.
    """

    if still:
        opening = f"This image is a single still figure of {subject}.\n"
        coordinate_space = "whole image"
    else:
        opening = (
            f"This image is a four-frame animation strip of {subject}, read left to right. Look "
            f"only at frame {frame_index + 1}, counting from the left.\n"
        )
        coordinate_space = "selected frame"
    return (
        opening + "Measure the subject's head: report the vertical position of the top of the head "
        "(including hair, ears, horns, or a hat that sits on the skull) and the bottom of the "
        "head at the chin or jaw.\n"
        "Also report the left and right edges of the head at its widest.\n"
        f"Report top and bottom as fractions of the {coordinate_space}'s height, and left and "
        f"right as fractions of the {coordinate_space}'s width, where 0.0 is the very top or "
        f"left edge of the {coordinate_space} and 1.0 is the very bottom or right edge. Measure "
        f"against the {coordinate_space}, not against the subject, and bound only the head - "
        "not the neck, shoulders, or body.\n"
        "Set part to 'head' when the subject has a head that can be told apart from its body. "
        "For a creature that is one undivided mass - a slime, a blob, a boulder - set part to "
        "'body' and measure the whole creature from its highest point to its lowest instead.\n"
        "Set confident to false if the subject is obscured or you are estimating."
    )


def parse_actor_scale_reference(decoded: object) -> ActorScaleReference:
    return ActorScaleReference.model_validate(decoded)


def evaluate_actor_scale_reference(
    reference: ActorScaleReference,
    *,
    frame_width: int,
    frame_height: int,
) -> dict[str, object]:
    """Turn a reading into a recorded reference extent in source pixels, or reject it.

    Rejection is deliberate rather than clamping: a silently wrong reference resizes the whole
    character, which is far harder to notice than a stage that fails.
    """

    if not 0.0 <= reference.top < reference.bottom <= 1.0:
        raise ActorScaleReferenceError(
            f"reference bounds are not ordered inside the frame (top {reference.top}, "
            f"bottom {reference.bottom})"
        )
    if not 0.0 <= reference.left < reference.right <= 1.0:
        raise ActorScaleReferenceError(
            f"reference bounds are not ordered inside the frame (left {reference.left}, "
            f"right {reference.right})"
        )
    height_fraction = reference.bottom - reference.top
    extent = reference.extent_pixels(frame_width=frame_width, frame_height=frame_height)
    if height_fraction < MINIMUM_REFERENCE_FRACTION:
        raise ActorScaleReferenceError(
            f"reference occupies {height_fraction:.3f} of the frame, too little to scale from"
        )
    if reference.part == "head" and height_fraction > MAXIMUM_HEAD_FRACTION:
        raise ActorScaleReferenceError(
            f"a head occupying {height_fraction:.3f} of the frame is the whole sprite, not a head"
        )
    return {
        "part": reference.part,
        "top_fraction": round(reference.top, 6),
        "bottom_fraction": round(reference.bottom, 6),
        "left_fraction": round(reference.left, 6),
        "right_fraction": round(reference.right, 6),
        "extent_pixels": round(extent, 3),
        "confident": reference.confident,
        "evidence": reference.evidence,
    }


def actor_scale_reference_json_schema() -> dict[str, object]:
    return cast(dict[str, object], ActorScaleReference.model_json_schema())


def measures_scale_reference(stage: str) -> bool:
    """Whether a stage produces an actor sheet whose draw scale has to be reconciled.

    Every actor sheet whose generated artifact is also the artifact the runtime loads, which
    includes the ladder climb even though it carries no facing contract: scale and facing are
    different questions, and climb is the sheet whose scale is furthest adrift because its cells
    are 64x128 against the master states' 600x688.

    The five master states are excluded here and measured in `post-split` instead. Their
    generated strips are composed and re-sliced before publication, so the sheet the runtime
    loads is a different artifact from the one generated - and a reference has to describe the
    pixels actually being drawn.

    Village residents' idle strips are measured for the same reason mobs are, and the stake is
    higher: a village puts an NPC and the player side by side, standing still, for as long as the
    player cares to look. A mis-scaled mob is a moving target in a fight, while a townsfolk drawn
    at half or twice the player's height is the first thing anyone sees on entering the hub.
    Their turnaround sheets are excluded - they are concept art, not an artifact the runtime
    draws.
    """

    return (
        is_mob_strip_stage(stage)
        or stage in ("character-attack", "character-climb")
        or (
            stage.startswith("village-npc-")
            and (stage.endswith("-idle") or stage.endswith("-still"))
        )
    )


def scale_reference_frame(stage: str) -> int:
    """Which frame to measure.

    The first frame of a loop is its rest pose, which is where a head is least obscured. Attack
    is the exception: its first frame is the anticipation crouch, while the second stands the
    subject upright with the head clear of the swing.

    A mob's attack has the same four-beat shape and the same tucked opening frame, so the answer
    comes from the state record rather than from a second hard-coded name here - see
    `mob_states`, which exists because this rule was previously spelled out in five places and
    four of them failed silently when one was missed.
    """

    mob_state = mob_strip_state_for_stage(stage)
    if mob_state is not None:
        return mob_state.scale_reference_frame
    return 1 if stage == "character-attack" else 0
