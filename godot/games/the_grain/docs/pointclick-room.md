# Point-and-click puzzle room

> **Scope: game consumers.** This document describes the formats used by these Godot games.
> The public asset SDK and new games do not require this authoring format.

> **Checked by:** `tests/contract/test_current_game_docs.py`, `tests/contract/test_generation_pipeline_docs.py`, `tests/unit/games/pointclick_room/test_workflow.py`.

> **Contract maturity: exact-current for the authored contract, the pipeline,
> and the runtime manifest.** Executable authority:
> `godot/games/the_grain/pipeline/src/the_grain_pipeline/pointclick_room/` and `godot/games/the_grain/gameplay/pointclick_room/`.

The third recipe on the engine, at taxonomy path `2d/roomview/pointclick`
(`roomview` ≜ `screen_space_room_stage_v1` in the
[view and style taxonomy](../../_shared/docs/formats/view-and-style-taxonomy.md)): one fixed painted
room, cursor-driven hotspots, an inventory, and a puzzle that is **declared as
data and proven finishable before any generation is paid for**.

The design rule this genre exists to exercise: **the system owns vocabulary;
the author owns composition.** The whole gameplay grammar — two verbs
(`inspect`, `use`), four effects (`set_flag`, `grant_item`, `remove_item`,
`reveal_hotspot`), guards, and a win condition — is recipe code at a declared
taxonomy path. The authored `room.toml` is a text IR composed inside that
grammar. Generation supplies art and narration only; puzzle logic never comes
from a model.

## Authored contract — `pointclick-room-v3`

One room = one authored package directory `godot/games/<game>/inputs/` holding
`room.toml` beside the `references/` its art is generated against — the same
package shape the platformer's `game.toml` uses (schema: `PointClickRoom` in
[`models.py`](../pipeline/src/the_grain_pipeline/pointclick_room/models.py);
unknown fields rejected):

- `schema_version = 1`, `kind = "pointclick-room-v3"`, `room_id`,
  `display_name`, `revision`.
- `[[references]]` — the authored images this room is drawn against: id,
  `source` under `references/`, `source_sha256`, and an explicit rights status
  and basis. The resolver reads the bytes and refuses a digest that no longer
  matches, offline, before any spend.
- `[style]` — label, keywords, avoid, and `reference_ids` naming at least one
  declared reference; the words feed the model-selected canonical style anchor
  exactly as the dialogue recipe does, and the reference carries the look.
- `[scene]` — the backdrop brief and the fixed frame (default 1280×720).
- `[[hotspots]]` — id, label, brief, `hidden` flag, `art`, and **two normalized
  rectangles that mean different things**. `art_region` is art direction: where
  a `"scenery"` hotspot is asked to be painted into the backdrop, and where a
  `"sprite"` hotspot asks the backdrop to leave a quiet, uncluttered surface for
  the object that will be composited there. `region` is the hit area the runtime
  tests the cursor against. `art` selects which of the two draws: `"sprite"`
  hotspots get their own generated transparent object, `"scenery"` hotspots are
  painted into the backdrop and carry a hit area only.
- `[[items]]` — id, label, brief; every item must be obtainable through some
  effect.
- `[[interactions]]` — `on = {verb, hotspot, item?}` plus `requires` (flags),
  `effects`, and optional authored `narration`; a missing narration is a
  declared gap one structured call fills in the room's voice. An interaction
  with effects fires once; a pure narration line repeats.
- `[win]` — required flags and an optional authored closing line.

**Admission is a proof.** `resolve_pointclick_room` breadth-first-searches the
exact reachable state space (flags × inventory × reveals × fired one-shots)
and refuses a room that cannot reach its win condition, names interactions
that can never fire, and rejects hidden hotspots nothing reveals or items
nothing grants. The proof, with one shortest solution as evidence, is a
`pointclick-solvability-v1` record. The builder resolves the room first, so a room
the proof refuses is refused while planning and nothing is paid for; the delivered
room carries no copy of the proof, because the host plays the manifest and the
build re-proves the room every time it plans.

## Building the room

The game's folder is a gnode project; `pipeline/workflow.py:room` reads one room
package with the room's own reader and writes one step per asset. From
`godot/games/the_grain`:

```bash
gnode plan pipeline/workflow.py:room --arg package=inputs/rooms/window
gnode run pipeline/workflow.py:room --arg package=inputs/rooms/window --live --max-usd 25 \
  --deliver package=../../../out/<tag>/{key}
```

A model picks one approved style mode for the room (`style.select`, judged so it
treats every asset kind drawn); the backdrop, one cut-out per sprite hotspot and
one icon per item are each painted against the cover and judged — the exact
canvas, and for a cut-out native alpha around one isolated subject — and drawn
again when they fail. One structured call writes every narration line the
author left open, judged to cover exactly those ids (it is absent when the
author wrote every line). The shared UI sheet family draws each interface role.
The last step reads the room again from its own files and writes
`manifest.json` over everything it publishes.

<!-- pipeline-graph-contract:start -->
```json
{
  "kind": "pointclick-room-gnode-plan-contract-v1",
  "fixture_ref": "godot/games/the_grain/inputs/rooms/window",
  "builder": "pipeline/workflow.py:room",
  "workflow_id": "the-grain-room",
  "topology_sha256": "eb7f4667e7c596bdba7063f86e5dec8ebbb6b4bb09ec716a134222191e187949",
  "node_count": 99,
  "step_count": 29,
  "first_take_operation_counts": {
    "image.edit": 6,
    "local": 19,
    "structured.generate": 4
  },
  "outputs": [
    "package"
  ],
  "type_ids": [
    "./pipeline/nodes/interface.py#admit_ui_sheet",
    "./pipeline/nodes/interface.py#publish_ui_sheet",
    "./pipeline/nodes/interface.py#ui_review_schema",
    "./pipeline/nodes/interface.py#ui_template",
    "./pipeline/nodes/room.py#admit_room_image",
    "./pipeline/nodes/room.py#room_package",
    "./pipeline/nodes/style.py#admit_style",
    "./pipeline/nodes/style.py#selection_schema",
    "./pipeline/nodes/style.py#style_record",
    "gnode/image.edit@1",
    "gnode/structured.generate@1"
  ]
}
```
<!-- pipeline-graph-contract:end -->

**The interface is generated, and the nodes that generate it are not this
recipe's.** Panels and buttons are the one thing every genre draws the same
way, so the room plans the shared `2d/ui/atlas.*` triplet declared beside the
[UI contract](../../_shared/docs/formats/ui.md) rather than a private copy of it, reading its own
`ui.toml` beside `room.toml`. The HUD bar, the narration plate and the win
card are one `panel_frame` sheet stretched to three sizes; the verb bar is one
`button_rect` sheet read at four states, with the chosen verb shown in the
pressed cell because a four-state sheet publishes no selected one. Where the
narration text sits is measured on the drawn frame — the producer publishes
the ornament-free interior — rather than guessed from a fixed inset.

**The cover is the art direction of record, and the author supplies it.**
Every image the room generates — backdrop, hotspot sprites, item icons — is
sent the authored `references/cover.png` as an input reference plus a clause
naming it a style reference. Words alone do not hold a look across independent
draws: a flat-graphic room came back with a flat backdrop and glossy gradient
icons from the identical style clause. So the reference is pixels, and it is
an authored package member rather than something the pipeline paints for
itself first — the look is chosen once, by a person, and every draw is held to
it. It is attached to every image call, so replacing the file is a different
request and re-bills the room deliberately rather than leaving assets drawn
against a reference that no longer exists. The package step republishes it,
because the manifest names it and a package must carry the bytes it names.

**A hit area is not art direction, and correcting one is free.** Hotspot
rectangles are authored before the plate exists, so they are a guess at a
composition the generator is not bound by. The author then measures the
delivered backdrop and corrects them — and that correction must not redraw the
backdrop, because generation is unseeded: a second draw is a different picture,
and the rectangles just measured would be wrong for it. Measured on this pilot,
before the split: 3 corrected rectangles in the motor court redrew the plate and
the composition drifted ~27px; 12 in the window room re-imagined it and 7 of 14
rectangles were lost, leaving a gating exit on blank stone. So the two jobs are
two fields. `art_region` is the composition an image is told about — it is the
only rectangle any prompt reads, so editing it is a request for a different
picture and re-bills as it must. `region` is the hit area; **no image step reads
it**, it is carried to the player in the runtime manifest, and moving it re-runs
only the package step, so the corrected rectangles reach the runtime and nothing
is drawn again. The two start equal, and the second one diverges as the room is fitted
to the art that actually arrived. The solvability proof reads neither.

Every image prompt is stated in the plan: the room's static brief ends with the
style anchor's clause, which a template fills from the anchor once it is picked.

### Image routing

The game's `gnode.yaml` names the routes: images on GPT Image 2.5 Sunburst over OpenAI, structured
calls on OpenRouter. The backdrop is an opaque reference edit at the authored exact frame; hotspot
sprites, item icons and the UI sheets are transparent reference edits, and declare
`transparent_background`, so a route that cannot paint alpha is refused while planning. Missing
credentials and provider failures never trigger a fallback route.

## Runtime manifest — `pointclick-room-runtime-v3`

The package step writes `manifest.json` beside what it publishes: the cover
ref, scene frame and backdrop ref, hotspots (region, hidden, sprite ref or scenery), items with
icon refs, interactions with narration **resolved** (authored line or the
generated one), the win condition, the three interface roles with the geometry
the gate measured on each sheet, and a digest-bound closure of every
published artifact — the republished cover and all three sheets included.

The consumer (`godot/games/the_grain/gameplay/pointclick_room/` for the rules,
`godot/games/the_grain/scenes/pointclick_room/` for the picture) plays the room from this
document alone: one canvas, sized to the authored frame plus a HUD band, scaled
to whatever window it lands in. Backdrop, hotspot sprites, narration panel,
inventory and verb controls are all drawn **inside that canvas** — nothing
around it contributes anything, so the same build is a phone game and a page
embed. The engine is only the view: every transition goes through the pure
reducer over `{flags, inventory, revealed, fired}` — the same state machine
the solvability proof searched, so a room the proof admits is a room the
runtime can finish. Touch is first-class: tap acts, hold inspects (as does
the secondary button), a mode toggle makes inspect sticky, and a control
outlines the live hotspots, because a phone has no hover to discover them
with.
