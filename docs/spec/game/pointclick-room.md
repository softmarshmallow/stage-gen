# Point-and-click puzzle room

> **Contract maturity: exact-current for the authored contract, the pipeline,
> and the runtime manifest.** Executable authority:
> `src/stage_gen/recipes/pointclick_room/` and `web/lib/pointclick/`.

The third recipe on the engine, at taxonomy path `2d/roomview/pointclick`
(`roomview` ≜ `screen_space_room_stage_v1` in the
[view and style taxonomy](view-and-style-taxonomy.md)): one fixed painted
room, cursor-driven hotspots, an inventory, and a puzzle that is **declared as
data and proven finishable before any generation is paid for**.

The design rule this genre exists to exercise: **the system owns vocabulary;
the author owns composition.** The whole gameplay grammar — two verbs
(`inspect`, `use`), four effects (`set_flag`, `grant_item`, `remove_item`,
`reveal_hotspot`), guards, and a win condition — is recipe code at a declared
taxonomy path. The authored `room.toml` is a text IR composed inside that
grammar. Generation supplies art and narration only; puzzle logic never comes
from a model.

## Authored contract — `pointclick-room-v1`

One room = one directory `library/rooms/<room_id>/` holding `room.toml`
(schema: `PointClickRoom` in
[`models.py`](../../../src/stage_gen/recipes/pointclick_room/models.py);
unknown fields rejected):

- `schema_version = 1`, `kind = "pointclick-room-v1"`, `room_id`,
  `display_name`, `revision`.
- `[style]` — label, keywords, avoid; feeds the model-selected canonical style
  anchor exactly as the dialogue recipe does.
- `[scene]` — the backdrop brief and the fixed frame (default 1280×720).
- `[[hotspots]]` — id, label, brief, normalized `region` rect, `hidden` flag,
  and `art`: `"sprite"` hotspots get their own generated transparent object
  composited at the region; `"scenery"` hotspots are painted into the backdrop
  and carry a hit area only.
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
nothing grants. The proof, with one shortest solution as evidence, is
persisted into the run as `puzzle.validation.json`
(`pointclick-solvability-v1`).

## Pipeline — `pointclick-room-execution-graph-v1`

`stage-gen pointclick-room generate --input library/rooms/<id>/room.toml
--output out/<tag>` (add `--dry-run` for the free rehearsal). The graph for
the shipped room is 14 nodes: `room.resolve` → `style_anchor.select` → the
backdrop, one generate+validate pair per sprite hotspot
(`hotspot-pipeline@v1` template instances) and per item icon
(`item-icon-pipeline@v1`), one `narration.compile` structured call covering
every authored narration gap under a closed-id strict schema (omitted
entirely when the author wrote every line), the local `puzzle.validate`
proof, and the terminal `room.bundle`.

Every generation node's **complete static prompt rides its card in the plan**
— the handler sends the card text verbatim with the style anchor appended
once, so `execution-plan.json` states exactly what each node will be told
before a cent is spent, and the run viewer renders it.

## Runtime manifest — `pointclick-room-runtime-v1`

The terminal bundle writes `manifest.json` into the run directory: scene frame
and backdrop ref, hotspots (region, hidden, sprite ref or scenery), items with
icon refs, interactions with narration **resolved** (authored line or the
generated one), the win condition, and a digest-bound closure of every
published artifact. The web consumer (`web/lib/pointclick/`, route
`/room/<tag>`) renders the room from this document alone: backdrop image,
positioned hotspot sprites, cursor verbs, an inventory bar, and a pure
reducer over `{flags, inventory, revealed, fired}` — the same state machine
the solvability proof searched, so a room the proof admits is a room the
runtime can finish.
