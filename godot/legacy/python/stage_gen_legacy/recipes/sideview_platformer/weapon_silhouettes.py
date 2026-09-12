"""The one place that knows how each declared player equipment must be drawn.

Written in the shape `projectile_silhouettes.py` and `mob_states.py` established, and for the same
reason: art direction spelled out separately in the prompt builder and the vision review acquires
two copies of one decision, and one of them fails silently when a member is added.

What this module is answering is narrower than it looks, and the narrowness is the point. The
authored prompt still names the specific object - a simple wooden training sword, a bandolier of
folded paper darts - exactly as a projectile's prompt describes the dart whose silhouette is
`axial_v1`. This module supplies only the *structural* instruction that the authored prose has no
way to carry: that the thing is present in every cell of every strip, or that it is absent from all
of them. Those are the two failures actually measured on this pipeline.

Both failure directions have a recorded price. The wayfarer's sword vanished in 2 of 10 ladder
strips and 4 of 6 rope strips with `Preserve ... equipment` in every prompt, so presence is not
free. And during the same spike the propless phrasing *lost* the sword more often than it kept it,
while an explicit prohibition - the prop "itself is never drawn" - cleared the rope 4 of 4. So the
absent case is written as a prohibition and never as an omission, because an omission has been
measured and does not work.

What deliberately is *not* here: any judgement about whether the drawn weapon suits the character,
the genre, or the story. That is the author's business, and the contract says so. The only thing
held against the declared equipment is the gameplay `weapon_class`, checked by
`WEAPON_CLASSES_BY_PLAYER_EQUIPMENT` at package validation, where both sides are closed names and
no prose is read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class PlayerEquipmentArt:
    """One equipment declaration's art contract."""

    #: Identifier in the authored contract.
    equipment: str
    #: The clause placed *first* in the prompt, before the subject is even named. Leading, because
    #: this recipe has watched facing, isolated-view framing, reach, and projectile axis each fail
    #: as trailing sub-clauses and succeed as leading labelled ones.
    carry_directive: str
    #: What the vision review is asked to confirm about the drawn result. Equipment was previously
    #: absent from every review criterion, which is why the measured drift was never reported.
    review_clause: str


#: Every equipment a player may be drawn with, in contract order.
PLAYER_EQUIPMENT_ART: Final[tuple[PlayerEquipmentArt, ...]] = (
    PlayerEquipmentArt(
        equipment="hand_weapon_v1",
        carry_directive=(
            "EQUIPMENT, before anything else: this character carries ONE hand weapon, described "
            "in the authored direction below. It is held in or worn on the body in EVERY frame "
            "without exception - never set down, never dropped, never omitted, and never swapped "
            "for a different object. A frame in which it is missing is a defect, not a variation."
        ),
        review_clause=(
            "the one authored hand weapon is present and recognizably the same object in every "
            "cell of every strip, never missing from a frame and never replaced by another object"
        ),
    ),
    PlayerEquipmentArt(
        equipment="unarmed_v1",
        carry_directive=(
            "EQUIPMENT, before anything else: this character fights with their hands and carries "
            "NO weapon. No sword, blade, axe, club, staff, wand, bow, or thrown object is drawn "
            "anywhere in the image, in any frame, held or stowed. The character's hands are empty."
        ),
        review_clause=(
            "no weapon of any kind is drawn in any cell - the hands are empty and nothing is "
            "stowed on the body"
        ),
    ),
    PlayerEquipmentArt(
        equipment="thrown_kit_v1",
        carry_directive=(
            "EQUIPMENT, before anything else: this character throws, and carries the thrown "
            "supply described in the authored direction below - worn on the body, visible in "
            "EVERY frame. They carry NO melee weapon: no sword, blade, axe, club, or staff is "
            "drawn anywhere in the image, in any frame, held or stowed. The throwing hand is "
            "empty except when it holds one of the thrown objects itself."
        ),
        review_clause=(
            "the authored thrown supply is visibly worn in every cell, and no sword, blade, axe, "
            "club, or staff appears anywhere in any cell"
        ),
    ),
    PlayerEquipmentArt(
        equipment="focus_implement_v1",
        carry_directive=(
            "EQUIPMENT, before anything else: this character projects power through the single "
            "focus implement described in the authored direction below - a wand, rod, staff, or "
            "orb - held in EVERY frame without exception. They carry NO bladed or bludgeoning "
            "weapon: no sword, blade, axe, or club is drawn anywhere in the image, in any frame, "
            "held or stowed. The focus is never used as a club."
        ),
        review_clause=(
            "the one authored focus implement is present and recognizably the same object in "
            "every cell, and no sword, blade, axe, or club appears anywhere in any cell"
        ),
    ),
)

_BY_EQUIPMENT: Final[dict[str, PlayerEquipmentArt]] = {
    entry.equipment: entry for entry in PLAYER_EQUIPMENT_ART
}


def player_equipment_art(equipment: str) -> PlayerEquipmentArt:
    """The art contract for one declared equipment.

    Raises rather than defaulting. An equipment the contract accepts and this module has never
    heard of would otherwise be drawn to whichever directive happened to be first - and for this
    family that is worse than a missing directive, because three of the four members carry an
    explicit prohibition that would then be applied to the wrong character.
    """

    try:
        return _BY_EQUIPMENT[equipment]
    except KeyError as error:
        raise KeyError(f"no art contract is declared for player equipment {equipment}") from error
