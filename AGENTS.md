# AGENTS.md

Repository-specific guardrails. [README.md](README.md) owns setup, [ARCHITECTURE.md](ARCHITECTURE.md) boundaries,
[CONTRIBUTING.md](CONTRIBUTING.md) contribution policy, and [VERIFICATION.md](VERIFICATION.md) gates. Focused procedures
live in [providers](docs/models/providers.md), [publication](docs/generated-media-publication.md), [storage](docs/repository-storage.md),
and [IP](docs/oss-ip.md). This file controls applicability; focused docs control procedure and must be reconciled on conflict.

## Architecture

- Keep identifiers, comments, logs, tests, and user-facing source strings in English.
- Python is the headless implementation. The public product has two layers: `src/gnode/` is the ringed asset-graph
  SDK and `src/stage_gen/` is the application that consumes it. gnode's rings (`docs/spec/gnode-rings.md`):
  ring 0 the agnostic engine core (topology, scheduling, trace, run view, model bindings, reliability,
  provenance — media-free), ring 1 per-modality model specs and retry-owning services, ring 2 first-party
  provider adapters. A ring imports only rings below it; nothing game-, recipe-, or genre-specific belongs
  in any ring, and the engine ships no brand — provenance identities come from the application. Consumers
  import only declared surfaces (`from gnode import X`; provider adapters via `gnode.providers.<name>`);
  gnode imports no application package; a contract test enforces all of it. Providers
  implement the ring-1 protocols, and orchestration is the composition root. Shared recipe-neutral media
  inspection and transforms belong in `media`; capability-specific processing stays with its component, and
  recipe-specific canonicalization with its recipe.
- The product owns asset-pipeline authoring, execution, artifacts and inspection. Components own bounded capabilities;
  recipes compose useful asset outcomes. Their inputs never require a complete game, selected demo or gameplay schema.
  Consumer adapters own runtime camera, scene, engine and gameplay assumptions. `web/` consumes public run/artifact
  contracts and is not a second generator. Bounded animation, terrain, spatial and scenario contracts may remain optional.
- Complete game builders, canonical game schemas and their existing input/readers belong to Godot legacy ownership.
  Preserve old formats and supported reader/input pairs; do not rewrite all legacy TOML as a migration prerequisite.
  Legacy code may import the public asset product; public components and pipeline code must not import legacy code.
- Each supported asset recipe/example owns its graph documentation and executable contract. Changes to its stages,
  asset dependencies, consumed inputs, operation counts or cache/scheduling semantics update that evidence together.
  Historical whole-game graph specifications apply only to their legacy consumers, not every future asset pipeline.

## Schema naming

- Schema definitions and persisted/public contract fields use `lower_snake_case`; do not add camelCase aliases for
  convenience. Translate to language-native runtime shapes only at explicit adapters or boundaries. Preserve mandatory
  external-standard vocabulary exactly, including JSON Schema `$ref`, `$defs`, and `additionalProperties`.

## Provider and artifact safety

- Provider routes are declared in a `gnode` binding table as `model@provider` with the features each route supports;
  a missing feature is refused while planning, offline, before any spend. Do not name a model inside a node's logic.
- Each AI/provider operation has one retry owner and at most six attempts: one initial plus five retries with capped
  backoff. Keep transport, decoding, schema/media checks, and caller validation inside it; disable nested retry loops.
- Mark artifacts successful only after validation and rollback-safe atomic artifact-plus-sidecar persistence. Cache
  reuse must validate content and lineage, not merely path existence.
- Use the existing allowlisted provider-key loader. Treat `.env` as optional and local; never assume it is populated,
  overwrite, print, or commit it, or copy provider secrets into `web/`. `.env.example` owns non-secret defaults.
- Offline operation is the default. Live/provider calls require explicit task intent and documented opt-in. Re-check current provider contracts before changing adapters or model identifiers.
- Pipeline run artifacts require canonical portable provenance, because the manifest, cache, and consumers read it.
  A figure or capture authored for the docs is not a pipeline artifact and gets none. Never persist credentials,
  authorization headers, signed URLs, embedded references, private absolute or temporary paths. Confine writes and
  reject traversal or symlink escapes.

## Media and rights

- Use canonical fixtures in place. Copy only across a real package, build, deployment, or public-consumer ownership
  boundary; preserve provenance and rights, do not symlink across it, and never promote unreviewed output into fixtures.
- Prompts, examples, fixtures, and committed media must be original and brand-neutral. Referenced inputs need a
  documented rights basis; source licensing does not grant media redistribution.
- Accepted generated visuals require semantic review by someone other than their producer. Reference inspection and
  exploration do not; label exploration unreviewed. Audio quality claims need a separate listening verdict.
  Semantic regeneration runs are not provider retries.
- Generated media published as art is unapproved by default. Follow publication and storage gates before commit or
  publication; public binding, activation, or publication requires explicit authorization. The gate covers the declared
  publication roots only; `docs/media` and `docs/diagrams` are documentation and carry no sidecar or inventory entry.

## Verification

- Run focused checks for each changed boundary. For Python handoff run credential-free `uv run python scripts/check.py`;
  follow `VERIFICATION.md` for docs and web gates. Offline gates remain provider-free; live and semantic gates stay scoped.
