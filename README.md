# stage-gen

`stage-gen` is a general-purpose, headless pipeline and component library for generating
coherent 2D game assets. It turns typed inputs, prompts, and optional visual
references into validated artifacts with reproducibility metadata.

The project is not a game engine and it is not defined by one genre, camera,
or control scheme. Individual recipes may request side-view scenery, top-down
props, interface elements, animation sheets, music, or other asset families;
the reusable components remain independent of those product choices.

The first demonstrated consumer is an optional web-based scrolling-game
preview. It exists to exercise generated assets end to end. Its camera,
terrain, movement, combat, and scene-composition assumptions are adapter
concerns, not core generation contracts.

## Repository shape

```text
README.md        public entry point
docs/            architecture, provider, policy, and recipe documentation
components/      reusable generation and post-processing modules
stage-gen/       headless CLI/server plus benchmark and research entrypoints
web/             optional scrolling-preview adapter
```

Each component should have typed inputs and outputs, validate its returned
media, use the shared retry policy, and emit provenance beside its artifacts.
Pipelines compose components; preview or engine integrations consume pipeline
outputs. Components must not import from `web/` or encode a particular camera,
genre, gameplay loop, or engine.

## Setup

Prerequisites are Bun and provider credentials for the stages you intend to
run. Copy the public template and fill values locally:

```sh
cp .env.example .env
bun install
bun run stage-gen -- doctor
bun run stage-gen -- recipes
bun run stage-gen -- --help
```

The operational credentials are:

- `OPENROUTER_API_KEY` for image, text/vision, and experimental music calls.
- `FAL_KEY` for the default AI background-removal strategy. It is not
  required when a recipe is explicitly run with the degraded `chroma`
  fallback.

Never commit or print `.env`. A workspace that needs its own env file receives
a copy, not a symlink.

## Provider-backed stages

| Capability | Operational route | Status |
|---|---|---|
| Image generation/editing | OpenRouter image API with `openai/gpt-image-2` | Model identity and image endpoint verified |
| Background removal | fal endpoint `fal-ai/birefnet/v2` | Request and response contract verified |
| Music generation | OpenRouter with `google/lyria-3-pro-preview` | Experimental until a key-backed response-envelope smoke test passes |

### Transparency strategy

Transparency-producing assets default to `ai`. The image prompt requests a
neutral grey or naturally isolated background, then the background-removal
component produces and validates the canonical transparent PNG. Fully opaque
assets, including the world concept and designated opaque backdrop, bypass
removal and are unchanged.

`chroma` is an explicit degraded fallback. It requests exact `#FF00FF` and
uses deterministic local keying without calling the remover. The pipeline
never switches to `chroma` automatically: an `ai` run without `FAL_KEY`, or
with failed removal/validation, fails closed.

```sh
# Default; equivalent to --transparency ai and requires FAL_KEY.
bun run stage-gen -- generate --recipe scrolling-preview "original rain-dark stone ruins with pale moss"

# Explicit degraded fallback; does not require FAL_KEY.
bun run stage-gen -- generate --recipe scrolling-preview --transparency chroma "original rain-dark stone ruins with pale moss"
```

The local HTTP run input uses `transparencyMode: "ai" | "chroma"`. Run
manifests and provenance record the selected strategy so consumers never infer
it from filenames or prompts.

The music model and its audio modality are discoverable through OpenRouter,
but a Lyria-specific response envelope is not currently documented there.
The adapter must inspect and validate live returned media rather than assume a
speech-oriented audio shape, fixed sample rate, or duration field.

See [Provider operations](docs/providers.md) for exact request constraints,
verified claims, and primary sources.

## Reliability and provenance

Every network/model call uses five blind retries with capped backoff. A call is
also retried when the transport succeeds but its contract does not: empty
media, malformed JSON, schema failure, unsupported MIME type, or invalid
dimensions are failures.

Each artifact must have a sidecar or manifest entry containing at least:

- component and pipeline versions;
- provider and exact model/endpoint identifier;
- prompt plus non-secret request parameters;
- input/reference paths and content hashes;
- output MIME type, byte size, dimensions or media duration when known;
- attempt count, timestamp, and output hash;
- deterministic post-processing steps.

Provenance makes a run auditable and repeatable. It does not grant copyright,
trademark, publicity, or training-data rights.

## Headless and research first

The supported public entry point is:

```sh
bun run stage-gen -- <args>
```

Use `--help` as the source of truth for available pipelines and benchmark
commands. Research runs should preserve raw provider metadata, normalized
artifacts, provenance, validation results, timings, and failures. Do not tune a
component only against the optional web preview; benchmark its declared media
contract independently.

The initial recipe and offline benchmark can be invoked directly. Generation
defaults to `--transparency ai`:

```sh
bun run stage-gen -- generate --recipe scrolling-preview "original rain-dark stone ruins with pale moss"
bun run stage-gen -- benchmark smoke
```

Provider-backed media components also have headless entrypoints:

```sh
bun run stage-gen -- remove-background --input ./input.png --output ./out/subject.png
bun run stage-gen -- generate-music --output ./out/theme.mp3 --format mp3 "original instrumental exploration loop with a gentle pulse"
```

See [Benchmarking and research](docs/benchmarking.md).

## Optional web preview

The `web/` workspace is a development adapter for one scrolling-world recipe.
It launches the public headless command, visualizes run progress and artifacts,
and can mount them in a browser scene.

```sh
bun run web
```

The preview is deliberately replaceable. A production game may consume the
same exported assets from any suitable engine or custom runtime.

## Game-engine status

No gameplay engine has been selected. A dedicated 2D engine, including Godot,
may be evaluated alongside other candidates, but the decision remains open.
Provider adapters, components, manifests, and asset contracts must not depend
on that future choice. See [Game-engine evaluation](docs/game-engine-evaluation.md).

## OSS and IP rules

Repository prompts, fixtures, examples, and generated placeholders must use an
original, neutral brief. Do not request or imply imitation of a named
franchise, brand, character, artist, studio, game, album, track, or a living
creator's recognizable style. Contributors must have rights to every supplied
reference and every committed media file.

The BSD-3-Clause license covers repository source. It does not automatically
license generated artifacts, user inputs, model weights, hosted outputs, or
third-party services. Review provider terms and applicable law before shipping
generated media. See [OSS and IP policy](docs/oss-ip.md) and
[CONTRIBUTING.md](CONTRIBUTING.md).

## Repository storage policy

Git LFS is not enabled. After the legacy audio purge, tracked binaries total
about 15.7 MiB and the largest is about 1.73 MiB, so LFS would add contributor
friction without useful savings. Reconsider when one intentionally tracked
binary reaches 10 MiB or a frequently revised binary family is projected to
add 50 MiB of reachable history. Generated run output stays gitignored.

## Documentation

- [Documentation index](docs/README.md)
- [System overview](docs/spec/system-overview.md)
- [Provider operations](docs/providers.md)
- [Component contract](docs/component-contract.md)
- [Benchmarking and research](docs/benchmarking.md)
- [OSS and IP policy](docs/oss-ip.md)
- [Repository storage policy](docs/repository-storage.md)
- [Scrolling-preview recipe contracts](docs/spec/asset-contracts.md)

## License

Source code is available under the [BSD 3-Clause License](LICENSE).
