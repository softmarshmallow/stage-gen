# Architecture

`stage-gen` is a headless, general-purpose system for producing coherent 2D
game assets. The reusable core stops at validated artifacts, manifests, and
provenance. A preview or game runtime is a downstream consumer, never the
definition of the generator.

## Repository boundaries

```text
README.md        public entry point
docs/            contracts, operations, research, and policy
components/      reusable media capabilities
stage-gen/       headless CLI, HTTP service, recipes, and benchmarks
web/             optional browser preview adapter
fixtures/        small, redistributable references and neutral text cases
```

The dependency direction is one way:

```text
components <- stage-gen recipes <- optional consumers
```

Components do not import recipes or `web/`. They accept explicit typed inputs,
validate outputs, and expose provider-neutral artifact information. Recipes
may add genre, projection, camera, sheet-layout, or gameplay-oriented
constraints. Consumers may translate a completed manifest into an engine's
textures, scenes, or import settings.

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
bun run stage-gen -- <args>
```

The CLI is the primary automation surface. The HTTP service exposes the same
headless capabilities for local tools. Benchmarks and research cases also live
under `stage-gen/`; they test declared component contracts without depending
on a browser scene.

Generated runs live below the configured output directory. Recipe-specific
names and file layouts belong in recipe manifests, not in generic
orchestration. Deterministic post-processing is explicit, independently
testable, and recorded in provenance.

Transparency is a recipe input, not a provider-global toggle. The first recipe
defaults to validated AI background removal; its explicit degraded chroma
fallback remains deterministic and local. Opaque artifacts bypass both paths.
The selected strategy and raw-to-derived lineage travel in manifests and
sidecars so consumers load canonical outputs without guessing from colour.

## Optional preview

The current `web/` application is a development adapter for the first
side-view scrolling recipe. Its horizontal camera, parallax, terrain,
movement, combat, and interaction rules are local preview decisions. It may
launch the public headless command and read completed run manifests, but it
does not own generation or define reusable component contracts.

No production gameplay engine has been selected. A dedicated 2D engine,
including Godot or another suitable candidate, may be evaluated later. The
choice is deliberately deferred and must not force changes to provider
adapters, artifact schemas, or component boundaries.

## Storage and redistribution

Generated output, populated environment files, caches, and local verification
captures are ignored. Only small intentional fixtures with a documented
rights basis belong in version control. Generated music replaces the removed
legacy recording library; no third-party recording is retained as a fallback.
See [Repository storage policy](docs/repository-storage.md) and
[OSS and IP policy](docs/oss-ip.md).
