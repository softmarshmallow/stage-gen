# Optional web preview adapter

`web/` is the first consumer of generated output. It provides run controls,
artifact inspection, progress events, and a browser scene for a 2D scrolling
recipe.

Its assumptions are intentionally local:

- horizontal follow camera and parallax;
- one-dimensional terrain heightmap and fixed tile roles;
- side-view character movement, gravity, combat, drops, and portals;
- browser texture registration and a fixed preview viewport.

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

New run manifests declare `input.transparencyMode`. For both `ai` and `chroma`,
the pipeline's canonical image artifacts are already transparent PNGs, so the
preview loads their alpha normally. Runtime chroma keying exists only as a
compatibility path for legacy manifests that do not declare a strategy. It
must never be applied to a new `ai` or `chroma` run, because doing so could
erase intentional subject colours.

Because a legacy manifest does not contain a reproducible strategy choice,
the adapter previews it but refuses per-asset retry. Restart it from the
picker with an explicit current strategy.

The HTTP start body is `{ prompt, transparencyMode }`, where
`transparencyMode` is `"ai"` or `"chroma"` and omitted means `"ai"`. The web
adapter treats the returned run tag as opaque; it does not assume equal prompts
share a cache entry across strategies.

Static third-party background music is not part of this adapter. Generated
music is a headless component artifact and may be previewed only after its
provenance and media contract are present.

The browser gameplay implementation remains unchanged and optional. All Node
and TypeScript code is confined to `web/`; the headless implementation is
Python.
