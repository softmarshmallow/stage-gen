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

[ ] TC-001: Repository installs cleanly on a fresh checkout
  given: a clean clone of the repo and a system with Bun installed
  when: the documented install command is run from the repo root
  then: install completes with zero errors and zero unresolved deps
  check: install command exits 0; no `error` lines in its stdout/stderr

[ ] TC-002: Required environment variables are documented and discoverable
  given: a fresh checkout with no `.env` configured
  when: a QA reads the project's setup docs
  then: every required env var (image-gen key, text-gen key, gateway URL,
        any others) is named in `.env.example` with a one-line purpose
  check: `.env.example` exists at repo root and lists every key the
         pipeline reads; `.env` is gitignored

[ ] TC-003: Pipeline fails fast on missing env vars with a clear message
  given: `.env` is empty or missing one required key
  when: the pipeline CLI is invoked
  then: it exits non-zero within 2 seconds with a message naming the
        missing key
  check: stderr contains the missing key's name; exit code ≠ 0

[ ] TC-004: Repository has the three documented workspace areas
  given: the repo is checked out
  when: a QA inspects the top-level layout
  then: there is a clear separation between pipeline code, web app code,
        and committed fixtures, each independently runnable
  check: each area has its own entry point and own dependency manifest

---

## PHASE 1 — Single-command pipeline invocation

[ ] TC-010: A single CLI command runs the full pipeline for one prompt
  given: env is configured and the repo is installed
  when: the documented one-shot command is run with a one-line prompt
        argument
  then: the command runs to completion (success or surfaced error)
        without requiring further input
  check: command exits 0 on success; any failure is surfaced as a
         non-zero exit with a one-line cause

[ ] TC-011: The output tag is derived deterministically from the prompt
  given: the same prompt is passed twice
  when: the pipeline computes the output directory name
  then: the same tag is produced both times — a stable slug plus a
        short hash
  check: re-running with the same prompt resolves to the same `out/<tag>/`
         path

[ ] TC-012: Each run isolates its outputs to its own per-tag directory
  given: two different prompts have been run
  when: a QA inspects the output area
  then: each prompt's artifacts live under `out/<tag>/` with no
        cross-contamination of files between tags
  check: no shared filenames between the two output dirs other than
         contractually-named per-tag artifacts

[ ] TC-013: Generated outputs are not committed to git
  given: a pipeline run has produced files under `out/`
  when: a QA runs `git status`
  then: the generated files are gitignored and do not appear as
        candidates for commit
  check: `git status --porcelain out/` is empty

---

## PHASE 2 — Concept and world bible (the bottleneck wave)

[ ] TC-020: Concept image is the first artifact written
  given: a one-line prompt is being processed
  when: the pipeline begins execution
  then: the concept image lands on disk before any downstream asset
        starts generation
  check: `concept_<tag>.png` exists in `out/<tag>/` strictly earlier (by
         file mtime) than every other generated PNG

[ ] TC-021: Concept image has the contracted dimensions and is non-blank
  given: TC-020 has produced a concept image
  when: a QA reads the file's metadata and a sampled subset of pixels
  then: dimensions are exactly 1536×1024 and the image is not a single
        flat colour
  check: width/height read as 1536/1024; pixel variance check passes

[ ] TC-022: Concept image has no chroma-key magenta region
  given: a concept image exists
  when: a vision-capable subagent inspects it for the contract magenta
        (`#FF00FF`) chroma colour
  then: the concept is a painterly, fully-opaque image with no
        chroma-key zones
  check: vision verdict = pass; reason names "no chroma magenta region"

[ ] TC-023: World bible JSON is produced and conforms to its schema
  given: the concept image exists
  when: the world-design step runs
  then: `world_spec_<tag>.json` is written and parses against the
        documented schema with no missing or extra fields
  check: a schema-parse exits 0 against the JSON

[ ] TC-024: World bible names are agent-invented (no enum-like reuse)
  given: two distinct prompts have produced two world bibles
  when: a QA compares the two specs side-by-side
  then: mob names, item names, layer names, and theme strings differ
        between the two; nothing reads as "picked from a fixed list"
  check: zero exact-string matches across the two specs' name fields
         (excluding contractually-named keys)

[ ] TC-025: World bible mob ladder has the contracted shape
  given: a world bible exists
  when: a QA inspects the `mobs[]` array
  then: the array length is at least 1 (default 8); every entry has a
        name, a brief, a tier label, and a body plan; adjacent rungs
        have distinct body plans
  check: schema parse + adjacency-distinctness check exits 0

[ ] TC-026: World bible item list has exactly 8 entries with distinct kinds
  given: a world bible exists
  when: a QA inspects the `items[]` array
  then: length is exactly 8 and every entry has a unique `kind`
  check: array length = 8; no duplicate `kind` values

[ ] TC-027: World bible obstacle sheet list has the contracted shape
  given: a world bible exists
  when: a QA inspects the `obstacles[]` array
  then: length is at least 1 (default 3); every entry has a unique
        `sheet_theme`
  check: schema parse + uniqueness check exits 0

[ ] TC-028: World bible parallax layer stack is well-formed
  given: a world bible exists
  when: a QA inspects the `layers[]` array
  then: length is between 1 and 5; exactly one layer has `opaque: true`
        and that layer sits at `z_index: 0` with `parallax: 0`
  check: schema parse + opaque-layer constraint check exits 0

---

## PHASE 3 — Wave A: parallel asset fan-out

The TCs in this phase do not constrain implementation order within the
wave — the agent may dispatch them in parallel — but **every TC in
Phase 3 must pass before any TC in Phase 4 starts** (Wave B reads Wave A
outputs as references).

[ ] TC-030: Skybox layer is generated at the contracted canvas size
  given: world bible and concept image exist
  when: the skybox generator runs
  then: the opaque skybox layer PNG is written at exactly 2400×800
  check: file exists; dimensions read as 2400×800

[ ] TC-031: Each parallax layer (1–5) is generated at the contracted size
  given: world bible has L layers (1 ≤ L ≤ 5)
  when: each parallax layer's generator runs
  then: L layer PNGs are written, each at exactly 2400×800
  check: file count = L; each file dimensions = 2400×800

[ ] TC-032: Non-opaque parallax layers carry the contract chroma-key colour
  given: a non-opaque parallax layer has been generated
  when: a vision subagent inspects the layer for sky/background regions
  then: those regions are the exact contract magenta `#FF00FF`, not a
        near-magenta or a transparent fill
  check: vision verdict = pass for "uses #FF00FF as chroma key"

[ ] TC-033: Ground tileset is generated at the contracted size and grid
  given: world bible and concept exist
  when: the tileset generator runs
  then: `tileset_<tag>.png` is written at 2400×800 and visibly contains
        a 12×4 grid of cells
  check: file exists; dimensions = 2400×800; vision verdict = pass on
         "12 columns × 4 rows of tile cells visible"

[ ] TC-034: Character turnaround is generated as a 3-pose sheet
  given: world bible (character description) and concept exist
  when: the character turnaround generator runs
  then: `character_concept_<tag>.png` is written at 2400×800 with three
        clearly distinct poses on a chroma-key magenta ground
  check: file exists; dimensions = 2400×800; vision verdict = pass on
         "three poses, magenta background"

[ ] TC-035: One mob turnaround is generated per ladder rung
  given: world bible specifies N mobs
  when: the mob turnaround generators run
  then: N files of the form `mob_concept_<tag>_<i>.png` are written, one
        per rung
  check: file count = N

[ ] TC-036: Mob turnarounds visually escalate up the ladder
  given: all N mob turnarounds exist
  when: a vision subagent compares rung 0 with rung N-1 against the
        world bible's tier labels
  then: rung 0 reads as the weakest silhouette, rung N-1 as the
        strongest, with monotonic progression in between
  check: vision verdict = pass on "monotonic escalation matches
         tier_label progression"

[ ] TC-037: Obstacle sheets are generated, one per declared sheet theme
  given: world bible specifies M obstacle sheets
  when: the obstacle generators run
  then: M sheets of the form `obstacles_<tag>_<i>.png` are written, each
        with a 4×2 grid of distinct props on chroma-key magenta
  check: file count = M; vision verdict = pass on "4×2 grid, distinct
         props, magenta ground" for each

[ ] TC-038: Items sheet contains exactly 8 distinct pickup props
  given: world bible items list of length 8 exists
  when: the items generator runs
  then: `items_<tag>.png` is written as a 4×2 grid of 8 visibly distinct
        pickup props on chroma-key magenta
  check: file exists; vision verdict = pass on "4×2 grid, 8 distinct
         items, magenta ground"

[ ] TC-039: Inventory panel is generated at the contracted size
  given: world bible exists
  when: the inventory panel generator runs
  then: `inventory_<tag>.png` is written at 1536×1024 with locked slot
        positions visible
  check: file exists; dimensions = 1536×1024; vision verdict = pass on
         "inventory panel with discrete slot positions"

[ ] TC-040: Portal pair is generated at the contracted size
  given: world bible exists
  when: the portal generator runs
  then: `portal_<tag>.png` is written at 2048×1024 containing two
        distinct portal renderings (entry / exit)
  check: file exists; dimensions = 2048×1024; vision verdict = pass on
         "two distinct portals visible"

[ ] TC-041: All Wave A outputs share the concept's stylistic palette
  given: every Wave A asset has been generated for one tag
  when: a vision subagent compares each output to the concept image
        for palette and brushwork coherence
  then: every output reads as belonging to the same world as the
        concept; no asset reads as a stylistic outlier
  check: vision verdict = pass for each asset against the concept

[ ] TC-042: Reproducibility metadata is persisted next to every Wave A asset
  given: a Wave A asset has been generated
  when: a QA inspects the output directory
  then: alongside each PNG there is a sidecar holding the prompt, seed,
        model name, reference paths, and any params used
  check: for each Wave A PNG, a sidecar metadata file exists in the
         same directory

---

## PHASE 4 — Wave B: animation states (depend on Wave A turnarounds)

[ ] TC-050: Character motion master sheet is generated
  given: TC-034 has produced the character turnaround
  when: the master-sheet generator runs
  then: `character_<tag>_combined.png` is written at exactly 2400×3440
        with a 5-row × 4-column layout of motion frames
  check: file exists; dimensions = 2400×3440; vision verdict = pass on
         "5 rows × 4 columns of motion frames visible"

[ ] TC-051: Master sheet preserves character scale across all 20 cells
  given: the master sheet exists
  when: a vision subagent compares head height and feet position
        across every cell
  then: head and feet sit on the same horizontal rails in every cell
  check: vision verdict = pass on "head/feet rails consistent across
         all 20 cells"

[ ] TC-052: Character attack strip is generated
  given: TC-034 has produced the character turnaround
  when: the attack-strip generator runs
  then: `character_<tag>_attack.png` is written as a 1×4 strip on
        chroma-key magenta
  check: file exists; vision verdict = pass on "1×4 attack frames,
         magenta ground"

[ ] TC-053: One idle strip is produced per mob rung
  given: all N mob turnarounds (TC-035) exist
  when: the per-mob idle generators run
  then: N files of the form `mob_<tag>_<i>_idle.png` are written, each
        a 1×4 idle strip on chroma-key magenta
  check: file count = N; each is a 1×4 strip

[ ] TC-054: One hurt strip is produced per mob rung
  given: all N mob turnarounds exist
  when: the per-mob hurt generators run
  then: N files of the form `mob_<tag>_<i>_hurt.png` are written, each
        a 1×4 hurt strip on chroma-key magenta
  check: file count = N; each is a 1×4 strip

[ ] TC-055: Animation strips preserve subject identity from their turnaround
  given: a character or mob turnaround and its derived strips exist
  when: a vision subagent compares the strips to the source turnaround
  then: silhouette, palette, and proportions are recognisably the same
        creature across the source and every derived strip
  check: vision verdict = pass on "identity preserved" for character
         master sheet, character attack, and every mob idle/hurt pair

---

## PHASE 5 — Post-processing (deterministic, no model calls)

[ ] TC-060: Character master sheet is sliced into five per-state strips
  given: TC-050 has produced the master sheet
  when: the post-processing slicer runs
  then: five files of the form `character_<tag>-fromcombined_<state>.png`
        are written for the states idle, walk, run, jump, crawl
  check: exactly five strip files exist with the documented state names

[ ] TC-061: Sliced strips contain the expected frames at the contracted height
  given: the five sliced strips exist
  when: a QA reads each strip's dimensions
  then: each strip is the expected 1×4 layout consistent with the
        master sheet's row height
  check: each strip's dimensions match the documented per-row geometry

[ ] TC-062: Chroma-key replacement produces clean transparency at runtime
  given: any chroma-keyed sprite (character/mob/items/obstacles) is loaded
  when: the runtime applies its chroma-key step
  then: every `#FF00FF` pixel becomes alpha 0; sprite edges have no
        magenta fringe
  check: vision verdict = pass on a sprite previewed against a
         contrasting background — no visible halo at edges

[ ] TC-063: Per-cell alpha bounding-box crop honours variable prop sizes
  given: an obstacle or items sheet has been processed
  when: the runtime extracts each cell's prop
  then: each prop is cropped to its own visible content's bounding box,
        not to a fixed cell rectangle
  check: extracted prop dimensions vary cell-to-cell within the same
         sheet

[ ] TC-064: Parallax layer edges fade to transparent after the runtime loads them
  given: a non-opaque parallax layer has been loaded by the runtime
  when: the runtime samples alpha along the left and right edges of
        the in-memory texture (after its load-time edge-fade pass)
  then: alpha tapers smoothly from opaque inward to fully transparent
        at both the left and right outer columns; the source PNG on
        disk is unmodified
  check: alpha at the outermost column reads as 0; alpha 64px inward
         reads as > 0; vision verdict = pass on a checker-background
         preview of the loaded texture; on-disk PNG byte hash unchanged
         before vs. after load

---

## PHASE 6 — Runtime: scene loading

[ ] TC-070: Web runtime loads a per-tag asset directory without errors
  given: a complete `out/<tag>/` produced by the pipeline exists
  when: the web runtime is pointed at that tag
  then: the scene mounts in the browser with no `console.error` output
  check: a headless run records zero console errors during the first
         3 seconds after the canvas appears

[ ] TC-071: Skybox renders and stays fixed relative to camera scroll
  given: TC-070 passes
  when: the player moves horizontally in the loaded scene
  then: the skybox visibly does not scroll with the world
  check: vision verdict = pass on a before/after screenshot pair —
         skybox content unchanged after camera movement

[ ] TC-072: Parallax layers scroll at decreasing speeds with depth
  given: TC-070 passes and at least two non-opaque layers exist
  when: the player moves horizontally
  then: deeper layers scroll slower than shallower layers; no layer
        scrolls faster than the foreground
  check: vision verdict = pass on a before/after pair — back layer has
         smaller pixel displacement than front layer

[ ] TC-073: Parallax loop seams are invisible during continuous scroll
  given: a layer has been scrolled past one full tile width
  when: a QA watches the seam transition
  then: no vertical edge, line, or visible repeat artifact appears at
        the seam
  check: vision verdict = pass on three screenshots taken across one
         seam transition — no visible discontinuity

[ ] TC-074: Ground terrain assembles from the tileset along a heightmap
  given: TC-070 passes
  when: a QA inspects the rendered ground band
  then: the ground reads as a continuous walkable surface with slope
        transitions at column changes; no gaps; no overlapping tiles
  check: vision verdict = pass on a wide screenshot — "continuous
         walkable ground with slope transitions"

[ ] TC-075: Obstacles are placed on flat ground, bottom-anchored, never on slopes
  given: the runtime has spawned obstacles in the loaded scene
  when: a QA inspects each obstacle's placement
  then: every obstacle sits with its contact band on a flat ground
        column, not floating, not embedded, not on a slope column
  check: vision verdict = pass on a full-scene screenshot — every
         obstacle bottom-anchored on flat ground

[ ] TC-076: Mobs spawn in fixed columns and play their idle animation
  given: TC-070 passes and at least one mob is on-screen
  when: a QA watches the scene for a few seconds
  then: each visible mob plays its idle strip in a steady loop and
        does not drift between frames
  check: vision verdict = pass on a 2-second screen recording — mobs
         visibly cycling through idle frames

[ ] TC-077: Player character is anchored bottom-center on the ground line
  given: TC-070 passes
  when: a QA inspects the player's resting position
  then: the player's feet sit on the painted ground band, not on tile
        tops or below the surface
  check: vision verdict = pass on a player-rest screenshot — feet on
         grass band

[ ] TC-078: Foreground accents render in front of the player and runtime-blur
  given: a foreground layer exists in the world bible
  when: the scene renders during play
  then: the foreground appears in front of all gameplay elements and
        is visibly blurred relative to background bands
  check: vision verdict = pass on a gameplay screenshot — "foreground
         layer in front, visibly blurred"

[ ] TC-079: Sustained framerate at 1280×720 is at least 30 fps
  given: TC-070 passes
  when: the scene runs continuously for 30 seconds at 1280×720 in a
        modern Chromium-based browser
  then: the average framerate stays at or above 30 fps
  check: a runtime fps probe reports `min ≥ 30` over the window

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
