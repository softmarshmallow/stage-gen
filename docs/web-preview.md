# Optional web preview adapter

`web/` is the first consumer of generated output. It provides run controls,
artifact inspection, progress events, and a browser scene for a 2D scrolling
recipe.

Its assumptions are intentionally local:

- horizontal follow camera and parallax;
- one-dimensional terrain heightmap and fixed tile roles;
- side-view character movement, one-way upper platforms, ladder traversal,
  gravity, combat, drops, and portals;
- browser texture registration and a fixed preview viewport.

The preview's typed semantic composition rules, canonical depth stack, ground
baseline, and zoom-safe parallax placement are documented in
[Browser scene-layer contract](scene-layers.md). Generated `z_index` values do
not directly become Phaser depths.

These belong in `web/lib/runtime/` and preview routes. They must not leak into
`src/stage_gen/components/`, the public CLI contract, or provider adapters.

The server-only adapter invokes the authoritative Python command from the
repository root. Its default launch is exactly:

```text
uv run stage-gen generate --recipe scrolling-preview --transparency <mode> <prompt>
```

The process API receives an executable and argument array with `shell: false`;
prompt text is never interpolated into a command string. The optional
`STAGE_GEN_EXECUTABLE` override accepts only `uv`, `stage-gen`, `stage-gen-py`,
or a normalized absolute path whose basename is one of those values. Output is
rooted at `STAGE_GEN_OUT_DIR` (default `out/`) for both processes. The adapter
consumes manifests, run summaries, SSE progress, and confined artifacts through
server routes. Browser code never receives provider credentials.

The Generate view exposes **AI background removal**, on by default. On maps to
the headless `ai` transparency strategy; off explicitly requests the degraded
`chroma` fallback. Launches and per-asset retries preserve that choice. The UI
shows the selected strategy in run metadata instead of inferring it from the
prompt or asset colour.

The exact current `recipe_run_v3` summary must declare `input.transparency_mode`. For both `ai`
and `chroma`, the pipeline's canonical image artifacts are already transparent
PNGs, so the preview loads their alpha normally and never performs runtime
chroma keying. A missing or invalid strategy fails closed because the adapter
cannot reproduce the run's generation policy.

The HTTP start body is `{ prompt, transparency_mode }`, where
`transparency_mode` is `"ai"` or `"chroma"` and omitted means `"ai"`. The web
adapter treats the returned run tag as opaque; it does not assume equal prompts
share a cache entry across strategies.

Static third-party background music is not part of this adapter. Generated
music is a headless component artifact and may be previewed only after its
provenance and media contract are present.

The browser gameplay implementation remains optional. All Node and TypeScript
code is confined to `web/`; the headless implementation is Python.

## Vertical gameplay adapter

The model demo selects a reserved four-tier graph before placing props or mobs.
The approved seed owns columns `19..47`, disjoint from opening-encounter
columns `0..13`. Its one-way decks are launch `[1280,1664]` at y `528`,
transfer `[1728,2112]` at y `464`, bridge `[2176,2560]` at y `400`, and
summit `[2624,3008]` at y `336`. Each body/cap is connected terrain-depth
paint; the one decorative summit ladder renders at prop depth on x `2976` and
connects the summit to terrain y `592`. Geometry, not image alpha, is
authoritative.

Every adjacent rise and gap is 64 pixels. With the runtime's shared 30Hz
semi-implicit physics (520px/s jump, 1500px/s² gravity, 540px/s run), a rising
deck is crossed on step 15 after 270 horizontal pixels; each jump therefore has
206 pixels of range margin. The jump-only chain reaches all four tiers without
the ladder. The ladder is a direct safe shortcut, while Down+Space exposes
drop-through recovery to the terrain below every platform source column.

Ladder activation uses a typed 30-pixel horizontal half-width and is vertically
clamped to the explicit deck/terrain endpoints. The approved 80x320 raster has
a separate typed 32-pixel visual overshoot above and below the 256-pixel climb
span; visual bounds never expand the climb zone. Ladder texture, the required
four-frame `character_climb` strip, platform materials, both render groups,
graph routes, reservations, and collision commit as one transaction; any
failure rolls everything back and surfaces an asset error.

Player support is exactly one of `terrain`, `platform`, `ladder`, or `air`.
Up enters the summit shortcut from terrain; Down enters from its owning deck.
While attached, gravity and horizontal movement are suppressed, releasing the
vertical key holds position and pauses the deterministic rear-facing/no-flip
climb loop, and Space jumps off. Down+Space on a deck drops through when no
ladder entry applies. The camera follows feet through a
zoom-aware screen deadzone from 420 to 528 pixels and clamps world scroll Y to
`[-512, 0]`. Its projection uses Phaser's centered camera origin:
`screenY = originY + (footY - scrollY - originY) * zoom`; culling uses the
matching zoomed half-extents around `scroll + viewport/2`, not `scroll` as the
world-view top-left. HUD and near-foreground remain screen-composited.
