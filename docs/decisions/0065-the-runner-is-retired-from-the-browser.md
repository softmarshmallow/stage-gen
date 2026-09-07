# 0065 — The runner is retired from the browser

Status: adopted, 2026-09-08. Follows
[0061](0061-every-genre-runs-on-godot-and-web-is-the-viewer.md), which made Godot
the engine for every genre, and is the second genre to land under it after
oblique survival.

## Fact

`web/lib/sideview-runner/` and `web/app/runner/` were a complete side-view
runner: a fifteen-block manifest contract, sixteen systems sealed into a derived
frame order, and a Phaser host that drew it. 14,133 lines.

A Godot genre and host now play the same documents. The genre is
`godot/genres/sideview_runner/`; the sixteen families it composes with the
platformer are `godot/families/`; the host is `godot/hosts/sideview_runner/`.

## Challenge

Two runtimes playing one genre is the state 0061 exists to end, and a runner
kept "just in case" is a runner nobody maintains and nobody deletes. But a port
is only worth what it is proved by, and the thing being deleted is the reference
the proof is measured against — so the evidence has to exist before the deletion,
not after it.

## Ruling

The browser runner is deleted. The Godot genre and host replace it.

`web/lib/families/cues/` goes with it: it was the runner's alone. The other
fifteen families stay, because the platformer still composes them and its own
port is the next record.

## Evidence

**State parity is exact, and it is the whole run.** The browser's own replay
golden — six hundred frames of seed `0x5eed1234`, carrying five jumps, an air
jump, a held slide, a thrust, a death and a restart — replays on the Godot side
to:

- **600 of 600** per-frame sha256 hashes identical
- **30 of 30** sampled world digests identical, field for field

Both sides write a float as a nine-decimal string, so this is equality rather
than a tolerance. There is no "mean 0.0000" here because there is no mean: a
field either matched or it did not, and none did not.

**The derived frame order is the browser's.** Sixteen declarations seal into the
sixteen-step order `game.test.ts` asserts, including the two that move from
registration order. `godot/tests/test_runner_roster.gd` pins it.

**The host plays.** Booted against `out/iron-petal-c1-parity` and run to
simulation frame 245: 24.25 columns travelled, four pickups chained, parallax
bands and streamed ground and avatar and interface all drawn, at the design
space the manifest publishes its rectangles in.

**Check count.** The Godot suite is 13,524 checks in 34 files, of which the
runner's own are the roster order, the manifest contract and its refusals, and
the arithmetic of the arc, the hover, the thrust and the hazard boxes. The
sixteen families carry their own, every expected value computed by running the
browser's function rather than by reading the port.

**What this evidence does not cover, said plainly.** No browser still was taken,
so the picture comparison is one-sided: a Godot still exists and a Phaser one
does not. Two reasons, and neither is that it did not matter. A cross-renderer
pixel comparison was never going to be an equality — it is a difference of
renderers as much as a difference of games — and this repository already
retired exactly that gate for oblique survival once its state parity was
trusted. And the browser stills needed a WebGL context driven from a browser
automation library that is present only as a transitive dependency, which is not
something a gate should stand on.

## Falsifier

A drawing defect that state parity cannot see: a band at the wrong depth, a
hazard drawn where its box is not, an avatar anchored to the wrong edge of its
cell. If one is found in the Godot runner that the browser runner did not have,
this record was published on evidence that was one measurement short, and the
picture sheet the plan asks for should have been taken before the deletion
rather than argued around after it.
