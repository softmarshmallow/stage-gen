#!/usr/bin/env python3
"""Measure the dialogue scene's gate sheet.

    python3 tools/dialogue_shots_check.py <shot directory> [--report]

Decision 0066: a genre is not ported until its picture is measured, and the
measurement must be shown to fail on the defect it exists to catch. The
scenario runtime this scene plays has been exact against the browser for
twenty-six actions since it landed, and twenty-six exact digests say nothing
about whether a portrait is drawn, which way round the speaker and the listener
are, or whether the line is on the panel or off the bottom of it.

Six named moments are photographed by `tools/dialogue_capture.gd` against
`out/the-grain-scene-a`, and each check below is one defect this port could ship
without the state proof noticing. Thresholds carry the reading that motivated
them.

`--report` prints every measured value instead of judging them.

No dependencies: `tools/shot_png.py` is thirty lines of zlib.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shot_png import (
    UNPAINTED,
    Shot,
    fraction_near,
    ink_fraction,
    mean_difference,
)

#: The rectangles below are `DialogueLayout` resolved for `out/the-grain-scene-a`:
#: a 1672x941 frame and a `panel_frame` with 96px insets at `draw_scale` 2, so a
#: panel of 198 interior is 294 tall and opens at y 617.
PANEL = (36, 617, 1600, 294)
#: The speaker's row, right of where any name reaches: blank drawn plate on every
#: shot where the panel is up.
PANEL_BLANK = (900, 668, 640, 34)
BODY = (94, 707, 1484, 150)
PROGRESS = (1300, 828, 278, 28)

#: Firmly inside the `left` slot and clear of `center`: `left` opens at x 344.7
#: and `center` at 662.4, so this window is Edwin and nobody else.
LEFT_SLOT = (500, 150, 150, 500)

#: Frame margins the cast never reaches. The leftmost slot in play at these
#: moments is `left` at x 344.7 and the rightmost is `right`, ending at 1594.8.
#: A portrait drawn at the *raw* framing scale rather than the one normalised
#: against the zoom its plates were painted at is 3.244x too large and covers
#: both. Restricted to above the panel so the panel is not the thing being read.
MARGIN_LEFT = (0, 0, 140, 600)
MARGIN_RIGHT = (1600, 0, 72, 600)

#: Inside the first admitted option's button, clear of its centred label: the
#: row opens at y 216 for two options and each button is 1137x84.
CHOICE_BLANK = (330, 240, 180, 36)
#: Inside the end card, clear of its title and beside its control.
END_BLANK = (540, 500, 180, 40)

UNPAINTED_TOLERANCE = 8

#: How much of a drawn plate may be something other than the plate. A panel that
#: did not draw shows the backdrop through it, which is a painting.
#: Measured: 0.0% over the blank row on all four panelled moments, and 72.8% at
#: `choice`, where the panel is deliberately down and the reading is the
#: backdrop showing through the rectangle it used to cover.
PLATE_NOISE_MAXIMUM = 0.10

#: How much of the body box must be ink. Measured across the four panelled
#: moments: 1.2% at `pair` (three words), 1.7% at `boot` and `swap`, 6.6% at
#: `narration` (two full lines). With the line written in the panel's own colour
#: the same boxes read 0.5%, which is the plate's paper grain and not a word, so
#: the floor sits between the two rather than under both.
BODY_INK_MINIMUM = 0.008

#: The same, for the progress readout, which is the one thing on the panel that
#: is neither the words nor who said them. Measured: 14.0% to 14.8%.
PROGRESS_INK_MINIMUM = 0.02

#: How far a portrait's own window must change when the speaker changes.
#: A listener is drawn at 0.88 alpha over a cool tint and a speaker at full and
#: 1.045 about its feet, so the same actor between two adjacent lines is two
#: different pictures. Measured: 18.9 between `pair` and `swap`, over a window
#: that is Edwin and nothing else. A first draft read a wider window that was
#: mostly the backdrop behind him and got 7.6 for the same change — true, but a
#: margin that thin is a coincidence waiting to happen.
EMPHASIS_DIFFERENCE = 6.0

#: How far the same window must change when somebody walks into it. Measured:
#: 30.3 between `boot`, where the slot is empty motor court, and `pair`, where
#: Edwin is standing in it.
CAST_DIFFERENCE = 10.0

#: How far the frame's margins may move between moments that share a backdrop.
#: They must not: the cast never reaches them. Measured 0.0 across all four, and
#: see the record for the reading with the framing scale left un-normalised.
MARGIN_DIFFERENCE_MAXIMUM = 0.5


def _plate_colour(shot: Shot, box) -> tuple[int, int, int]:
    """The surface a region is drawn on: its most common colour, coarsely."""
    buckets: dict[tuple[int, int, int], list[int]] = {}
    for pixel in shot.region(box, 2):
        key = (pixel[0] // 16, pixel[1] // 16, pixel[2] // 16)
        found = buckets.setdefault(key, [0, 0, 0, 0])
        found[0] += pixel[0]
        found[1] += pixel[1]
        found[2] += pixel[2]
        found[3] += 1
    if not buckets:
        return (0, 0, 0)
    best = max(buckets.values(), key=lambda entry: entry[3])
    return (best[0] // best[3], best[1] // best[3], best[2] // best[3])


#: The moments the panel is up on. `choice` and `end` replace it.
PANELLED = ("boot", "pair", "swap", "narration")
#: The moments that share the motor-court backdrop, for the margin reading.
SAME_BACKDROP = ("boot", "pair", "swap", "narration")


def measure(shots: dict[str, Shot]) -> dict[str, float]:
    read: dict[str, float] = {}
    for name, shot in sorted(shots.items()):
        read[f"{name}.unpainted"] = fraction_near(
            shot, (0, 0, shot.width, shot.height), UNPAINTED, UNPAINTED_TOLERANCE
        )
        plate = _plate_colour(shot, PANEL_BLANK)
        read[f"{name}.panel_noise"] = ink_fraction(shot, PANEL_BLANK, plate, 30, 2)
        read[f"{name}.body_ink"] = ink_fraction(shot, BODY, plate, 40, 2)
        read[f"{name}.progress_ink"] = ink_fraction(shot, PROGRESS, plate, 40, 1)

    if "pair" in shots and "swap" in shots:
        read["swap.emphasis"] = mean_difference(shots["pair"], shots["swap"], LEFT_SLOT)
    if "boot" in shots and "pair" in shots:
        read["pair.cast"] = mean_difference(shots["boot"], shots["pair"], LEFT_SLOT)
    present = [name for name in SAME_BACKDROP if name in shots]
    if len(present) > 1:
        first = shots[present[0]]
        worst = 0.0
        for name in present[1:]:
            worst = max(
                worst,
                mean_difference(first, shots[name], MARGIN_LEFT),
                mean_difference(first, shots[name], MARGIN_RIGHT),
            )
        read["cast.margin_difference"] = worst
    if "choice" in shots:
        button = _plate_colour(shots["choice"], CHOICE_BLANK)
        read["choice.button_noise"] = ink_fraction(shots["choice"], CHOICE_BLANK, button, 30, 1)
    if "end" in shots:
        card = _plate_colour(shots["end"], END_BLANK)
        read["end.card_noise"] = ink_fraction(shots["end"], END_BLANK, card, 30, 2)
    return read


def check(shots: dict[str, Shot], read: dict[str, float]) -> list[str]:
    problems: list[str] = []
    for name in sorted(shots):
        if read[f"{name}.unpainted"] > 0.0:
            problems.append(
                f"{name}: {read[f'{name}.unpainted']:.1%} of the frame is unpainted "
                "background or a stand-in for art that did not load"
            )
    for name in PANELLED:
        if name not in shots:
            continue
        if read[f"{name}.panel_noise"] > PLATE_NOISE_MAXIMUM:
            problems.append(
                f"{name}: {read[f'{name}.panel_noise']:.1%} of the panel's blank row is not "
                "the panel; the conversation box is not drawn"
            )
        if read[f"{name}.body_ink"] < BODY_INK_MINIMUM:
            problems.append(
                f"{name}: the body box is {read[f'{name}.body_ink']:.1%} ink; "
                "the line is not written on the panel"
            )
        if read[f"{name}.progress_ink"] < PROGRESS_INK_MINIMUM:
            problems.append(
                f"{name}: the progress corner is {read[f'{name}.progress_ink']:.1%} ink; "
                "the readout is not drawn"
            )
    if "swap" in shots and read.get("swap.emphasis", 0.0) < EMPHASIS_DIFFERENCE:
        problems.append(
            f"the speaker changed and Edwin's window moved by "
            f"{read['swap.emphasis']:.1f}; nobody is emphasised"
        )
    if "pair" in shots and read.get("pair.cast", 0.0) < CAST_DIFFERENCE:
        problems.append(
            f"an actor took the stage and his window moved by {read['pair.cast']:.1f}; "
            "the cast is not drawn"
        )
    if read.get("cast.margin_difference", 0.0) > MARGIN_DIFFERENCE_MAXIMUM:
        problems.append(
            f"the frame's margins move by {read['cast.margin_difference']:.1f} between "
            "moments that share a backdrop; a portrait is oversized"
        )
    if "choice" in shots:
        if read["choice.button_noise"] > PLATE_NOISE_MAXIMUM:
            problems.append(
                f"choice: {read['choice.button_noise']:.1%} of the first option is not a "
                "button; the choice row is not drawn"
            )
        if read["choice.panel_noise"] <= PLATE_NOISE_MAXIMUM:
            problems.append(
                "choice: the conversation panel is still drawn under the options; "
                "exactly one of the two belongs on screen"
            )
    if "end" in shots and read["end.card_noise"] > PLATE_NOISE_MAXIMUM:
        problems.append(
            f"end: {read['end.card_noise']:.1%} of the end card is not the card; it is not drawn"
        )
    return problems


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3) or (len(argv) == 3 and argv[2] != "--report"):
        print(__doc__)
        return 2
    directory = Path(argv[1])
    paths = sorted(directory.glob("*.png"))
    if not paths:
        print(f"dialogue shots: no pictures in {directory}")
        return 1
    shots = {path.stem: Shot(path) for path in paths}
    read = measure(shots)
    if len(argv) == 3:
        for key in sorted(read):
            print(f"   {key:34s} {read[key]:.4f}")
        return 0
    problems = check(shots, read)
    if problems:
        for problem in problems:
            print(f"   {problem}")
        print(f"dialogue shots: {len(problems)} problems across {len(shots)} pictures")
        return 1
    print(f"   {len(shots)} of {len(shots)} pictures carry what they must")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
