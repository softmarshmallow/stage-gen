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
