# Architecture

`stage-gen` is a headless, general-purpose system for producing coherent game
assets — 2D today, with 3D as a deferred axis the
[asset taxonomy](docs/spec/asset-taxonomy.md) reserves a name for. The
reusable core stops at validated artifacts, manifests, and provenance. A
preview or game runtime is a downstream consumer, never the definition of the
generator.

It is built on `gnode`, an **asset graph** SDK: a build system for generative
assets whose contracts must be met. Nodes produce persistent, content-addressed
artifacts validated before they are accepted; correctness does not depend on
execution order; a failed provider operation is retried by exactly one owner and
never by the scheduler. `gnode` grows in rings ([gnode rings](docs/spec/gnode-rings.md)):
a media-free engine core, per-modality model specs and services above it, and
first-party provider adapters above those. A ring imports only rings below it,
and nothing game-, recipe-, or genre-specific belongs in any ring — `stage-gen`
is one application on top of the SDK.

## Repository boundaries

```text
src/gnode/                    ringed asset-graph SDK — ring 0: engine core
                              (topology, scheduling, trace, run view, model
                              bindings, reliability, provenance; media-free);
                              ring 1 gnode/modalities/: per-modality model
                              specs and retry-owning services, including the
                              bounded tool-loop agent; ring 2
                              gnode/providers/: OpenAI, OpenRouter, and fal
                              adapters behind declared per-provider surfaces
src/stage_gen/components/     application components and capability processing
src/stage_gen/providers/      adapters for application-owned component
                              protocols (the masked image-repeat edit)
src/stage_gen/media/          shared recipe-neutral inspection and transforms
src/stage_gen/recipes/        recipe-specific composition, processing, and manifests
src/stage_gen/orchestration/  run preparation, concrete composition, and summaries
src/stage_gen/interfaces/     argparse CLI, the only automation surface
src/stage_gen/resources/      wheel-packaged recipe resources
library/games/                source-checkout or external authored package workspace
web/                          optional browser preview adapter
docs/                         contracts, operations, research, and policy
```

Arrows below point from an importer to the layer it imports:

```text
interfaces    --imports----------> orchestration
orchestration --imports/composes-> recipes   --imports----------> components
orchestration --imports/composes-> providers --implements-------> gnode ring-1 model specs
components    --imports----------> media
everything in stage_gen -------->  gnode (declared surfaces only)
gnode         --imports----------> nothing in stage_gen; ring N only rings < N
```

The last two lines are the engine boundary, and they are enforced mechanically
by `tests/contract/test_import_boundaries.py` in both directions. One import
surface keeps the engine free to move its modules; importing no application
keeps it usable without one.

Optional consumers invoke an interface through its CLI or HTTP contract; they
are not imported by the Python package.

Components do not import recipes or `web/`. They accept explicit typed inputs,
validate outputs, and expose provider-neutral artifact information. Shared,
recipe-neutral media inspection and transforms live in `media/`; deterministic
processing specific to a capability stays with its component contract, and
recipe-specific canonicalization stays with its recipe.

Recipes may add generation-specific genre, composition, projection, framing,
sheet-layout, artifact, and validation constraints. Consumers may translate a
completed manifest into an engine's textures or import settings, and they own
runtime camera, scene, engine, movement, combat, and gameplay rules.

Provider routes are declared, not scattered. A `gnode` binding table names each
route as `model@provider` — `gpt-image-2@openai`, `openai/gpt-image-2@openrouter`
— with the features that route is known to support and the date the claim was
last verified. A node type asks for a capability plus features; a route that does
not declare one is refused while planning, offline, before any spend. The two
halves are persisted as separate `provider` and `model` fields, so the combined
form is a configuration surface and never an identity.

`stage_gen.orchestration.runtime` is the application composition root. It may
import both provider-neutral component services and concrete providers; those
layers do not import it. An AST contract test enforces that reusable components
never import providers, recipes, orchestration, interfaces, or `web/`.

## Operational capabilities

The initial hosted adapters use OpenRouter for structured text/vision, image
generation, and experimental music generation, and fal for background
removal. Exact model identifiers, request envelopes, environment variables,
and verification status are documented in [Provider operations](docs/providers.md).
Those names are operational configuration, not architectural dependencies:
recipes consume capability interfaces and provenance records rather than raw
provider response types.

Every AI operation has one retry owner. Transport failures and silent contract
failures—empty media, malformed JSON, schema mismatch, invalid containers, or
failed caller validation—remain inside that boundary. Successful artifacts
must be committed with their provenance and integrity metadata; credentials,
authorization headers, signed query strings, and embedded reference bytes are
never persisted.

## Headless path

The supported entry point is:

```sh
uv run stage-gen <args>
```

The CLI is the only automation surface: there is no HTTP service, and no
process outside it starts a run. Five recipes compile onto the one engine —
`sideview-platformer` and `sideview-runner` build distinct prepared-game
members from a `game.toml` package, `dialogue-scene` builds a scene bundle from
an authored request document, and `pointclick-room` builds a fixed painted
puzzle room from an authored package whose puzzle is proven finishable before generation is scheduled
(`stage-gen pointclick-room generate --input library/games/<id>
--output out/<tag>`), and `universe` builds an explorable storyworld package —
typed entities and one concept image each — from a poster, a synopsis, and an
expansion direction. Each declares its own graph document kind, so no recipe
can read another's plan.

Generated runs live below the configured output directory. Recipe-specific
names and file layouts belong in recipe manifests, not in generic
orchestration. Shared, capability-specific, and recipe-specific deterministic
processing stays at its owning boundary, remains independently testable, and
is recorded in provenance.

Transparency is a recipe input, not a provider-global toggle. Native
provider alpha is the default; validated AI background removal and an explicit
degraded chroma fallback remain available, the latter deterministic and local. Opaque artifacts bypass both paths.
The selected strategy and raw-to-derived lineage travel in manifests and
sidecars so consumers load canonical outputs without guessing from colour.

## Optional preview

The current `web/` application is an optional consumer with six committed
integration surfaces, none of which can start a run. The side-view platformer
preview boots one published `prepared-game-runtime-v11` package; its horizontal
camera, parallax, terrain, movement, combat, and interaction rules are local
consumer decisions. The runner at `/runner/<tag>` plays one published
`sideview-runner-runtime-v13` run with its own fixed-step simulation. The asset
explorer projects the platformer manifest's closure. The deterministic
dialogue-scene showcase consumes a committed browser fixture and schema. The
room player at `/room/<tag>` replays one published `pointclick-room-runtime-v3`
manifest through a pure reducer. The run viewer consumes a run's derived
`execution-view.json` and renders it read-only. No surface owns generation or
defines reusable component contracts.

No production gameplay engine has been selected. A dedicated 2D engine,
including Godot or another suitable candidate, may be evaluated later. The
choice is deliberately deferred and must not force changes to provider
adapters, artifact schemas, or component boundaries.

The Python packages are the sole headless implementation. Node and TypeScript are
confined to the optional `web/` adapter, which launches the public Python CLI.

## Storage and redistribution

Generated output, populated environment files, caches, and local verification
captures are ignored. Only small intentional fixtures with a documented
rights basis belong in version control. Generated music replaces the removed
legacy recording library; no third-party recording is retained as a fallback.
See [Repository storage policy](docs/repository-storage.md) and
[OSS and IP policy](docs/oss-ip.md).
