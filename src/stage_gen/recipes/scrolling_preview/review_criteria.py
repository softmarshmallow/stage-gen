"""Semantic review criteria for this recipe's actor strips.

The grid contracts in `raster_contracts` prove everything the pixels can prove on their own:
that cells are populated, isolated, free of template furniture, and drawn from one camera. They
cannot prove which way the subject points, and that is not a threshold that has yet to be
found - it is outside what the geometry carries.

Facing is decided by where a creature's face is, and no measurement of a silhouette locates a
face. Measured across a full run's actor set, the correlation between mirror overlap and true
facing is absent: strips of one character whose facings genuinely differ score `-0.132` (reads
as agreeing) while strips that genuinely agree score `+0.041` (reads as flipped). Silhouette
overlap between two different poses is dominated by the pose. The same run's mob set contains a
snail, a heron, a griffin, a flower and a stone golem, and no geometric rule names the front of
all five.

So this module states the criteria and leaves the verdict to a vision model, matching
`docs/spec/actor-boundary-and-semantic-review.md`. It holds no provider knowledge: it produces a
prompt and a schema, and reads back a decoded verdict.
"""

from __future__ import annotations

from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from stage_gen.recipes.scrolling_preview.mob_states import is_mob_strip_stage

ACTOR_FACING_SCHEMA_NAME = "scrolling_preview_actor_facing_v1"
ACTOR_FACING_ERROR_CODE = "scrolling-actor-facing-v1"

#: Facing every side-view actor strip is authored to. The runtime mirrors a sprite to move it
#: the other way, so a source that already points left renders backwards whenever the actor
#: advances - the reported defect was a player walking right while facing left.
REQUIRED_SIDE_VIEW_FACING = "right"

#: Facing a still resident is authored to. A townsperson stands in a square and is spoken to from
#: in front, so the viewer is who they face; the runtime draws them without mirroring, so unlike a
#: side-view actor there is no direction the artwork can be flipped into.
REQUIRED_STILL_FACING = "front"

ActorFacing = Literal["left", "right", "front", "back", "indeterminate"]


class ActorFacingVerdict(BaseModel):
    """A vision model's reading of which way an actor strip points."""

    model_config = ConfigDict(extra="forbid", strict=True)

    facing: ActorFacing
    confident: bool = Field(
        description="False when the subject's front cannot be located from the image alone.",
    )
    evidence: str = Field(
        min_length=1,
        max_length=400,
        description="The visible feature the verdict rests on, such as where the eyes point.",
    )


class ActorFacingError(ValueError):
    """A strip was reviewed and found to face the wrong way."""

    def __init__(self, message: str, *, facing: str, evidence: str) -> None:
        super().__init__(f"{ACTOR_FACING_ERROR_CODE}: {message}")
        self.code = ACTOR_FACING_ERROR_CODE
        self.facing = facing
        self.evidence = evidence

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": str(self),
            "facing": self.facing,
            "evidence": self.evidence,
        }


def reviews_facing(stage: str) -> bool:
    """Whether a stage produces artwork whose facing is contractual.

    The ladder-climb strip is authored rear-facing on purpose and the concept sheets are
    turnarounds, so neither carries a facing contract to check. That exclusion covers the
    village residents' turnaround sheets too: `village-npc-concept-<i>` is three views of one
    resident, and a review that demanded a single facing of it would reject the artwork for
    doing exactly what it was asked to do. Their idle strips and their stills are both reviewed,
    because an NPC who stands in a village facing away from an approaching player reads as a bug
    either way - only the direction they are held to differs, and `required_facing` decides that.
    """

    if stage == "character-climb":
        return False
    return (
        is_mob_strip_stage(stage)
        or stage.startswith("character-master-strip-")
        or stage == "character-attack"
        or is_resident_still(stage)
        or (stage.startswith("village-npc-") and stage.endswith("-idle"))
    )


def is_resident_still(name: str) -> bool:
    """Whether a stage or runtime role names a single-cell forward-facing resident.

    Both halves are load-bearing, exactly as they are for the idle-strip test in
    `raster_contracts`: the prefix alone would also catch `village-npc-concept-<i>`, which is a
    three-view turnaround.
    """

    return name.startswith("village-npc-") and name.endswith("-still")


def required_facing(stage: str) -> str:
    """Which way a reviewed stage's subject must point.

    One function rather than a constant read at each call site, so the prompt, the verdict gate
    and the stage list cannot drift apart - which is the same reason
    `_side_view_facing_directive` reads `REQUIRED_SIDE_VIEW_FACING` instead of writing "right".
    """

    return REQUIRED_STILL_FACING if is_resident_still(stage) else REQUIRED_SIDE_VIEW_FACING


def actor_facing_prompt(subject: str, *, still: bool = False) -> str:
    """Ask only what the pixels cannot answer, in the terms the artwork is drawn in.

    The opening sentence describes the artwork the reviewer is actually looking at. Telling a
    vision model that a single portrait is a four-frame strip invites it to answer about frames
    that are not there, and the second sentence - which exists to stop the strip's reading order
    being mistaken for the subject's facing - is meaningless for a still and is dropped with it.
    """

    if still:
        opening = (
            f"This image is a single still figure of {subject}. Decide which way the subject "
            "faces.\n"
        )
    else:
        opening = (
            f"This image is a four-frame side-view animation strip of {subject}, read left to "
            "right. Decide which way the subject faces.\n"
            "Answer for the subject's own body, not for the strip: the frames advance rightwards "
            "across the sheet regardless of where the creature looks.\n"
        )
    return (
        opening
        + "Use the front of the body - where the eyes, face, beak, or snout point. For a shelled "
        "or tailed creature the head end is the front, not the shell or tail. Weapons, cloaks, "
        "carried objects, and outstretched limbs do not decide it.\n"
        "Answer 'right' when the subject faces the right edge, 'left' when it faces the left "
        "edge, 'front' when it faces the viewer head-on, and 'back' when it is seen from "
        "behind. Answer 'indeterminate' only when the artwork genuinely does not resolve, such "
        "as a plant or a featureless mass with no locatable front.\n"
        "Set confident to false whenever you are guessing."
    )


def parse_actor_facing(decoded: object) -> ActorFacingVerdict:
    return ActorFacingVerdict.model_validate(decoded)


def evaluate_actor_facing(
    verdict: ActorFacingVerdict,
    *,
    required: str = REQUIRED_SIDE_VIEW_FACING,
) -> dict[str, object]:
    """Accept or reject a reviewed strip, and record the reading either way.

    Only a confident reading of the wrong side view is rejected. `front` and `back` are left to
    the deterministic camera check in `raster_contracts`, which measures mirror symmetry and
    already owns that question; an unconfident or indeterminate reading is recorded and passed.

    That asymmetry is deliberate. Roughly half of a run's strips arrive facing the wrong way, so
    a rejection is common and each one costs a full regeneration - but a subject with no
    locatable front, of which this recipe's mob sets produce several, would fail forever. The
    gate fires only where the evidence is actually there.
    """

    record: dict[str, object] = {
        "actor_facing": verdict.facing,
        "actor_facing_confident": verdict.confident,
        "actor_facing_required": required,
        "actor_facing_evidence": verdict.evidence,
    }
    if required == REQUIRED_STILL_FACING:
        # A still resident is held to a wider rule than a side-view strip, and it can afford to
        # be. The side-view gate leaves `front` and `back` alone because a mob roster contains
        # subjects with no locatable front and a strict rule would fail them forever; a resident
        # is a person, drawn from a turnaround that already resolved their front, so a confident
        # reading of any direction other than the viewer is a real defect. `back` in particular
        # matters here and is invisible to the deterministic symmetry check, which reads a figure
        # seen from behind as a perfectly good front view.
        if verdict.confident and verdict.facing in ("left", "right", "back"):
            raise ActorFacingError(
                f"still faces {verdict.facing} but a resident is spoken to from in front and is "
                f"drawn without mirroring, so it would stand turned away ({verdict.evidence})",
                facing=verdict.facing,
                evidence=verdict.evidence,
            )
        return record
    if verdict.confident and verdict.facing in ("left", "right") and verdict.facing != required:
        raise ActorFacingError(
            f"strip faces {verdict.facing} but the runtime mirrors from a {required}-facing "
            f"source, so it would render backwards while advancing ({verdict.evidence})",
            facing=verdict.facing,
            evidence=verdict.evidence,
        )
    return record


def actor_facing_json_schema() -> dict[str, object]:
    return cast(dict[str, object], ActorFacingVerdict.model_json_schema())
