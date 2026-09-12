# Documentation

Start with the [repository directory preview](repository-layout.md),
[architecture](../ARCHITECTURE.md) and [public pipeline SDK](../src/stage_gen/pipeline/README.md).
The product is the asset pipeline; complete games are consumers.

## Authoring and inspection

- [Contained 3D characters](character-3d.md): development-only brief, geometry, provider rig and motion recipe; installed launch, immutable recovery, explicit qualification modes and the fixed-hand SD human scope.
- [Looping parallax](../src/stage_gen/recipes/looping_parallax/README.md): runnable supplied-layer recipe and preview contract.
- [GNode rings](spec/gnode-rings.md): engine and provider ownership.
- [Viewer](web-viewer.md): generic persisted-run inspection and optional inspectors.
- [Providers](models/providers.md): bindings, credentials and live-operation boundaries.
- [Godot consumers](../godot/README.md): packages, games and templates.
- [Godot project charter](../godot/CHARTER.md): the example product's continuing goals, ownership and independent evolution.
- [Godot ownership layout](plans/godot-consumer-layout.md): named games, local inputs and private shared support.
- [Asset consumer template](../godot/templates/asset_consumer/README.md): explicit file import and GDScript display.
- [Concept Studio](../apps/concept_studio/README.md): optional concept application.
- [Verification](../VERIFICATION.md): owned gates and aggregate checks.

Examples belong next to the SDK, component or recipe they demonstrate. The directory
preview names existing owners and distinguishes implemented examples from future
work; there is no mandatory centralized example package.

## Retained references

The [game guide](../godot/games/README.md) indexes the maintained consumers.
Their current format documents live with their owners: [shared package readers](../godot/games/_shared/docs/game-package.md),
[Bellweather's build graph](../godot/games/bellweather/docs/generation-pipeline.md),
[Iron Petal Unit's runner contract](../godot/games/iron_petal_unit/docs/runner.md),
[Ember Hollow's generation](../godot/games/ember_hollow/docs/generation-v1.md), and
[The Grain's case composition](../godot/games/the_grain/docs/case.md). These formats
serve those games; they are not requirements for new pipelines or new games.

Standalone component and recipe specifications remain useful within their named
scope, including scenario, sprite processing, terrain, portrait motion, universe
and storefront. Historical [decisions](decisions/README.md), research and plans
retain their original context; the current architecture controls new work.

## Repository policy

[Contribution policy](../CONTRIBUTING.md), [storage](repository-storage.md),
[generated-media publication](generated-media-publication.md) and [IP](oss-ip.md)
apply independently of the product/demo split. The
[implementation ledger](plans/repository-reshape.md) records the reshape.

The independent [universe recipe](spec/universe/generation-v1.md),
[world vocabulary](research/world-generation-vocabulary.md),
[storefront recipe](spec/storefront/generation-v1.md), and
[asset taxonomy](spec/asset-taxonomy.md) remain scoped references.

Ember Hollow references: [generation](../godot/games/ember_hollow/docs/generation-v1.md),
[ground](../godot/games/ember_hollow/docs/ground.md), [seasons](../godot/games/ember_hollow/docs/seasons.md),
[crafting](../godot/games/ember_hollow/docs/crafting.md), and [world](../godot/games/ember_hollow/docs/world.md).
