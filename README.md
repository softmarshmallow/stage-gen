# stage-gen

`stage-gen` is a general-purpose, headless Python pipeline and component library
for producing coherent 2D game assets with validation, deterministic
post-processing, and content-bound provenance. The repository includes one
reference scrolling-world recipe and an optional web-based scrolling-game
preview; gameplay remains a consumer of the generated artifacts, not part of
the reusable core.

![Current deterministic 20-asset model demo with multi-tier platforms and ladder traversal](docs/media/gameplay-model-demo.png)

_Current deterministic 20-asset model demo. The screenshot is a canvas-only
capture from the multi-tier gameplay fixture. Its adjacent
[provenance and review record](docs/media/gameplay-model-demo.png.meta.json)
binds the published bytes to the verified source state._

[Watch the historical deterministic 30-second capture (18-asset build)](docs/media/gameplay-showcase.mp4).
Its [poster](docs/media/gameplay-showcase.poster.png), adjacent provenance
sidecars, and [artifact-specific media notice](docs/media/gameplay-showcase.LICENSE.md)
remain bound to that older capture. They must not be presented as a recording
of the current 20-asset fixture.

## Quickstart

### Try the headless package without credentials

Requirements are Python 3.12 or newer and
[`uv`](https://docs.astral.sh/uv/). These commands do not call a hosted
provider or create a populated environment file:

```sh
uv sync --all-extras
uv run stage-gen recipes
uv run stage-gen benchmark smoke
```

### Generate the reference recipe

Create `.env` only when it does not already exist, then populate the required
keys. Do not overwrite an existing file:

```sh
test -e .env || cp .env.example .env
```

The CLI default is `--transparency ai`; it requires both `OPENROUTER_API_KEY`
and `FAL_KEY`. A doctor run with blank keys intentionally reports an incomplete
configuration and exits with status 2.

```sh
uv run stage-gen doctor --transparency ai --json
uv run stage-gen generate --recipe scrolling-preview \
  "original rain-dark stone ruins with pale moss"
```

Use `--transparency chroma` for the explicit degraded local-keying path.
`FAL_KEY` is not required for an explicit `--transparency chroma` run, although
OpenRouter remains required for image and structured generation. Standalone
background removal always requires `FAL_KEY`, independent of the recipe's
transparency setting:

```sh
uv run stage-gen remove-background \
  --input ./input.png --output ./out/subject.png
```

Generated runs default to `out/<prompt-tag>-<mode>/`. Every run writes an
atomic `run.json`; a successful scrolling-preview run also writes manifest
schema v2 and adjacent artifact provenance. A bare prompt remains a
compatibility alias for `generate --recipe scrolling-preview`.

For opt-in JSON/TOML theme compilation, see
[Theme art-direction controls](docs/theme-art-direction.md).

## What it provides

- Typed, provider-neutral components for image and structured generation,
  background removal, experimental music generation, and endpoint-conditioned
  loop synthesis.
- Deterministic image/audio inspection, normalization, persistence, retries,
  cancellation, path confinement, and redaction.
- Recipe orchestration with progress, cache validation, atomic summaries,
  manifests, artifact hashes, and adjacent provenance.
- A CLI plus an optional loopback HTTP/SSE service.
- A replaceable Next.js/React/Phaser preview that consumes completed manifests
  without moving gameplay assumptions into Python components.

## Recipe boundary

The stable product boundary is coherent **2D asset generation**. Genre,
viewpoint and camera, composition rules, and validation harnesses belong to
individual recipes. `scrolling-preview` is the only implemented recipe today:
it is the side-view reference integration, not a template whose platformer
assumptions or asset layout may define future recipes.

## Showcase: Visual Novel Scene Kit

![Signal at Blue Hour anime dating-sim demo with Mio Amamiya and state-driven expression variants](docs/media/dialogue-scene-showcase.webp)

**Signal at Blue Hour** is a deterministic, playable 15+ slow-burn romance
vignette built from a background, one adult heroine identity, four transparent
expression variants, caller-authored dialogue, and presentation data. Mio
Amamiya is a 23-year-old graduate astronomy researcher on the night shift at a
seaside radio observatory. Each dialogue beat selects a discrete `neutral`,
`delighted`, `flustered`, or `concerned` variant; these are reusable sprite
states, not animation frames and not a rig.

Run the optional web app and open `/dialogue-scene/demo` to play the vertical
slice. The same page keeps the numeric `framingZoom` control and camera-term
prompt mapping over `25..85`, while a deterministic viewport owns the final
crop. Mio's committed sprites are authored upper-body at baseline `70`, so
looser values make that source smaller but correctly do not claim to reveal
unauthored full-body pixels.

The browser showcase is implemented; the provider-backed `dialogue-scene`
headless recipe remains planned. Its asset direction now pairs one appearance
concept with a finite expression-variant set while background generation,
choices, rigging, lip sync, and motion stay outside the committed slice. The
boundaries are recorded in the
[asset contract](docs/spec/dialogue-scene-assets.md),
[preview contract](docs/dialogue-scene-preview.md),
[framing control](docs/dialogue-scene-framing.md), and
[deferred animation notes](docs/dialogue-scene-animation.md).

## Architecture

Python under `src/stage_gen/` is the sole headless implementation. Node and
TypeScript are confined to `web/`.

```text
src/stage_gen/
  contracts/           typed artifact and provenance contracts
  components/          provider-neutral image, structured, removal, music,
                       and endpoint-conditioned loop-synthesis operations
  providers/           OpenRouter and FAL HTTP adapters
  media/               deterministic image/audio inspection and normalization
  reliability/         retries, cancellation, redaction, paths, and persistence
  recipes/             application compositions and exported manifests
  orchestration/       run preparation, concrete composition, and run.json
  interfaces/          CLI and optional HTTP/SSE API
  benchmarks/          credential-free and opt-in evaluation suites
  resources/           wheel-packaged templates and approved fallback music
web/                    optional browser preview consumer
```

Dependencies point inward: providers implement component protocols, recipes
compose components, and `orchestration.runtime` joins concrete providers to
recipes for the interfaces. Components and recipes do not import providers or
the web preview. The Python loop-synthesis service defines endpoint-conditioned
masked-bridge generation and seam validation, but its recipe activation is
deferred until a configured provider adapter supports the exact masked-edit
contract.

See [Architecture](ARCHITECTURE.md), the
[system overview](docs/spec/system-overview.md), and the
[component contract](docs/component-contract.md).

## Optional web preview

Web development and deterministic gameplay automation require Bun 1.3.3 (the
version pinned by `web/package.json`). Install the locked dependencies and the
matching Playwright Chromium browser once:

```sh
cd web
bun install --frozen-lockfile
bunx playwright install chromium
bun run dev
```

`ffmpeg` and `ffprobe` must be on `PATH` for gameplay recording and generated
music normalization/inspection. Verify the optional adapter with:

```sh
cd web
bun run check
bun test
bun run build
bun run gameplay:verify
```

`gameplay:verify` runs the current 900-frame fixed-step transcript twice and
requires identical selected-frame hashes. It validates the current demo; the
historical capture's immutable evidence remains in its adjacent sidecars.

Create a reusable 30-second local report with:

```sh
cd web
bun run gameplay:record
```

The default writes `gameplay-report.mp4`, `gameplay-report.poster.png`, and
`gameplay-report.recording.json` under the ignored `output/playwright/`
directory. Reports bind fixture, timeline, source, transcript, checkpoint, and
media-probe hashes and remain `unreviewed` until independently reviewed.
Run `bun run gameplay:record -- --help` for custom-source, output, and dry-run
options.

The web server launches `uv run stage-gen generate ...` from the repository
root with an argument array and no shell. Browser code receives manifests,
progress, and confined artifacts—not provider credentials.

## Configuration and providers

`.env.example` is the configuration reference. The Python application imports
only `OPENROUTER_API_KEY` and `FAL_KEY` from a root `.env`; existing process
environment values take precedence. Endpoints, model overrides, output paths,
timeouts, force mode, transparency mode, and the optional web executable are
read from the process environment.

- OpenRouter backs image, structured, and experimental music generation.
- FAL backs the default recipe `ai` transparency mode and the standalone
  `remove-background` capability.
- `chroma` is an explicit degraded local-keying fallback, never an automatic
  replacement for failed AI removal.
- Music generation remains experimental until its current provider envelope
  passes the documented key-backed contract smoke.

Provider and model contracts can change independently of this repository.
Review [Provider operations](docs/providers.md) before changing an adapter.

The optional API is loopback-only unless public binding is explicitly
authorized:

```sh
uv run stage-gen serve --host 127.0.0.1 --port 4317
```

## Reliability and provenance

Every provider operation has one initial attempt plus at most five retries
with capped backoff. Network failures and silent contract failures—including
empty media, malformed JSON, schema mismatch, invalid base64, unsupported
media, and failed caller validation—remain inside that single retry owner.

An artifact succeeds only after contract validation and rollback-safe
artifact-plus-sidecar persistence. Provenance records provider/model identity,
sanitized prompts and parameters, input hashes, attempts, validation,
tool/component identity, deterministic post-processing, output digests, and any
explicit rights decision. It never persists credentials, authorization headers,
signed URLs, temporary paths, or embedded media. Provenance supports
reproducibility; it is not a redistribution grant.

## Testing

Run the locked credential-free Python handoff gate:

```sh
uv run python scripts/check.py
```

It **checks** formatting, runs lint and strict typing, executes all non-live
tests, builds the sdist and wheel, verifies packaged resources, and exercises
CLI smoke commands. It does not rewrite source formatting.

Provider-backed tests require explicit opt-in. Confirm that live tests remain
safely skipped with:

```sh
STAGE_GEN_RUN_LIVE=0 uv run pytest -m live -q
```

Focused commands and the intentional `STAGE_GEN_RUN_LIVE=1` workflow are in
[Testing](docs/testing.md). Generated visual output still requires independent
review by an agent other than its producer.

## Documentation and publication policy

- [Documentation index](docs/README.md)
- [Asset contracts](docs/spec/asset-contracts.md)
- [Endpoint-conditioned loop synthesis](docs/loop-synthesis.md)
- [Scene-layer contract](docs/scene-layers.md)
- [Verification rules](VERIFICATION.md)
- [Generated-media publication](docs/generated-media-publication.md)
- [Repository storage policy](docs/repository-storage.md)
- [OSS and IP policy](docs/oss-ip.md)

Prompts, fixtures, examples, and committed outputs must use original,
brand-neutral briefs. BSD-3-Clause covers repository source; it does not
automatically license generated artifacts, user inputs, provider outputs,
models, or third-party services.

## License

Source code is available under the [BSD 3-Clause License](LICENSE).
