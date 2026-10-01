# Architecture

Stage Gen provides asset-pipeline authoring, execution and inspection. Consumers own what
those assets mean in a complete application. Dependencies point from consumers to workflows
and components, then to GNode; the product never imports its example games.

## Two products in one repository

Stage Gen is the main asset-generation product. The Godot example project is a separately
owned consumer product, demonstrating asset use in complete games and developing its own
runtime packages, templates and tools. Its continuing purpose and internal review criteria
are defined in the [Godot project charter](godot/CHARTER.md).

The Godot directory serves as engine-specific examples for Stage Gen. Internally, it can
evolve as its own project: sharing game systems, extracting packages or reviewing
visual-novel implementations does not expand the main product's scope. The asset product
remains useful without Godot. GNode and the Stage Gen application are layers of that main
product; this is distinct from the two-product ownership boundary. Co-location does not
require common game formats or synchronized releases.

## Layers

Each layer imports only the layers above it in this list.

1. **GNode** (`src/gnode/`) keeps its three rings. Ring 0 owns media-independent topology,
   scheduling, traces, run views, model binding, reliability and provenance. Ring 1 owns
   modality specifications and retry-owning services. Ring 2 owns first-party provider
   adapters. Imports point inward. GNode imports no Stage Gen package, workflow, game or
   brand. Consumers use declared public surfaces. See [ring rules](docs/spec/gnode-rings.md).
2. **SDK** (`src/stage_gen/pipeline/`): definitions, planning, execution and persisted-run
   inspection over ordinary GNode graphs, plus `GraphDocument`, the sealed-document base
   class. It supplies explicit roots, selected-node closure, input lineage, service
   injection, node admission and portable views, and reuses GNode's atomic artifact and cache
   machinery. It prescribes no workflow or game schema. See the [SDK guide](docs/sdk/guide.md).
3. **Components** (`src/stage_gen/components/`): bounded capabilities with their node types,
   graph fragments, contracts and services. A component never runs alone and never imports
   a workflow. Shared workflow-neutral media inspection and transforms belong in
   `src/stage_gen/media/`. See the [component contract](src/stage_gen/components/README.md).
4. **Workflows** (`src/stage_gen/workflows/<id>/`): the product unit. A workflow composes
   components into one named deliverable and owns its layout, generation and validation
   assumptions. Its folder holds `workflow.py` (the code facts: typed steps over the real
   node types, persisted identity, an offline sample plan and its run readers),
   `workflow.toml` (what code cannot know: title, promise, tools, output notes, try-it
   commands and pinned examples), `page.mdx`, `contract.md`, `cli.py`, `example.py` where
   it has an importer, `inputs/`, and its implementation. `_registry.py`, `_catalog.py`
   and `_checks.py` read them, and the catalog's drift check fails when code, manifest and
   prose disagree.
5. **Runs and examples.** A run is one execution folder. An example is a frozen export of
   real runs (`workflow-example-v1`), pinned by sha256 in its owner's manifest and kept in
   the local, gitignored store `out/examples/<owner>/<id>/`; `stage_gen.examples` is its
   public contract, which games use too. `library/` holds committed, approved
   character-3d examples that the catalog builds from tracked files.
6. **Surfaces.** The `stage-gen` CLI (`src/stage_gen/interfaces/`) has one verb set over
   the workflow ids. The [viewer](docs/viewer.md) (`web/viewer`, opened by `stage-gen view`)
   reads run folders. The [site](docs/site.md) (`web/site`) is built from the catalog
   export and the example store. `web/` is one Bun workspace and the only Node boundary;
   the viewer and the site share only `web/ui` and the versioned data contracts.
7. **Consumers.** The Godot example project and the optional applications under `apps/`.

Provider configuration, credentials and concrete service construction belong to the
composition root, `src/stage_gen/orchestration/`: runtime and services, the
`GraphExecutor` that graph-document workflows run on, image routing, and the provider
composition of the movie-sprite, portrait-motion and character-3d workflows. Application
provider adapters that are not GNode ring-2 adapters live in `src/stage_gen/providers/`.
Neither the SDK nor a workflow's graph builder acquires those responsibilities.

## Import rules

`tests/contract/test_import_boundaries.py` enforces these, and every scan asserts that it
matched at least one file:

- GNode imports nothing above it, and consumers import only its declared surfaces.
- Workflows never import each other. A workflow may import its own package, its own frozen
  implementation root and `stage_gen.workflows._registry`.
- Generic orchestration, the SDK and components import no workflow; the registry, catalog,
  checks and `stage_gen.examples` import no workflow either.
- Concrete providers are imported only in `orchestration` and `providers`.
- The product imports no game, and no optional consumer.

## Identity is frozen where it is persisted

Moving or renaming code must not move a cache key or a persisted identity, and
`tests/contract/test_workflow_identity.py` pins them in one machine-independent golden:

- the bytes of the movie-sprite `pipeline.py` and `authoring.py` and of every
  `components/movie_sprite` file, which are digested into the paid generate and finish keys;
- the portrait-motion implementation fingerprint, which hashes an explicit list of files;
- every member of the character-3d implementation;
- pipeline ids and cache namespaces, graph-document literals and kinds, cache record kinds,
  the node-type inventory, provenance names and the run-view schema version;
- the cache keys of plans made only from committed or constant bytes.

No digest may glob a workflow folder. A digest names its files, so adding `workflow.py`,
`cli.py`, `example.py` or prose beside an implementation never changes an identity. The
persisted strings that keep an older word (the graph-document field `recipe`, the
`*-execution-*` kinds, the pipeline ids `looping-parallax` and `movie_sprite_body_idle`) are
listed in the [glossary](docs/glossary.md) so nobody renames them.

The character-3d implementation stays at `stage_gen.recipes.character_3d`, a frozen path
beside its frozen orchestration, components, providers and resources under
`*/character_3d/`. Every character run hashes that source closure into its lineage, and any
member change needs a new paid qualification cohort, so `workflows/character_3d/` holds only
the workflow's declaration, CLI and example importer, which a run never imports.

## Bounded contracts and flexible composition

Public components include independent sound effects, speech, music, voice profiles, UI
artwork, screen artwork, effects artwork, terrain, layers, sprites and portrait motion.
Spatial generation and sprite locomotion retain their precise constraints; host combat and
physics stay out. Scenario authoring and execution belong to the Godot project,
independently of asset generation.

The looping-parallax workflow owns layer images, repeat axes, offsets and relative scroll
factors. It does not own a player, level or camera controller. Portrait motion owns its
generation, qualification and recovery process; the consuming presentation decides when
that animation plays. These contracts are not combined into a universal gameplay language.

TOML remains suitable for a workflow's asset requests. Ordinary Python is the composition
language for arbitrary graphs. GDScript and scenes compose Godot games. Do not require users
to describe general-purpose computation or gameplay as TOML.

## Consumers and optional tools

The viewer reads public graph, trace, manifest and view records, and derives a missing view
into a user cache, never into a run folder. It never starts a run or implements a game's
logic. Basic previews are generic; specialist inspectors are optional adapters over bounded
metadata. Unknown preview contracts retain readable metadata rather than disappearing.

`godot/packages/` contains independently bounded reusable runtime packages. `godot/games/`
contains playable consumers. `godot/templates/` contains starting projects whose preparation
scripts import assets explicitly. A game's configuration is local to that game. No runtime
package has to depend on all other packages.

[Scenario](godot/packages/scenario_runtime/README.md) is the Godot-owned VN-oriented
invocation framework. Its independent Python compiler and native Session executor share one
data contract. A game owns and invokes a sequence, grants installed capabilities, and
retains its world, camera, input, resource bindings and saves. Presentation mechanisms
remain in the lower `game_presentation` package. This framework imposes no game contract or
dependency on Stage Gen.

Each named game in `godot/games/` owns its authored inputs, optional Python preparation
package, Godot project, gameplay and asset bindings. Existing TOML readers remain supported
game formats; GDScript and resources can replace them when that game's needs warrant it. No
repository-wide selected game exists. A game publishes what it made as examples through
`stage_gen.examples` (`demo-games example export <game>`); output only a game can make is an
example made by that game, not a workflow, until it has product-owned inputs, a standalone
product graph and a real product run.

`godot/games/_shared/` holds private implementation with multiple game consumers: bounded
simulation and IO support, input readers and media binding helpers. Shared code imports no
named game. Cross-game CLI dispatch and fixture maintenance live under `godot/tools/`; the
optional `games` installation group supplies that tooling and the individual game
preparation packages. The public product imports none of these packages. Game formats are
documented with their owning game or shared reader, independently of the asset SDK's
authoring contract.

The current division between game-local code, private shared support and runtime packages
may change through review within the Godot project. Reuse between games alone does not make
a mechanism an asset SDK capability. Moving functionality to Stage Gen requires a separate,
game-independent asset-pipeline responsibility.

`apps/concept_studio/` is a separately installable concept-authoring application.

## Enforcing the boundary

Import tests enforce GNode rings and the absence of product-to-game dependencies. Package
tests verify installed use outside the checkout. Product verification runs without optional
consumers; the aggregate gate additionally verifies game readers, Godot, the web workspace
and applications. Each workflow's graph contract lives in its `contract.md`, and each game's
in that game's docs. There is no repository-wide canonical game graph.

Cache identity, route preflight, retry ownership, atomic persistence, provenance, path
confinement and media review rules hold through every move. See
[verification](VERIFICATION.md), decision
[0071](docs/decisions/0071-workflows-are-the-product-unit-and-the-web-splits-into-site-and-viewer.md)
and the [directory preview](docs/repository-layout.md).
