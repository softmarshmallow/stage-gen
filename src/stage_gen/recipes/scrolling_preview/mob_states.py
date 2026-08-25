"""The one place that knows which animation strips a mob has, and what each one is.

A mob's states used to be spelled out, independently, in five different predicates: the prompt
builder, the producer grid contract, the scale-reference gate, the scale-reference frame choice,
and the facing review. Each one carried its own `stage.startswith("mob-idle-") or
stage.startswith("mob-hurt-")`, and adding a third state meant editing all five.

Four of those five fail *silently* when they are missed, and each fails differently:

- `contract_for_stage` falls through to `None`, so the sheet gets no grid validation whatsoever -
  no cell isolation, no empty-cell check, no painted-gutter check, no fixed-side-view check.
- `measures_scale_reference` writes no `.scale-reference.json`, so the manifest omits the entry
  and the runtime draws the sheet at whatever raw size it happens to be.
- `scale_reference_frame` measures frame zero, which for an attack is the anticipation crouch
  with the head tucked - the exact mis-scaling the module exists to prevent.
- `reviews_facing` skips the vision review, and roughly half of a run's strips arrive mirrored.

Only the prompt builder fails loudly, because its motion table raises `KeyError`.

That is the same defect class that produced three separate silent failures in the village work -
a fact each call site had to know, hard-coded once per site, behind error handling that reads a
missing answer as "not applicable". So the states are declared once here and every predicate asks
this module. Adding a state is a line in `MOB_STRIP_STATES`; forgetting to teach a predicate is
no longer possible, because none of them hold a list any more.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class MobStripState:
    """One animation strip a mob is drawn for, and everything the pipeline needs to know about it.

    The fields are exactly the questions the five predicates used to answer separately. Keeping
    them on one record is what makes the answers impossible to disagree with each other.
    """

    #: Identifier in the stage name (`mob-<state>-<slot>`) and the artifact
    #: (`mob_<tag>_<slot>_<state>.png`). Both spellings are derived here, never written by hand.
    state: str
    #: The motion clause the strip prompt asks for, describing four distinct phases.
    motion: str
    #: Extra appendage nouns the cell-containment directive must name for this state, beyond the
    #: creature anatomy every strip carries. An attack extends a limb or a weapon horizontally,
    #: which is precisely what breaks cell isolation - the same reason `character-attack` needed
    #: its own widened list.
    appendages: str
    #: Which frame the head is measured in. Zero for a rest pose; a strip whose first frame is an
    #: anticipation crouch must be measured on the frame that stands the subject upright, or the
    #: head reads as smaller than it is and the runtime scales the whole creature up to match.
    scale_reference_frame: int = 0
    #: Whether the deterministic frame-to-frame mirror check applies.
    #:
    #: It measures how much better two frames match when one is flipped, and treats a good match
    #: as the camera having changed sides. That works for a breathing or staggering creature,
    #: whose pose barely moves between frames. It does not work for a strike: a serpentine body
    #: that coils one way and lashes the other is a large, legitimate reversal of curvature, and
    #: mirror overlap cannot tell that from a flip.
    #:
    #: `character-attack` already carries the plainer contract for exactly this reason - it is
    #: the one character state excluded from the check - so a mob's attack follows it. Facing is
    #: still contractual and still enforced, by the vision review in `review_criteria`, which
    #: reads where the eyes point instead of counting overlapping pixels.
    holds_fixed_side_view: bool = True
    #: A clause placed *first* in the prompt, before the subject is even named.
    #:
    #: Empty for the states that need nothing extra. This module has now watched three separate
    #: directives fail as trailing sub-clauses and succeed as leading labelled ones - facing,
    #: isolated-view framing, and now reach - so a state that needs a constraint honoured states
    #: it at the front rather than trusting a sentence at the end of a paragraph.
    lead_directive: str = ""


#: Every strip a mob is drawn for, in generation order.
#:
#: `idle` and `hurt` predate the attack system and their motion strings are reproduced exactly as
#: they were, so an existing run's prompts - and therefore its cached artwork - are unchanged.
MOB_STRIP_STATES: Final[tuple[MobStripState, ...]] = (
    MobStripState(
        state="idle",
        motion="four visibly distinct phases of a subtle breathing cycle; it stays planted",
        appendages="wings, tails, limbs, and antennae",
    ),
    MobStripState(
        state="hurt",
        motion="four phases of impact, stagger, settling, and recovery",
        appendages="wings, tails, limbs, and antennae",
    ),
    MobStripState(
        state="attack",
        # Phrased as the character attack strip phrases it, because it is the same four-beat
        # shape and that wording is the one this recipe has already generated successfully.
        motion="four phases of anticipation, swing, impact, and recovery",
        # Widened deliberately. `character-attack` was the one pose whose horizontally extended
        # weapon broke cell isolation, and a lunging creature extends further than a breathing
        # one: the reach is the whole point of the pose.
        appendages=(
            "wings, tails, limbs, antennae, claws, jaws, and anything the creature strikes with"
        ),
        # Frame zero of an attack is the anticipation crouch, head tucked toward the body. Frame
        # one stands the subject upright with the head clear of the swing.
        scale_reference_frame=1,
        # Measured, not assumed: a Ribbon Newt - "serpentine, with fins, whiskers, and no legs" -
        # exhausted all six attempts at 0.10 over the ceiling, because its strike reverses the
        # curve of its whole body.
        holds_fixed_side_view=False,
        # Measured. The Gilded Hartlebeetle - "six-legged stag-beetle chimera with antlers, wing
        # cases, and a plated abdomen" - failed cell isolation on twelve consecutive attempts,
        # and the second run failed *wider* than the first: cells 2-3 became cells 1-2-3. Its
        # spread wing cases at strike simply do not fit a 600px cell at the scale the model
        # chooses by default, and the containment clause's own "scale that subject down" sits at
        # the end of a long paragraph where it was doing no work.
        lead_directive=(
            "REACH, before anything else: a striking creature is drawn SMALLER than a resting "
            "one. Size each frame so the fullest extension of the strike - the widest spread of "
            "wings, antlers, claws, or limbs at the moment of impact - still leaves clear empty "
            "margin inside its own cell. Choose the scale from the widest frame, then draw all "
            "four frames at that same smaller scale. A creature that fills its cell at rest will "
            "not fit when it lunges.\n\n"
        ),
    ),
)

#: The states an undirected run draws. Attack is generated only when a game contract asks for it,
#: so a run without one keeps its exact two-strip cost and its artifacts stay cache-valid.
BASE_MOB_STRIP_STATES: Final[tuple[str, ...]] = ("idle", "hurt")

_BY_STATE: Final[dict[str, MobStripState]] = {entry.state: entry for entry in MOB_STRIP_STATES}

#: Prefix every mob strip stage name carries. Not the same as the `mob-` prefix used by runtime
#: roles, which also covers `mob-concept-<i>`.
_STAGE_PREFIX: Final = "mob-"


def mob_strip_stage(state: str, slot: int) -> str:
    """The stage name for one mob's strip. The only place this spelling is constructed."""

    return f"{_STAGE_PREFIX}{mob_strip_state(state).state}-{slot}"


def mob_strip_artifact(tag: str, slot: int, state: str) -> str:
    """The artifact filename for one mob's strip, matching `mob_strip_stage`."""

    return f"mob_{tag}_{slot}_{mob_strip_state(state).state}.png"


def mob_strip_runtime_role(slot: int, state: str) -> str:
    """The runtime role the manifest publishes for one mob's strip.

    Deliberately a different shape from the stage name - `mob-<i>-<state>` rather than
    `mob-<state>-<i>` - because that is what the manifest and the web runtime already publish for
    idle and hurt, and changing it would rename roles every existing consumer reads.
    """

    return f"{_STAGE_PREFIX}{slot}-{mob_strip_state(state).state}"


def mob_strip_state(state: str) -> MobStripState:
    """The record for one state, or a clear failure naming what is available."""

    try:
        return _BY_STATE[state]
    except KeyError:
        known = ", ".join(sorted(_BY_STATE))
        raise ValueError(f"unknown mob strip state {state!r}; expected one of {known}") from None


def parse_mob_strip_stage(stage: str) -> tuple[str, int] | None:
    """Split a mob strip stage name into its state and slot, or None if it is not one.

    This is the function every predicate calls. It returns None for `mob-concept-<i>`, which is a
    three-view turnaround and not a strip, and for anything that merely starts with `mob-`.
    """

    if not stage.startswith(_STAGE_PREFIX):
        return None
    remainder = stage[len(_STAGE_PREFIX) :]
    state, separator, slot = remainder.rpartition("-")
    if not separator or state not in _BY_STATE or not slot.isdigit():
        return None
    return state, int(slot)


def is_mob_strip_stage(stage: str) -> bool:
    """Whether a stage draws one of a mob's animation strips."""

    return parse_mob_strip_stage(stage) is not None


def is_mob_strip_runtime_role(role: str) -> bool:
    """Whether a published runtime role is one of a mob's animation strips."""

    if not role.startswith(_STAGE_PREFIX):
        return False
    remainder = role[len(_STAGE_PREFIX) :]
    slot, separator, state = remainder.partition("-")
    return bool(separator) and slot.isdigit() and state in _BY_STATE


def mob_strip_state_for_stage(stage: str) -> MobStripState | None:
    """The state record a stage draws, or None when the stage is not a mob strip."""

    parsed = parse_mob_strip_stage(stage)
    return None if parsed is None else _BY_STATE[parsed[0]]


__all__ = [
    "BASE_MOB_STRIP_STATES",
    "MOB_STRIP_STATES",
    "MobStripState",
    "is_mob_strip_runtime_role",
    "is_mob_strip_stage",
    "mob_strip_artifact",
    "mob_strip_runtime_role",
    "mob_strip_stage",
    "mob_strip_state",
    "mob_strip_state_for_stage",
    "parse_mob_strip_stage",
]
