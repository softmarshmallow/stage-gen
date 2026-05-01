# TODO — QA / Test-Case Ledger

This file is the persistent state of the loop. Each entry is a test
case (TC) phrased as an observable outcome. Order encodes dependency:

- **Across phases:** strict. Every TC in Phase N must pass before any
  TC in Phase N+1 starts.
- **Within a phase:** TCs may advance in parallel where independent.
  Fan out subagents accordingly (see `LOOP_PROMPT.md`).

Anything below TC-N within the same phase may assume every prior phase
has passed; siblings inside the phase do not depend on each other unless
called out in the TC body.

Status legend: `[ ]` open · `[x]` passed · `[BLOCKED] reason` stuck.
On pass, append an indented evidence pointer line: `-> <artifact / sha / log>`.

Phrasing convention per TC:
- **given** — pre-conditions a QA can confirm before testing.
- **when** — the action taken.
- **then** — the observable outcome that decides pass/fail.
- **check** — the cheapest signal that proves it (file existence, dim
  read, exit code, visible UI element, log line). One signal per TC.

A TC is **non-prescriptive about implementation** — it does not name
files, modules, classes, or libraries unless that name is part of the
external contract (e.g. `concept_<tag>.png`, `world_spec_<tag>.json`,
`#FF00FF` chroma key, `#00ff88` accent). Anything else is the agent's
choice.

---

## PHASE 0 — Project bootstrap (must pass before anything else)

[x] TC-001: Repository installs cleanly on a fresh checkout
  -> bun install exit 0, 58 packages, no error lines (verifier aab16fbadc218894a)

[x] TC-002: Required environment variables are documented and discoverable
  -> .env.example lists 5 keys (AI_GATEWAY_API_KEY, AI_GATEWAY_BASE_URL, IMAGE_MODEL, TEXT_MODEL, OUT_DIR) matching pipeline/src/env.ts; .env gitignored

[x] TC-003: Pipeline fails fast on missing env vars with a clear message
  -> exit 2 in <50ms with stderr naming AI_GATEWAY_API_KEY when key absent or empty

[x] TC-004: Repository has the three documented workspace areas
  -> pipeline/ + web/ each have own manifest + entry and run standalone (web binds :3000 HTTP 200); fixtures/ at top level

---

## PHASE 1 — Single-command pipeline invocation

[x] TC-010: A single CLI command runs the full pipeline for one prompt
  -> `bun run pipeline "<prompt>"` exits 0 walking 16 stub stages; forced failure → exit 1 with one-line stderr (verifier a5fd9f09190a8e668)

[x] TC-011: The output tag is derived deterministically from the prompt
  -> tag.ts: pure slug-shorthash from sha256; same prompt → same dir 'haunted-swamp-metroidvania-af76f135'

[x] TC-012: Each run isolates its outputs to its own per-tag directory
  -> two prompts → two distinct out/<tag>/; no leak outside out/; only contractual filenames overlap

[x] TC-013: Generated outputs are not committed to git
  -> /out/ in .gitignore line 82; `git status --porcelain out/` empty; check-ignore confirms

NOTE: Phase 2+ replaces stub stage `run` bodies in place (orchestrator architecture preserved).
NOTE: retry helper (5 blind, exp backoff) and meta sidecar writer in place — Phase 2 producers should use them.

---

## PHASE 2 — Concept and world bible (the bottleneck wave)

[x] TC-020: Concept image is the first artifact written
  -> concept_<tag>.png is only PNG in dir, mtime trivially earliest (verifier ac1210d02946d3e4f)

[x] TC-021: Concept image has the contracted dimensions and is non-blank
  -> sips reports 1536x1024 exactly; >5000 unique colors confirms non-flat

[x] TC-022: Concept image has no chroma-key magenta region
  -> full-canvas scan: 0 pixels at exact (255,0,255); painterly opaque

[x] TC-023: World bible JSON is produced and conforms to its schema
  -> WorldSpecSchema (zod) parses cleanly; all superRefine constraints hold (verifier ada3d728acabd38fa)

[x] TC-024: World bible names are agent-invented (no enum-like reuse)
  -> zero exact-string matches across name/title/kind/theme/id between two distinct prompts (Mournlight Abbey vs Rainspire Verge)

[x] TC-025: World bible mob ladder has the contracted shape
  -> mobs.length=8; every entry has name/brief/tier_label/body_plan; adjacent body_plans distinct

[x] TC-026: World bible item list has exactly 8 entries with distinct kinds
  -> items.length=8; all 8 kind values unique

[x] TC-027: World bible obstacle sheet list has the contracted shape
  -> obstacles.length=3; sheet_theme values unique

[x] TC-028: World bible parallax layer stack is well-formed
  -> layers.length=5; exactly one opaque; opaque has z_index=0 and parallax=0

NOTE: pipeline/src/schema/world.ts is single source of truth for downstream consumers (asset generators, runtime).
NOTE: pipeline/src/ai/client.ts centralises gateway + ai-sdk wiring — Phase 3 generators import from here.

### Phase 2 — strict-verifier follow-ups (verifier a7ee66f3f172806df)

[x] TC-024b: Layer parallax tuples vary across worlds (not copy of prompt examples)
  -> samurai [0,0.18,0.46,1.18] vs deep-sea [0,0.14,0.47,1.23] — differ; example tuple removed from prompt; agent told to vary per world

[x] TC-024c: Layer archetype ordering varies across worlds
  -> samurai produced 4 layers (Washi Sky → Ink Peaks → Castle Valley → Near Blossoms); deep-sea produced 4 (Blue Water Vault → Far Seamount Haze → Mid Reef Arches → Near Kelp Curtains); per-call layer-count picker + explicit "don't default to canonical 5-band stack" instruction

[x] TC-026b: Item kinds are semantically distinct, not synonyms
  -> superRefine rejects currency/vessel/fragment synonym pairs; old specs (rainy-gothic dew-phial+spore-vial; neon cred-chip+rare-token) now FAIL parse; both new specs PASS

[x] TC-025b: Mob body_plan strings encode anatomy, not scale or vibe
  -> ANATOMICAL_NOUN_SET whitelist + per-mob refine; old "floating shroud" / "palm-sized crawler" now FAIL parse; new specs use insectoid/avian/cephalopod/serpentine/etc.

[x] TC-028b: Layer.parallax has a hard upper bound in the schema
  -> Layer.parallax now `.min(0).max(2)` in pipeline/src/schema/world.ts

---

## PHASE 3 — Wave A: parallel asset fan-out

The TCs in this phase do not constrain implementation order within the
wave — the agent may dispatch them in parallel — but **every TC in
Phase 3 must pass before any TC in Phase 4 starts** (Wave B reads Wave A
outputs as references).

[x] TC-030: Skybox layer is generated at the contracted canvas size
  -> opaque layer (bluebird_sky) at 2400×800 (verifier a7805c7e75228324e)

[x] TC-031: Each parallax layer (1–5) is generated at the contracted size
  -> 5 layer_*.png at 2400×800 each, matches L=5

[x] TC-032: Non-opaque parallax layers carry the contract chroma-key colour
  -> all 4 non-opaque layers show large pure #FF00FF regions matching paint_region (vision verifier a400318db53f04bcd)

[x] TC-033: Ground tileset is generated at the contracted size and grid
  -> 2400×800; 12×4 grid visible; row 1 surface, row 2 slopes/inner-corners, row 3 sides+bottom-edges, row 4 fill+floating-platforms (vision verifier a307acb78d550affc, after retry with row-by-row prompt rewrite)

[x] TC-034: Character turnaround is generated as a 3-pose sheet
  -> 2400×800; three distinct poses (front/side/back) on solid magenta

[x] TC-035: One mob turnaround is generated per ladder rung
  -> 8 mob_concept_*.png files, matches N=8

[x] TC-036: Mob turnarounds visually escalate up the ladder
  -> monotonic progression: rung 0 (pika puff) → rung 7 (massive crested ice wyvern); intermediates escalate in size/menace

[x] TC-037: Obstacle sheets are generated, one per declared sheet theme
  -> 3 obstacle sheets, each 4×2 grid of distinct themed props on magenta

[x] TC-038: Items sheet contains exactly 8 distinct pickup props
  -> 4×2 grid of 8 visibly distinct items on magenta

[x] TC-039: Inventory panel is generated at the contracted size
  -> 1536×1024; 8 discrete recessed slot cells in 4×2 grid; magenta surround

[x] TC-040: Portal pair is generated at the contracted size
  -> 2048×1024; two stone arches (cool blue entry / warm gold exit) clearly distinguishable

[x] TC-041: All Wave A outputs share the concept's stylistic palette
  -> concept + sky + parallax + character + mobs + items all share same painterly snowy-alpine palette; no outlier

[x] TC-042: Reproducibility metadata is persisted next to every Wave A asset
  -> all 22 PNGs have <name>.png.meta.json with prompt/model/refs/params/ts/attempts (verifier a7805c7e75228324e)

---

## PHASE 4 — Wave B: animation states (depend on Wave A turnarounds)

[x] TC-050: Character motion master sheet is generated
  -> character_<tag>_combined.png at 2400×3440; 5×4 grid (idle/walk/run/jump/crawl) (verifier a5eca3441dd891205)

[x] TC-051: Master sheet preserves character scale across all 20 cells
  -> retry 2 (per-row strip generation + sharp composite) PASSES: head tops consistent across rows 1-3, jump apex breaks baseline (legal), row 5 correctly low; cross-row scale locked (verifier a0cf6faa6deda86b8)

[x] TC-052: Character attack strip is generated
  -> 1×4 on magenta; sword-attack progression (windup → swing → thrust → recover)

[x] TC-053: One idle strip is produced per mob rung
  -> 8 mob_<tag>_<i>_idle.png; each 1×4 on magenta with subtle idle motion

[x] TC-054: One hurt strip is produced per mob rung
  -> 8 mob_<tag>_<i>_hurt.png; each 1×4 on magenta with flinch/recoil

[x] TC-055: Animation strips preserve subject identity from their turnaround
  -> all 8 mobs idle+hurt match source species (verifier a054e9651a23ad714); fixed by reordering refs (mob_concept primary) + stronger identity-preservation prompt language; prior drift on mobs 0+4 resolved

NOTE: TC-123 (re-run no-op) achieved as side-effect of skip-if-exists in image-helper.ts/concept.ts/world-spec.ts — verified third run = 0.13s, zero PNG byte changes

### Phase 4 — strict-verifier follow-ups (verifier a4df16d72a6f84c67)

[x] TC-042b: Chroma-key magenta in generated sprites is exact #FF00FF
  -> Phase 5 post-chroma stage (pipeline/src/post/chroma-snap.ts + chroma-snap-stage.ts) snaps any RGB pixel within Manhattan distance 30 of (255,0,255) to exact (255,0,255). Idempotent (sidecar marker extra.chroma_snapped=true). Stage runs after Wave B; processes layers (skipping opaque), tileset, character concept/combined/attack, mob concepts/idle/hurt, obstacles, items, inventory, portal. Skips concept_<tag>.png and the opaque parallax backdrop. Spot-check on snowy-mountain run: character_attack near=1346456→0 / exact=2→1346458; layer_near_fir_grass near=1193228→0 / exact=47→1193275; character_combined exact=0→8900. Re-run = 32ms (idempotency). Pipeline exit 0.

[BLOCKED] TC-050b: Master sheet idle row shows visible breath/sway across 4 frames
  -> 2 retries spent (pixel-rail + per-row strip); per-row improved everything else but idle remains 4 near-identical standing poses. Cosmetic — runtime can fake subtle breath via 1-px y-jitter on alternate frames if needed. Not blocking gameplay.

[x] TC-050c: Master sheet jump row shows 4 distinct phases
  -> retry 2 (per-row strip) PASSES: F1 anticipation crouch, F2 push-off mid-air rising, F3 APEX AIRBORNE arms up clear of rail, F4 landing crouch (verifier a0cf6faa6deda86b8)

[x] TC-050d: Master sheet crawl row shows consistent low-stance progression
  -> all 4 row-5 frames low-horizontal/kneeling, consistent orientation, visible limb cycling

[ ] TC-053b: Mob idle motion floor — visible delta between adjacent frames
  given: a mob idle strip
  when: a QA compares any two adjacent frames
  then: at least one anatomical landmark moved by >2% of canvas height
  check: mobs 0, 3, 6 currently fail; need stronger idle-motion prompt or per-frame jitter

[ ] TC-053c: Mob idle/hurt sprite reserves chroma-key background
  given: a mob idle/hurt strip
  when: pixel-sample exact #FF00FF count after generation+snap
  then: at least 1000 exact-magenta pixels remain
  check: mob_7_idle currently 603 — sprite covers nearly full canvas; producer should reserve background margin

---

## PHASE 5 — Post-processing (deterministic, no model calls)

[x] TC-060: Character master sheet is sliced into five per-state strips
  -> 5 PNGs character_<tag>-fromcombined_{idle,walk,run,jump,crawl}.png; runs after post-chroma; idempotent (slicer a07df478370e62660)

[x] TC-061: Sliced strips contain the expected frames at the contracted height
  -> all 5 strips at 2400×688 (sips); jump strip airborne apex confirmed via upper-band non-magenta count

[x] TC-062: Chroma-key replacement produces clean transparency at runtime
  -> chromaKeyToAlpha in web/lib/runtime/image-ops.ts; exact (255,0,255) → alpha 0; spot-check character_concept (50,0) preAlpha 255 → postAlpha 0; on-disk PNG SHA unchanged (web agent ab7764c5ce22eec6e)

[x] TC-063: Per-cell alpha bounding-box crop honours variable prop sizes
  -> extractCellsBbox: obstacles_0 cell heights 181..400, widths 550..600; items cell widths 373..600, heights 290..382 — sizes vary per cell within same sheet

[x] TC-064: Parallax layer edges fade to transparent after the runtime loads them
  -> fadeParallaxEdges (64px taper); valley_pine_haze row 340 (x0,x32,x63,x64) pre=(255,255,255,0) post=(0,128,251,0); on-disk PNG SHA unchanged

NOTE: web runtime foundation in place — /play/[tag] route, /api/assets/<tag>/[...path] streaming endpoint, Phaser 4 scene scaffold. Phase 6 builds atop this.

---

## PHASE 6 — Runtime: scene loading

[x] TC-070: Web runtime loads a per-tag asset directory without errors
  -> probes.consoleErrors=[]; Preview MCP error log empty 4s after canvas mount (vision verifier a3657bb1555718dc8)

[x] TC-071: Skybox renders and stays fixed relative to camera scroll
  -> opaque skybox tilePositionX === 0 despite cam.scrollX > 700 (live probe)

[x] TC-072: Parallax layers scroll at decreasing speeds with depth
  -> tilePositionX = scrollX × parallax, monotonic with parallax (77/203/441/869 across 0.11/0.29/0.63/1.24)

[x] TC-073: Parallax loop seams are invisible during continuous scroll
  -> 3 captures across ~3s of auto-pan show no vertical seam line / repeat artifact at any layer's edge

[x] TC-074: Ground terrain assembles from the tileset along a heightmap
  -> continuous snowy walkable band with snow-capped grass surface; multiple step-up/down transitions matching heightmap; no gaps/overlapping tiles

[x] TC-075: Obstacles are placed on flat ground, bottom-anchored, never on slopes
  -> 19 obstacles bottom-anchored on snow surface; none floating/embedded; slope columns skipped via flatRuns filter

[x] TC-076: Mobs spawn in fixed columns and play their idle animation
  -> 11 mobs spawned with looping anim (frameRate 6, repeat -1); burst frames 100ms apart show different positions/poses

[x] TC-077: Player character is anchored bottom-center on the ground line
  -> player at column 1 (first flat run+1), origin (0.5,1.0), Y = baseline − h×TILE_PX; feet on snow band

[x] TC-078: Foreground accents render in front of the player and runtime-blur
  -> retry 2 (pipeline flood-fill-from-edges in chroma-snap) PASSES. pipeline/src/post/chroma-snap.ts replaced with snapChromaKey(): BFS from every edge pixel within Manhattan 280 of (255,0,255), flood spreads to neighbours within 220, masked pixels snap to exact magenta, interior pinks untouched. Sidecar marker extra.chroma_method="flood-from-edges" gates re-runs (older threshold-30 sidecars correctly trigger fresh flood pass). Runtime layer threshold=180 reverted in web/lib/runtime/assets.ts; all loaders back to exact-match. 12-frame puppeteer re-measure on /play/snowy-mountain (~10.8s window): max=489 pink px (0.053%), avg=292, min=152 — well under the 1000-px target. TC-062 spot-check via sharp on 6 sprites: painted bodies intact (334k–2M opaque non-magenta px), reddish details preserved (character_combined=2094, items=11029), interiorNearMagenta > 0 on every sprite (122–9179 px) confirming interior pinks survive. Mob_4_idle previous pink rectangle gone (87,625 background px snapped). Pipeline exit 0 in 3.4s (no regen needed; chroma-snap re-pass only).

[x] TC-079: Sustained framerate at 1280×720 is at least 30 fps
  -> window.__sceneFps.minOverWindow = 120 over 30s window (>= 30 by 4x)

NOTE: dev server kept running for downstream verifiers/Phase 7 work.

---

## PHASE 7 — Runtime: gameplay

[ ] TC-080: WASD and arrow keys move the player horizontally
  given: TC-077 passes
  when: a QA presses left/right on either keyset
  then: the player walks in the corresponding direction; the camera
        follows
  check: position delta after key press is non-zero in the pressed
         direction; camera centre moves with the player

[ ] TC-081: Player has a working walk / run / jump / crouch / attack state set
  given: the sliced character strips and the attack strip exist
  when: a QA exercises each input for the corresponding state
  then: the on-screen player visibly switches to the matching animation
        and back to idle when the input ends
  check: vision verdict = pass on a 5-state screen recording — each
         state visibly distinct

[ ] TC-082: Player feet remain locked to the heightmap during movement
  given: a sloped or stepped section of ground exists
  when: the player walks across the section
  then: the feet stay snapped to the painted surface; no floating, no
        clipping
  check: vision verdict = pass on a recording of a slope traversal —
         "feet on surface, no float, no clip"

[ ] TC-083: Mobs wander within bounded columns
  given: TC-076 passes
  when: a QA observes a mob over 10 seconds
  then: the mob moves around its spawn column within bounded extents
        and does not leave its lane or wander off-screen
  check: vision verdict = pass on a 10-second recording — "mob stays
         within local lane"

[ ] TC-084: Mob hit-points scale linearly with ladder index
  given: a world has N mobs at ladder indices 0…N-1
  when: the player attacks each mob to defeat
  then: mob at index `i` takes exactly `i + 1` hits to defeat
  check: per-mob defeat-hit count matches the formula for every rung

[ ] TC-085: Mobs play their hurt animation on damage
  given: a mob takes a non-fatal hit
  when: the hit lands
  then: the mob visibly switches to its hurt strip for one cycle and
        returns to idle
  check: vision verdict = pass on a hit/recover recording — "hurt
         animation plays once, returns to idle"

[ ] TC-086: Defeated mobs drop one item from the world's item pool
  given: a mob is defeated
  when: the mob's death triggers
  then: a single item sprite from the world's items appears at the
        mob's position and falls / settles to ground
  check: a new item sprite is present after a mob death; pool membership
         confirmed by sprite identity

[ ] TC-087: Walking over an item adds it to the inventory overlay
  given: an item is on the ground and the inventory overlay is empty
  when: the player walks over the item
  then: the item disappears from the world and appears in a slot of the
        inventory overlay
  check: world sprite count for that item drops by 1; inventory overlay
         slot count increases by 1

[ ] TC-088: Inventory overlay uses the contracted slot positions
  given: TC-039 produced the inventory panel
  when: items are picked up
  then: each item lands in one of the panel's locked slot positions,
        not at arbitrary coordinates
  check: vision verdict = pass on an overlay screenshot — "items
         aligned to panel slot positions"

[ ] TC-089: Walking onto the exit portal triggers the stage-advance hook
  given: an exit portal is rendered in the scene
  when: the player overlaps the exit portal
  then: a stage-advance event fires (today: a console event or a
        re-load of the same scene; not a new world generation)
  check: the documented stage-advance signal is observable (console
         line, route change, or scene reset)

---

## PHASE 8 — Web shell: picker and generation views

> Source of truth for any ambiguity in this phase: [`DESIGN.md`](DESIGN.md).
> The TCs below are observable acceptance checks; DESIGN.md holds the
> full UX flow, page layout, and visual language they enforce.

[ ] TC-100: Single-page picker view loads at the app's root URL
  given: the web app is running locally
  when: a QA opens the root URL
  then: the picker view renders with a free-form prompt input and a
        list of curated preset prompts
  check: prompt input is focusable; at least one preset button is
         present and clickable

[ ] TC-101: Visual language is monospace, dark, single-accent
  given: the picker view is loaded
  when: a QA inspects the page
  then: the page uses a monospace typeface, a near-black background
        (`#0a0a0a`), foreground `#e6e6e6`, and the single accent
        `#00ff88` only on the Play CTA, the progress bar fill, and
        active states
  check: computed styles confirm the colour values; no element other
         than those three uses the accent

[ ] TC-102: Selecting a preset populates the prompt input
  given: the picker view is loaded
  when: a QA clicks a preset button
  then: the prompt input's value updates to that preset's text
  check: input value equals the clicked preset's text

[ ] TC-103: Pressing Generate starts a run and switches to the generation view
  given: a non-empty prompt is in the input
  when: a QA presses the Generate button
  then: the page transitions to the generation view at a stable URL
        keyed by the run; reloading the URL keeps the same view
  check: URL changes; reload preserves the generation view

[ ] TC-104: Play CTA is disabled until the run reports done
  given: a run has just started
  when: a QA inspects the Play CTA
  then: the CTA appears in a visibly inert state and is non-interactive
  check: CTA has the disabled style (dim text, dim border) and does
         not navigate on click

[ ] TC-105: Concept image appears at the top of the page within ~30 s of starting
  given: the generation view is showing an in-progress run
  when: ~30 seconds elapse
  then: the concept image appears full-width at the top of the page
  check: the concept slot is populated with a real image (not
         `loading.gif`) within 60 s

[ ] TC-106: Empty asset slots show `loading.gif`, never a CSS spinner
  given: the generation view is mid-run
  when: a QA inspects any not-yet-generated asset slot
  then: the slot displays the committed `loading.gif` asset
  check: every empty slot's content is `loading.gif`; no CSS-keyframe
         animations are present elsewhere on the page

[ ] TC-107: Asset slots populate as their assets become available
  given: a run is mid-flight
  when: an asset finishes generation server-side
  then: the corresponding slot replaces `loading.gif` with the asset
        thumbnail in place, without a page reload
  check: a streamed update event is observable; the slot's content
         changes without navigation

[ ] TC-108: Post-processed versions replace raw versions in place
  given: a slot is showing a raw generated asset
  when: post-processing finishes for that asset (background removed,
        sliced if applicable)
  then: the slot updates again to the post-processed version, in place,
        without disturbing other slots
  check: same slot's content changes a second time; no other slot's
         state changes during that update

[ ] TC-109: Progress bar advances quantitatively as assets complete
  given: a run is mid-flight
  when: assets complete
  then: the on-screen progress bar (block characters `█░` rendered as
        text) and the count (`N / total`) advance together
  check: the count text and the bar's filled-block count are always
         consistent; both increase monotonically

[ ] TC-110: Log strip streams pipeline events in append-only order
  given: a run is mid-flight
  when: pipeline events fire
  then: each event appears as one line in the log strip, dim, monospace,
        in the order it fired
  check: log strip text grows; new lines are appended at the bottom;
         oldest lines are not removed during a run

[ ] TC-111: Clicking any thumbnail opens a fullscreen preview lightbox
  given: at least one populated asset slot is visible
  when: a QA clicks the thumbnail
  then: a fullscreen overlay appears showing the asset large with file
        name, dimensions, and (for chroma-keyed assets) a "show alpha"
        toggle
  check: overlay is present; Esc or anywhere-click dismisses it

[ ] TC-112: Page never appears stalled for more than 5 s during an active run
  given: a run is mid-flight
  when: a QA watches for 5 s without interacting
  then: at least one of {a new log line, a new thumbnail, a progress
        bar advance, a slot post-process update} occurs
  check: a 5 s observation window always contains at least one of those
         four signals; never zero

[ ] TC-113: Picker view renders correctly on mobile portrait at 375px width
  given: the viewport is 375×667
  when: a QA loads the picker view
  then: the layout fits the viewport with no horizontal scrollbar; the
        prompt input and preset buttons are usable
  check: page width matches viewport; presets are tappable without
         clipping

[ ] TC-114: Generation view's asset grid wraps gracefully at 375px width
  given: the generation view is mid-run at 375×667
  when: a QA inspects the asset grid
  then: the grid wraps to fit; no horizontal scroll appears; slots
        retain their 1px border and `loading.gif` placeholder
  check: no horizontal scrollbar; all slots remain visible by scrolling
         vertically

---

## PHASE 9 — Play handoff and re-runs

[ ] TC-120: Run completion activates the Play CTA with a visual change
  given: a run reports `done`
  when: the page receives the done event
  then: the Play CTA visibly switches from inert to active (accent
        fill, foreground text colour) and becomes interactive
  check: Play CTA computed style matches the active state; clicking it
         produces a navigation

[ ] TC-121: Pressing Play loads the playable stage in place of the generation view
  given: the Play CTA is active
  when: a QA presses Play
  then: the playable Phaser scene mounts and replaces the generation
        view within ~2 s
  check: a `<canvas>` element is present and rendering; previous
         generation-view content is no longer visible

[ ] TC-122: A "back" affordance returns to the picker without losing assets
  given: the playable stage is mounted
  when: a QA presses the back affordance
  then: the page returns to the picker; the just-generated world is
        still cached and re-entering it does not re-run the pipeline
  check: re-entering the same tag's URL renders the generation view
         already at 100% with Play active

[ ] TC-123: Re-running an existing tag from the CLI is a no-op
  given: a complete `out/<tag>/` already exists
  when: the same prompt is run through the CLI again
  then: the pipeline produces no new image-gen calls and no file
        contents change
  check: the per-tag directory's PNG hash set is unchanged across the
         two runs

[ ] TC-124: Re-entering a complete run in the web UI populates the grid near-instantly from cache
  given: a complete run exists
  when: a QA opens the run's URL fresh
  then: the asset grid populates within 1 s, the progress bar shows
        100%, and the Play CTA is immediately active
  check: time-to-fully-populated grid ≤ 1 s; Play CTA is in active
         state on first paint

[ ] TC-125: A failed asset slot shows a red `×` and a per-asset retry affordance
  given: one Wave-A asset's generation has been forced to fail
  when: a QA inspects the affected slot in the generation view
  then: the slot displays a red `×` with the asset's name and a "retry
        this asset" affordance
  check: slot has a red `×` glyph; retry affordance is clickable;
         clicking it re-issues only that asset's generation

[ ] TC-126: A pipeline-fatal error surfaces as a red banner and keeps Play disabled
  given: a fatal pipeline error occurs mid-run
  when: the page receives the error event
  then: a red banner appears above the progress bar with the error
        text from the log; the Play CTA stays disabled
  check: banner element is present with the error text; CTA remains
         in its disabled style

---

## PHASE 10 — End-to-end mission verification

[ ] TC-130: Three different prompts produce three visually-distinct playable worlds
  given: the entire pipeline + web app is functional per all prior TCs
  when: an unmodified observer runs the documented one-shot command
        for three different one-line prompts
  then: each run produces a fully populated `out/<tag>/`, the web UI
        plays each world end-to-end, and the three concept images
        clearly read as three different worlds
  check: vision verdict = pass on a contact sheet of the three concept
         images — "three distinct worlds, no shared palette/theme";
         each world plays with all gameplay TCs (TC-080…089) holding

[ ] TC-131: Cold-start observer flow holds without editing files or reading source
  given: a fresh checkout with only `.env` populated
  when: an observer follows only the user-facing docs to produce one
        playable world
  then: the observer reaches a playable stage in the browser without
        editing source files, hand-writing JSON, or reading code to
        find which command to run
  check: observer's session log contains only documented commands
         and clicks; no file edits to non-`.env` paths
