# Asset taxonomy and module namespace

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

A new camera segment MUST be introduced by binding it to a canonical profile
(a future `topdown` binds to `overhead_nadir_orthographic_ground_plane_v1`);
an unbound informal label MUST NOT become a segment. This reconciles the
namespace rules in the view and style taxonomy: bare labels remain banned *as
authorities*; a namespace segment is a navigation name whose authority is its
binding.

## Where the taxonomy lives — identifiers, not directories

The full path is the **type identifier namespace**: when the node ABI lands,
`type_id` values persist taxonomy paths (`2d/sideview/platformer/terrain_47tile`).
Directory trees do NOT mirror the taxonomy — an eight-level source tree buys
depth, not clarity. Module paths carry the **flattened honest name** instead:
the narrowest segments that make the assumption visible (`platformer_map`, not
`two_d/sideview/platformer/map`). One name, stated once, greppable.

## Census

Assumption tiers: **(a)** modality-only · **(b)** game-generic ·
**(c)** camera-specific · **(d)** genre-specific. Judged from the code, not
the old names.

| Was | Is (this pass) | Taxonomy path (type_id target) | Tier |
| --- | --- | --- | --- |
| `components/game_map` | `components/platformer_map` | `2d/sideview/platformer/map` | c/d — side-on level profile, heightfield ground, one-way platforms |
| `components/game_content` | `components/platformer_content` | `2d/sideview/platformer/content` | d — jump/crouch/climb motion states, mirrorable side sprites |
| `components/gameplay_contract` | `components/platformer_gameplay` | `2d/sideview/platformer/gameplay` | d — left/right/jump navigation, hunting routes |
| `components/platformer_map_design` | unchanged (already honest) | `2d/sideview/platformer/map_design` | d |
| `components/game_sequence` | `components/dialogue_sequence` | `2d/frontview/vn/sequence` | b with a front-view lock |
| `components/game_contract` | unchanged — the container | declares the profile; not itself camera-scoped | container |
| `components/game_ui` | unchanged | `2d/ui` | b — screen-space |
| `components/game_soundtrack` | unchanged | `soundtrack` | b |
| `components/character_profile` | unchanged | `character_profile` | a/b |
| `components/image_repeat` | unchanged | `2d/image_repeat` | a by declaration, c in practice — repair prompts assume a gravity-bearing horizon; documented, ungated |
| `recipes/scrolling_preview` | `recipes/sideview_platformer` | `2d/sideview/platformer` (the recipe is the genre package) | c/d |
| `recipes/dialogue_scene` | unchanged | `2d/frontview/vn/scene` | c |
| `web/lib/sideview-platformer` | `web/lib/sideview-platformer` | consumer adapter for `2d/sideview/platformer` | d |

The modality components (image, structured, music, background removal) left
this table in the same change series: they are `gnode` ring-1 material — see
[gnode rings](gnode-rings.md).

## Persisted vocabulary is frozen until the next bump

Module paths, directory names, and class names are free to rename because no
persisted document may contain them (an existing engine rule). Persisted
strings are not renamed by this pass: the recipe id `"scrolling-preview"`, the
graph document kinds, annotator keys, and cache namespaces stay byte-frozen —
their taxonomy-aligned successors ride the next coordinated schema bump
together with the node ABI's `type_id` registry, so existing runs are dropped
once, not once per rename.

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
   horizontal for a runner, vertical for an infinite jumper. Loop admission
   today is single-axis with only horizontal callers, which is exactly why an
   infinite-jumper demo is currently impossible. Home: loop-axis modules under
   the camera (`2d/sideview/loop_x`, `2d/sideview/loop_y`), genre profiles
   above them (`runner`, `jumper`).
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
