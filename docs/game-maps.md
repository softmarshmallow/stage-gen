# Authored game maps

> **Contract maturity: exact-current prepared-package overview.**
>
> The field-level authority is the
> [Authored map-generation contract](spec/game/map-generation-contract.md).
> This page explains where a map sits in the game package and which concerns it
> owns. It intentionally does not duplicate the complete TOML schema.

## Current boundary

Each `maps/<map_id>.toml` is one `game-map-v10` source. It describes the assets
and composition needed to generate one side-view map and the static topology
needed to render its ground, climbables, and portal structures.

The root `game.toml` catalogs every map by its exact package-relative source
path. There is no map index. The root `gameplay.toml` references maps by
`map_id` and owns how the game uses them.

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
| `game.toml` | Game identity, package membership, and exact map source paths |
| `maps/<map_id>.toml` | Map references, side-view envelope, continuity, ordered layers, ground generation, the terrain request a generator answers, the climbable roster, portal presentation and endpoint anchors, and whole-map review |
| `gameplay.toml` | Entry map, movement permission, transition relationships, spawning, encounters, NPC/item use, and soundtrack selection |
| Scrolling recipe | Provider operations, deterministic terrain-atlas assembly, validation, review, and immutable artifacts |
| Consumer | Coordinate projection, collision, camera, input, rendering, and simulation |

A map does not choose where a portal leads. It supplies the visible portal pair
and stable endpoint anchors; gameplay connects those anchors to another map.
Likewise, a map supplies its climbable atlas and terrain-relative placements, while
gameplay decides whether climb movement is enabled.

## Per-map composition

A current map source contains:

- identity: `game_id`, `map_id`, revision, and display name;
- a side-view camera and horizontal continuity envelope;
- explicit, digest-locked reference images with rights statements;
- any number of ordered background and foreground layer requests, each declaring
  its vertical anchor from a closed placement vocabulary and its consumer-only
  depth treatment;
- one binary terrain-occupancy grid, its vertical fit and walk-surface row, and a
  ground-material prompt;
- an optional `climbable-atlas-v1` definition with terrain-relative placements;
- an optional `portal-pair-1x2-v1` definition with entry/exit anchors; and
- no gameplay flow, spawn rules, transition destinations, or engine objects.

Reference filenames are arbitrary. A reference may guide the whole map, one
layer, the terrain material, one climbable atlas, or a portal pair. Every paid image
operation names its references explicitly; directory presence never implies
use.

## Vertical composition

`plane` orders layers front to back; it says nothing about where a layer belongs
vertically. That is `vertical_anchor`, chosen from `canvas_cover`, `screen_top`,
`screen_bottom`, or `walk_surface`. The two bottom-registered anchors register a
layer's full-coverage line — the lowest row every column still spans — rather
than its deepest stray tip, so a ragged near-camera silhouette seals the frame
edge instead of showing the sky plate through the gaps between its tips.

Authors declare the anchor and normally nothing else. The producer trims each
canonical layer to its alpha box vertically, measures its reference frames, and
resolves the placement fraction from the raster it actually received; a fraction
written before generation would be a prediction about pixels that do not exist
yet. `vertical_offset` remains available as a reviewed override, and one that
cannot seal is rejected against the measured minimum.

`ground.vertical_fit = "floor_to_screen_bottom"` bottoms the deepest authored row
out at the viewport edge, so no gap can open below the world, and
`walk_surface_row` names the occupancy row that `walk_surface` layers meet.

## Terrain projection

The authored occupancy grid is the collision and composition truth. The
scrolling recipe asks the image model to paint the attributed 47-mask topology
template using authorized concept references. A deterministic local canonicalizer
extracts magenta chroma alpha and enforces connector continuity while preserving the
painted cell interiors and packaged 47-mask lookup. The emitted terrain atlas is a
12-by-4 sheet of 120-pixel RGBA
cells. The prepared consumer selects cells from the canonical lookup and constructs
collision directly from occupancy.

This split keeps topology exact while allowing the provider to concentrate on
rendering quality. Structural admission does not imply that a generated paintover
has passed artistic review.

## Runtime depth presentation

Every layer declares `contrast`, `saturation`, `atmosphere_color`,
`atmosphere_strength`, and `detail_blur_screen_pixels`. These fields describe
how the accepted raster is displayed, not what the image model paints. They are
projected into the prepared manifest and applied once by the consumer; changing
them does not invalidate provider generation, deterministic layer validation,
or the authored review composite. Neutral values are `1`, `1`, `#ffffff`, `0`,
and `0` respectively.

## Resolution and runtime projection

Package resolution verifies every reference, digest, identity, cross-contract
map reference, climbable/climb dependency, and portal transition before provider
work. Integration emits only `prepared-game-runtime-v10`; the web runtime does
not infer missing terrain, climbable, portal, or gameplay semantics.

The canonical Bellweather package is the repository example:

```sh
uv run stage-gen package validate --input library/games/bellweather
uv run stage-gen package plan --input library/games/bellweather
```

See also:

- [Game package](game-package.md) for the complete prepared closure.
- [Terrain atlas](spec/terrain-atlas.md) for the 47-mask artifact contract.
- [Scene and gameplay components](spec/scene-gameplay-components.md) for
  consumer ownership.
- [Canonical generation pipeline](spec/game/generation-pipeline.md) for DAG,
  operation counts, scheduling, cache, and manifest boundaries.
