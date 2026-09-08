# The Godot promotion: the path

Status: in flight. Steps 0 to 3, the kernel and the runner have landed, and step 10's three
simulations are ported and proved; the table marks them. Companion to [the host contract](../spec/game/host-contract.md)
(the end state) and
[decision 0061](../decisions/0061-every-genre-runs-on-godot-and-web-is-the-viewer.md)
(the ruling). This document is the path, and it dies when the path is walked.

Four browser games become four Godot hosts; `web/` keeps the run list, the run
view, the inspector and the gallery, and plays nothing. Hosting — an upload, a
channel, a catalogue, a URL — is out of scope and stays in
[issue 8](https://github.com/softmarshmallow/stage-gen/issues/8).

## The rules that hold across every step

- **Zero provider operations.** Every input is a run already under `out/` or a
  fixture serialised from a browser test. No art is regenerated, no manifest
  kind moves, no published run is dropped by a consumer change.
- **The incumbent is the reference until it is gone.** Before a genre is
  ported, the browser side commits its own per-step state for a scripted seed
  as `<script>.web.jsonl`, plus design-space stills. The host replays the same
  script and the diff must be empty. The browser game is deleted in the change
  that lands its host, so no genre is ever played twice.
- **A retirement is a numbered record**, carrying the parity line count, the
  picture sheet, the smoke, and the check count against the tests it replaces.
- **The gate is green at every boundary.** A commit that leaves `bun run check`
  or `uv run python scripts/check.py` red is not a boundary.
- **A record is written in the commit that holds its evidence**, never earlier.

## The steps

| # | Commit | What lands | The gate |
| --- | --- | --- | --- |
| 0 ✔ | A | The rulings that have their evidence today (0061, 0062), the host contract, the doc moves, the history exemption in the docs gate | `check_docs.py`, the docs contract tests |
| 1 ✔ | B | The viewer is decoupled: the home index stops importing genre readers, `/packages` goes, `/runs/<tag>/artifacts` arrives, dead platformer modules go, every run with a plan gets an execution view | `bun run check`, `bun test`, `check.py` |
| 2 ✔ | C | Survival's instruments pinned on the unmoved tree: three parity scripts as goldens, one capture sheet | the goldens reproduce twice, byte for byte |
| 3 ✔ | D | The mono-project: one `godot/project.godot`, the layers as directories, the survival host relocated by text edits, names prefixed, paths edited | goldens byte-identical, capture sheet mean 0.0 / p99 0.0 |
| 4 | E | The export factory proved on survival: the exporter, the release record, the run root rule, the bridge, the web shell | an export opens standalone and answers all six verbs; two exports agree on the closure digest |
| 5 ✔ | F | The kernel in GDScript, and survival sealed: declarations, a derived order equal to the pasted one, the event queue, refusals as values, the interface writing through the latch | the goldens unchanged line for line |
| 6 | G | The suite enters the locked gate: a supervisor per test file, fixtures with synthesised media, the CI job | `check.py` fails without the engine; an injected error and an injected hang both turn it red |
| 7 ◐ | H | The browser instruments: the platformer's slice list, every fixture and reference committed, stills taken | the references reproduce; the fixtures carry current identities |
| 8 ✔ | I | **The runner**, and the browser runner is deleted | 600/600 frames and 30/30 digests, sealed order equal to the documented one; the view was unproved and shipped broken, and [0066](../decisions/0066-a-state-proof-is-not-a-picture-proof.md) is the picture gate that closes it |
| 9 ◐ | J | **The platformer**, and the browser platformer is deleted | the same, per map, plus the map-scope reset — and see the reordering note: this is a disentangling, not a translation. **In flight**: the simulation is 326 of 600 frames exact from the first and the host draws; what is left is the panels, the numbers over a body, and the retirement |
| 10 ◐ | K | **The room, the scene and the case**, and their browser surfaces are deleted together | the three simulations are ported and exact (14/14, 26/26, 20/20); their hosts and the deletion are what is left |
| 11 | L | The sweep: the last web references, the census rows, the identities regenerated | `check.py` green; no `phaser` anywhere under `web/` |

**Two reorderings, with their reasons.** Step 5 (the kernel) landed before step 4
(the export factory): the kernel was ready and the factory needed a 1.3 GB
toolchain download, and nothing in the ports depends on the factory. Step 6 (the
gate) is next rather than the factory, because the gate protects every port that
follows it while the factory protects nothing until there is something to export.

**What step 6 turns out to cost.** Nearly every one of the twenty-nine Godot test
files reads the real run — through `TestFixtures.world()` if not directly — so a
suite that runs in CI needs a media-free fixture document, a small world, and
synthesised media at the sizes that document declares, with the real-run count
pins moving to tier 2 behind `--run`. That is a restructuring of the suite rather
than a wrapper around it, and it is why the step is its own commit.

**What step 8 owed, did not pay, and has now paid.** The rules above ask a
retirement for a picture sheet as well as a parity count. The runner's parity is
the strongest kind — six hundred frames, equal rather than close — but no browser
still was taken, so the picture evidence was one-sided. 0065 stated that in full
rather than quietly meeting a weaker bar, and carried the falsifier.

Stating it was not enough. Played, the port drew no cut-in, no boss, no boss
projectiles and no boss bar; it scaled a trimmed foreground band 3.58x too tall,
left 200 px of bare engine grey down the right of every frame, read none of the
five depth fields every band publishes, threw no dust, played no sound and turned
no coins — and every one of those is invisible to a frame hash. A falsifier that
is written down and then not acted on is documentation, not a gate.

`tools/runner_shots_check.py` is the measurement, and
[0066](../decisions/0066-a-state-proof-is-not-a-picture-proof.md) is the record:
a genre is not ported until its picture is measured, and the measurement must be
shown to fail on the defect it exists to catch. Run against the build 0065
shipped it fails every shot that build can produce; against the build now, 4 of 4
pass. The rule this leaves for step 9 is not "take a still" but "shoot the steps
where a defect would be visible, and prove the sheet catches one".

**Step 7 is half done, and its platformer instrument was wrong.** The runner's
and the platformer's references are committed, but the platformer's pair
described two different runs. `replay.test.ts` runs two scripted runs — the
village walk that talks to the baker, and the stand-and-die that reaches the
defeat panel — and both wrote to the same `REPLAY_DUMP` and `REPLAY_FRAMES`
paths, in order. The second overwrote the first, so the committed golden carried
the defeat run's six hundred frames under the village run's name, beside the
village run's intents. Nothing looked wrong: each half was internally
consistent, and they disagreed only with each other. Proved rather than argued —
a regenerated defeat dump is 600 of 600 frame hashes identical to what was
committed, and the village dump is 0 of 600. Each run writes to its own path
now, and the fixture is the village run it always said it was.

**And its exclusion list was three fields short.** Settled and re-measured: 126
leaf fields at frame 300 survive it on the village run, 132 on the defeat run,
and that is the floor the port must match. What left is what a second runtime
cannot reproduce without reproducing this one's renderer — the inventory panel's
laid-out `slots`, the loader's `diagnostics` about a package with no art, and a
gate's drawn `w`, which the browser takes from the artwork's own bounding box.
The list's own note said the panel's sentence was "already owed"; it is written
now, and what forced it was three fields that survived to the end of the Godot
port's first parity pass, every one of them a reading of a picture rather than
of a body. The room, the scene
and the case get theirs in the change before their port rather than all at once,
because an instrument taken early is an instrument that can drift, and the risk
it guards against — deleting a game before its reference exists — is covered as
long as each genre's capture precedes its own port. The stills are not taken
yet; they need the browser's WEBGL renderer rather than its capture mode, whose
canvas path draws no tint at all.

Steps 8 to 10 each carry their retirement record. The order was the two
kernel-sealed genres first, while the families port is fresh, then the three
turn-based surfaces.

**A third reordering, and this one is measured rather than convenient.** Step 10
was taken before step 9. The reason is that step 9 is not the same kind of work
as step 8, which this plan assumed it was. The runner's simulation was written
in modules that import no engine, so its port was a translation; sixteen of the
platformer's files import Phaser and they include `player.ts` (1,496 lines),
`mob.ts` (868), `portal.ts` (521) and `prepared-scene.ts` (3,729), which is the
scene and the simulation in one file. Porting it is a disentangling and a
re-derivation, not a translation, and that is what `PARITY_EXCLUDE` has been
telling us: the golden hashes a Phaser scene, and 126 of its leaf fields are all
that survive dropping what one host is allowed to have an opinion about.

The three turn-based surfaces, by contrast, have one engine-bound file each and
the case has none. They carry no floating-point state, and all three ported to
exact parity on the first or second attempt. Taking them first means three of
the four genres are on Godot while the platformer is still being worked out,
rather than none of them.

**Where step 9 has got to.** The port is driven by the golden frame by frame and
the gate is a *prefix* rather than a whole-file diff — `tools/frames_prefix.py`
asserts how far the run agrees counting from frame one, because a diff answers
"no" for six hundred frames on the day the first fifty-nine are right. The pin
moves with each unit and lives in three places that must agree:
`tests/test_platformer.gd`, `tools/validate.sh`, and the commit that raised it.

What the simulation now carries: the body and its maps, the gate between them,
the conversation and the effects an ending is worth, the seeded soundtrack, the
dead-zone camera and the tremor a kill puts in it, the population director and
the creatures it stands up, their awareness and their committed blows, the
rounds in the air, contact damage and the hold it puts on the frame, the loot
that falls out of a kill and the experience it banks, and coming back from a
defeat.

What the host now draws: the parallax bands, the ground from its own atlas with
the browser's overscan padding, the gates, the ladders, the body and every
creature sized from the ruler its producer published, the rounds, what is lying
on the ground, and a health bar.

What is left: the inventory panel, the dialogue box, the numbers that float off
a body, a creature's own health bar, the props along a map, and the retirement
record with the browser deletion. One divergence is open and written down rather
than papered over — the column a replacement creature spawns in at frame 327,
measured in `tests/test_platformer.gd` with the numbers that would close it.

**What running it found that the golden could not.** The media-free fixture the
golden was recorded against publishes every field it declares. A shipped package
does not: `bellweather-c6-parity` publishes `aggression` as an explicit null, and
`String(null)` in GDScript is not a cast but a constructor that does not exist —
so the host died at its first creature while six hundred frames of parity stayed
green. A picture gate would not have caught it either. Playing it did.

## What is deliberately not here

The upload, channel pointers, a catalogue, cache and CORS policy, rights
activation on published bytes, and any web route that serves an executable. A
block table for the room, the bundle and the survival manifest, and the survival
document's schema number, are each their own later record, provider-free, with
the cache-key golden as the proof that they cost nothing.
