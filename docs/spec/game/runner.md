# Runner genre family

> **Contract maturity: exact-current authored contracts.** Executable
> authority: `src/stage_gen/components/runner_gameplay/`,
> `src/stage_gen/components/runner_track/`,
> `src/stage_gen/components/runner_content/`,
> `src/stage_gen/components/runner_audio/`, and the runner member resolution
> in `src/stage_gen/orchestration/game_package.py`. The generation recipe
> lives in `src/stage_gen/recipes/sideview_runner/` and the playable runtime
> in `web/lib/sideview-runner/`, served at `/runner/<tag>`.

The infinite runner is a genre member of the `game-contract-v9` container
([authored contract schema](authored-contract-schema.md)). It may be the only
member of a prepared package, as Iron Petal Unit is, or share a container with
another genre, as Bellweather does. In either case the root owns the style,
proportion, scale, evidence, and rights used by the endless side-scrolling run.
Its taxonomy home is `2d/sideview/runner`
([asset taxonomy](../asset-taxonomy.md)). The gameplay reference is CookieRun:
OvenBreak, adopted for its level *language* - the pickup trail as routing, so
greed and survival point the same way - and refused for its level
*architecture*: hand-built episodes whose fairness guarantee is a human seeing
the next forty columns. Ours is the offline admission proof below.

## Member table

A runner member claims the fixed `runner/` prefix inside the package:

| Member | Kind | Notes |
| --- | --- | --- |
| `runner/gameplay.toml` | `runner-gameplay-v2` | Named profiles only; the consumer owns the feel numbers |
| `runner/track.toml` | `runner-track-v3` | One track of authored segments and one closed ground mode |
| `runner/content/avatar.toml` | `runner-avatar-v3` | Exactly one runtime actor: one character or one visible rider-and-machine silhouette |
| `runner/content/props.toml` | `prop-content-v2` | Obstacles, reused verbatim |
| `runner/content/items.toml` | `item-content-v2` | Pickups, reused verbatim |
| `runner/audio.toml` | `runner-audio-v1` | Required event bindings and sound-effect realizations |
| `runner/soundtrack.toml` | `game-soundtrack-v1` | Optional |

There is no UI member (the runtime draws its distance/score HUD itself) and no
scenario member yet; both are additive later. The member's cast is one
`avatar_id`; character identity is shared with a sibling genre by binding the
same digest-locked reference bytes, never by a container-level cast join.

`runner-avatar-v3` states the actor honestly. `age` is the chronological age of
the visible person, bounded from 0 through 130; it is not an adult-content
admission proxy. `single_character_v1` uses `character_head_v1` as its
proportion basis. `visible_rider_machine_v1` requires
`body_kind = "piloted_machine"`, `proportion_basis = "visible_rider_head_v1"`,
and an explicit root `[proportion.by_body_kind]` override. That override measures
the complete robot-feet-to-rider-top figure in the visible rider's head units.
The rider is never a second actor: framing, draw scale, collision, duck
clearance, motion rebase, and every motion strip apply to the complete combined
silhouette. These fields enter concept and motion prompts and their cache
identities, so an old single-character rendering cannot be reused for a piloted
machine.

Native-alpha admission is quantitative, not an extrema check. Avatar concepts, motion sources,
and catalog cutouts require at least 10% fully transparent pixels, 10% transparent perimeter, and
0.5% pixels at alpha 16 or greater. Transparent parallax-layer sources require at least 5% fully
transparent pixels, 5% transparent perimeter, and the same 0.5% visible coverage. An opaque canvas
with a token transparent corner, or an interior-only transparent hole, is therefore retried.
Runner motion repacking also selects the recipe-neutral `exact_required_slots` policy: exactly one
principal connected component must occupy every authored frame slot and no other meaningful
component of 32 pixels or more may be discarded. A disconnected visible rider, machine part, or
propulsion assembly fails provider admission instead of being silently dropped from the runtime
frame.

## Gameplay: named profiles

`runner-gameplay-v2` declares `track_id`, `[run]` (`speed_profile`,
`jump_profile`, `collision_policy`, and an optional `duck_profile`) and
`[ramp]` (`profile`). Every value is a closed name. The rule that decides
where a number lives: **it belongs in the SDK constant table iff a refusal
depends on it; it stays consumer-owned iff only the feel depends on it.** So
each name declares its admission arithmetic as SDK constants - the jump's
`max_clear_gap_columns`, `max_rise_tiles`, `peak_margin_tiles` and
`airtime_headroom`; the speed's base columns per second and its
`max_speed_multiplier` cap (spacing proofs run at the cap, press windows at
the base - each is the other family's worst case, and the consumer's ramp is
clamped to the cap); the collision box widths; the duck's height fraction and
clearance margin - and the manifest publishes them, so the arc the runtime
flies and the arc admission proved are the same closed forms. The ramp's
pacing shapes only feel and stays in the consumer. Scoring is runtime-owned:
distance plus pickups, with a chain multiplier that breaks on a missed
pickup.

Jump names: `single_arc_v1`, and `double_arc_v1`, whose air jump is **recovery,
never reach** - it declares the identical single-hop admission arithmetic, so
no authored chunk ever demands both hops, a player who spends the air jump
early is never stranded, and admission stays a one-dimensional existential
over launch columns rather than a search over jump sequences.

Duck names: `slide_v1`. A gameplay contract that declares one obligates a
drawn `slide` motion; a track that hangs overhead hazards obligates a duck
profile; and an avatar that draws a slide obligates a duck profile to trigger
it. All three directions are refused at resolution, so an overhead prop with
nothing to duck under - or a paid slide strip no input can ever play - is
unsayable rather than dead art. The avatar contract also refuses every
playback shape the runtime would refuse (run loops, everything else plays
once, each state declares a rate and stays inside the atlas columns), so an
admitted package never bills a graph whose manifest no consumer opens.

## Track: authored tiled segments

`runner-track-v3` reuses the platformer map's generation vocabulary for
`[view]`, `[continuity]` and loop construction, digest-locked
`[[references]]`, and `[[layers]]` with parallax and presentation. It replaces
generated terrain geometry with authored `[segments]` and gives ground
presentation a closed union:

- `terrain-atlas-3x3-minimal-v1` generates one reusable 47-mask material atlas;
  it remains the appropriate economical mode for deliberately tiled ground.
- `runner-structural-ground-v1` generates one bespoke native-alpha painting per
  authored segment. A local node first renders the exact occupancy plus common
  seam aprons into a 1536-by-1024 guide. A native-alpha GPT Image 2 edit paints
  that guide with `background = "transparent"`; planning refuses any image
  model not explicitly verified as a GPT Image 2 native-alpha route, and the
  generative layer-loop route separately requires masked-edit capability. No
  chroma key or background-removal fallback exists. One shared local node takes
  the first authored segment's already generated right two-column apron,
  preserves its left-to-right painting, and
  canonicalizes it to `128` by `rows * 64` with exact seam occupancy and a
  deterministic material fallback. Every segment canonicalizer then masks its
  own result back to exact occupancy, installs shared bridge column 0 at its
  right edge and bridge column 1 at its left edge, and publishes `columns * 64`
  by `rows * 64` RGBA. Thus any A-to-B join reconstructs the original generated
  two-column bridge rather than repeating a flat guide-palette tile. Every
  chunk report carries the same bridge, left-role, right-role, and lineage
  digests. Source admission counts painted coverage only at alpha 128 or
  greater, so a technically nonzero but effectively invisible provider result
  is retried rather than hidden under the deterministic fallback; left and
  right seam-apron coverage are measured independently, so one preserved side
  cannot conceal a missing other side, and every authored solid cell must keep
  meaningful painted coverage. Empty cells and pits are alpha zero;
  occupied canonical cells are alpha 255. The image is presentation only and
  can never change collision.

Transparent generated layers use quantitative native-alpha admission before
looping; opaque layers remain required to be fully opaque. This gate is
independent of seam-repeat admission, which still proves the installed loop
unit after construction.

Both modes share the segment discipline below:

- One shared grid: `rows` and `walk_surface_row` hold for every chunk.
- `[[segments.chunks]]` each carry a `segment_id`, a `difficulty` rank, a
  rectangular `{0,1}` occupancy (8-64 columns), and authored `[[hazards]]`
  and `[[pickups]]` (item in an empty cell).
- Every hazard declares its `anchor`: `surface` stands on its supported
  column's ground and answers to the jump; `overhead` hangs above it with
  `clearance_rows` of open air beneath, measured up from the same surface,
  and answers to the slide. Both anchors demand a supported column.
- **Pits are legal**: a bottom-row `0` run is the genre's defining hazard. The
  platformer family's bottom-supported-escape-floor rule is exactly the rule
  this family drops - and keeps, unchanged, on its own side.
- **The seam rule** makes the track infinite: every chunk's first and last
  columns are exactly empty above `walk_surface_row` and solid from that row
  down, so no detached overhead solid can survive offline admission and any
  chunk may follow any chunk in any order without a cross-chunk geometry check.
- The camera is `auto_run_x_v1`: it advances on its own rather than following
  input, which is the genre fact the platformer's `player_follow` cannot say.

There is no terrain-design provider node: segment geometry is authored, not
designed. Structural-ground image calls paint that admitted geometry; they do
not invent it. A later `[segments]` mode may reintroduce a geometry designer
additively, but it would still need the same offline proof before spend.

## The placement discipline

Admission proves every chunk against `reaction_fair_v1`, the placement
discipline selected by the SDK constant `RUNNER_PLACEMENT_PROFILE` (a
one-member vocabulary is a constant; the name becomes a persisted field the
moment a second discipline exists). Its rules, each derived from the declared
arc at each family's worst case - base speed for press windows and spans
(airtime is fixed by construction, so ramping only lengthens jumps), the
`max_speed_multiplier` cap for every spacing rule (a faster run stretches
every flown arc):

- **The apron**: one flat jump span - flown at the speed cap - of calm
  walk-surface, hazard-free ground at each end of every chunk. This is the
  price of the seam rule: without it, a chunk ending in a pit could hand its
  landing to a chunk opening with a hazard, with no surviving launch frame
  between them.
- **Span-with-rise**: every consecutive supported pair, adjacent or across a
  pit, is proved inside the arc together - a rise steals airtime, so a
  max-width pit and a max-height rise are not simultaneously clearable and
  are refused as one demand, not admitted as two bounds.
- **Landing clearance**: level, hazard-free ground after every pit and rise
  landing; a window that runs off the chunk's edge is already proven calm by
  the end apron.
- **Demand separation**: adjacent same-anchor hazards read as one silhouette
  and are proved as one demand; everything else - hazard clusters and terrain
  feature groups alike - stands a full separation apart, wider than one arc
  flown at the speed cap, so two demands never share a jump uninvited.
- **The drop scatter**: a drop-off is a landing with no launch - the run
  leaves the ledge at full speed and no verb is available mid-fall - so the
  whole scatter zone beneath it, computed at the cap speed, must be level and
  calm, and the drop edge separates from other demands like any feature.
- **The press window**: a surface hazard cluster must leave real launch-timing
  slack over its tallest member, from the arc's time-above-height minus the
  crossing time of its collision span. The first time a beautiful prop fails
  this proof, the designer's rule is: **if the silhouette is wanted at full
  height, the correct fix is a taller jump profile, not a lowered threshold.**
- **The overhead proof**: the ground proof with the anchor flipped - a ducked
  avatar plus daylight must fit beneath the declared clearance
  (`segment_hazard_unclearable`), and the clearance must still refuse a
  standing run (`invalid_runner_track`), or the placement is dead art.
- **The telegraph** (`pickup_arc_v1`): every jump demand - pit, rise, and
  surface hazard cluster alike - places at least three pickups on the arc the
  clearance proof flew, sampled from the same closed forms, so greed walks
  the player down the safe line on first sight, which is the only teaching
  channel that survives uniform chunk selection. A prop used as a surface
  hazard must declare `height_units`, or the press-window proof has nothing
  to prove against and refuses.

## Rhythm is refused

Not on cost - it would still be no with unlimited budget. The seam rule and
beat sync are mutually exclusive: rhythm runners map a *through-composed*
song onto a *fixed* level, and this genre's defining property is that any
chunk may follow any chunk, drawn at runtime. You cannot through-compose
against a random permutation - **the exact property that makes the runner
infinite is the property that forbids the rhythm model.** It is independently
disqualified by the ramp: speed is continuous in distance, so a column has no
fixed beat phase at any point in a run. The compatible fraction ships instead:
per-event audio one-shots, specific to *how* the obstacle was avoided.
`runner/audio.toml` explicitly binds takeoff, air jump, landing, slide, hazard
clear, collect, and death events to named effects. Its current
`oscillator_sweep_v1` realization authors waveform, start/end frequency,
duration, gain, and optional strength-driven pitch response at zero provider
cost; the consumer translates those values and owns only Web Audio lifecycle.
A future generated-file realization extends the effect side without changing
the stable event bindings.

Music remains the separate optional `runner/soundtrack.toml` catalog and uses
the existing provider-neutral `game-soundtrack-v1` generation path. The runtime
shuffles its declared loop-ready tracks after audio unlock. Do not let a tempo
field into `game-soundtrack-v1`: it is shared across genres, and the other
genres have no tempo.

## Runtime composition

Successful runner generation emits `sideview-runner-runtime-v4`. Its `ground`
field is the same closed union as the authored track. Atlas mode publishes one
atlas path. Structural mode publishes `cell_px = 64` and an authored-order
`chunks` array whose `segment_id`, image path, columns, and rows must match the
occupancy chunks one for one. The browser preloads those exact image dimensions
and draws the corresponding full raster for every streamed chunk; all physics
continues to read occupancy.

Layer placement preserves the source cover-frame scale after transparent rows
are trimmed, so a sparse upper truss does not expand merely because its empty
lower canvas was removed or because a generated seam bridge changed its repeat
width. Collectibles keep their authored collision cell while
presentation applies per-instance bob, horizontal flip, and a short glint.
Hazards preserve authored height, clamp visible width to the published collision
span, register surface obstacles to the footing line, and receive only a local
readability cue rather than a screen-wide warning. These are consumer
presentation rules, not authored geometry and not generation prompts.

Keyboard play uses Space or Arrow Up to jump and holds Arrow Down to slide.
Pointer play divides the canvas into stable zones: the upper 68% jumps (and
restarts after death), while holding the lower 32% holds the slide until every
lower-zone pointer is released. The visible control hint states the lower-zone
mapping only when the manifest admits both a duck profile and slide motion;
pointer capture preserves release when a finger leaves the canvas.

## Machine-checked graph contract

The embedded contract is content-insensitive where content does not change
topology: a changed prompt or reference re-keys node cache identities and
`graph_sha256`, not `topology_sha256`. Adding a segment in structural-ground
mode, a layer, a motion state, a catalog entry, or a soundtrack member changes
the topology and therefore this checked snapshot. The checked runner fixture is
Iron Petal Unit so the snapshot covers the per-segment structural-ground fan-out
rather than only the atlas branch. Regenerate with
`uv run python scripts/write_pipeline_graph_contract.py --write`; the gate is
`tests/contract/test_generation_pipeline_docs.py`.

<!-- pipeline-graph-contract:start -->
```json
{
  "kind": "sideview-runner-execution-graph-contract-v1",
  "fixture_ref": "library/games/iron-petal-unit",
  "graph_schema_version": 1,
  "topology_sha256": "2be1a6e40521e10a2a1387edde513cc6dfd4de272454e33d733c7bf3ec88d13e",
  "node_count": 70,
  "terminal_node_id": "manifest-assemble",
  "operation_counts": {
    "local": 39,
    "image_generation": 27,
    "structured_generation": 2,
    "music_generation": 2
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

For the exact Iron Petal Unit fixture, the normal graph contains 31 first-pass
provider operations. Provider transport retries and later semantic
regenerations are reported by their owning node and are not extra graph nodes.
Every provider node also publishes one attempt-ledger artifact that binds the exact graph-visible
prompt, records unsuccessful operations neutrally as `not_selected` when the failure stage is not
known, and distinguishes provider, fallback, local, or absent output selection. A selected provider
artifact carries its digest. A cache hit restores that original generation ledger byte-for-byte;
current hit/miss telemetry stays in the execution trace so it cannot perturb downstream cache
lineage.

| Domain | Concrete expansion | Image | Structured | Music | Local |
| --- | --- | ---: | ---: | ---: | ---: |
| World | 11 segments × (guide + structural paint + canonicalize), one shared generated-apron seam bridge, plus 3 layers × (generate + loop + validate) | 17 | 0 | 0 | 26 |
| Avatar | One combined rider-machine concept, 4 motion strips and validations, two whole-silhouette motion-rebase judgements | 5 | 2 | 0 | 4 |
| Catalog | 4 obstacles and 1 collectible, each generated and locally validated | 5 | 0 | 0 | 5 |
| Soundtrack | 2 loop-ready tracks and technical validation | 0 | 0 | 2 | 2 |
| Package | Captured-package barrier and terminal runtime assembly | 0 | 0 | 0 | 2 |
| **Total** | **70 nodes** | **27** | **2** | **2** | **39** |

## Resolution and admission

The container resolver resolves a declared runner member either alone or
alongside siblings, registers its files into the same exact closure
(missing/orphan/`closure_sha256`), and cross-validates before any spend:

- identity: every runner contract shares the container's `game_id`
  (`cross_game_identity`);
- audio: all seven semantic events bind to declared effects, every effect is
  used, and each realization is bounded before execution
  (`invalid_runner_audio`);
- bindings: cast avatar, gameplay `track_id`, hazard `prop_id`, and pickup
  `item_id` all resolve (`unresolved_cross_reference`);
- verbs: overhead hazards demand a duck profile
  (`invalid_runner_gameplay`), a duck profile demands a drawn slide, and a
  drawn slide demands a duck profile (`invalid_runner_avatar`);
- seams: both seam columns of every chunk are empty above and solid from the
  shared walk surface down (`segment_seam_mismatch`);
- gaps: no pit run exceeds the jump name's `max_clear_gap_columns`, and no
  pit-plus-rise pair exceeds the arc's span at that rise
  (`segment_gap_unclearable`);
- placement: the apron, demand separations, landing clearances, and drop
  scatter zones of the discipline above all hold
  (`segment_placement_violation`);
- silhouettes: every hazard cluster declares a height and leaves a real press
  window, and every overhead clearance fits a ducked avatar
  (`segment_hazard_unclearable`); a clearance admitting a standing run is
  refused as dead art (`invalid_runner_track`);
- telegraphs: every jump demand carries its pickup arc
  (`segment_untelegraphed`);
- terrain: hazards never hang or stand over pits, pickups occupy empty cells,
  and rises stay within the jump profile (`invalid_runner_track`).

Address the member from the CLI with `--genre runner` on `stage-gen package
plan` and `stage-gen generate`; `--genre` defaults only when a package
declares a single member.
