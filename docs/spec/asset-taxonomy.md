# Asset taxonomy and module namespace

> **Checked by:** none.

> **Contract maturity: current naming discipline.** The renames it prescribes
> are implemented; persisted vocabulary is explicitly out of scope until the
> next coordinated schema bump.

This repository started as one genre — a 2D side-view scrolling platformer —
and named its modules as if that were the whole world: the most
platformer-specific packages wore the most generic names. This document fixes
the namespace those modules grow into, so that new cameras and genres arrive
under declared paths instead of drifting into generic-sounding packages.

## Grammar

A module's taxonomy path is:

```text
<space>/<camera>/<genre>/<module>
```

- **space** — the asset space: `2d` today; `3d` is reserved and deferred (it
  exists in the grammar so `2d` is a statement, not a default).
- **camera** — a human-readable alias **bound to a canonical presentation
  profile family** in the
  [view and style taxonomy](game/view-and-style-taxonomy.md). Aliases never
  carry their own authority; the bound profile does.
- **genre** — the gameplay composition profile the module assumes
  (`platformer`, `vn`, later `rpg`, `runner`, …).
- **module** — the `lower_snake_case` leaf (`terrain_47tile`, `map_design`,
  `sequence`).

Segments to the left of the module are **omitted where the axis does not
apply**: a camera-neutral module takes no camera segment, a genre-neutral one
no genre segment. The namespace is a discipline, not a bureaucracy —
`character_profile` and `soundtrack` are complete paths.

Current camera aliases:

| Alias | Bound presentation-profile family |
| --- | --- |
| `sideview` | `lateral_orthographic_side_plane_v1` |
| `frontview` | `screen_space_dialogue_stage_v1` |
| `roomview` | `screen_space_room_stage_v1` |
| `obliqueview` | `elevated_oblique_perspective_ground_plane_v1` |

A new camera segment MUST be introduced by binding it to a canonical profile
(a future `topdown` binds to `overhead_nadir_orthographic_ground_plane_v1`);
an unbound informal label MUST NOT become a segment. This reconciles the
namespace rules in the view and style taxonomy: bare labels remain banned *as
authorities*; a namespace segment is a navigation name whose authority is its
binding.

## Where the taxonomy lives — identifiers, not directories

The full path is the **type identifier namespace**: the node ABI persists
taxonomy paths as every node's `type_id`
(`2d/sideview/platformer/motion_atlas.generate` — path names the module, the
`.step` suffix names the step within it). Directory trees do NOT mirror the
taxonomy — an eight-level source tree buys depth, not clarity. Module paths
carry the **flattened honest name** instead: the narrowest segments that make
the assumption visible (`platformer_map`, not `two_d/sideview/platformer/map`).
One name, stated once, greppable.

## Census

Assumption tiers: **(a)** modality-only · **(b)** game-generic ·
**(c)** camera-specific · **(d)** genre-specific. Judged from the code, not
the old names.

| Was | Is (this pass) | Taxonomy path (type_id target) | Tier |
| --- | --- | --- | --- |
| `components/game_map` | `components/platformer_map` | `2d/sideview/platformer/map` | c/d — side-on level profile, heightfield ground, one-way platforms |
| `components/game_content` | `components/platformer_content` | `2d/sideview/platformer/content` | d — jump/crouch/climb motion states, mirrorable side sprites |
| `components/gameplay_contract` | `components/platformer_gameplay` | `2d/sideview/platformer/gameplay` | d — left/right/jump navigation, hunting routes |
| `components/platformer_map_design` | `components/sideview_map_design` | `2d/sideview/map_design` | c — its own docstring says it: not one game constant, every threshold arrives in the profile a caller hands it; renamed in the engineering pass |
| `components/game_sequence` | `components/dialogue_sequence` | `2d/frontview/vn/sequence` | b with a front-view lock |
| `components/game_contract` | unchanged — the container | declares the profile; not itself camera-scoped | container |
| `components/game_ui` | unchanged | `2d/ui` | b — screen-space |
| `components/game_fx` | new in the cut-in pass | `2d/fx` | b — screen-space transitions and overlays; `cut_in.*` today, the reserved home for the deferred world-space effect sprites (`sprite.*`) |
| `components/game_soundtrack` | unchanged | `soundtrack` | b |
| `components/character_profile` | unchanged | `character_profile` | a/b |
| `components/image_repeat` | unchanged | `2d/image_repeat` | a by declaration, c in practice — repair prompts assume a gravity-bearing horizon; documented, ungated |
| `recipes/scrolling_preview` | `recipes/sideview_platformer` | `2d/sideview/platformer` (the recipe is the genre package) | c/d |
| `recipes/dialogue_scene` | unchanged | `2d/frontview/vn/scene` | c |
| `recipes/pointclick_room` | new in the ABI pass | `2d/roomview/pointclick` | c/d — fixed-room stage, cursor-only interaction |
| `recipes/universe` | new in the universe pass | `universe` | a — no camera and no genre: the semantic half of this recipe proposes, plans and admits a storyworld as text, and only its gallery half draws |
| `recipes/oblique_survival` | new in the survival pass | `2d/obliqueview/survival` (the recipe is the genre package) | c/d — fixed elevated-oblique perspective camera, billboard cards on a ground plane, and the survival rules the cards obey |
| the recipe's ground steps | new in the survival pass | `2d/obliqueview/survival/ground_*` | c — material plates, the macro colour field, the road and water plates, and the litter, forage and standing-plant sheets a consumer scatters |
| the recipe's actor steps | new in the survival pass | `2d/obliqueview/survival/actor_concept`, `.../motion_atlas`, `.../motion_rebase` | c — the four-way facing set, billboard strip geometry, ground-contact measurement |
| the recipe's world steps | new in the survival pass | `2d/obliqueview/survival/item_*`, `.../prop_*`, `.../season_look`, `.../weather_*`, `.../world_layout` | d — pickups and their icons, prop states and their interaction art, the season looks, the weather layers, and the algorithmic layout |
| `godot/oblique_survival` | new in the survival pass | consumer host for `2d/obliqueview/survival` | d |
| `web/lib/sideview-platformer` | `web/lib/sideview-platformer` | consumer adapter for `2d/sideview/platformer` | d |
| `web/lib/pointclick` | new in the ABI pass | consumer adapter for `2d/roomview/pointclick` | d |
| `web/lib/dialogue-scene` | unchanged | consumer adapter for `2d/frontview/vn/scene` | d |
| `web/lib/dialogue-scene` | new | the agnostic conversation core both genres walk | a |
| `components/actor_content` | new in the runner pass | `2d/actor_content` | b — shared drawn-actor blocks (references, motion playback) |
| `components/runner_gameplay` | new in the runner pass | `2d/sideview/runner/gameplay` | d |
| `components/runner_track` | new in the runner pass | `2d/sideview/runner/track` | d — authored tiled segments over the shared side-view stage |
| `components/runner_content` | new in the runner pass | `2d/sideview/runner/content` | d |
| `components/sideview_terrain` | lifted from the platformer recipe | `2d/sideview/terrain_47tile` | c — both side-view genres paint one atlas |
| `components/sideview_actor` | lifted from the platformer recipe | `2d/sideview/actor` | c — magnitude, strip geometry, rebase admission |
| `components/sideview_stage` | lifted from `platformer_map` in the engineering pass | `2d/sideview/stage` | c — the view, continuity, reference, layer and ground blocks both side-view genres author; the runner stopped importing the platformer's map for them |
| `components/sideview_layers` | lifted from the platformer recipe | `2d/sideview/loop_x` | c — the horizontal-loop layer contract |
| `web/lib/kernel` | new in the vitals pass; `game-systems` until runtime step 1 | the agnostic runtime substrate every genre may seal against | a — sealed system protocol, frame event queue, and the bounded-resource gauge; no genre, no engine, and deliberately not named after health |
| `web/lib/families/hud/gauge-bar.ts` | new in the vitals pass; `sideview/gauge-bar.ts` until runtime step 6 | shared side-view presentation | c — one capsule widget, placed by its caller in world or screen space |

The modality components (image, structured, music, background removal) left
this table in the same change series: they are `gnode` ring-1 material — see
[gnode rings](gnode-rings.md).

## The coordinated bump happened with the node ABI

Module paths, directory names, and class names were always free to rename
because no persisted document may contain them (an existing engine rule).
Persisted strings waited for one coordinated schema bump — and that bump
landed together with the node ABI's `type_id` registry, exactly as planned,
so existing runs were dropped once, not once per rename:

| Was (persisted) | Is |
| --- | --- |
| recipe id `"scrolling-preview"` | `"sideview-platformer"` |
| `prepared-game-execution-{graph,event,summary,projection,view}-v1` | `sideview-platformer-execution-*-v1` |
| `dialogue-scene-execution-graph-v1` | `dialogue-scene-execution-graph-v3` (node shape and authored contract changed) |
| cache namespaces `prepared-world-v1` / `prepared-content-v3` | `sideview-platformer-{world,content}-v1` |
| provenance component `@stage-gen/scrolling-preview` | `@stage-gen/sideview-platformer` |

The next levers are per-type: each `NodeType.contract_version` invalidates one
kind of work; a cache namespace invalidates one recipe's whole tree.

## Validation cases

The namespace earns its keep only if plausible expansions have obvious homes.
None of these is scheduled; each is resolved to a path now so it cannot drift
later:

1. **Painted terrain with traced colliders** (illustration-first maps where
   rigid bodies are traced after the art): an asset-taxonomy concern before a
   gameplay one — a second terrain discipline beside the tile atlas.
   Home: `2d/sideview/painted_terrain` (genre-neutral: platformers and
   side-view RPGs both consume it).
2. **Runner vs jumper**: the asset-facing difference is the loop axis —
   horizontal for a runner, vertical for an infinite jumper. The horizontal
   runner now exists at its reserved home: `runner` is a `game-contract-v9`
   genre member (`docs/spec/game/runner.md`) over the shared `2d/sideview`
   modules. Loop admission is still single-axis, so an infinite-jumper demo
   remains impossible until `2d/sideview/loop_y` has a caller.
3. **Settlements on terrain** (side-view RPG maps that do not loop):
   settlements composed onto terrain, far blurred background, no foreground —
   a finite map, which is not the looping layer system with different
   parameters but a different composition module.
   Home: `2d/sideview/rpg/settlement_layer` plus a non-looping map profile.
4. **Minigames from existing assets** (time-attack mob waves): asset-side,
   nothing new — this is composition of already-generated contracts plus a
   consumer runtime mode. It is the clearest case for the ownership rule
   below: no generator module should exist for it.

## System or intelligence

The recurring question — is a new genre the system's job or the
`game.toml` author's? — has a ratified answer: **the system owns vocabulary;
the author owns composition.** New taxonomy entries are SDK code first (node
types under declared paths); declarative instances come only after a type has
stabilized in code. An author composes within the vocabulary a recipe exposes
and never smuggles a new genre in through prompt text. When a proposal needs
new asset semantics, it lands as a module at a declared taxonomy path — that
is what this namespace is for.
