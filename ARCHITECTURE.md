# Architecture

Stage Gen provides asset-pipeline authoring, execution and inspection. Consumers own
what those assets mean in a complete application. Dependencies point from consumers
to recipes and components, then to GNode; the product never imports its demos.

## GNode: execution and model capabilities

`src/gnode/` retains its three rings. Ring 0 owns media-independent topology,
scheduling, traces, run views, model binding, reliability and provenance. Ring 1 owns
modality specifications and retry-owning services. Ring 2 owns provider adapters.
Imports point inward. GNode imports no Stage Gen package, recipe, game or brand.
Consumers use declared public surfaces. See [ring rules](docs/spec/gnode-rings.md).

## Public asset harness

`src/stage_gen/pipeline/` exposes definitions, planning, execution and persisted-run
inspection. A definition composes an ordinary GNode graph and binds node handlers.
The harness reuses GNode scheduling and the proven atomic artifact/cache machinery.
It supplies explicit roots, selected-node closure, input lineage, service injection,
node admission and portable views. It does not prescribe a recipe or game schema.

Nodes describe a capability with explicit inputs and outputs. Components group
capability-specific models, processing and graph builders. Recipes compose these
into a bounded result and own their layout, generation and validation assumptions.
A recipe is not required to subclass a fixed game executor. Historical executor
adapters remain for existing recipes while new definitions use the public harness.

Shared media inspection and transforms belong in `media`. Provider configuration,
credentials and concrete service construction belong in `orchestration`; the
harness and recipe graph builders do not acquire those responsibilities. CLI
adapters in `interfaces` load only the selected workflow.

## Bounded contracts and flexible composition

Public components include independent sound effects, speech, music, voice profiles,
UI artwork, screen artwork, effects artwork, terrain, layers, sprites, portrait
motion and scenarios. A scenario program can declare narrative events without
prescribing a game's world or state machine. Spatial generation and sprite
locomotion may retain their precise constraints; host combat and physics stay out.

A parallax recipe may own layer images, repeat axes, offsets and relative scroll
factors. It does not own a player, level or camera controller. Portrait motion owns
its generation, qualification and recovery process under its recipe; the consuming
presentation decides when that animation plays. These contracts are not combined
into a universal gameplay language.

TOML remains suitable for a recipe's asset requests. Ordinary Python is the
composition language for arbitrary graphs. GDScript and scenes compose Godot games.
Do not require users to describe general-purpose computation or gameplay as TOML.

## Consumers and optional tools

`web/` reads public graph, trace, manifest and view records. It never generates
assets or implements a game's logic. Basic previews are generic; specialist
inspectors are optional adapters over bounded metadata. Unknown preview contracts
retain readable metadata rather than disappearing.

`godot/packages/` contains independently bounded reusable runtime packages.
`godot/games/` contains playable consumers. `godot/templates/` contains starting
projects whose preparation scripts import assets explicitly. A game's configuration
is local to that game. No runtime package has to depend on all other packages.

Each named game in `godot/games/` owns its authored inputs, optional Python
preparation package, Godot project, gameplay and asset bindings. Existing TOML
readers remain supported game formats; GDScript and resources can replace them
when that game's needs warrant it. No repository-wide selected game exists.

`godot/games/_shared/` holds private implementation with multiple game consumers:
bounded simulation and IO support, input readers and media binding helpers. Shared
code imports no named game. Cross-game CLI dispatch and fixture maintenance live
under `godot/tools/`; the optional `games` installation group supplies that tooling
and the individual game preparation packages. The public product imports none of
these packages. Game formats are documented with their owning game or shared
reader, independently of the asset SDK's authoring contract.

`apps/concept_studio/` is a separately installable concept-authoring application.
Examples live beside the SDK, component or recipe they demonstrate. Documentation
indexes them; `library/` is removed because it has no remaining distinct owner.

## Enforcing the boundary

Import tests enforce GNode rings and the absence of product-to-game dependencies.
Package tests verify installed use outside the checkout. Product verification
runs without optional consumers; the aggregate gate additionally verifies game
readers, Godot, viewer and applications. Per-recipe graph contracts remain with the
recipe or demo that owns them. There is no repository-wide canonical game graph.

Cache identity, route preflight, retry ownership, atomic persistence, provenance,
path confinement and media review rules survive the reshape. Moving code does not
license changes to existing cache keys or accepted input bytes. See
[verification](VERIFICATION.md) and the [directory preview](docs/repository-layout.md).
