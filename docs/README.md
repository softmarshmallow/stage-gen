# Documentation

New here? Read [getting started](getting-started.md) and the [glossary](glossary.md).
Then start with the [repository directory preview](repository-layout.md),
[architecture](../ARCHITECTURE.md) and the [SDK guide](sdk/guide.md).
The product is the asset pipeline; complete games are consumers.

This folder holds only what crosses workflows. Each workflow's guide and exact contract
live beside its code, in `src/stage_gen/workflows/<id>/page.mdx` and `contract.md`, and
`stage-gen show <id>` describes it from the command line.

## Workflows

The root README's [workflow table](../README.md#workflows) links each workflow's page and
is checked against its `workflow.toml`; `stage-gen list` and `stage-gen show <id>` print the
same facts from the command line.

The universe vocabulary is ratified separately in [taxonomy V0](spec/universe/taxonomy-v0.md),
beside the [world vocabulary](research/world-generation-vocabulary.md) research; the
[universe contract](../src/stage_gen/workflows/universe/contract.md) holds its source roles,
both phases and their graphs.

## Authoring and inspection

- [SDK guide](sdk/guide.md): define, plan, run and inspect your own graph, with
  [samples](sdk/pipelines/README.md) and the
  [provider-neutral image node](sdk/provider-neutral-image-node.md) pattern.
- [Components](../src/stage_gen/components/README.md): the component table and the component contract.
- [GNode rings](spec/gnode-rings.md): engine and provider ownership.
- [Viewer](viewer.md): `stage-gen view`, the local read-only client over run folders.
- [Site](site.md): the static landing and documentation site, built by `scripts/site.py` from the catalog and the example store.
- [Providers](models/providers.md): bindings, credentials and live-operation boundaries.
- [Character library](character-library.md): the committed character profiles and approved 3D examples.
- [Godot consumers](../godot/README.md): packages, games and templates.
- [Godot project charter](../godot/CHARTER.md): the example product's continuing goals, ownership and independent evolution.
- [Godot architecture](../godot/docs/architecture.md): named games, local inputs and private shared support.
- [Scenario](../godot/packages/scenario_runtime/README.md): Godot-owned narrative framework, compiler and game-owned invocation.
- [Scenario directory preview](../godot/packages/scenario_runtime/docs/layout.md): execution, authoring, bindings, content and game responsibilities.
- [Asset consumer template](../godot/templates/asset_consumer/README.md): explicit file import and GDScript display.
- [Concept Studio](../apps/concept_studio/README.md): optional concept application.
- [Verification](../VERIFICATION.md): owned gates and aggregate checks.

Sample inputs belong next to the workflow, SDK or component they demonstrate. The directory
preview names existing owners and distinguishes implemented examples from future work; there
is no mandatory centralized example package.

## Retained references

The [game guide](../godot/games/README.md) indexes the maintained consumers.
Their current format documents live with their owners: [shared package readers](../godot/games/_shared/docs/game-package.md),
[Bellweather's build graph](../godot/games/bellweather/docs/generation-pipeline.md),
[Iron Petal Unit's runner contract](../godot/games/iron_petal_unit/docs/runner.md),
[Ember Hollow's generation](../godot/games/ember_hollow/docs/generation-v1.md), and
[The Grain's case composition](../godot/games/the_grain/docs/case.md). These formats
serve those games; they are not requirements for new pipelines or new games.

Standalone component specifications under [`spec/`](spec/) remain useful within their named
scope, including sprite processing, terrain and the [asset taxonomy](spec/asset-taxonomy.md)
of type ids. Scenario's current contract is maintained under the Godot package. Historical
[decisions](decisions/README.md), research and plans retain their original context; the
current architecture controls new work, and
[decision 0071](decisions/0071-workflows-are-the-product-unit-and-the-web-splits-into-site-and-viewer.md)
records how workflows became the product unit.

## Repository policy

[Contribution policy](../CONTRIBUTING.md), [storage](repository-storage.md),
[generated-media publication](generated-media-publication.md) and [IP](oss-ip.md)
apply independently of the product/demo split. The
[implementation ledger](plans/repository-reshape.md) records the reshape.

Ember Hollow references: [generation](../godot/games/ember_hollow/docs/generation-v1.md),
[ground](../godot/games/ember_hollow/docs/ground.md), [seasons](../godot/games/ember_hollow/docs/seasons.md),
[crafting](../godot/games/ember_hollow/docs/crafting.md), and [world](../godot/games/ember_hollow/docs/world.md).
