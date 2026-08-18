# stage-gen

`stage-gen` is a general-purpose headless Python pipeline and component library
for generating coherent 2D game assets. Typed inputs and optional visual
references become validated artifacts with adjacent, content-bound provenance.

The Python package is the authoritative backend. It is not a game engine and
does not assume a genre, camera, movement model, or runtime. The optional
Next.js/React/Phaser application consumes one scrolling-preview recipe without
moving gameplay assumptions into reusable components.
It is an optional web-based scrolling-game preview, not the product boundary.

## Showcase

[![Poster for the deterministic real gameplay showcase](docs/media/gameplay-showcase.poster.png)](docs/media/gameplay-showcase.mp4)

The poster links to a deterministic 30-second real-gameplay capture rendered
with the historical set of 18 independently approved image-model-generated
assets. The current live demo fixture has 20 approved assets; the ladder and
back-facing climb strip were added after this published capture. Transparent
assets bind their documented extraction lineage in producer provenance. Verify
the fixed-step transcript and selected canvas hashes locally with:

```sh
cd web
bun run check
bun run build
bun run gameplay:verify
```

Create a reusable local gameplay report with the model-demo preset:

```sh
cd web
bun run gameplay:record
```

The default writes `gameplay-report.mp4`, `gameplay-report.poster.png`, and
`gameplay-report.recording.json` below the repository's ignored
`output/playwright/` directory. The metadata binds the capture to its fixture,
timeline, source hashes, deterministic transcript, checkpoints, and media
probe; a new report remains `unreviewed` until it receives an independent
visual review. Choose another confined MP4 name with, for example,
`--output output/playwright/vertical-demo.mp4`.

`--dry-run` validates command-line shape and prints the resolved artifact,
simulation, and media plan without reading fixture contents, starting a
browser, encoding video, or writing report artifacts:

```sh
bun run gameplay:record --dry-run \
  --output output/playwright/vertical-demo.mp4
```

The default source is `--preset model-demo`. A custom report instead requires
all three source flags; partial custom input and mixing it with a preset are
rejected:

```sh
bun run gameplay:record \
  --fixture out/<tag> \
  --tag <tag> \
  --timeline path/to/timeline.json \
  --output output/playwright/custom-demo.mp4
```

The fixture must be the matching real `out/<tag>` directory, and the timeline
must be schema version 1 with exactly `duration × 30` contiguous fixed-step
frames. Recording snapshots the fixture, timeline, and relevant source files
before capture and refuses to install outputs if any change during the run.
Duplicate deterministic verification is on by default; the explicit
`--no-verify-twice` option disables that second simulation.

## Topology

```text
src/stage_gen/
  components/          provider-neutral image, structured, removal, and music operations
  providers/           OpenRouter and fal HTTP adapters
  media/               deterministic image/audio inspection and normalization
  reliability/         retry, cancellation, redaction, safe paths, and atomic persistence
  recipes/             application compositions; scrolling-preview is the reference recipe
  orchestration/       run preparation, concrete provider composition, summaries, and run.json
  interfaces/          argparse CLI and optional FastAPI-compatible HTTP/SSE app
  benchmarks/          credential-free and opt-in evaluation suites
  resources/           wheel-packaged layout fixtures and approved fallback music
tests/                  unit, integration, contract, and opt-in live tests
scripts/check.py        locked credential-free Python gate
web/                    optional server-side launcher and browser preview adapter
docs/                   architecture, provider, policy, recipe, and testing documentation
```

Dependencies point inward: providers implement component protocols, recipes
compose components, and `orchestration.runtime` is the application composition
root that joins both concrete sides for interfaces. Neither reusable components
nor recipes import providers or the web preview.

## Install

Requirements:

- Python 3.12;
- [uv](https://docs.astral.sh/uv/);
- `ffmpeg` and `ffprobe` for generated-music normalization and inspection; and
- Bun only when developing or verifying the optional web adapter.

```sh
uv sync --all-extras
cp .env.example .env
uv run stage-gen --help
uv run stage-gen doctor --json
uv run stage-gen recipes
```

The package can also be built and installed as a wheel. Required recipe
templates and the approved fallback-music artifact, sidecar, and notice ship
inside `stage_gen.resources`; an installed wheel does not depend on checkout
paths.

## Configuration

`.env.example` documents the supported names. Never commit, print, forward, or
copy populated values into logs or provenance.

The Python application automatically reads only `OPENROUTER_API_KEY` and
`FAL_KEY` from `.env` in the current working directory. Existing process
environment values take precedence. All endpoint, model, runtime, and web
settings must be supplied through the process environment; arbitrary `.env`
entries are intentionally ignored.

- Credentials: `OPENROUTER_API_KEY`, `FAL_KEY`.
- Optional provider endpoints: `OPENROUTER_BASE_URL`, `FAL_BASE_URL`.
- Model selection: `STAGE_GEN_IMAGE_MODEL`, `STAGE_GEN_TEXT_MODEL`,
  `STAGE_GEN_MUSIC_MODEL`, `STAGE_GEN_BACKGROUND_REMOVAL_MODEL` (legacy
  unprefixed model names remain accepted during migration).
- Runtime: `STAGE_GEN_OUT_DIR`, `STAGE_GEN_STAGE_TIMEOUT_MS`,
  `STAGE_GEN_CAPABILITY_TIMEOUT_MS`, `STAGE_GEN_FORCE`, `TRANSPARENCY_MODE`.
- Optional web launcher: `STAGE_GEN_EXECUTABLE`.

OpenRouter is required for image, structured, and music generation. `FAL_KEY`
is required only for the default `ai` transparency mode. The explicit degraded
`chroma` mode performs deterministic local keying and never silently replaces a
failed AI-removal request.
`FAL_KEY` is not required for an explicit chroma run.

## Quickstart

Run the credential-free smoke benchmark:

```sh
uv run stage-gen benchmark list
uv run stage-gen benchmark smoke
```

Generate the reference recipe. The output directory is
`out/<prompt-tag>-<mode>/` unless configured otherwise.
The default is `--transparency ai`; select chroma explicitly when required.

```sh
# Default AI removal; requires OPENROUTER_API_KEY and FAL_KEY.
uv run stage-gen generate --recipe scrolling-preview \
  "original rain-dark stone ruins with pale moss"

# Explicit degraded fallback; requires OPENROUTER_API_KEY only.
uv run stage-gen generate --recipe scrolling-preview --transparency chroma \
  "original rain-dark stone ruins with pale moss"
```

A bare prompt remains a compatibility alias for `generate --recipe
scrolling-preview`. Every run writes an atomic `run.json`; successful scrolling
runs also write manifest schema v2. Transparency mode is part of the tag, cache
identity, provenance, and manifest.

Standalone capability commands use the same component services:

```sh
uv run stage-gen generate-image --output ./out/concept.png "original forest shrine"
uv run stage-gen remove-background --input ./input.png --output ./out/subject.png
uv run stage-gen generate-music --output ./out/theme.mp3 --format mp3 \
  "original instrumental exploration loop with a gentle pulse"
```

The local API is loopback-only unless public binding is explicitly authorized:

```sh
uv run stage-gen serve --host 127.0.0.1 --port 4317
```

It exposes health, recipes/capabilities, run start/status/cancellation, SSE
events, confined artifact reads, and standalone image generation. Request-body,
path, and binding limits are enforced server-side.

## Reliability and provenance

Every AI/provider operation has exactly six attempts at most: one initial
attempt plus five retries with capped backoff. Network errors, timeouts, 5xx
responses, empty media, malformed JSON, schema mismatch, invalid base64,
unsupported media, and failed caller validation all remain inside that single
retry owner. Do not stack a second SDK retry loop beneath it.

Artifacts are successful only after contract validation and rollback-safe
artifact-plus-sidecar persistence. Provenance records the provider/model,
sanitized prompt and parameters, input hashes, attempts, validation, tool and
component identity, deterministic post-processing, output digest, and explicit
rights decision when one exists. Temporary paths, credentials, authorization
headers, and embedded media are not persisted.

## Testing

Run the complete credential-free gate:

```sh
uv run python scripts/check.py
```

It formats/lints, runs strict typing and all non-live tests, builds the sdist
and wheel, verifies packaged resources, and runs CLI smoke commands. Focused
module commands, opt-in live policy, web checks, and the `ffmpeg` requirement
are listed in [Testing the Python reboot](docs/testing.md).

Verify that every live smoke remains safely skipped, even if the parent shell
was previously opted in:

```sh
STAGE_GEN_RUN_LIVE=0 uv run pytest -m live -q
```

Intentional provider calls require an explicit
`STAGE_GEN_RUN_LIVE=1`; see the testing guide for the exact command.

## Optional web preview

The web workspace is a replaceable consumer, not the backend:

```sh
cd web
bun install --frozen-lockfile
bun run dev
```

Its server-only launcher invokes `uv run stage-gen generate ...` from the
repository root using an argument array with no shell. `STAGE_GEN_EXECUTABLE`
may select only `uv`, `stage-gen`, `stage-gen-py`, or a normalized absolute path
whose basename is one of those names. Prompt text never becomes a command
string. The browser receives progress, manifests, and artifacts—not provider
credentials. React/Phaser gameplay code remains an optional adapter.

## Implementation boundary

Python under `src/stage_gen/` is the sole headless implementation. Node and
TypeScript are confined to `web/`, whose server launches the public Python CLI
and whose browser code consumes completed manifests and artifacts.

## OSS and IP

Prompts, fixtures, examples, and committed outputs must use original,
brand-neutral briefs. Contributors need rights to supplied references and
committed media. BSD-3-Clause covers repository source; it does not
automatically license generated artifacts, user inputs, provider outputs,
models, or third-party services. See [OSS and IP policy](docs/oss-ip.md) and
[Generated-media publication](docs/generated-media-publication.md).

## Documentation

- [Documentation index](docs/README.md)
- [System overview](docs/spec/system-overview.md)
- [Component contract](docs/component-contract.md)
- [Provider operations](docs/providers.md)
- [Testing the Python reboot](docs/testing.md)
- [Verification rules](VERIFICATION.md)
- [Benchmarking and research](docs/benchmarking.md)
- [Optional web preview](docs/web-preview.md)
- [Scrolling-preview asset contracts](docs/spec/asset-contracts.md)
- [Game-engine evaluation](docs/game-engine-evaluation.md)

## License

Source code is available under the [BSD 3-Clause License](LICENSE).
