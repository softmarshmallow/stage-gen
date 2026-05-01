# MISSION

You are an autonomous coding agent operating inside a self-pacing loop
(see `LOOP_PROMPT.md` for the loop's discipline). This file is the
contract. Every iteration, you re-read this file and the TODO that lives
next to it, then advance the work. This document tells you what success
looks like, what the boundaries are, and what signal proves the mission
is complete.

Read this file in full before touching code.

---

## 1. What we're building

A **one-prompt → playable-2D-platformer-world pipeline**.

### Input contract

A single natural-language string from a human user, e.g.

    "a snowy mountain platformer with crystal caverns and aurora skies"
    "fungal mushroom realm at twilight, spore creatures, glowing toadstools"
    "cyberpunk back-alley, drone scavengers, broken neon signs"

That is the entire user input. No structured fields, no asset lists, no
style tags. The pipeline must take it from here.

### Output contract

For each invocation with a prompt `P` and a derived tag `T`:

1. A directory `./out/<T>/` (or whatever path the kit configures) containing:
   - `concept_<T>.png` — the world's style root (single painterly image).
   - `world_spec_<T>.json` — structured world bible: world narrative,
     mob ladder (N rungs), obstacle sheets (M sheets × 8 props), 8 items,
     1–5 parallax layers. **All names and design choices are agent-invented
     per world** — there is no static menu of mobs/items/themes anywhere.
   - `layer_<T>_<id>.png` × L (1–5) — parallax depth layers, 2400×800.
   - `tileset_<T>.png` — 2400×800 ground tileset, 12×4 cells.
   - `character_concept_<T>.png` — 3-pose turnaround, 2400×800.
   - `character_<T>_combined.png` — 5×4 motion master sheet, 2400×3440.
   - `character_<T>-fromcombined_<state>.png` × 5 — sliced per-state strips
     (idle/walk/run/jump/crawl).
   - `character_<T>_attack.png` — 1×4 attack strip.
   - `mob_concept_<T>_<i>.png` × N — per-rung creature turnarounds.
   - `mob_<T>_<i>_idle.png` × N — per-rung 1×4 idle strips.
   - `mob_<T>_<i>_hurt.png` × N — per-rung 1×4 hurt strips.
   - `obstacles_<T>_<i>.png` × M — 4×2 prop sheets.
   - `items_<T>.png` — 4×2 item sheet (8 pickups).
   - `inventory_<T>.png` — 1536×1024 bag panel with locked slot positions.
   - `portal_<T>.png` — 2048×1024 entry/exit pair.

2. A **runnable web demo** that loads `./out/<T>/` and renders a playable
   stage: parallax scrolling, heightmap terrain painted from the tileset,
   character with WASD/arrow movement (walk/run/jump/crouch/attack),
   wandering mobs that take damage and drop items, items collectible into
   an inventory overlay, and entry/exit portals. The runtime is the
   playback path; do not redesign it from scratch (see §4).

### Reference spec

The three load-bearing reference docs in this kit are:

- `docs/spec/system-overview.md` — the system dictionary (what each of
  the ten subsystems is and how they relate).
- `docs/spec/asset-contracts.md` — the per-asset spec: canvas size, inputs,
  layout prior, wave, slicing rules. This is the **asset contract**.
  When you write a generator, the output must satisfy what's written here.
- `DESIGN.md` — the web application's UX + visual spec: user flow,
  page layout, monospace visual language, streaming-progress behaviour.
  This is the **web-UX contract**. When you build the web shell, the
  observable behaviour must satisfy what's written here.

The wave-orchestration shape described in those docs is one viable
structure, not the only one.

---

## 2. Why this is hard

Each of the following is a real, load-bearing technical challenge. You
will not succeed by hand-waving any of them.

- **Multi-modal pipeline orchestration.** Five serial waves of work, with
  fan-out inside each wave (up to ~25 parallel image-gen calls in wave 2).
  Wave dependencies are real (downstream calls take upstream PNGs as
  reference inputs); breaking the wave order corrupts cross-call
  consistency.

- **Vision-LLM structured output (the world-design agent).** A single
  vision LLM call must look at the concept image and emit a world bible
  that names every concrete asset (mob ladder, obstacle props, item
  palette, parallax layer stack) with no pre-defined enums. The schema
  must be enforced (zod / generateObject) because a malformed spec
  silently breaks every downstream image script.

- **Image-gen contracts (per-asset).** Every image-gen call is a contract
  with the runtime: the chroma-key colour is exactly `#FF00FF`; layout
  priors use a fixed 4-colour vocabulary (magenta/yellow/cyan/green); cell
  geometry in the prior must match what the runtime slicer reads. Drift
  in any of these silently corrupts sprites without throwing.

- **Cross-call style consistency.** Without a single style root (the
  concept image) carried as a reference into every downstream call, the
  outputs drift wildly in palette / brushwork / lighting and the world
  reads as a collage instead of one place. The fan-out-from-style-root
  pattern is what makes this pipeline work.

- **Subject consistency across many calls (the turnaround pattern).** The
  player character and each mob get rendered into many different sprite
  states (idle/walk/run/jump/crawl/attack for the character, idle+hurt
  for each mob). Without a per-subject "concept turnaround" reference
  driving each state's gen, anatomy and silhouette drift between cells
  and animation breaks.

- **Sprite-sheet slicing and chroma-key post-processing.** The 2400×3440
  character master sheet has to be split into 5 per-state strips on
  exact pixel coordinates. Chroma-key keying needs soft falloff and
  per-pixel despill or sprites get magenta halos. Per-cell alpha-bbox
  cropping is required for variable-size props/items.

- **Runtime compositing.** Parallax loop seams are crossfaded at runtime
  via paired alpha-gradient edges (no painter cooperation); depth-of-field
  blur is derived from per-layer parallax speed; mob HP scales linearly
  with ladder index; portals advance the stage on overlap. Each of these
  has to actually work in the engine, not just be specified in markdown.

- **Wall-clock budget.** The near-cap character master sheet is the
  longest single call and dominates its wave; wave 2 fires roughly
  `5 + L + N + M` parallel calls and is gated by upstream concurrency
  limits. Treat the master sheet as the critical path and design the
  orchestrator so other waves fit inside its window. Adding `await`s
  is not a substitute for parallelism; flattening waves is not a
  substitute for measuring.

---

## 3. Acceptance criteria

A short ordered checklist. Self-check against this before declaring any
TODO item done. Each item is concrete and verifiable from the filesystem
or by running the demo.

1. **Bootstrap.** `bun install` (or the equivalent) inside the kit
   succeeds with zero errors. Required env vars (image-gen key, text-gen
   key, gateway URL if applicable) are documented in `.env.example` and
   the pipeline fails fast with a clear message if any are missing.

2. **Concept root.** Given any one-line prompt `P`, running the pipeline
   produces `concept_<T>.png` (1536×1024, no chroma key) within ~60 s.
   `T` is deterministic from `P` (a stable slug + short hash).

3. **World bible.** `world_spec_<T>.json` exists, conforms to the schema,
   and contains: a `world` block; `mobs[]` of length N (default 8) with
   strictly distinct `body_plan` between adjacent rungs; `obstacles[]`
   of length M (default 3) with non-duplicate `sheet_theme`; `items[]`
   of length 8 with non-duplicate `kind`; `layers[]` of length 1–5 with
   exactly one `opaque: true` entry at `z_index: 0, parallax: 0`.

4. **Asset fan-out.** All wave-2 PNGs land in `./out/<T>/` at the
   declared canvas sizes from `docs/spec/asset-contracts.md`. Spot-check by
   reading the file headers — wrong dimensions are a contract break.

5. **Sprite consistency.** Character motion strips and mob idle/hurt
   strips share silhouette / proportions across frames within a single
   strip. The character is the same overall body size across all 20
   master-sheet cells (head/feet rails enforced).

6. **Chroma key.** Loading any sprite PNG into the runtime (or a small
   test harness) replaces `#FF00FF` with full alpha-0 transparency, with
   no visible magenta fringe at sprite edges (despill applied).

7. **Slicing.** `character_<T>_combined.png` is split into 5 strip PNGs
   on the documented row boundaries; per-cell alpha bbox crops work for
   props and items (variable per-cell size honoured).

8. **Mob ladder is monotonic.** Visual inspection (or a sized-thumbnail
   contact sheet generated by the kit) shows mob 0 reads as the weakest
   silhouette, mob N-1 as the strongest. The runtime takes
   `mobHpForTier(i) = i + 1` hits to kill, end-to-end.

9. **Web runtime loads the world.** Pointing the web runtime at
   `./out/<T>/` produces a playable scene: parallax scrolls, character
   moves under WASD/arrows, mobs wander and take damage, items drop and
   collect into the inventory, both portals are present. Sustained
   ≥30 fps on a modern laptop in a Chromium-based browser at 1280×720.

10. **Loop.** Walking into the exit portal triggers the stage-advance
    hook (today: console event or scene reload — not a new world
    generation). The world doesn't have to be infinite, but the trigger
    must fire.

11. **Re-runnable.** Re-running the pipeline with the same prompt and
    tag is a no-op (cache check on existing files). Re-running with a
    new prompt produces a fully separate `./out/<T>/` directory with no
    cross-contamination.

12. **Self-contained.** The kit runs standalone with no external
    repository on disk. The shipping pipeline must not import from any
    outside source tree or require one at runtime.

---

## 4. Out of scope

Hard boundaries. If a TODO item drifts into any of these, push back —
mark it `WONTFIX (out of scope per MISSION.md §4)` and move on.

- **Do not redesign the runtime engine.** Phaser (or whatever 2D web
  engine the kit ships with) is the playback layer. You
  may extend its scene-loading code to consume new asset types; you may
  not rewrite the engine, swap engine vendor, or build a custom WebGL
  renderer.

- **Do not build user accounts, login, sessions, or persistence.** The
  pipeline is stateless: prompt in, files out, demo plays. No database,
  no user store, no save state.

- **Do not build multiplayer, networking, or any server-side runtime
  game logic.** The web demo runs entirely client-side after assets are
  generated.

- **Do not build a level editor, asset editor, or any GUI for tuning
  the pipeline.** Configuration is via CLI flags and env vars only.

- **Do not add audio generation.** BGM is curated (a fixture library),
  not generated. SFX is out of scope entirely. If audio appears in the
  scope, it must be a static fixture, not a generation step.

- **Do not add new gameplay systems** — no combat depth (player HP /
  damage / projectiles), no NPCs / dialogue / quests, no equipment /
  crafting / consumable use, no multi-floor or destructible terrain,
  no slopes mid-stage. The current template's gameplay is "demo-quality"
  by design; deepening it is a separate mission.

- **Do not migrate image models** without a written contract validation
  pass. The asset spec is written against gpt-image-2 (multi-image
  reference, ~8.3 Mpx cap, in-canvas chroma-key + layout-prior approach).
  Switching to a model with different reference semantics (Imagen, FLUX,
  SDXL/ControlNet) is a project of its own — every per-asset contract
  has to be re-validated.

- **Do not change the image-gen-call wave structure** to "improve
  parallelism" without first measuring. The waves exist because each
  one consumes outputs of the previous one as references; flattening
  them breaks cross-call consistency, even if it shortens wall-clock.

- **Do not add monitoring, telemetry, analytics, or remote logging.**
  `console.log` and exit codes are sufficient. No external services.

- **Do not commit secrets.** `.env` is gitignored; `.env.example` is the
  only source of truth for what keys exist.

- **Do not commit generated outputs.** `./out/` is gitignored. The
  git repo holds the pipeline, not the artefacts.

- **Do not add unit-testing infrastructure as a goal in itself.** Tests
  exist where they catch real regressions in the asset contracts (slicer
  cell coordinates, schema validation, chroma-key falloff); broad
  test-coverage drives are scope creep here.

---

## 5. Definition of done

> **The mission is complete when an unmodified observer, given only this
> kit and an OpenAI image-gen API key, can run a single command of the
> form `bun play "<one-line prompt>"`, wait for the pipeline to finish,
> open the resulting URL, and play through a full side-scrolling stage
> in their browser — parallax scrolling smoothly, character moving and
> attacking, mobs wandering and dropping items, items collecting into the
> inventory overlay, exit portal triggering — without ever editing a
> file, writing a JSON spec by hand, or reading source code to figure
> out which command to run next.**

If that paragraph is true for three different prompts producing three
visually-distinct playable worlds, the mission is done. Until it is true
for at least one prompt end-to-end, the mission is not done — no matter
how many TODO items have been checked off.

---

## Working notes for the loop

- The TODO file next to this MISSION is the persistent state. Each loop
  iteration: read TODO, plan the next fan-out per `LOOP_PROMPT.md`,
  dispatch subagents, audit, update TODO, commit, sleep. Items inside a
  phase may advance in parallel; phase boundaries are strict.
- If a TODO test case is ambiguous, refine it into smaller TCs in place
  rather than guessing. Keep the dependency order intact.
- If a TODO test case conflicts with this MISSION, MISSION wins. Edit
  the TODO to reconcile, then proceed.
- Never edit this MISSION except to fix factual errors about the asset
  contracts. Scope changes belong in a separate conversation with the
  human, not in autonomous loop work.
- Commit messages: imperative mood, name the TC(s) advanced, no
  co-author trailers, no marketing language.
