"""The one place that knows what each projectile silhouette must be drawn as.

Written in the shape the platformer recipe's `mob_states.py` established, and for the same reason
it was written: a family whose art direction is spelled out separately in the prompt builder, the
deterministic validator, and the vision review acquires three copies of one decision, and two of
them fail silently when a member is added. Here a silhouette is one record, and every predicate
asks this module.

It sits beside the contract rather than inside one recipe because a silhouette name is a *contract*
word: `ProjectileContent.silhouette` already declares that the name is a statement about the
published pixels, so the sentence that makes it true belongs with the model, not with whichever
genre happens to throw things. Two genres draw projectiles today.

A projectile has one problem no other isolated object in this pipeline has: **the runtime moves
it**. A prop stands where it was placed and an item lies where it dropped, so how the artwork is
oriented inside its canvas is invisible. A projectile is scaled along its travel axis, may be
mirrored, and may be rotated — so the axis the subject was drawn along is load-bearing, and a
mistake in it is not cosmetic. That is what `axis_directive` exists for, and why it is a *leading*
clause: this recipe has now watched facing, isolated-view framing, and reach each fail as trailing
sub-clauses and succeed as leading labelled ones.

What deliberately is *not* here: any threshold on aspect ratio. A hard numeric band on how long or
how round a subject may be is the shape of gate this repository has already recorded as producing
unrecoverable rejections — a legitimately drawn orb with an angled ring, or a dart with a long
ribbon, lands outside any band tight enough to be worth having. Whether the subject actually reads
as axial or radial is judged by the vision review, which can see it, exactly as mob facing is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class ProjectileSilhouetteArt:
    """One silhouette's art contract, and what the runtime is allowed to do with the result."""

    #: Identifier in the authored contract and in the stage name.
    silhouette: str
    #: The clause placed *first* in the prompt, before the subject is even named.
    axis_directive: str
    #: A short phrase naming the shape family, folded into the body of the prompt.
    shape_clause: str
    #: What the vision review is asked to confirm about the drawn axis.
    review_clause: str


#: Every silhouette a projectile may be drawn as, in contract order.
PROJECTILE_SILHOUETTES: Final[tuple[ProjectileSilhouetteArt, ...]] = (
    ProjectileSilhouetteArt(
        silhouette="radial_v1",
        axis_directive=(
            "AXIS, before anything else: this object has NO leading end and NO long axis. Draw it "
            "so it reads the same whichever way it travels — roughly as wide as it is tall, with "
            "no point, nose, tip, fletching, tail, or trailing element that would tell a viewer "
            "which direction it is moving."
        ),
        shape_clause="a self-contained rounded form",
        review_clause=(
            "reads as directionless — roughly as wide as it is tall, with no leading point or "
            "trailing tail"
        ),
    ),
    ProjectileSilhouetteArt(
        silhouette="axial_v1",
        axis_directive=(
            "AXIS, before anything else: this object has ONE long axis and ONE leading end, and it "
            "is drawn travelling to the RIGHT. Its leading end — point, nose, or head — touches "
            "the right side of the subject, its trailing end is on the left, and the long axis "
            "lies flat and horizontal. Do not draw it tilted, vertical, or pointing left."
        ),
        shape_clause="an elongated form with a clear leading end",
        review_clause=(
            "lies horizontally with its leading end toward the right edge, not tilted, vertical, "
            "or reversed"
        ),
    ),
    ProjectileSilhouetteArt(
        silhouette="irregular_v1",
        axis_directive=(
            "AXIS, before anything else: this object has no clean long axis and no symmetry. Draw "
            "it as a solid irregular mass whose orientation carries no meaning — a viewer must not "
            "be able to say which end leads."
        ),
        shape_clause="a solid irregular mass",
        review_clause="reads as an irregular mass with no leading end a viewer could name",
    ),
)

_BY_SILHOUETTE: Final[dict[str, ProjectileSilhouetteArt]] = {
    entry.silhouette: entry for entry in PROJECTILE_SILHOUETTES
}


def projectile_silhouette_art(silhouette: str) -> ProjectileSilhouetteArt:
    """The art contract for one silhouette.

    Raises rather than defaulting. A silhouette the contract accepts and this module has never
    heard of would otherwise be drawn to whichever directive happened to be first, which is the
    silent failure the module exists to make impossible.
    """

    try:
        return _BY_SILHOUETTE[silhouette]
    except KeyError as error:
        raise KeyError(
            f"no art contract is declared for projectile silhouette {silhouette}"
        ) from error
