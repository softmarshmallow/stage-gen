# Documentation

Start with the [repository directory preview](repository-layout.md),
[architecture](../ARCHITECTURE.md) and [public pipeline SDK](../src/stage_gen/pipeline/README.md).
The product is the asset pipeline; complete games are consumers.

## Authoring and inspection

- [Looping parallax](../src/stage_gen/recipes/looping_parallax/README.md): runnable supplied-layer recipe and preview contract.
- [GNode rings](spec/gnode-rings.md): engine and provider ownership.
- [Viewer](web-viewer.md): generic persisted-run inspection and optional inspectors.
- [Providers](models/providers.md): bindings, credentials and live-operation boundaries.
- [Godot consumers](../godot/README.md): packages, games and templates.
- [Asset consumer template](../godot/templates/asset_consumer/README.md): explicit file import and GDScript display.
- [Concept Studio](../apps/concept_studio/README.md): optional concept application.
- [Verification](../VERIFICATION.md): owned gates and aggregate checks.

Examples belong next to the SDK, component or recipe they demonstrate. The directory
preview names existing owners and distinguishes implemented examples from future
work; there is no mandatory centralized example package.

## Retained references

The [legacy demo guide](../godot/legacy/README.md) owns the old game-package, gameplay,
map, content and host documents, including [game package](game-package.md),
[game contract](game-contract.md), [game graph](spec/game/generation-pipeline.md) and
survival specifications. These remain useful descriptions of supported old readers.
They are not requirements for new pipelines or complete games.

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

Legacy survival references: [generation](spec/survival/generation-v1.md),
[ground](spec/survival/ground.md), [seasons](spec/survival/seasons.md),
[crafting](spec/survival/crafting.md), and [world](spec/survival/world.md).
