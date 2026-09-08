# 0066 — A state proof is not a picture proof

Status: adopted, 2026-09-08. Corrects the evidence
[0065](0065-the-runner-is-retired-from-the-browser.md) retired the browser runner
on, and pays the debt that decision recorded rather than closing it quietly.

## Fact

0065 replaced a 14,133-line Phaser runner with a Godot genre and host, and
proved it with six hundred per-frame hashes and thirty sampled world digests,
all identical, field for field. That measurement was true then and is still true
now: it has been re-run at every step of this change and has never moved.

It was also, on its own, worth very little. Played, the port:

- drew no cut-in, so the world froze for ninety-eight frames on a blank screen
  at boot and again at every fight
- drew no boss, no boss projectiles, no player projectiles and no boss bar, so
  the player was shot to death by something invisible — measured across five
  seeds, **every** idle run ends `endedBy=shot` between 196 and 227 columns
- scaled a trimmed foreground band by its own height rather than by the frame it
  was painted against, drawing a 286-row canopy strip 3.58× too tall
- laid three tile widths where the viewport needed four, leaving 200 px of bare
  engine grey down the right of every frame
- read none of the five depth fields every band publishes, so the far glazing
  drew as sharp and as saturated as the rail underfoot
- threw no dust, played no sound, cast no contact shadow, and turned no coins
- sized the avatar by its atlas cell rather than by its calibration, so the body
  changed height between motions

Not one of those could move a frame hash. Every one of them is the first thing a
player sees.

## Challenge

The obvious reading is that the port was rushed. It was not especially: the
simulation is exact and has stayed exact. The real failure is narrower and worse,
because it is repeatable — **the proof measured the half of the work that was
easy to measure, and the retirement went ahead on it.**

0065 knew. Its evidence section says, in full, that no browser still was taken
and the picture comparison is one-sided, and the plan records the same debt under
"What step 8 turned out to owe, and did not pay". Both are honest. Neither
stopped the deletion. A falsifier that is written down and then not acted on is
documentation, not a gate.

The counter-argument for shipping anyway was real: a cross-renderer pixel diff
was never going to be an equality, this repository already retired that gate for
survival for exactly that reason, and the browser stills needed a WebGL context
driven from a transitive dependency. All of that is true, and none of it licenses
shipping *no* picture measurement. "The obvious gate is unavailable" is a reason
to find the gate that is available, not a reason to have none.

## Ruling

**A genre is not ported until its picture is measured, and the measurement must
be shown to fail on the defect it exists to catch.**

Where a reference frame exists, diff against it. Where none does — a retired
renderer, a new host, a genre whose only reference was deleted — the picture is
held to a weaker but real standard instead: that the things which must be in it
are in it, in the region they belong to, at a strength nothing else in the frame
reaches. That is `tools/runner_shots_check.py`.

A threshold in such a gate carries the measurement that motivated it, so a
reader can tell a margin from a coincidence. A threshold nobody measured is a
guess wearing a number, and two of this gate's first draft were exactly that.

## Evidence

**The gate is falsified before it is trusted.** Run against the build 0065
shipped, it fails every shot that build can produce:

    boot:  the cut-in covers 0.7% of the frame; the moment is not drawn
    fight: the boss bar region varies 671 down its columns; no bar is drawn
    run:   the sky window is 0.0% sky; a foreground band is oversized

Against the build this decision adopts, 4 of 4 pass. The unpainted-pixel check
has its own falsification: band coverage was broken on purpose and the sheet
re-shot, and 3 of 4 shots failed — `boot` excepted, honestly, because the cut-in
covers the hole at that step.

**Two thresholds were guesses and were corrected by measuring.** The boss-bar
check first asked only whether its region was *saturated*; the build with no bar
passed it, because the foliage showing through where the bar should have been is
saturated. It asks about column uniformity now: 100.8 mean per-column variance
with a bar drawn, 671.1 without. And a check on the bands' depth grading was
**dropped** rather than kept at a threshold that separates nothing — over a
region both builds agree on, graded and ungraded read 0.413 and 0.418. That
transform is gated where it can be: against the browser's own arithmetic in
`test_layer_presentation.gd`, and through the host path that carries it to a
texture, byte for byte, from a package on disk.

**The simulation never moved.** 600 of 600 frame hashes and 30 of 30 digests
stayed identical through every commit of this change, which is what a view being
a view means.

**Everything ported is checked against the browser's own output, not against
itself.** `presentation.ts`, the pure half of `dust.ts`, `gauge-bar.ts` and
`prepared-layer-presentation.ts` were each run over the test's exact inputs and
their answers printed to nine decimals. Three of those four modules are still in
the tree because the platformer calls them; the fourth was read out of a clone of
the commit before the deletion.

    13,768 checks in 39 files passed
    validate.sh --runner-run: four parities green, 4 of 4 pictures carry what they must
    boundaries contract: 5 passed

**What it costs.** Boot is 2.69 s, almost all of it the bands' depth grading.
Presenting at source resolution on one thread costs 12.7 s; presenting at the
size the band is drawn and splitting the rows across cores brings it here. The
transform stays a statement about pixels that knows nothing about cores, and a
test pins that a split of any width reassembles into the answer one thread gives.

## Falsifier

If a future runner defect is visible in the first ten seconds of play and this
sheet still passes, the sheet is measuring the wrong four steps, and the fix is a
fifth shot rather than a wider tolerance on the four.
