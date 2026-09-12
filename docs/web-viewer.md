# The web viewer

`web/` is an optional, read-only consumer of asset pipeline outputs. It lists runs, displays
execution graphs and artifacts, and offers bounded previews. It does not start generation, receives
no provider credentials, and implements no gameplay. Playable projects and their asset wiring
belong to their Godot owners.

## Run inspection

`/` and `/runs` list runs; `/runs/<tag>` renders the derived `execution-view.json` and its node
inspector; `/runs/<tag>/artifacts` lists declared outputs. The generic envelope has
`kind = "pipeline-execution-view-v1"`, `schema_version = 3`, `pipeline_id`, and `title`.
Pipeline identities and node type IDs do not need registration in the viewer. A user-authored
pipeline can use the same graph, state, timing, cache, artifact, and provenance surfaces as a
built-in recipe. Node types without joined display metadata use the generic node view.

The viewer also retains readers for historical platformer, dialogue, point-and-click, runner,
survival, universe, and storefront execution views. These readers describe old run records; they
do not restore those games' browser runtimes. Unsupported versions and malformed documents are
listed as unreadable instead of being silently hidden. Re-export a compatible plan with
`stage-gen export-view --run out/<tag>`; an older plan that cannot be read remains a historical
record rather than being migrated by the viewer.

The index reads `kind` and `schema_version` from historical consumer documents or the execution
view. Artifact inspection uses the execution view's declared references, digests, byte counts,
media types, presence flags, and node ports. Provenance uses the port's declared sidecar pairing,
with the historical filename convention retained for artifacts without a declared port.

## Artifact previews

The application selects renderers for image, audio, video, text, and data artifacts. Unknown
artifact display hints on generic pipeline views fall back to an ordinary artifact link.
GNode carries renderer hints as JSON; it does not own a sprite or parallax contract.

The historical `motion` field still describes a uniform strip of 1 through 16 frames. Its
application-owned parser preserves that bound; a different atlas layout needs its own preview
kind. The existing motion player provides frame stepping and sample playback.

A `preview` object with `kind = "parallax-background-v1"` describes supplied layers: canvas
size, run-local image references, layer order, dimensions, offsets, parallax factors, and repeat
flags. The node inspector provides horizontal and vertical camera-offset sliders and per-layer
visibility controls. This inspects a composition; it does not infer layers from a reference or
simulate a game. The renderer accepts up to 32 layers with dimensions up to 16384 pixels and
rejects malformed geometry and paths. Unknown preview kinds retain the ordinary artifact
fallback. Model files such as GLB retain their media type and can be opened or downloaded;
there is no dedicated spatial renderer yet.

[`artifact-preview.ts`](../web/lib/run-viewer/artifact-preview.ts) owns these adapters and
[`ParallaxPreview.tsx`](../web/app/runs/[tag]/ParallaxPreview.tsx) owns the interactive layer
preview. Adding a renderer is an application change, independent of adding a pipeline.

## Other consumers and serving

`/universe/<tag>` renders a universe gallery, `/storefront/<tag>` presents storefront art and
listing copy, and `/universe/demo` demonstrates illustrated-map navigation. These specialized
asset consumers read their own manifests and contracts. Their parsers do not define the
contract for generic run inspection, and none reads a canonical gameplay contract to play a
game.

`/api/assets/<tag>/<path>` serves files under the selected run root. It validates run tags and
portable artifact paths, checks filesystem confinement, and refuses symlink escapes. It serves
known passive image, audio, video, model, text, and JSON media types, with an opaque fallback and
`nosniff`. It does not serve executable HTML or SVG media types. Runs default to `out/`; set
`STAGE_GEN_OUT_DIR` to inspect a different local output root.

Nothing under [`lib/shell`](../web/lib/shell) starts a subprocess. Generation, retry, cache
admission, artifact publication, and exporting a run view belong to the Python application.
The web workspace imports no game engine.

## Presentation

The shell uses Tailwind CSS v4. [`app/globals.css`](../web/app/globals.css) declares design tokens
and the transparent-image checkerboard; [`app/ui.ts`](../web/app/ui.ts) holds shared utility
class strings. OpenLayers supplies the illustrated-map view's navigation and its own CSS.

## Verification

Credential-free gates for this boundary are:

```sh
cd web
bun run check
bun test
bun run build
```

Tests cover generic and historical view parsing, run discovery, confined paths, bounded previews,
node and graph inspection, and the specialized asset consumers. A browser check can prove that
supplied layers load and respond to preview controls. It does not establish generated-media
quality or prove that a game is playable.
