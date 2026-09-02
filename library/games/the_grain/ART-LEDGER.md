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
