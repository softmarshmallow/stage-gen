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
`components/`, the public CLI contract, or provider adapters.

The adapter invokes the public root command (`bun run stage-gen -- ...`) and
consumes output manifests/files through server-side routes. Browser code never
receives provider credentials. The preview may be replaced or removed without
changing a component's typed input/output contract.

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
