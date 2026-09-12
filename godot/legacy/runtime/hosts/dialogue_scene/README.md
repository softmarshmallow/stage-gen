# Dialogue scene — the Godot host

A Godot 4.7 host that plays one scenario of a `dialogue-scene` run: a run
directory holding `bundle.json` beside the plates, backdrops and tracks it
names. The host ships no media — a run is named on the command line every time.

The simulation was ported first and separately, and it is exact:
`tools/scene_parity.gd` replays the browser's own twenty-six scripted actions and
agrees with it digest for digest, state and view together. This directory is the
other half.

## Running it

```sh
Godot --path godot/legacy/runtime res://hosts/dialogue_scene/main.tscn -- \
    --run <absolute run directory> --scenario <scenario id>
```

| Flag | Values | Meaning |
| --- | --- | --- |
| `--run` | absolute path | the run directory holding `bundle.json` (required) |
| `--scenario` | a `scenario_id` | which of the run's scenarios to play |

**`--scenario` is not optional in practice.** A `dialogue-scene-bundle-v8` run
publishes the union of every scenario its game holds — `out/the-grain-scene-a`
carries six — and a bundle with more than one is refused by name rather than
opened on whichever came first. The browser's own `/scene/<tag>` route omits it
and throws on every run that exists; there is no run under `out/` that route can
play.

**Which runs open.** The contract is `dialogue-scene-bundle-v8` at
`schema_version` 8: `out/the-grain-scene-a`, `out/the-grain-scene-4` and
`out/the-grain-scene-5`. The Grain is the retained game consumer of this host.
Older bundle schemas remain unsupported; changing only their version field does
not supply the required scenario array or UI bindings.

## The controls

A scenario has no clock, so there is no loop here either: a transition is a
keypress and the view redraws when the reducer moves.

| Does | How |
| --- | --- |
| the next line | click anywhere, `Space`, `Enter`, `→` |
| answer a choice | click an option, or press its number |
| answer the end card | the same, on the card's own control |

## What it refuses

A refusal is a sentence on screen rather than a black window. The host refuses a
run of another kind or at a schema version it does not read, a bundle naming a
scenario it does not publish, a bundle publishing more than one scenario with
none named, a scenario program at another schema version, a package with no
panel or button art, an opening backdrop that will not decode, and a panel whose
drawn interior leaves no room for a speaker and a line.

## What is corrected against the browser, and why

- **The line ran off the panel.** The browser asks for a 208px panel; under this
  sheet's 96px insets its interior is 112, of which the speaker's row and the
  paddings take 48. Sixty-four pixels is one wrapped line, and the longest line
  the six published scenarios carry is 288 characters, which is three. Here the
  panel's height is its *interior* plus the package's own insets, the body has
  the same step-down ladder the room's narration has, and the label clips —
  `godot/legacy/runtime/tests/test_dialogue_layout.gd` holds the fitting.
- **The slot vocabulary was three deep.** `FamilyScenarioProgram.SLOTS` said
  `left, center, right`; the contract publishes five, and The Grain's scripts use
  `far_left` and `far_right` heavily. The constant was never referenced, so
  nothing had gone wrong yet — and the first view to lay the three out would have
  put half a cast in the middle of the stage.
- **The end card's title had no depth.** The browser builds it with no depth set
  while its siblings sit at 200, so whether the words drew over the card or under
  it was the engine's business. It is explicitly above the frame here, fitted to
  the room above the control, and clipped to it.

`restoreScenarioState` and `scenarioProgress` had no Godot port at all and now
do, as `FamilyScenarioRuntime.restore` and `.progress` — the first is what lets a
case offer a Continue that does not open on an actor nobody declares.

## The picture gate

```sh
Godot --path godot/legacy/runtime --rendering-driver metal --disable-render-loop \
    --audio-driver Dummy --quit-after 120000 -s res://tools/dialogue_capture.gd -- \
    --run <absolute run directory> --out <absolute directory> --shots all
python3 tools/dialogue_shots_check.py <that directory>
```

Six named moments — `boot`, `pair`, `swap`, `narration`, `choice`, `end` — two of
them from a second scenario of the same bundle, because the one the rest are
taken in has no choice in it. Seven measurements, every threshold carrying the
reading that set it, and every one of them shown to fail by breaking the host on
purpose and re-shooting the whole sheet.
