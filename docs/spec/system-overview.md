# System overview

`stage-gen` is a headless orchestration surface over reusable 2D media
components. It produces validated artifacts and provenance for games and game
tools; it does not own gameplay or require a particular runtime.

## Topology

```mermaid
flowchart LR
    I["Typed input manifest"] --> C["Reusable components"]
    C --> P["Headless pipeline"]
    P --> A["Artifacts + provenance"]
    P --> B["Benchmarks and research evidence"]
    A --> W["Optional web preview adapter"]
    A --> E["Future engine adapters"]
```

- `src/stage_gen/components/` owns provider-neutral service contracts;
  `src/stage_gen/providers/` implements vendor adapters.
- `src/stage_gen/media/` owns deterministic inspection and normalization.
- `src/stage_gen/recipes/` owns recipe graphs and manifests;
  `src/stage_gen/orchestration/` owns concrete provider composition, run state,
  and summaries.
- `src/stage_gen/interfaces/` and `src/stage_gen/benchmarks/` expose the
  Python CLI, optional HTTP/SSE API, and research workflows.
- `web/` is an optional consumer that visualizes output and demonstrates one
  scrolling-world recipe.
- `docs/` records contracts, verified provider behavior, policies, and recipe
  evidence.

The dependency direction is one way. A component does not import a pipeline;
a pipeline does not import a preview; a preview does not become an implicit
validator for the reusable component.

## Component graph

A pipeline builds a directed acyclic graph from explicit inputs. Independent
nodes may run concurrently; dependent nodes receive artifacts through typed
results or a manifest. A recipe decides which component families to compose.

Examples of reusable operations include:

- image generation from text and optional references;
- background removal and mask extraction;
- media validation and deterministic normalization;
- [grid/sheet slicing and packing](sprite-sheet-processing.md), a planned
  deterministic core operation that is not implemented yet;
- structured text/vision design data; and
- music generation and audio inspection.

A recipe may request platformer motion names, top-down props, dialogue
portraits, interface panels, or a particular projection. That vocabulary is
recipe input, not a hidden property of the underlying provider or media
component.

## Run contract

Every headless run has:

1. a validated input manifest;
2. a deterministic run identifier when all identity-bearing inputs are stable;
3. an isolated output directory;
4. component-level progress and failure state;
5. resumable skip-if-valid behavior;
6. artifact results with adjacent provenance; and
7. one exact `recipe_run_v3` summary that records the graph and final status.

An artifact is valid only after media inspection succeeds. HTTP success or a
non-empty URL is insufficient. Partial files do not satisfy the cache.

## Reliability

Every provider/network call receives one initial attempt plus five blind
retries with capped backoff: six attempts at most.
Transport failures and silent contract failures use the same retry boundary.
Inputs/references are read and hashed once outside the loop when safe; every
attempt records non-secret diagnostics. Deterministic post-processing is
separate from provider retries and is safe to rerun.

See [the component contract](../component-contract.md) and
[provider operations](../providers.md).

## Provenance

The recipe manifest links each artifact to its component, exact provider/model or
endpoint, prompt and non-secret parameters, input hashes, attempt count,
timestamp, media facts, post-processing, and output hash. Provenance supports
debugging and reproducibility; it is not an IP license.

## First recipe and preview

The existing detailed asset contracts describe a side-view scrolling-world
recipe: a concept root, parallax layers, terrain tiles, character/mob sheets,
props, items, inventory, and portals. Those contracts remain useful as the
first comprehensive integration case.

The browser preview composes that recipe into a scene with a horizontal camera,
heightmap terrain, movement, interactions, and portals. All of those choices
stay under `web/`. A different recipe or engine can consume the same generic
component results through a different manifest/adapter.

See [scrolling-preview asset contracts](asset-contracts.md) and the
[web preview boundary](../web-preview.md).

The planned `dialogue-scene` sibling recipe packages one caller-directed
appearance concept, a finite set of static expression variants for that
identity, and portable scene data for the Visual Novel Scene Kit. Its
[asset contract](dialogue-scene-assets.md),
[optional preview](../dialogue-scene-preview.md), and
[deferred animation notes](../dialogue-scene-animation.md) preserve the same
headless-recipe and downstream-consumer boundary. A deterministic browser
vertical slice implements state-driven variant swapping; the provider-backed
headless recipe does not yet exist.

The Python package under `src/stage_gen/` is the sole headless implementation.
Node and TypeScript are confined to the optional `web/` adapter.

## Game engine

No engine is selected for future gameplay. The current browser adapter is not
the default production target. Dedicated 2D engines, including Godot, may be
evaluated with alternatives once export manifests are stable; see
[game-engine evaluation](../game-engine-evaluation.md).
