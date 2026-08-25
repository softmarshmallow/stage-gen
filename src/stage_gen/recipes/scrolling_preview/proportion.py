"""Head-to-body proportion for the player character.

Nothing in this recipe stated a build before this module: the character concept prompt described
identity, wardrobe, and palette, and left proportion entirely to the image model. Two runs of the
same prompt could return a naturalistic figure and a chibi one, and neither was wrong by any
contract the pipeline held.

Proportion is stated in heads because that is the unit character artists size a figure in, and
because it converts to something an image model can act on: N heads tall means the head occupies
1/N of the standing silhouette. The number alone is a weak instruction, so the rendered clause
also gives that fraction and names the build.

Unset is the default and stays meaningful - it hands the choice back to the model rather than
quietly picking a house style.
"""

from __future__ import annotations

from typing import Final

CHARACTER_PROPORTION_SCHEMA_VERSION: Final = 1

#: Floor on how stylised a build may be requested. At two heads the head is half the whole
#: figure, which is about as far as the super-deformed end of the range goes before a body stops
#: being able to carry readable limbs, a wardrobe, or a weapon at sprite scale.
MINIMUM_HEADS_TALL: Final = 2.0
#: Ceiling at a naturalistic adult figure. Past roughly eight heads a character reads as
#: elongated stylisation rather than realism, which is a different art direction than this
#: parameter is for.
MAXIMUM_HEADS_TALL: Final = 8.0


def parse_character_heads_tall(value: object) -> float:
    """Validate a requested build, in heads.

    Accepts ints and floats; rejects bools, which are ints in Python and would otherwise read
    `True` as one head.
    """

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("character_heads_tall must be a number")
    heads = float(value)
    if heads != heads or heads in (float("inf"), float("-inf")):
        raise ValueError("character_heads_tall must be finite")
    if heads < MINIMUM_HEADS_TALL or heads > MAXIMUM_HEADS_TALL:
        raise ValueError(
            f"character_heads_tall must be between {MINIMUM_HEADS_TALL} and "
            f"{MAXIMUM_HEADS_TALL} heads"
        )
    # One decimal is the finest distinction that survives a sprite a few hundred pixels tall,
    # and rounding here keeps the run tag stable across equivalent requests.
    return round(heads, 1)


def _build_description(heads: float) -> str:
    if heads <= 2.5:
        return (
            "This is a super-deformed build: a very large head on a small compact body, with "
            "short limbs and a torso barely taller than the head."
        )
    if heads <= 4.0:
        return "This is a chibi build: an oversized head on a small, softly rounded body."
    if heads <= 5.5:
        return "This is a stylised build with a noticeably oversized head and a compact torso."
    if heads <= 7.0:
        return "This is a lightly stylised build, close to natural adult proportions."
    return "This is a naturalistic adult build."


def character_proportion_prompt(heads: float) -> str:
    """Render the proportion directive for the character concept prompt.

    The head fraction is spelled out because "three heads tall" is jargon an image model honours
    inconsistently, while "the head is a third of the full standing height" is a measurement.
    """

    fraction = 1.0 / heads
    return (
        f"CHARACTER PROPORTION: draw the character exactly {heads:g} heads tall. The head, "
        f"measured from the crown of the hair to the chin, is {fraction:.0%} of the full "
        "standing height from crown to sole. "
        f"{_build_description(heads)} "
        "Hold this proportion identical in every view and every frame."
    )


def character_proportion_tag_suffix(heads: float) -> str:
    """Separate run directories by build, so two proportions never share cached artwork."""

    return f"heads-{heads:g}".replace(".", "p")


#: Widest a measured build may stray from the requested one before the sheet is rejected.
#:
#: A multiple rather than a difference, because the tolerable error scales with the request: half
#: a head is a different character at two heads and a rounding error at eight.
#:
#: Two is deliberately generous. It is not there to police style drift - it is there to catch the
#: image model ignoring the directive outright, which is a large, unmistakable failure rather than
#: a near miss. Measured on the first village generated with the directive in place, a run
#: requesting two heads returned residents at 2.54, 3.06 and 3.34 heads - all visibly the right
#: cast - alongside one elf at 7.47, drawn as a realistic adult as though nothing had been asked.
#: The runtime matches heads, so that resident would have rendered about three and a half times
#: the player's height. A ceiling of twice the request separates those two cases cleanly.
PROPORTION_TOLERANCE_FACTOR: Final = 2.0

ACTOR_PROPORTION_ERROR_CODE = "scrolling-actor-proportion-v1"


class ActorProportionError(ValueError):
    """A sheet was drawn to a different build than the run asked for."""

    def __init__(self, message: str, *, measured: float, requested: float) -> None:
        super().__init__(f"{ACTOR_PROPORTION_ERROR_CODE}: {message}")
        self.code = ACTOR_PROPORTION_ERROR_CODE
        self.measured = measured
        self.requested = requested

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": str(self),
            "measured_heads_tall": round(self.measured, 3),
            "requested_heads_tall": self.requested,
        }


def measured_heads_tall(*, sprite_height_px: float, head_extent_px: float) -> float:
    """How many heads tall a drawn sheet actually is.

    Both terms are already on hand wherever this is called: the painted height comes from the
    alpha the canonicalizer has measured anyway, and the head extent is the scale reference the
    runtime is published for a separate reason. So the build is checkable without asking a
    provider anything, which is why this is a gate rather than a review.
    """

    if head_extent_px <= 0:
        raise ValueError("head extent must be positive to derive a build")
    if sprite_height_px <= 0:
        raise ValueError("sprite height must be positive to derive a build")
    return sprite_height_px / head_extent_px


def evaluate_actor_proportion(
    *,
    requested_heads: float,
    sprite_height_px: float,
    head_extent_px: float,
    tolerance_factor: float = PROPORTION_TOLERANCE_FACTOR,
) -> dict[str, object]:
    """Accept or reject a sheet's drawn build, and record the measurement either way.

    Bounded on both sides. A run asking for a realistic build and handed a chibi is wrong for the
    same reason and by the same mechanism as the reverse, and the head-matching runtime makes
    either one render at the wrong size rather than merely in the wrong style.
    """

    if tolerance_factor <= 1:
        raise ValueError("proportion tolerance factor must exceed 1")
    measured = measured_heads_tall(sprite_height_px=sprite_height_px, head_extent_px=head_extent_px)
    ceiling = requested_heads * tolerance_factor
    floor = requested_heads / tolerance_factor
    record: dict[str, object] = {
        "requested_heads_tall": requested_heads,
        "measured_heads_tall": round(measured, 3),
        "accepted_range": [round(floor, 3), round(ceiling, 3)],
        "sprite_height_px": round(sprite_height_px, 1),
        "head_extent_px": round(head_extent_px, 1),
    }
    if not floor <= measured <= ceiling:
        raise ActorProportionError(
            f"sheet is {measured:.2f} heads tall against a requested {requested_heads:g}; the "
            f"runtime matches heads, so it would render about {measured / requested_heads:.1f}x "
            "the intended height",
            measured=measured,
            requested=requested_heads,
        )
    return record
