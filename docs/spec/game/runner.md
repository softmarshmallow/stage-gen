# Runner genre family

> **Contract maturity: exact-current authored contracts.** Executable
> authority: `src/stage_gen/components/runner_gameplay/`,
> `src/stage_gen/components/runner_track/`,
> `src/stage_gen/components/runner_content/`, and the runner member resolution
> in `src/stage_gen/orchestration/game_package.py`. The generation recipe and
> web runtime land separately; this document does not claim a runner has been
> generated or is playable.

The infinite runner is the second genre member of the `game-contract-v8`
container ([authored contract schema](authored-contract-schema.md)): the same
game, the same style, proportion, scale, evidence, and rights, played as an
endless side-scrolling run. Its taxonomy home is `2d/sideview/runner`
([asset taxonomy](../asset-taxonomy.md)).

## Member table

A runner member claims the fixed `runner/` prefix inside the package:

| Member | Kind | Notes |
| --- | --- | --- |
| `runner/gameplay.toml` | `runner-gameplay-v1` | Named profiles only; the consumer owns the numbers |
| `runner/track.toml` | `runner-track-v1` | One track of authored tiled segments |
| `runner/content/avatar.toml` | `runner-avatar-v1` | Exactly one drawn character |
| `runner/content/props.toml` | `prop-content-v2` | Obstacles, reused verbatim |
| `runner/content/items.toml` | `item-content-v2` | Pickups, reused verbatim |
| `runner/soundtrack.toml` | `game-soundtrack-v1` | Optional |

There is no UI member (the runtime draws its distance/score HUD itself) and no
scenario member in v1; both are additive later. The member's cast is one
`avatar_id`; character identity is shared with a sibling genre by binding the
same digest-locked reference bytes, never by a container-level cast join.

## Gameplay: named profiles

`runner-gameplay-v1` declares `track_id`, `[run]` (`speed_profile`,
`jump_profile`, `collision_policy`) and `[ramp]` (`profile`). Every value is a
closed name; each jump name declares its admission arithmetic
(`max_clear_gap_columns`, `max_rise_tiles`) as an SDK constant so tracks are
provable offline. Scoring is runtime-owned: distance plus pickups.

## Track: authored tiled segments

`runner-track-v1` reuses the platformer map's generation vocabulary verbatim -
`[view]`, `[continuity]` and the loop constructions, digest-locked
`[[references]]`, `[[layers]]` with parallax and presentation, and the
`terrain-atlas-3x3-minimal-v1` `[ground]` atlas request - and replaces
generated terrain with authored `[segments]`:

- One shared grid: `rows` and `walk_surface_row` hold for every chunk.
- `[[segments.chunks]]` each carry a `segment_id`, a `difficulty` rank, a
  rectangular `{0,1}` occupancy (8-64 columns), and authored `[[hazards]]`
  (prop on a supported column) and `[[pickups]]` (item in an empty cell).
- **Pits are legal**: a bottom-row `0` run is the genre's defining hazard. The
  platformer family's bottom-supported-escape-floor rule is exactly the rule
  this family drops - and keeps, unchanged, on its own side.
- **The seam rule** makes the track infinite: every chunk's first and last
  columns are bottom-supported with their surface exactly at
  `walk_surface_row`, so any chunk may follow any chunk in any order and no
  cross-chunk geometry check exists.
- The camera is `auto_run_x_v1`: it advances on its own rather than following
  input, which is the genre fact the platformer's `player_follow` cannot say.

There is no terrain-design provider node: v1 segments are authored, not
designed. A later `[segments]` mode may reintroduce the designer additively.

## Machine-checked graph contract

The embedded contract is content-insensitive where content does not change
topology: a changed prompt or reference re-keys node cache identities and
`graph_sha256`, not `topology_sha256`. Adding a layer, a motion state, a
catalog entry, or a soundtrack member changes the topology and therefore this
checked snapshot. Regenerate with
`uv run python scripts/write_pipeline_graph_contract.py --write`; the gate is
`tests/contract/test_generation_pipeline_docs.py`.

<!-- pipeline-graph-contract:start -->
```json
{
  "kind": "sideview-runner-execution-graph-contract-v1",
  "fixture_ref": "library/games/bellweather",
  "graph_schema_version": 1,
  "topology_sha256": "f832c1b412887fcd44e05c2ec336cff9b88c9f16c9dfa41617b39722a9157f12",
  "node_count": 25,
  "terminal_node_id": "manifest-assemble",
  "operation_counts": {
    "local": 11,
    "image_generation": 12,
    "structured_generation": 2,
    "music_generation": 0
  },
  "resources": [
    {
      "resource_id": "local",
      "max_in_flight": 32,
      "requests_per_minute": null,
      "rate_limit_owner": "none"
    },
    {
      "resource_id": "openai-image",
      "max_in_flight": null,
      "requests_per_minute": 150,
      "rate_limit_owner": "provider_adapter"
    },
    {
      "resource_id": "openrouter-structured",
      "max_in_flight": null,
      "requests_per_minute": null,
      "rate_limit_owner": "none"
    },
    {
      "resource_id": "openrouter-music",
      "max_in_flight": null,
      "requests_per_minute": null,
      "rate_limit_owner": "none"
    }
  ]
}
```
<!-- pipeline-graph-contract:end -->

## Resolution and admission

The container resolver resolves a declared runner member alongside its
siblings, registers its files into the same exact closure
(missing/orphan/`closure_sha256`), and cross-validates before any spend:

- identity: every runner contract shares the container's `game_id`
  (`cross_game_identity`);
- bindings: cast avatar, gameplay `track_id`, hazard `prop_id`, and pickup
  `item_id` all resolve (`unresolved_cross_reference`);
- seams: both seam columns of every chunk present the shared walk surface
  (`segment_seam_mismatch`);
- gaps: no chunk's widest pit run exceeds the declared jump profile's
  `max_clear_gap_columns` (`segment_gap_unclearable`);
- terrain: hazards never stand over pits, pickups occupy empty cells, and
  interior rises stay within the jump profile (`invalid_runner_track`).

Address the member from the CLI with `--genre runner` on `stage-gen package
plan` and `stage-gen generate`; `--genre` defaults only when a package
declares a single member.
