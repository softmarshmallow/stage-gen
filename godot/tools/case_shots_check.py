#!/usr/bin/env python3
"""Measure the case's gate sheet.

    python3 tools/case_shots_check.py <shot directory> [--report]

Decision 0066: a genre is not ported until its picture is measured, and the
measurement must be shown to fail on the defect it exists to catch. The case
runtime has been exact against the browser for twenty actions since it landed —
the beat order, the facts crossing between beats, and the save written the moment
a beat is entered — and not one of those twenty digests says whether a beat is on
the screen, whether the bar names it, or whether the backlog is over the game or
under it.

Six named states are photographed by `tools/case_capture.gd` against
`out/the-grain-episode-one`, whose eight beats are six scenarios and two rooms.
Each check below is one defect this container could ship without the state proof
noticing.

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
    mean_luma,
)

#: The container's canvas is 1672x1024 with a 44px bar across the top.
#: The bar's own strip, left of the backlog toggle. A first draft read the whole
#: bar and passed a build whose title was blank, because the toggle's own word is
#: ink too — the region was wrong, not the threshold.
BAR = (0, 0, 1200, 44)
#: The part of that strip *after* the case's own name, where the beat and "beat N
#: of M" are written. The case name alone clears the whole-strip floor with room
#: to spare, so a container that never says which of eight beats you are in
#: passed a first sheet.
BAR_BEAT = (320, 0, 880, 44)
STAGE = (0, 44, 1672, 980)
#: The left of the stage. A scene draws 1672x941 and fills it edge to edge; a
#: room draws 1280x1214 and letterboxes to 1033 wide, leaving this strip the
#: container's own ground. Which of the two is here is how a still says which
#: kind of beat is being played.
STAGE_LEFT = (0, 60, 260, 940)
#: Around the Continue a finished beat offers, centred and lifted off the bottom.
CONTINUE = (700, 944, 280, 60)
#: The middle of a curtain, where its heading and its line are.
CURTAIN_TEXT = (400, 400, 872, 200)
#: The whole middle of a curtain, for finding its buttons in. Not a band under
#: the words: the curtain centres its column, so taking the buttons away moves
#: the words *down into* any fixed band beneath them — measured, an ink reading
#: there went **up** when the buttons were removed.
#:
#: What a button has and a word does not is a border: `CaseChromeButton.BORDER`
#: is the foreground at 0.7 alpha, which over the curtain's black reads as a mid
#: grey no label is drawn in.
CURTAIN_CONTROLS = (400, 380, 872, 300)
#: `Color(0.902, 0.902, 0.902, 0.7)` over `Color(0, 0, 0, 0.85)` on black.
CURTAIN_BORDER = (161, 161, 161)
#: The backlog's list, under its heading. A first sheet measured only how dark
#: the stage went behind the overlay, so a backlog drawn with not one line in it
#: read *better* than the real one.
BACKLOG_LINES = (40, 130, 1600, 680)

#: The container's own ground, and the bar's. Pure black, because the chrome
#: belongs to the case rather than to any package it plays.
GROUND = (0, 0, 0)

UNPAINTED_TOLERANCE = 8

#: How much of the bar must be something other than the bar. Measured: 5.3% to
#: 6.4% across all six shots, with the case, the beat and "beat N of M" written
#: across it. It is six and not three because the bar is *always* visible: a
#: curtain covers the beat and not the line saying which beat it is, which is
#: where the browser puts the two and which this got wrong first time. With the
#: line withheld the same strip reads 0.0%.
BAR_INK_MINIMUM = 0.005

#: How much of the stage must be something other than bare ground. Measured:
#: 75.7% with a scene, 47.2% with a letterboxed room.
STAGE_INK_MINIMUM = 0.30

#: How much of the stage's left strip is bare ground. A scene fills it; a room
#: letterboxes and leaves it. Measured: 1.8% at `boot` and 100.0% at `room`,
#: which is the container framing two genres of different shape without asking
#: either to change shape.
LETTERBOX_SCENE_MAXIMUM = 0.20
LETTERBOX_ROOM_MINIMUM = 0.80

#: How far the Continue's own rectangle must change when a beat reports its
#: outcome. Measured: 18.5 between `room` and `crossing`; 0.0 with the
#: affordance never shown.
CONTINUE_DIFFERENCE = 5.0

#: How dark the stage goes behind a curtain or the backlog. Measured: 70.5 luma
#: playing a room and 93.3 playing a scene, against 9.0 under the backlog and
#: 0.9 under a curtain. The two overlays are the browser's `bg-black/95` and
#: `bg-black/85`.
COVERED_MAXIMUM_LUMA = 12.0

#: How much of a curtain's middle must be words. Measured: 5.7% on the offer to
#: continue and 4.9% on the closing card.
CURTAIN_INK_MINIMUM = 0.01

#: How much of a curtain's middle must be button border. Measured: 0.43% on the
#: offer to continue and 0.28% on the closing card, against 0.11% and 0.07% with
#: the buttons taken away — the remainder being the labels' own anti-aliasing,
#: which passes through the same grey on its way from black to white.
CURTAIN_CONTROL_MINIMUM = 0.0018

#: How much of the bar *after* the case's own name must be ink. Measured: 4.0% to
#: 5.6% across all six shots, with the beat's name and "beat N of M" on it.
BAR_BEAT_INK_MINIMUM = 0.005

#: How much of the backlog's list must be lines. Measured: 3.2% with eight lines
#: in it against nothing at all when the list is empty, which a first sheet read
#: as an *improvement*, because the only thing it asked of the backlog was how
#: dark the stage went behind it.
BACKLOG_INK_MINIMUM = 0.01

#: The moments a leaf is on screen and uncovered.
PLAYING = ("boot", "room", "crossing")
#: The moments something the container drew is over the beat.
COVERED = ("backlog", "continue", "finished")


def measure(shots: dict[str, Shot]) -> dict[str, float]:
    read: dict[str, float] = {}
    for name, shot in sorted(shots.items()):
        read[f"{name}.unpainted"] = fraction_near(
            shot, (0, 0, shot.width, shot.height), UNPAINTED, UNPAINTED_TOLERANCE
        )
        read[f"{name}.bar_ink"] = ink_fraction(shot, BAR, GROUND, 24, 2)
        read[f"{name}.stage_ink"] = ink_fraction(shot, STAGE, GROUND, 24, 4)
        # Exactly the ground, not merely dark. A scene's own backdrop can be
        # near-black — the office at dusk is — and a loose tolerance counted it
        # as bare canvas: `boot` read 22.7% letterboxed when it is 0.4%.
        read[f"{name}.letterbox"] = fraction_near(shot, STAGE_LEFT, GROUND, 3, 4)
        read[f"{name}.stage_luma"] = mean_luma(shot, STAGE, 4)
        read[f"{name}.curtain_ink"] = ink_fraction(shot, CURTAIN_TEXT, GROUND, 40, 2)
        read[f"{name}.curtain_control_ink"] = fraction_near(
            shot, CURTAIN_CONTROLS, CURTAIN_BORDER, 14
        )
        read[f"{name}.bar_beat_ink"] = ink_fraction(shot, BAR_BEAT, GROUND, 24, 2)
        read[f"{name}.backlog_ink"] = ink_fraction(shot, BACKLOG_LINES, GROUND, 40, 4)
    if "room" in shots and "crossing" in shots:
        read["crossing.continue"] = mean_difference(shots["room"], shots["crossing"], CONTINUE)
    return read


def check(shots: dict[str, Shot], read: dict[str, float]) -> list[str]:
    problems: list[str] = []
    for name in sorted(shots):
        if read[f"{name}.unpainted"] > 0.0:
            problems.append(
                f"{name}: {read[f'{name}.unpainted']:.1%} of the frame is unpainted background"
            )
        if read[f"{name}.bar_ink"] < BAR_INK_MINIMUM:
            problems.append(
                f"{name}: the chrome bar is {read[f'{name}.bar_ink']:.1%} ink; "
                "nothing names where the player is"
            )
        if read[f"{name}.bar_beat_ink"] < BAR_BEAT_INK_MINIMUM:
            problems.append(
                f"{name}: the bar after the case's name is "
                f"{read[f'{name}.bar_beat_ink']:.1%} ink; it never says which beat this is"
            )
    for name in PLAYING:
        if name not in shots:
            continue
        if read[f"{name}.stage_ink"] < STAGE_INK_MINIMUM:
            problems.append(
                f"{name}: the stage is {read[f'{name}.stage_ink']:.1%} drawn; "
                "the beat is not on the screen"
            )
    if "boot" in shots and read["boot.letterbox"] > LETTERBOX_SCENE_MAXIMUM:
        problems.append(
            f"boot: {read['boot.letterbox']:.1%} of the stage's left strip is bare ground; "
            "a scene should fill the frame it was drawn for"
        )
    if "room" in shots and read["room.letterbox"] < LETTERBOX_ROOM_MINIMUM:
        problems.append(
            f"room: {read['room.letterbox']:.1%} of the stage's left strip is bare ground; "
            "a room is a different shape and should letterbox rather than stretch"
        )
    if "crossing" in shots and read.get("crossing.continue", 0.0) < CONTINUE_DIFFERENCE:
        problems.append(
            f"a beat reported its outcome and the Continue's own rectangle moved by "
            f"{read['crossing.continue']:.1f}; there is nothing to press"
        )
    for name in COVERED:
        if name not in shots:
            continue
        if read[f"{name}.stage_luma"] > COVERED_MAXIMUM_LUMA:
            problems.append(
                f"{name}: the stage reads {read[f'{name}.stage_luma']:.1f} luma under what "
                "the container drew over it; the beat is showing through"
            )
    for name in ("continue", "finished"):
        if name not in shots:
            continue
        if read[f"{name}.curtain_ink"] < CURTAIN_INK_MINIMUM:
            problems.append(
                f"{name}: the curtain is {read[f'{name}.curtain_ink']:.1%} ink; it says nothing"
            )
        if read[f"{name}.curtain_control_ink"] < CURTAIN_CONTROL_MINIMUM:
            problems.append(
                f"{name}: the curtain's middle is "
                f"{read[f'{name}.curtain_control_ink']:.2%} button border; "
                "there is nothing to press"
            )
    if "backlog" in shots and read["backlog.backlog_ink"] < BACKLOG_INK_MINIMUM:
        problems.append(
            f"backlog: the list is {read['backlog.backlog_ink']:.1%} ink; "
            "the backlog is open and holds nothing"
        )
    return problems


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3) or (len(argv) == 3 and argv[2] != "--report"):
        print(__doc__)
        return 2
    directory = Path(argv[1])
    paths = sorted(directory.glob("*.png"))
    if not paths:
        print(f"case shots: no pictures in {directory}")
        return 1
    shots = {path.stem: Shot(path) for path in paths}
    read = measure(shots)
    if len(argv) == 3:
        for key in sorted(read):
            print(f"   {key:30s} {read[key]:.4f}")
        return 0
    problems = check(shots, read)
    if problems:
        for problem in problems:
            print(f"   {problem}")
        print(f"case shots: {len(problems)} problems across {len(shots)} pictures")
        return 1
    print(f"   {len(shots)} of {len(shots)} pictures carry what they must")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
