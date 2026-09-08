#!/usr/bin/env python3
"""Measure the point-and-click room's gate sheet.

    python3 tools/room_shots_check.py <shot directory> [--report]

Decision 0066: a genre is not ported until its picture is measured, and the
measurement must be shown to fail on the defect it exists to catch. The runner
was retired on six hundred exact frame hashes and shipped with no boss, no
cut-in, no dust and no sound, because not one of those can move a hash. A room
has no frames at all — its whole simulation is a reducer over clicks, and its
state proof is fourteen clicks that agree with the browser exactly — so the gap
between "the state is right" and "the picture is right" is the whole of the
view.

Five named states are photographed by `tools/room_capture.gd` against
`out/the-grain-window-a4`, and each check below is one defect this port could
ship without the state proof noticing. Thresholds carry the measurement that
motivated them, so a reader can tell a margin from a coincidence.

`--report` prints every measured value instead of judging them. That is how the
thresholds here were set, and how a future one should be.

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
    mean_luma,
)

#: The rectangles below are `RoomLayout.of` resolved for `out/the-grain-window-a4`:
#: a 1280x720 scene, a `panel_frame` with 96px insets at `draw_scale` 2 (48 on
#: screen), and a `button_rect` with 80/48/74/52 at the same scale (40/24/37/26).
#: They are written out rather than recomputed so that a layout change has to
#: come here and say so.
ROOM = (0, 0, 1280, 720)
NARRATION_PLATE = (24, 732, 1232, 264)
NARRATION_TEXT = (78, 784, 1124, 160)
#: The canvas gaps either side of the narration plate. The browser's own defect
#: is here: its plate is 156px tall with a 52px interior, its step-down ladder
#: stops at 18px, and the window room's 516-character line is four wrapped lines
#: at that size — so the tail rendered *past the plate*, onto the backdrop above
#: and the control bar below. Ink in either gap is a sentence that escaped.
#:
#: A first draft of this check looked at the last rows *inside* the box instead,
#: on the theory that a clipped line leaves a cut glyph there. It does not: with
#: the ladder defeated on purpose the cut fell cleanly between two lines, the
#: strip stayed empty and the broken build passed. Measuring the outside is the
#: axis, and the inside was the coincidence.
NARRATION_GAP_ABOVE = (24, 721, 1232, 10)
NARRATION_GAP_BELOW = (24, 997, 1232, 10)
BAR = (0, 1008, 1280, 206)
VERB_ACT = (647, 1066, 195, 90)
VERB_LOOK = (854, 1066, 195, 90)
WIN_CARD = (280, 202, 720, 316)
#: Inside the end card and clear of its title and line, for the "is the card
#: drawn" reading.
WIN_INTERIOR = (340, 430, 600, 60)
#: A band of the room the end card does not reach — the card ends at y 518 — for
#: reading the dim behind it. Measured over the whole room band instead, the card
#: is a cream plate and *raises* the mean: 46.7 at `boot`, 63.1 at `solved`. The
#: dim is real; the region was wrong.
ROOM_BELOW_CARD = (0, 540, 1280, 180)

#: The canvas ground, `HostRoomLeaf.CANVAS_GROUND`. A declared plate showing it
#: is a plate that did not draw.
GROUND = (5, 7, 10)

#: Nothing in any package is anywhere near the sentinel, which is the point.
UNPAINTED_TOLERANCE = 8

#: How much of a plate may be canvas ground before the plate is not drawn.
#: Not zero, because a nine-slice's exterior is transparent by published policy
#: and its corners let the ground through: the control bar reads 1.5% with its
#: panel drawn. A panel that is not drawn at all reads far above this.
PLATE_GROUND_MAXIMUM = 0.04

#: How much of the narration box must be something other than the plate it is
#: written on. Measured on the sheet: 0.64% at `boot`, which is the room's name
#: and nothing else, and 12.1% at `narrated`, which is a full paragraph. The
#: floor is set under the smaller of the two, because a room that opens on its
#: own name is the least ink this box will ever legitimately carry.
NARRATION_INK_MINIMUM = 0.003

#: How much of the gap either side of the plate may carry something other than
#: canvas ground. Measured: 0.00% with the words fitted, and see the record for
#: the reading with the fitting removed.
NARRATION_ESCAPE_MAXIMUM = 0.005

#: How far the chosen verb's art must differ from the unchosen one beside it.
#: The sheet publishes `normal, hover, pressed, disabled` and a toggle borrows
#: the pressed cell, so two buttons in two states are two different pictures.
#: Measured: 40.6 between `act` (chosen) and `look` (not) at `boot`; 0.0 if
#: `set_selected` does nothing.
VERB_STATE_DIFFERENCE = 12.0

#: How far the room must change when the hotspot overlay is switched on.
#: Measured: 3.0 over the whole room band with fourteen markers drawn, 0.0
#: without. Small because a 3px outline on fourteen rectangles is a small part
#: of a 1280x720 picture — which is why the floor is well under it and why the
#: reading is a difference rather than a coverage.
MARKER_DIFFERENCE = 0.5

#: The end card dims the room it is drawn over. Measured on the band below the
#: card: 36.6 luma at `boot`, 15.1 at `solved`.
WIN_DIM_MAXIMUM_LUMA = 30.0


def _plate_colour(shot: Shot, box) -> tuple[int, int, int]:
    """The surface a region is drawn on: its most common colour, coarsely.

    Quantised to sixteen levels per channel and averaged inside the winning
    bucket, so ink grain and a paper texture do not each become their own
    colour. This is measured rather than declared because the plate is generated
    art — cream in this package, near-black in the next.
    """
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


def measure(shots: dict[str, Shot]) -> dict[str, float]:
    """Every number this gate reads, named. `--report` prints these."""
    read: dict[str, float] = {}
    for name, shot in sorted(shots.items()):
        read[f"{name}.unpainted"] = fraction_near(
            shot, (0, 0, shot.width, shot.height), UNPAINTED, UNPAINTED_TOLERANCE
        )
        read[f"{name}.narration_plate_ground"] = fraction_near(shot, NARRATION_PLATE, GROUND, 12)
        read[f"{name}.bar_ground"] = fraction_near(shot, BAR, GROUND, 12)
        plate = _plate_colour(shot, NARRATION_PLATE)
        read[f"{name}.narration_ink"] = ink_fraction(shot, NARRATION_TEXT, plate, 40, 2)
        read[f"{name}.narration_escaped"] = max(
            ink_fraction(shot, NARRATION_GAP_ABOVE, GROUND, 24, 1),
            ink_fraction(shot, NARRATION_GAP_BELOW, GROUND, 24, 1),
        )
        read[f"{name}.room_luma"] = mean_luma(shot, ROOM)
        read[f"{name}.room_below_card_luma"] = mean_luma(shot, ROOM_BELOW_CARD)

    if "boot" in shots:
        boot = shots["boot"]
        # Two verbs in one frame: `act` is chosen and wears the pressed cell,
        # `look` is not and wears the normal one. Read on the same frame, so a
        # sheet whose four cells are one picture cannot pass by accident.
        read["boot.act_vs_look"] = _rect_difference(boot, VERB_ACT, VERB_LOOK)
    if "boot" in shots and "look" in shots:
        read["look.act_changed"] = mean_difference(shots["boot"], shots["look"], VERB_ACT)
    if "boot" in shots and "hints" in shots:
        read["hints.marker_difference"] = mean_difference(shots["boot"], shots["hints"], ROOM)
    if "solved" in shots:
        read["solved.card_ground"] = fraction_near(shots["solved"], WIN_CARD, GROUND, 12)
        card = _plate_colour(shots["solved"], WIN_INTERIOR)
        read["solved.card_is_plate"] = 1.0 - ink_fraction(
            shots["solved"], WIN_INTERIOR, card, 40, 2
        )
    return read


def _rect_difference(shot: Shot, first, second) -> float:
    """How far two same-sized rectangles of one shot differ, per channel."""
    x0, y0, w, h = first
    x1, y1, _w, _h = second
    total, count = 0.0, 0
    for dy in range(0, h, 2):
        for dx in range(0, w, 2):
            here, there = shot.at(x0 + dx, y0 + dy), shot.at(x1 + dx, y1 + dy)
            total += sum(abs(here[c] - there[c]) for c in range(3)) / 3.0
            count += 1
    return total / count if count else 0.0


def check(shots: dict[str, Shot], read: dict[str, float]) -> list[str]:
    """Every problem this sheet has, named. Empty is a pass."""
    problems: list[str] = []
    for name in sorted(shots):
        # Nothing unpainted, anywhere. The first build of this host drew no
        # canvas ground at all, so the HUD's own margins and the gap between its
        # two plates were the clear colour, in every shot.
        if read[f"{name}.unpainted"] > 0.0:
            problems.append(
                f"{name}: {read[f'{name}.unpainted']:.1%} of the frame is unpainted background"
            )
        for label, key in (
            ("narration plate", "narration_plate_ground"),
            ("control bar", "bar_ground"),
        ):
            value = read[f"{name}.{key}"]
            if value > PLATE_GROUND_MAXIMUM:
                problems.append(
                    f"{name}: {value:.1%} of the {label} is bare canvas; its panel is not drawn"
                )
        if read[f"{name}.narration_ink"] < NARRATION_INK_MINIMUM:
            problems.append(
                f"{name}: the narration box is {read[f'{name}.narration_ink']:.1%} ink; "
                "nothing is written on the plate"
            )
        if read[f"{name}.narration_escaped"] > NARRATION_ESCAPE_MAXIMUM:
            problems.append(
                f"{name}: {read[f'{name}.narration_escaped']:.1%} of the canvas beside the "
                "narration plate is not canvas; the words are running off the plate"
            )

    if "boot" in shots and read["boot.act_vs_look"] < VERB_STATE_DIFFERENCE:
        problems.append(
            f"the chosen verb differs from the unchosen one by {read['boot.act_vs_look']:.1f}; "
            "the button states are one picture"
        )
    if "look" in shots and read.get("look.act_changed", 0.0) < VERB_STATE_DIFFERENCE:
        problems.append(
            f"choosing Look moved the Act button by {read['look.act_changed']:.1f}; "
            "the selection is not drawn"
        )
    if "hints" in shots and read.get("hints.marker_difference", 0.0) < MARKER_DIFFERENCE:
        problems.append(
            f"the hotspot overlay moved the room by {read['hints.marker_difference']:.2f}; "
            "no markers are drawn"
        )
    if "solved" in shots:
        if read["solved.card_ground"] > PLATE_GROUND_MAXIMUM:
            problems.append(
                f"solved: {read['solved.card_ground']:.1%} of the end card is bare canvas; "
                "the card is not drawn"
            )
        if read["solved.card_is_plate"] < 0.9:
            problems.append(
                f"solved: the end card's interior is {read['solved.card_is_plate']:.1%} one "
                "surface; it is not a drawn plate"
            )
        if read["solved.room_below_card_luma"] > WIN_DIM_MAXIMUM_LUMA:
            problems.append(
                f"solved: the room reads {read['solved.room_below_card_luma']:.1f} luma "
                "beside the end card; it is not dimmed"
            )
    return problems


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3) or (len(argv) == 3 and argv[2] != "--report"):
        print(__doc__)
        return 2
    directory = Path(argv[1])
    paths = sorted(directory.glob("*.png"))
    if not paths:
        print(f"room shots: no pictures in {directory}")
        return 1
    shots = {path.stem: Shot(path) for path in paths}
    read = measure(shots)
    if len(argv) == 3:
        for key in sorted(read):
            print(f"   {key:38s} {read[key]:.4f}")
        return 0
    problems = check(shots, read)
    if problems:
        for problem in problems:
            print(f"   {problem}")
        print(f"room shots: {len(problems)} problems across {len(shots)} pictures")
        return 1
    print(f"   {len(shots)} of {len(shots)} pictures carry what they must")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
