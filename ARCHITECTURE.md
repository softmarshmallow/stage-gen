# Architecture

`stage-gen` is a headless, general-purpose system for producing coherent 2D
game assets. The reusable core stops at validated artifacts, manifests, and
provenance. A preview or game runtime is a downstream consumer, never the
definition of the generator.

## Repository boundaries

```text
src/stage_gen/components/     provider-neutral services and capability processing
src/stage_gen/providers/      OpenRouter and fal adapters
src/stage_gen/media/          shared recipe-neutral inspection and transforms
src/stage_gen/recipes/        recipe-specific composition, processing, and manifests
src/stage_gen/orchestration/  run preparation, concrete composition, and summaries
src/stage_gen/interfaces/     argparse CLI and optional HTTP/SSE API
src/stage_gen/benchmarks/     headless evaluation entrypoints
src/stage_gen/resources/      wheel-packaged recipe resources
library/characters/           source-checkout or external authored profile workspace
web/                          optional browser preview adapter
docs/                         contracts, operations, research, and policy
```

Arrows below point from an importer to the layer it imports:

```text
interfaces    --imports----------> orchestration
orchestration --imports/composes-> recipes   --imports----------> components
orchestration --imports/composes-> providers --implements-------> components
components    --imports----------> contracts + reliability + media
```

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

Visual Content Direction is an optional `scrolling-preview` recipe stage,
implemented by the v1 `theme-compile` node. It uses the provider-neutral
structured-generation component to compile strict numeric content controls and
a base brief into a recipe-specific seven-field prose plan before deterministic
recipe composition. It is not itself a reusable component or standalone image
pipeline. Raw controls do not cross the image boundary. The packaged policy
digest, compiler version, and normalized control digest bind provenance and
downstream cache identity; see
[Visual Content Direction](docs/visual-content-direction.md).

## Headless path

The supported entry point is:

```sh
uv run stage-gen <args>
```

The CLI is the primary automation surface. The HTTP service exposes the same
headless capabilities for local tools. Benchmarks and research cases live
under `src/stage_gen/benchmarks/`; they test declared component contracts
without depending on a browser scene.

Generated runs live below the configured output directory. Recipe-specific
names and file layouts belong in recipe manifests, not in generic
orchestration. Shared, capability-specific, and recipe-specific deterministic
processing stays at its owning boundary, remains independently testable, and
is recorded in provenance.

Transparency is a recipe input, not a provider-global toggle. The first recipe
defaults to validated AI background removal; its explicit degraded chroma
fallback remains deterministic and local. Opaque artifacts bypass both paths.
The selected strategy and raw-to-derived lineage travel in manifests and
sidecars so consumers load canonical outputs without guessing from colour.

## Optional preview

The current `web/` application is an optional consumer with two committed
integration surfaces. The side-view scrolling preview may launch the public
headless command and read completed run manifests; its horizontal camera,
parallax, terrain, movement, combat, and interaction rules are local consumer
decisions. The deterministic dialogue-scene showcase consumes a committed
browser fixture and schema backed optionally by installed output from the
provider-backed dialogue-scene recipe. Neither surface owns generation or
defines reusable component contracts.

No production gameplay engine has been selected. A dedicated 2D engine,
including Godot or another suitable candidate, may be evaluated later. The
choice is deliberately deferred and must not force changes to provider
adapters, artifact schemas, or component boundaries.

The Python package is the sole headless implementation. Node and TypeScript are
confined to the optional `web/` adapter, which launches the public Python CLI.

## Storage and redistribution

Generated output, populated environment files, caches, and local verification
captures are ignored. Only small intentional fixtures with a documented
rights basis belong in version control. Generated music replaces the removed
legacy recording library; no third-party recording is retained as a fallback.
See [Repository storage policy](docs/repository-storage.md) and
[OSS and IP policy](docs/oss-ip.md).
