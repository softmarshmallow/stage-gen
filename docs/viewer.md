# The viewer

The viewer is the local web client for the `stage-gen` CLI. It lists every run under the folders
you give it, grouped by the workflow that made it, draws each run's execution graph and artifacts,
and shows each workflow's offline plan and the commands that run it. It is read-only: it
does not start runs, receives no provider credentials, and implements no gameplay. Playable
projects and their asset wiring belong to their Godot owners. The [site](site.md) is a separate
surface: it documents workflows and shows their examples, and it never reads run folders.

## Start it

```sh
uv run stage-gen view
uv run stage-gen view --runs out --runs spikes/movie_sprite --port 3100 --no-open
```

`stage-gen view [--runs DIR]... [--port 3000] [--no-open]` needs a source checkout and Bun,
because the viewer is the Next app in [`web/viewer`](../web/viewer). It finds the checkout by
walking up from the installed package, then from the working directory, to the `pyproject.toml`
named `stage-gen` that has `web/viewer` beside it. From an installed wheel, or without Bun on
`PATH`, it exits 2 and points here. Install the web workspace once with
`cd web && bun install --frozen-lockfile`.

Before it starts the server, the command:

- exports the catalog into `~/.cache/stage-gen/catalog/catalog.json` (`$XDG_CACHE_HOME`
  replaces `~/.cache` when it is an absolute path). The viewer groups runs by it and draws plans
  from it; it never plans anything itself.
- sets `STAGE_GEN_RUN_ROOTS` (the absolute run folders, joined by the platform's path separator;
  `out/` of the checkout when no `--runs` is given), `STAGE_GEN_CATALOG`, `STAGE_GEN_VIEW_CACHE`
  (`~/.cache/stage-gen/views`) and `STAGE_GEN_REPO_ROOT` for the server. Provider keys are removed
  from the server's environment.
- starts a thread that derives missing views into the view cache every three seconds (below).

It then runs `bun run --cwd web/viewer dev --port PORT --hostname 127.0.0.1`, opens the browser
once the port answers unless `--no-open` is given. The server leads its own process group; when the
launcher ends, by Ctrl-C, SIGTERM, a hangup or the server exiting, it stops that whole group, so
nothing it started outlives it. The server listens on the loopback interface only.

Run without `stage-gen view` (`cd web/viewer && bun run dev`), the viewer reads `out/` of its
checkout and has neither a catalog nor a view cache: runs are listed ungrouped and only views a
run carries itself are drawn.

## Runs and their views

A run is a folder that holds `execution-plan.json`, `execution-view.json`, `manifest.json`,
`bundle.json` or `case.json`; or `graph.json` beside `summary.json` or `trace.jsonl` (a
character run); or `plan.json` beside `execution.json` (a portrait run). Runs are found up to
four folders below each root. A run's own folders are not searched again, hidden folders and
`node_modules` are skipped, symlinked folders are not followed out of the root, and the example
store at the top of a root (`out/examples`) is not a run. [`src/stage_gen/runs.py`](../src/stage_gen/runs.py)
and [`lib/shell/runs.ts`](../web/viewer/lib/shell/runs.ts) apply the same rules.

The view a run page draws is the run's own `execution-view.json`, or the one derived into the view
cache, whichever is newer. Derived views are written only under
`~/.cache/stage-gen/views/<first 16 hex digits of sha256(real path)>/execution-view.json`; the
viewer and the refresher never write into a run folder. The refresher derives a view when a run's
plan, trace or own record is newer than both its own view and its cached one:

- SDK runs, and runs of the SDK workflows, are joined from their plan and trace by the SDK;
- universe and storefront runs without a view are joined by their graph document's view builder;
- a character run's `graph.json` and `trace.jsonl` are staged under gnode's names in a temporary
  folder and joined there, titled from the workflow's `[labels]`;
- a portrait run is joined the same way from its portrait sub-run's `graph.json` and traces, with
  artifact references made relative to the run. A portrait run prepared but never run has no
  trace to join, and is listed with its own `execution.json` status;
- a game run is never derived. Its persisted view is drawn, or its row says the view is not
  exported, and `demo-games export-view --run DIR` exports one.

`stage-gen inspect RUN --write-view DIR` writes the same derived view into a folder you name.

The viewer reads any `*-execution-view-v1` envelope at `schema_version = 3`, and gnode's own
`gnode-run-view-v1`, which a joined character or portrait view carries. Header fields a producer
adds beside the envelope (`pipeline_id`, `title`, a graph document's `recipe` literal, a game's
ids, a joined view's `graph_kind`) are kept as the run's subject. Pipeline identities and node
type IDs need no registration. A user-authored pipeline uses the same graph, state, timing, cache,
artifact and provenance surfaces as an installed workflow, and node types without joined display
metadata use the generic node view. A document at another version is refused with a re-derive
message rather than migrated.

## Pages

- `/` lists every run under every root. Each installed workflow leads with its title and promise
  from the catalog and a link to its page; its runs follow, newest first, each with its state,
  node counts and when it last changed. Runs no workflow claims follow under "Game runs" (a graph
  document literal no workflow owns, or a consumer document) and "Other runs". Which workflow a
  run belongs to is read from the catalog's declared identities: an SDK run's pipeline id, a
  graph document's literal and graph kinds, a character run's graph kind, a portrait run's plan
  kind.
- `/workflows/<id>` shows a workflow's promise and summary, its commands with a copy button, the
  graph it plans offline from its committed sample inputs (drawn by the run viewer with every node
  pending; each lane is a step), its steps, and its runs.
- `/runs/<root>/<tag>` is one run. `<root>` is a root's folder name and a short digest of its real
  path; `<tag>` is the run's root-relative path with `/` written as `~`. A universe gallery or a
  storefront run shows its output as a reader would see it, with the graph one link away
  (`?view=graph`); any other run with a view fills the window with its graph and node inspector; a
  run with neither shows its own record and how to get a view. `/runs/<root>/<tag>/artifacts`
  lists the declared outputs.

While a run on a page is live (its trace was written in the last fifteen minutes and it has not
finished), the page refreshes itself every two seconds; the graph keeps its camera and selection.

## Artifact previews

The application selects renderers for image, audio, video, text, and data artifacts. A display
hint the renderer has no view for falls back to an ordinary artifact link. GNode carries renderer
hints as JSON; it does not own a sprite or parallax contract.

The historical `motion` field still describes a uniform strip of 1 through 16 frames. Its
application-owned parser preserves that bound; a different atlas layout needs its own preview
kind. The existing motion player provides frame stepping and sample playback.

A `preview` object with `kind = "parallax-background-v2"` describes supplied layers: canvas
size, run-local image references, layer order, dimensions, offsets, parallax factors, repeat
flags, and how each layer repeats (`mirror_repeat`, `seam_repaint`, or `admitted`). Version 1
manifests, which claimed one reflection for every layer, fall back to the ordinary artifact view.
The node inspector provides horizontal and vertical camera-offset sliders and per-layer visibility
controls. This inspects a composition; it does not infer layers from a reference or simulate a
game. The renderer accepts up to 32 layers with dimensions up to 16384 pixels and rejects
malformed geometry and paths. Unknown preview kinds retain the ordinary artifact fallback. Model
files such as GLB retain their media type and can be opened or downloaded; there is no dedicated
spatial renderer yet.

[`artifact-preview.ts`](../web/ui/contracts/artifact-preview.ts) owns these adapters and
[`ParallaxPreview.tsx`](../web/viewer/app/runs/[root]/[tag]/ParallaxPreview.tsx) owns the
interactive layer preview. Adding a renderer is an application change, independent of adding a
workflow.

## Serving and boundaries

`/api/assets/<root>/<tag>/<path>` serves files under one run folder of one configured root. It
validates the root key, each tag segment and the portable artifact path, checks filesystem
confinement, and refuses symlink escapes. It serves known passive image, audio, video, model,
text, and JSON media types, with an opaque fallback and `nosniff`. It does not serve executable
HTML or SVG media types.

Nothing under [`lib/shell`](../web/viewer/lib/shell) starts a subprocess, and a docs check fails if
anything there imports one. Generation, retry, cache admission, artifact publication and deriving a
run view belong to the Python application; the viewer only reads what it is given. The web
workspace imports no game engine. The viewer reads the run-view, catalog and example wire formats
through the shared parsers in [`web/ui/contracts`](../web/ui/contracts), whose hand-authored
fixtures a Python contract test also validates.

## Presentation

The shell uses Tailwind CSS v4. [`app/globals.css`](../web/viewer/app/globals.css) declares design
tokens and the transparent-image checkerboard; [`app/ui.ts`](../web/viewer/app/ui.ts) holds shared
utility class strings.

## Verification

Credential-free gates for this boundary are:

```sh
cd web
bun install --frozen-lockfile
bun run check
bun test
bun run --cwd viewer build
uv run pytest -q tests/unit/test_runs.py tests/unit/interfaces/test_view.py
```

Tests cover multi-root discovery, the derived-view cache and its fallback, grouping by workflow,
generic view parsing, confined paths, bounded previews, node and graph inspection, the workflow
page, the specialized output views, and the launcher's environment and refusals. A browser check
can prove that supplied layers load and respond to preview controls. It does not establish
generated-media quality or prove that a game is playable.
