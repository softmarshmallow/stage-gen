# Authored game maps

> **Contract maturity: exact-current prepared-package overview.**
>
> The field-level authority is the
> [Authored map-generation contract](spec/game/map-generation-contract.md).
> This page explains where a map sits in the game package and which concerns it
> owns. It intentionally does not duplicate the complete TOML schema.

## Current boundary

Each `maps/<map_id>.toml` is one `game-map-v4` source. It describes the assets
and composition needed to generate one side-view map and the static topology
needed to render its ground, ladders, and portal structures.

The root `game.toml` catalogs every map and digest-locks its source bytes. There
is no map index. The root `gameplay.toml` references maps by `map_id` and owns
how the game uses them.

```text
library/games/<game_id>/
├── game.toml
├── gameplay.toml
├── maps/
│   ├── <map_id>.toml
│   └── ...
└── references/
    └── ...
```

## Ownership

| Owner | Owns |
| --- | --- |
| `game.toml` | Game identity, package membership, and exact map-source digests |
| `maps/<map_id>.toml` | Map references, side-view envelope, continuity, ordered layers, binary terrain occupancy, ground generation, ladder geometry and placement, portal presentation and endpoint anchors, and whole-map review |
| `gameplay.toml` | Entry map, movement permission, transition relationships, spawning, encounters, NPC/item use, and soundtrack selection |
| Scrolling recipe | Provider operations, deterministic terrain-atlas assembly, validation, review, and immutable artifacts |
| Consumer | Coordinate projection, collision, camera, input, rendering, and simulation |

A map does not choose where a portal leads. It supplies the visible portal pair
and stable endpoint anchors; gameplay connects those anchors to another map.
Likewise, a map supplies a ladder and its terrain-relative placement, while
gameplay decides whether climb movement is enabled.

## Per-map composition

A current map source contains:

- identity: `game_id`, `map_id`, revision, and display name;
- a side-view camera and horizontal continuity envelope;
- explicit, digest-locked reference images with rights statements;
- any number of ordered background and foreground layer requests;
- one binary terrain-occupancy grid and ground-material prompt;
- an optional `ladder-4-tile-v1` definition with terrain-relative placements;
- an optional `portal-pair-1x2-v1` definition with entry/exit anchors; and
- no gameplay flow, spawn rules, transition destinations, or engine objects.

Reference filenames are arbitrary. A reference may guide the whole map, one
layer, the terrain material, a ladder, or a portal pair. Every paid image
operation names its references explicitly; directory presence never implies
use.

## Terrain projection

The authored occupancy grid is the collision and composition truth. The
scrolling recipe generates one opaque grass-and-dirt material board, then a
deterministic local assembler maps that material through the packaged 47-mask
topology template. The emitted terrain atlas is a 12-by-4 sheet of 120-pixel
RGBA cells. The prepared consumer selects cells from the canonical lookup and
constructs collision directly from occupancy.

This split keeps topology exact while allowing the provider to concentrate on
material quality. Structural admission does not imply that a generated board
has passed artistic review.

## Resolution and runtime projection

Package resolution verifies every reference, digest, identity, cross-contract
map reference, ladder/climb dependency, and portal transition before provider
work. Integration emits only `prepared-game-runtime-v4`; the web runtime does
not infer missing terrain, ladder, portal, or gameplay semantics.

The canonical Bellweather package is the repository example:

```sh
uv run stage-gen package validate --input library/games/bellweather
uv run stage-gen package plan --input library/games/bellweather
```

See also:

- [Game package](game-package.md) for the complete prepared closure.
- [Terrain atlas](spec/tileset.md) for the 47-mask artifact contract.
- [Scene and gameplay components](spec/scene-gameplay-components.md) for
  consumer ownership.
- [Canonical generation pipeline](spec/game/generation-pipeline.md) for DAG,
  operation counts, scheduling, cache, and manifest boundaries.
