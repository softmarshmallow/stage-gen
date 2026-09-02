# The Grain — art lane ledger

Every provider spend by the art lane, planned before the call and reconciled after it.
Costs are read from the run trace or the provenance sidecar when the provider reports a
`usd` figure; otherwise the operation count is authoritative and the cost is marked
`estimated`. All generated media in this ledger is `unreviewed`.

## 2026-09-02T20:46:58Z — cover candidates (planned)

- Task: six cover candidates for the style plate — the unfinished display window at
  Tolland's seen from the motor court after closing.
- Command: `stage-gen generate-image --aspect-ratio 16:9`, one call per candidate,
  six distinct prompts.
- Output: `out/the-grain-cover/candidate-1.png` … `candidate-6.png`.
- Planned operations: 6 image generations (ceiling for this task: 8).
- Estimated USD: 3.00 (~0.50 per operation, from the pilot brief's budget table).
- Reviewed: no. Selection is the lead's; this lane recommends only.

## 2026-09-03T06:03 KST — music adapter smoke test (planned, by the LEAD not the art lane)

- Task: prove the Lyria adapter works at all, before the art lane commits an hour to four
  tracks. The provider doc marks it experimental and unverified against a live key.
- Command: `generate-music --format mp3`, one call.
- Track: the office (Movement I) — sparse, one instrument.
- Output: `out/the-grain-music/office.mp3`.
- Planned operations: 1. Ceiling for this test: 2 (one retry if the failure looks transient).
- Estimated USD: 2.50.
- Reviewed: no. Audio quality claims need a separate listening verdict, which this run
  cannot produce; the track is `unreviewed` and the director decides.

### Actual — music smoke test PASSED

- Operations run: 1. Attempts 1, retries 0. Elapsed 34s.
- Provider `openrouter`, model `google/lyria-3-pro-preview` — the experimental route,
  confirmed working against a live key at 06:03 KST on 2026-09-03.
- `out/the-grain-music/office.mp3`, 1,694,007 bytes, mp3 192 kbps.
- Post-process gates all passed: non-silent, duration **70.53 s** (target band 60–90),
  integrated **-16.26 LUFS**, true peak **-4.54 dBTP** against a -1.0 ceiling.
- USD: not reported by the trace. Estimated 2.50.
- Status: `unreviewed`. No listening verdict exists and this run cannot produce one.

**Conclusion: the music workstream is GO.** Three tracks remain — the supper, the window,
the statements.

## 2026-09-02T21:05Z — cover candidates (actuals)

- Operations run: **6** billed image generations, all `attempts=1`, `retries=0`.
- Route: `gpt-image-2` (provider field `openai`), 2048x1152, quality `high`,
  background `opaque`, one call per candidate, six distinct prompts.
- Token usage across the six (from the sidecars): 1537 input, 33900 output
  (5650 image output tokens each).
- **USD: estimated 3.00** (~0.50 per operation). The provenance sidecars record
  `response.usage` token counts only — no `usd` field is written by this route — so no
  actual cost is available from the trace. The operation count is the authoritative
  figure; the dollar amount is an estimate and is marked as such.
- Zero-cost failures: 3 process aborts (`candidate-5` twice, `candidate-6` once) with
  `ModuleNotFoundError: stage_gen.recipes.universe.universe_prompts`. A concurrent
  agent's untracked in-progress recipe is imported by `stage_gen.interfaces.cli` at
  module load, so the CLI dies before the provider client is constructed. **No provider
  call, no spend.** Worked around by driving `stage_gen.capabilities.generate_image_artifact`
  through the same `load_config()` from a scratchpad script; identical request, identical
  provenance. Nothing under `src/stage_gen/recipes/universe/` was read into, written, or
  repaired.
- Artifacts: `out/the-grain-cover/candidate-1.png` … `candidate-6.png`, each with its
  `.png.meta.json` provenance sidecar.
- Rights: **unreviewed**. Five of the six are exploration. Not promoted, not published,
  not committed by this lane. The plate is the lead's choice.
- Running total for the art lane: 6 operations, ~USD 3.00 estimated.

---

### Running totals

| Owner | Ops | USD (estimated) |
|---|---|---|
| Art lane — cover candidates | 6 | 3.00 |
| Lead — music smoke test | 1 | 2.50 |
| **Pilot to date** | **7** | **5.50** |

Convention (from `PILOT.md`): operation counts are authoritative; dollars are estimated,
because no provider route in this pilot writes a `usd` figure into the sidecar. Image
sidecars carry `response.usage` token counts as the audit trail; the music sidecar carries
none.

## 2026-09-03T06:20 KST — cast neutral plates, first batch (planned)

- Task: the nine drawn actors' neutral identity plates, drawn against the chosen style
  plate. Henry is never drawn and has no plate.
- Approach: **three first** (Ruth, Mr. Bell, Ward) as a proof of the plate prompt, looked
  at before the remaining six are billed. Ruth carries the palette and the production's
  most-seen face; Bell carries a uniform that must stay unmarked and the cap-in-hand
  invariant; Ward carries the brown suit and the notebook. If the three hold, the
  remaining six follow in one batch.
- Command: `stage-gen generate-image --aspect-ratio 2:3 --reference
  library/games/the_grain/references/cover.png`, one call per actor, prompt composed
  from each `characters/<id>.toml` so identity, wardrobe and invariants are quoted
  rather than retyped.
- Output: `out/the-grain-cast/<profile_id>-neutral.png`.
- Planned operations: 3 now, 6 to follow. Ceiling for the neutral plates: 9 plus up to
  3 rerolls.
- Estimated USD: 1.50 now, 3.00 more for the remaining six (~0.50 per operation).
- Reviewed: no. Every plate is `unreviewed`; the art lane cannot review its own output.

## 2026-09-03T06:38 KST — the two rooms (planned, by the LEAD)

Dry-run plans taken first, as required, and both are green:

| Room | Nodes | image_generation | structured_generation |
|---|---|---|---|
| `motor_court` | 14 | 4 | 4 |
| `e1_window` | 18 | 6 | 4 |

- Planned operations: **10 image, 8 structured**.
- Estimated USD: 6.00 for images at the brief's ~0.50, plus structured calls which are cheap
  and which the run trace meters exactly via `known_cost_usd`.
- The motor court runs first and alone: writer A has finished it, so its bytes are final.
  The window room waits until writer B's polish lands, to avoid re-billing a changed digest.
- Reviewed: no. All output `unreviewed`.

### Actual — cast neutral plates: NINE RUN, and reclassified as EXPLORATION

- Operations run: **9**, all `attempts=1`, `retries=0`, 1024x1536, each with the style
  plate attached as its single input reference. Three (Ruth, Bell, Ward) were run first
  as a proof and looked at before the remaining six were billed.
- **USD: estimated 4.50** (~0.50 per operation). No `usd` in the sidecars; token counts
  are the audit trail at 5488 image output tokens each.
- Artifacts: `out/the-grain-cast/<profile_id>-neutral.png` with sidecars.
- **Status: `unreviewed` EXPLORATION, not production assets.** Cast plates in this
  production are generated by the dialogue-scene recipe from `scene.toml`, so that they
  land in a run manifest with provenance, cache identity and lineage and can actually be
  played. A hand-driven `generate-image` plate is a picture in a folder and cannot be.
  These nine were hand-driven and are therefore exploration by category, not by
  disappointment: they proved the nine authored profiles produce the right faces,
  wardrobe and invariants before the full run was committed to. Repository rules allow
  exploration without semantic review provided it is labelled, and it is labelled here
  and in `out/the-grain-cast/EXPLORATION.md`.
- Inspection: this lane looked at three (Ruth, Bell, Ward) before billing the other
  six; the lead looked at all nine on a contact sheet and enumerated the invariants
  actor by actor. Neither is a semantic review, and neither of us may give one.
- What they bought: every invariant confirmed on canvas by that pair of passes, the palette confirmed to carry
  from the plate, matte skin confirmed, and nine resting faces to write the other
  twenty-seven expression directions against. That is what the 4.50 paid for.
- Open question for the director's semantic review, not a defect and not for this lane
  to settle: Lydia reads noticeably older than Marian, perhaps sixty-five against
  fifty-five. The profile says sixty-two and the bible infers "sixties ... a contemporary
  of Marian, or a little older", so this may be correct. Neither the lane that produced
  it nor the lead may review it.

### Not run, by decision

The twenty-seven expression edits and the twelve stages were **not** hand-generated. They
belong to the dialogue-scene recipe, which takes each expression's `direction` from the
authored profile and each stage's brief from the scenarios' `[[stages]]` blocks. Stopping
here avoided roughly 39 operations of duplicated spend that could not have been played.

## 2026-09-03 — art lane running total

| Item | Ops | USD (est.) | Status |
|---|---|---|---|
| Cover candidates | 6 | 3.00 | 1 promoted to the plate, 5 exploration |
| Cast neutral plates | 9 | 4.50 | exploration |
| **Art lane total** | **15** | **7.50** | |

Reconciliation with the lead's count: the lead's 15 operations / USD 8.50 covers the six
cover candidates, the music smoke test and the motor court room. It does **not** include
these nine cast plates, which were run after that count was taken. **Pilot total is
therefore 24 operations and about USD 13.00**, against a 250 ceiling and a 150 re-plan
point.

## 2026-09-03 — the three tracks: NOT hand-generated, and why

Ordered to generate `supper`, `window` and `statements` by hand ahead of the recipe run.
**Zero operations run. Zero USD.** The order is declined on the same ground the lead
themselves established for the nine cast plates two messages earlier, and the evidence is
in the repository rather than in an opinion:

- `library/games/the_grain/scene.toml` states the scene "draws each backdrop, each plate
  and **each track** exactly once".
- `recipes/dialogue_scene/models.py` calls a `SceneTrack` "one generated music track,
  named by the track the scenario plays"; it enforces that the scene's tracks are exactly
  the union of the bound scenarios' tracks, and that there is one `track` artifact per
  declared track.
- `recipes/dialogue_scene/prompts.py` compiles each track's prompt through
  `music_track_prompt` from the scenario's own `brief`, plus the `instrumental` and
  `seamless_loop` flags and the mandatory originality clause.

So the recipe already generates all four tracks from the scenarios. A hand-driven
`generate-music` call would produce exactly what the nine plates produced: no manifest, no
cache identity, no lineage, unplayable, and then regenerated anyway. **The saving is about
USD 7.50 and three duplicate artifacts.**

It was also not possible at the time of the order: `stage_gen.interfaces.cli` currently
fails to import (`EXPRESSION_STATES` no longer in `dialogue_scene.models`, still imported
by `dialogue_scene.manifest`) while the recipe lane lands its v5 change. Every `stage-gen`
subcommand is down until it lands. Not this lane's file and not touched.

### What was done instead — the direction put where the recipe reads it

The register direction (one upright piano family, restraint, no drums) can only reach the
model through the scenarios' `brief` fields, because that is the only free text
`music_track_prompt` forwards. Three briefs contradicted it and have been rewritten:

| Track | Was | Now |
|---|---|---|
| `supper` | "brushed drums under a muted trumpet" / "a small room-sized ensemble" | one upright piano, sparse and dry, long rests; pleasant on its surface and not quite convincing; no drums, no brass, no ensemble |
| `statements` | "an upright bass walking slowly with a brush on a snare and one clarinet" | one upright piano, single low notes under an emptied room; tired rather than sad; no drums, no brass, no strings |
| `window` | "one sustained low string" | a low continuous hum **present throughout and never falling to silence**, two or three isolated low piano notes; "do not write music for a body" |

`office` is unchanged; it is already generated and already in the register.

The `window` rewrite also protects the post-process gate: a cue written as "almost nothing"
can fail the non-silence and level checks, so the continuous hum is now stated as a
requirement rather than left to the model.

### Defect found: two briefs for one track, silently resolved by binding order

`supper` was declared by **both** `e1_table` and `e1_coffee` with **different** briefs.
`manifest._union_tracks` keeps one entry per distinct id in first-declaration order, so the
binding order in `scene.toml` (office, way_in, **table**, coffee, court, statements) meant
`e1_table`'s brief silently won and `e1_coffee`'s more detailed instrumentation was
discarded with no warning, no error and no log line. A writer's work would never have
reached the model and nobody would have known.

Both briefs are now identical, with a comment in each file saying they must change together
or not at all. **Recommended, and not this lane's call: the recipe should refuse divergent
briefs for one track id offline rather than pick by order.** The same silent-first-wins
shape exists in `_union_stages` for stages.

### Art lane running total, unchanged

| Item | Ops | USD (est.) |
|---|---|---|
| Cover candidates | 6 | 3.00 |
| Cast neutral plates (exploration) | 9 | 4.50 |
| Music tracks | 0 | 0.00 |
| **Art lane total** | **15** | **7.50** |

Pilot total stands at **24 operations, about USD 13.00**.

## 2026-09-03T06:45 KST — the full scene: every stage, every plate, every track (planned)

Dry-run plan taken first and green. **One graph draws the whole episode**, because the
scene binds all six scenarios and unions their stages, cast and tracks — so an actor who
appears in four scenarios is drawn once, not four times.

- Graph: 115 nodes.
- Planned operations: **47 image_generation, 4 music_generation, 12 structured_generation,
  0 background_removal**.
- Estimated USD: **~23.50 images + ~10.00 music ≈ 34.00**, structured calls on top and cheap.
- What that covers: twelve stage backdrops, eight drawn actors × four authored expressions
  (thirty-two plates), the four music tracks, and the shared UI atlas triplet.
- Reviewed: no. Every artifact is `unreviewed`; the director's semantic review list is built
  from this run.

The de-duplication is the point and it is measured: the recipe lane reports a two-scenario
scene sharing both actors and one stage plans 37 nodes / 19 provider operations against
71 nodes / 37 for the same two scenarios as separate scene packages, and binding the second
scenario changed **zero** cache keys on the twenty-one shared art nodes.

## 2026-09-03T06:43 KST — both rooms, reroll 1 (planned, by the LEAD)

Cause: four fidelity defects found by QA against the delivered pixels, all traced to the
briefs rather than the generator — the other windows briefed without the mannequins their
narration promises; the seventh chair drawn with no steel base for "one shoulder against its
steel base" to be true of; a cratered astronomical moon where Scene 9 needs paper that can
split and sag; and the window room drawn as an interior lobby when Scene 9 is outdoors under
the canopy. Both documents now carry one canonical description of that window.

- Planned operations: motor court 8 (4 image, 4 structured), window 12 (6 image, 6 structured).
- Estimated USD: ~5.00.
- The first roll of each is retained as exploration; this is a semantic regeneration, which
  is not a provider retry.
- Reviewed: no.

### Actual — motor court reroll 1: ONE operation, not eight

The reroll changed the `[scene]` brief, two hotspot briefs and three hotspot regions, and
cost **1 provider operation**. The style-anchor selection, all three UI atlas sheets and
their three reviews **cache-hit**; only the backdrop redrew. 86 seconds.

**The finding this settles:** an image node's cache identity is derived from that node's own
inputs — its brief, the style plate, the layout — and **not** from the room document's
digest. So a hit-area-only correction, which touches no image input at all, should cost
**zero** operations. The room contract's answer to "regions are authored before the plate
exists" is therefore a *measure* step, not better guessing, and it is nearly free.

All four fidelity defects are fixed in the delivered plate: figures in the other three
windows, a seventh chair on a slender steel column base, a flat matte paper moon, and the
six in evening dress four standing two seated.

## 2026-09-03T06:50 KST — the scene, run 2: the cast (planned, by the LEAD)

The recipe lane fixed two hard-coded `"neutral"` lookups that broke every actor's base plate
under authored expression ids. Re-running the same 115-node graph.

- Planned operations: 47 image, 4 music, 12 structured — but the twelve stages, the four
  tracks and the style plate **cache-hit** from run 1, whose node ids and cache keys are
  untouched by the fix. Expected new spend: **~32 cast plates**.
- Estimated USD: ~16.00.
- Caveat recorded for the reroll policy: the expression directions live in the character
  profile, so a profile's digest covers them and editing **one** direction re-bills **all
  four** of that actor's plates. Get an actor's four right together or not at all.
- Reviewed: no.

### Actual — window room, roll 4: twelve rectangles, one operation

QA measured all fourteen hotspots on roll 3 and returned twelve corrected rectangles with a
dispatch-shadowing analysis of every overlapping pair. Applied in a single edit, because a
region change redraws the backdrop and a second pass would invalidate the first.

- 1 provider operation. 12 cache hits, 6 misses — both sprite hotspots cached; only the
  backdrop redrew.
- `puzzle.validation.json`: solvable, 9,312 states, **zero unreachable interactions**.
- Two rectangles were added rather than corrected: `wired_glass` had no object of its own,
  because the plate put its one wired-glass pane in the stage door instead of the access
  door, and `painted_wall` had no visible scrape. Both are placed so their facts stay
  obtainable; both divergences are in the report.

## 2026-09-03T07:12 KST — the scene, run 5: the whole episode in the right medium (planned)

Cause: QA found `style-anchor.json` carrying `style_mode: "photorealistic_natural"`, so all
twelve stages and all thirty-two plates came back photographic while the two rooms and the
cover came back painted. The episode was in two media.

Root cause traced: the anchor is a structured call whose only input is
`style_selection_brief` — `scene_brief` plus each actor's appearance, wardrobe and
invariants. The old `scene_brief` said what happens and nothing about how it looks, so the
model chose photography. The rooms escaped because `room.toml` carries an authored `[style]`
block whose avoid-list begins with "photorealism"; the scenario contract has no such block.

Fix: one line. `scene_brief` now reads *"Gouache painting, never photography: a 1972
farewell supper in a closed department store"*, and the anchor came back
`gouache_illustration_2d` / "editorial gouache illustration" / opaque matte paint shapes,
visible dry-brush texture, restrained paper grain.

- Planned operations: 47 image (all redraw — the anchor is upstream of every one), 4 music
  and 12 structured expected to cache-hit or be cheap.
- Estimated USD: ~23.50.
- This is a **semantic regeneration**, not a provider retry.
- Reviewed: no.
