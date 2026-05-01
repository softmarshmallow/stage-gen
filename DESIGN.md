# DESIGN — web application UX + visual spec

The web app's job, the user flow, and the visual language.

---

## What the web app does

One thing: **let a person turn a one-line world prompt into a playable
side-scroll stage, watching the assets appear as they generate, and
press Play when the world is ready.**

It is a thin shell over the pipeline. There is no account system, no
gallery, no settings page, no sharing. A single page does the whole
job.

---

## The user flow

A linear, single-page flow.

1. **Pick a prompt.**
   The page shows a curated list of pre-defined prompts. The user
   clicks one. They may also type a free-form prompt in the same
   input.

2. **(Optional) Tweak parameters.**
   A collapsed disclosure exposes server-accepted parameters (seed,
   tag override, anything else the server accepts). Default
   collapsed; most users never open it.

3. **Press Generate.**
   The button becomes a status label ("running…") and the page
   enters the generation view.

4. **Watch the world appear.**
   Wave 1 produces the world concept art. It shows up at full size
   at the top of the page **the moment it's ready**. As subsequent
   waves complete, their outputs slot into the asset grid below —
   and as soon as the server finishes post-processing an asset
   (background removed, sliced if applicable), the post-processed
   version replaces the raw one in place.

5. **Play.**
   The Play CTA at the top of the page is **disabled** until every
   required asset is present. The instant the pipeline reports done,
   it activates. Clicking it loads the playable stage.

That is the whole flow.

---

## The core UX premise: image gen is slow

Each wave takes roughly **30 seconds**. A full pipeline run is
**2–4 minutes wall-clock**. Every UX decision below exists because of
this single fact.

**Implications the design must respect:**

- **Never show a single blocking spinner for the whole run.** The
  user will think it's hung. Show *something happening* every few
  seconds.
- **Stream partial results.** The world concept being visible at
  ~30 s is the difference between "this is working" and "this is
  broken".
- **Surface progress quantitatively.** A counter ("4 / 25 assets")
  and a percentage bar give the user a real sense of how long is
  left. Track progress % whenever the expected total is known.
- **Make every asset previewable.** Click any thumbnail to open it
  large. The user is sitting here for minutes — give them something
  to look at and explore.
- **Show the loading affordance everywhere a slot is empty.** A
  dedicated `loading.gif` (committed asset, not a CSS spinner) fills
  every not-yet-generated slot. Consistent visual = "more is
  coming". `loading.gif` is the only animated element on the page.
- **Use streaming, not page reloads.** Either Server-Sent Events or
  polling — pick at implementation time based on what's simpler.
  Either way the user must never have to refresh to see new assets.

If a design choice trades clarity for cleverness, choose clarity.
The user is staring at this page for minutes; do not make them guess
what's happening.

---

## Page layout

Two views, both single-column, monospace, full-width with a
comfortable max content width centered on the page.

### View A — picker (idle)

```
┌──────────────────────────────────────────────────────┐
│ stage-gen                                            │
│                                                      │
│ prompt:                                              │
│ ┌──────────────────────────────────────────────────┐ │
│ │ snowy mountain village at dawn                   │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
│ presets:                                             │
│   [ snowy mountain village at dawn ]                 │
│   [ neon-lit night market ]                          │
│   [ haunted forest under a blood moon ]              │
│   [ sunbaked desert ruins ]                          │
│   ...                                                │
│                                                      │
│ ▸ advanced                                           │
│                                                      │
│                              [ generate ]            │
└──────────────────────────────────────────────────────┘
```

### View B — generation (active)

```
┌──────────────────────────────────────────────────────┐
│ stage-gen / snowy mountain village at dawn           │
│ tag: snowy_a3f1c2     [ play ▸ ] (disabled until done)│
│                                                      │
│ progress: ████████░░░░░░░░░░  12 / 25  (48%)         │
│                                                      │
│ ┌── world concept ─────────────────────────────────┐ │
│ │                                                  │ │
│ │           [ full-width concept image ]           │ │
│ │                                                  │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
│ layers                                               │
│ ┌────┬────┬────┬────┬────┐                           │
│ │ L0 │ L1 │ L2 │ L3 │ ⏳ │                           │
│ └────┴────┴────┴────┴────┘                           │
│                                                      │
│ character                                            │
│ ┌────┬────┬────┬────┬────┬────┐                      │
│ │ ck │idl │wlk │run │ ⏳ │ ⏳ │                      │
│ └────┴────┴────┴────┴────┴────┘                      │
│                                                      │
│ mobs   obstacles   items   inventory   portal        │
│ ...                                                  │
│                                                      │
│ log:                                                 │
│   00:00  generating world concept                    │
│   00:32  generating world spec                       │
│   00:51  layer 0 ready                               │
│   ...                                                │
└──────────────────────────────────────────────────────┘
```

The generation view has four regions, top to bottom:

1. **Header strip** — prompt echo, tag, the Play CTA.
2. **Progress strip** — text bar + counts. No spinner; the bar IS the
   spinner.
3. **Asset grid** — sectioned by asset family (concept, layers,
   character, mobs, obstacles, items, inventory, portal). Each slot
   is either a thumbnail or `loading.gif`. Click for full preview.
4. **Log** — append-only text stream of pipeline progress. Monospace,
   dim, scrolls itself. This is reassurance, not the primary signal.

---

## Visual language

**Monospace, zero design elements, raw.** The site looks like a
terminal in a browser: text-first, grid-aligned, no chrome.

### Type

- Single typeface, system monospace stack:
  `ui-monospace, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace`.
- One size for body (`14px`), one larger for the page title
  (`18px`). Headings within the page are achieved with prefix
  characters (`/`, `─`) and weight, not size.
- Line height `1.5`. Letter spacing default. No italics.

### Colour

- **Background**: `#0a0a0a` (near-black). Default dark.
- **Foreground**: `#e6e6e6`.
- **Dim**: `#666` for log text and metadata.
- **Accent**: a single accent (`#00ff88`) used for the Play CTA
  fill, the progress bar fill, and active states. **One accent
  only.**
- **Errors**: `#ff5555`. Used sparingly.

No gradients. No shadows. No rounded corners beyond `2px`
(effectively flat). No background images. No decorative dividers —
only `─` characters or 1px hairlines in dim colour.

### Layout primitives

- 8px base grid.
- Borders are 1px in dim colour. No box-shadow.
- Buttons are `[ label ]` style — bracket-wrapped text, 1px border,
  no fill. Active = inverted (filled with accent, text in
  background colour). Disabled = dim text, dim border.
- Inputs are bare 1px-bordered boxes; no rounded corners; cursor is
  the foreground colour.
- The loading affordance is **`loading.gif`** scaled to fit each
  slot. Same gif everywhere, no per-asset variants. CSS animations
  are forbidden — `loading.gif` is the only animated element on the
  page.

### Information hierarchy

- The Play CTA is the only visually loud element. It sits top-right
  of the header, large, and visibly inert until ready. Activation
  is a real event — it should feel like the world has finished
  cooking.
- Progress bar uses block characters (`█░`) rendered as text, not
  styled divs. This keeps the monospace promise.
- Asset grid: each slot is a square box (1px border) showing either
  the asset thumbnail or `loading.gif`. Below each slot, one line
  of monospace label.

### Anti-patterns

- No skeleton loaders. Use `loading.gif` consistently.
- No toast notifications. The log line IS the notification.
- No modals except the asset preview lightbox (click thumbnail →
  full-size overlay, click anywhere to dismiss).
- No icons. Text labels only. (`▸` for play, `⏳` for pending, `✓`
  for cached are the only glyphs allowed.)
- No tooltips. If something needs explanation, label it inline.

---

## Interaction details

### Generate

- Pressing Generate starts a run and transitions to the generation
  view. The page stays on a stable URL keyed by the run, so a
  reload during generation resumes the same view.

### Streaming updates

- The page subscribes to a stream of `asset` / `log` / `done` /
  `error` events for the active run. When an asset event arrives,
  the corresponding slot moves from `loading.gif` → raw thumbnail.
  When the post-processed version arrives, the slot updates again
  in place. When the done event arrives, the Play CTA activates.

### Cached re-runs

- Re-entering an existing run that's already complete populates the
  grid near-instantly from cache. No fake staging. The progress bar
  jumps straight to 100%; the Play CTA is immediately active.

### Preview lightbox

- Click any thumbnail → fullscreen overlay (95% viewport width or
  natural size, whichever is smaller) on a `#000` ground.
- Caption shows the file name, dimensions, and (for chroma-keyed
  assets) a "show alpha" toggle that swaps in a checker background.
- Esc or click-anywhere closes.

### Play

- Active CTA → loads the playable stage in place of the generation
  view.
- A small "back" link returns to the picker without throwing away
  the generated assets — the user can return to their world without
  regenerating.

### Error paths

- A failed asset shows a red `×` slot with the asset name and a
  "retry this asset" affordance.
- A pipeline-fatal error shows a red banner above the progress bar
  with the error text from the log. The Play CTA stays disabled.

---

## Technical baseline

- **Next.js + shadcn/ui**. Initialise shadcn (`shadcn init --template next`)
  and pull in only the primitives the page needs.

- shadcn primitives (Button, Dialog, Progress) are used as starting
  points and **re-skinned to the visual language above**. Most
  shadcn defaults — rounded corners, soft shadows, subtle gradients
  — are explicitly overridden. Treat shadcn as a primitives library,
  not as a design system to inherit.

Everything else is implementation choice.

---

## Definition of done (UX)

- A user lands on the page, picks a preset, presses Generate, and
  within ~30 s sees the world concept image appear.
- During the rest of the run (~3 min), the asset grid populates
  visibly every few seconds; the progress bar advances; the log
  scrolls.
- When all assets are ready, the Play CTA activates with a clear
  visual change (dim → accent-filled). Clicking it loads the
  playable stage within 2 s.
- Re-entering an already-complete run populates the grid in under a
  second from cache.
- The page never shows a blank or stalled state for more than 5 s
  without either a new log line or a new asset thumbnail. If it
  does, that is a bug.
- The page renders identically (modulo content) on mobile portrait
  width down to 375px — the asset grid wraps; nothing else changes.
