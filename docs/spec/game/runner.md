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
| `runner/gameplay.toml` | `runner-gameplay-v4` | Named profiles only; the consumer owns the feel numbers |
| `runner/track.toml` | `runner-track-v4` | One track of authored segments and one closed ground mode |
| `runner/content/avatar.toml` | `runner-avatar-v3` | Exactly one runtime actor: one character or one visible rider-and-machine silhouette |
| `runner/content/props.toml` | `prop-content-v2` | Obstacles, reused verbatim |
| `runner/content/items.toml` | `item-content-v2` | Pickups, reused verbatim |
| `runner/content/bosses.toml` | `boss-content-v1` | Optional: the actors an encounter brings, drawn facing left |
| `runner/content/projectiles.toml` | `projectile-content-v2` | Optional: what the fight throws, reused verbatim from the platformer |
| `runner/audio.toml` | `runner-audio-v3` | Required event bindings, sound-effect realizations (oscillator sweeps or generated clips), and the soundtrack's transitions at the run's edges |
| `runner/soundtrack.toml` | `game-soundtrack-v1` | Optional |
| `fx.toml` | `game-fx-v2` | Optional root sibling: the [screen FX](fx.md) plates and moment bindings this genre plays; the runner emits `stage_start`, and `encounter_start` when it declares an encounter |

There is no UI member (the runtime draws its distance/score HUD itself) and no
scenario member yet; both are additive later. The screen-FX document is the
first root sibling the genre consumes: it is game-global, and the runner is
only the first genre to emit one of its moments. The member's cast is one
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

`runner-gameplay-v4` declares `track_id`, `[run]` (`speed_profile`,
`jump_profile`, `collision_box`, an optional `duck_profile`, a
`[run.consequences]` table and an optional `[run.vitals]` gauge) and `[ramp]`
(`profile`). Every value is a closed name. The rule that decides
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
pacing shapes only feel and stays in the consumer, and so do every number
behind a consequence: how long immunity lasts, how fast the avatar blinks, and
how far recovery looks for footing are all feel, tunable without regenerating
an image. Scoring is runtime-owned:
distance plus pickups, with a chain multiplier that breaks on a missed
pickup.

Speed names currently include `steady_runner_v1` (6 columns per second, 1.5x
cap), `brisk_runner_v1` (7.5 columns per second, the same proved 1.5x cap) and
`swift_runner_v1` (9 columns per second, the same cap). A faster name is never
a relaxation: the arc is speed-invariant in columns, so every press window
scales as one over the base speed, and a hazard cluster that cleared under
`brisk_runner_v1` by a hair is refused under `swift_runner_v1`. The answer is
the designer's rule below - a shorter silhouette or a taller jump - never a
lowered threshold.
Ramp names currently include `gentle_ramp_v1`, which earns its bonus over
1,800 columns, and `brisk_ramp_v1`, which earns the same bonus over 720
columns. Separate names preserve existing package feel while a faster package
opts into both the new admission arithmetic and consumer pacing.

Jump names: `single_arc_v1`, and `double_arc_v1`, whose air jump is **recovery,
never reach** - it declares the identical single-hop admission arithmetic, so
no authored chunk ever demands both hops, a player who spends the air jump
early is never stranded, and admission stays a one-dimensional existential
over launch columns rather than a search over jump sequences.

Collision-box names: `torso_v1`. v3 renamed this member, because v2's
`collision_policy` carried two unrelated things under one word: the avatar's
torso box, which every press-window proof reads, and the assertion that a
contact ends the run. The box is geometry admission depends on; what a contact
costs is a choice a package makes. Splitting them is what let a package become
survivable without weakening a single proof.

Consequence names: `end_run_v1`, `drain_v1`, and `drain_and_recover_v1`.
`[run.consequences]` answers `hazard`, `pit` and `crush` separately and
explicitly - no source defaults, because a silent default is exactly how a pit
quietly stops being final. `drain_v1` spends one point and leaves the avatar
where it stands, which suits a hazard it runs through; `drain_and_recover_v1`
spends the same point and puts the avatar down on the next legal surface
ahead, which is what a pit or a crush needs because there is nowhere to leave
it standing. Recovery never rewinds earned distance and never skips an
unpassed hazard.

Vitals names: `single_point_v1`, `three_point_v1`, `five_point_v1`, each
declaring only its point count - the one vitals number a refusal and the HUD
both read. `[run.vitals]` is present exactly when some consequence drains, and
both directions are refused (`vitals_without_damage`, `damage_without_vitals`)
on the same principle as the duck triangle.

`hurt_representation` is the third obligation: `drawn_v1` requires a drawn
`hurt` motion in the avatar contract, and `blink_v1` requires its absence.
The game contract holds that visible gameplay requires visual coverage - a
subsystem may not advertise an actor transition without a validated asset or an
explicitly contracted nonvisual representation. `blink_v1` is that contracted
representation, stated rather than assumed: the avatar keeps its running pose
and the consumer blinks it for the immunity window.

**Admission is unchanged and stays exactly as strict.** `reaction_fair_v1`
still proves every hazard avoidable at the base speed. A gauge is forgiveness
laid over a fair track, never a licence to author an unfair one, and no
refusal reads the point count except the two obligation checks above.

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

`runner-track-v4` reuses the platformer map's generation vocabulary for
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

Ground is drawn in a declared **projection**, and `[ground.projection]` states it:
`orthographic_v1` is the only served member and what an absent block means. This
is a correctness rule rather than art direction. **Parallel projection is the
only projection invariant under horizontal translation**: a vanishing point
encodes a fixed camera position, while `auto_run_x_v1` scrolls the ground past
the camera and chunks repeat in arbitrary order, so a converging tile has its
vanishing point slide along with it and has no repeat unit at all. Orthographic
and oblique are both parallel; orthographic - a flat front elevation showing no
top face - is the truthful default for a strict side view.

Three admission checks hold the ground honest, all inside the provider's own
retry attempt so a bad painting re-rolls rather than ending the run.

**Walking-surface coverage.** A top-exposed cell must be painted nearly whole.
Where a solid cell is left transparent the canonicalizer's deterministic
material fallback fills it, and that fallback is built from the guide's own cap
and fill colours - so unpainted ground publishes *as guide material*. This is
the check that catches a part-painted walk surface, which the coverage floor
below it could not: a cell four fifths made of fallback passed the old one.

The floor is not a taste number. Publication grows the painting's own solid
colour a few pixels outward to sit under the rim its alpha feathers away, and
the floor is that same distance read as a coverage, so a cell is admitted
exactly when what it leaves bare is a feathered edge the canonicalizer can
cover rather than an unpainted cell it cannot. The two are written once and
derived from each other.

**Guide residue.** No guide-palette colour may survive above a small share of
the painted region. This catches the other shape of the same failure, where a
provider returns its conditioning image rather than a painting. Alpha checks
cannot see that at all, because every guide pixel is opaque - they measure
alpha rather than authorship.

A share over an area cannot see a line, and the defect that outlived this check
was one. Compositing a feathered edge straight onto the palette base published
a guide-coloured hairline along the row the avatar stands on: 0.805 of the
first opaque scanline, on a tile measuring 0.0075 overall. The fix is at the
cause - the base is for a cell nobody painted, never for the rim of one
somebody did - so the painting is laid down twice, its grown solid core under
its own true-alpha edge.

**Lean consistency.** The diagonal edge family's lean, sampled by horizontal
thirds of the authored body, must fit inside one arc of orientation: two
opposite receding families in one tile are two projection systems. The lean is
the magnitude-weighted circular mean of the doubled edge angles, and the spread
is the smallest arc covering the thirds, because orientation is circular modulo
180 degrees and +87 against -87 is six degrees of disagreement rather than 174.

The claim is deliberately narrow. Iron Petal's twelve shipped tiles spread 7.2
to 59.6 degrees across their thirds while being visibly correct front
elevations, because honest greenhouse detail - a pipe bend against a bracket
chamfer against a hanging vine - moves the measured lean that far on its own;
the same tiles hatched into an opposite-leaning splay spread 76.0 to 84.6, and
the tolerance sits in that gap. Refusing a single receding top face would need a
detector local to the surface run rather than a whole-tile edge statistic.

`oblique_v1` is the reserved second member. It would carry a receding angle and
a depth ratio (cabinet is 0.5, cavalier 1.0), and it is not merely unbuilt: the
canonical raster's alpha must match authored occupancy exactly, cell by cell,
and oblique depth spills into neighbouring cells. Serving it needs a
projection-aware expected mask and a canvas margin past `columns * 64` first, so
the vocabulary admits only what the pipeline can prove.

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

## The encounter: a locomotion override with an actor in it

An encounter is the genre's answer to a boss without breaking the seam rule
that makes it infinite. It is not a scripted stretch of track. It is an
**interlude**: at an authored interval the stream starts feeding one flat
`role = "arena"` chunk instead of drawing from the difficulty band, the fight
plays out over as many copies of it as it needs, and ordinary chunks resume.
The arena holds the seam profile in *every* column, not just its two edges, so
it may be entered anywhere, repeated back to back, and left anywhere. One
authored chunk therefore holds an encounter of any length, and no chunk ever
carries state about what came before it.

For the duration the avatar wears a different **locomotion**. `thrust_v1` is
the whole map from intent to vertical motion, not a modifier on running: held
climbs toward one cap, released falls toward a faster one, and there is no jump
edge, no slide, and no air-jump budget. It rides the same control as the jump -
press to go up - as a held level beside the existing edge, so the verb never
changes and `jump` keeps the edge semantics that stop a held key reading as a
stream of fresh jumps. The avatar's head is clamped at the top of the band,
because the salvo's lane is measured inside the band and an avatar above it
would dodge by leaving.

### Three proofs, offline, before any spend

Admission prices the fight the way it prices a hazard: closed form, from named
profiles, with no simulation and no provider call.

- **The lane.** A salvo of `salvo_shots` shots at `projectile_height_rows` each
  can occupy at most that much of the band, so what is left over is the
  smallest lane any placement can leave. It must exceed the avatar's own height
  plus `lane_margin_rows`. This is a pigeonhole, not a hope.
- **The dodge.** A shot's flight time is `firing_distance_columns` over
  `projectile_speed_columns_per_second`, and crossing the whole band costs the
  locomotion's worst-case traverse - the *climb*, whose cap is the lower of the
  two. The remainder is the reaction slack, and it is held to the same
  `min_hazard_clear_seconds` the placement discipline demands of a hazard. It
  bounds the band from **above** as well as below: a taller band takes longer
  to cross while the flight time is fixed, so a band can be too tall for a boss
  as easily as too short.
- **Winnable.** `hits_to_defeat` at the player's own cadence, plus one last
  shot's flight, must finish inside `salvo_budget * salvo_period_seconds`. The
  proof assumes every player shot lands, so the slack is the miss allowance.

Speeds are measured in the **avatar's** frame. The run carries the avatar and
the boss forward together, so what a player experiences is the closing speed;
measuring anywhere else would prove a number nobody gets. The runtime uses the
same frame, so it plays the fight admission proved.

### What the contract refuses

Every obligation is refused in both directions, exactly as duck/slide and
drain/gauge already are: an encounter with no `fly` motion to wear, a `fly`
motion no encounter can trigger, an arena chunk no encounter is fought over, a
boss catalog no encounter fights, a projectile no role fires, a `shot`
consequence no encounter can deliver, and an encounter whose hits cost nothing.
An arena carrying a hazard or a pickup is refused too: during the fight the
thing to read is the salvo, and a pickup line would sit in the lane the salvo
has to leave open.

A boss is drawn facing **left**. Every other runner actor faces right and is
mirrored by nothing; a boss holds a position against a moving avatar and fires
at it, so its facing is fixed in the artwork rather than at runtime. It may
loom: `height_units` above one player height is expected of a boss and of
nothing else.

The two projectile roles must be drawn separately. One silhouette flying both
ways is a fight in which a player cannot tell their own fire from the boss's,
which is a readability failure the contract can refuse offline instead of
waiting for a review to catch it.

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
clear, collect, hurt (a survivable vitals drain), and death events to named
effects. An effect is realized one of
two ways. `oscillator_sweep_v1` authors waveform, start/end frequency,
duration, gain, and optional strength-driven pitch response at zero provider
cost; the consumer synthesizes it and owns only Web Audio lifecycle.
`generated_clip_v1` authors a verbatim prompt, an exact duration of at least
half a second, optional prompt influence, and the same playback gain and pitch
response; the graph buys it once as `audio/<effect_id>.mp3` through the
`sound_effect_generation` route, admits it on container, duration, and level,
and the consumer decodes and plays it. The bindings are the same either way, so
a cue changes realization without remapping gameplay. The authoring contract
and its gates are in [game-sound-effects.md](../../game-sound-effects.md); the
route's measured boundary is in
[model-eleven-text-to-sound-v2.md](../model-eleven-text-to-sound-v2.md). Iron
Petal keeps five short cues on oscillators, including the jump, where nothing the
route returned was judged usable, and realizes three as generated clips chosen
by ear from auditioned draws: `unit_stalled` on death, a one-second machine
powering down with a metal clunk; `hull_clank` on a survivable hit, a hard hit
on sheet metal; and `seed_chime` on collect, a half-second coin collect named
by its game idiom, with the chain still lifting its playback rate.

The same contract owns what the soundtrack does at the run's edges, in the
vocabulary interactive-music middleware uses: an *action* on the music with a
fade time and a fade curve, posted beside the *stinger* (the effect bound to
the event), and an optional *duck* under a survivable hit. `[music.death]` is
`stop`, `pause`, or `continue`; `[music.restart]` must pair with it as `play`
(the next shuffled track from the top), `resume`, or `continue`; a zero fade is
the arcade hard cut. `[music.hurt]` dips the music to a gain factor, holds, and
recovers. Every value is consumer mixing outside every cache identity. Iron
Petal stops with a 1.2 s exponential fade under the power-down stinger, starts
the next track over 0.5 s on restart, and ducks to 0.4 for a fifth of a second
under the clank. Beat-synced transitions are excluded by the seam rule above.

Music remains the separate optional `runner/soundtrack.toml` catalog and uses
the existing provider-neutral `game-soundtrack-v1` generation path. The runner
recipe adds genre staging to the authored brief: the rhythmic engine begins on
the first beat, short action cells and clear transients preserve forward
motion, and exploration, town-theme, pastoral, cinematic, rubato, ambient, and
long-form orchestral development are explicitly excluded. The runtime shuffles
its declared loop-ready tracks after audio unlock and performs the authored
transitions at the run's edges. Do not let a tempo field into
`game-soundtrack-v1`: it is shared across genres, and the other genres have no
tempo; a runner author expresses BPM inside the creative brief.

## Runtime composition

Successful runner generation emits `sideview-runner-runtime-v10`. Its `ground`
field is the same closed union as the authored track. Atlas mode publishes one
atlas path. Structural mode publishes `cell_px = 64` and an authored-order
`chunks` array whose `segment_id`, image path, columns, and rows must match the
occupancy chunks one for one. The browser preloads those exact image dimensions
and draws the corresponding full raster for every streamed chunk; all physics
continues to read occupancy.

Layer placement preserves the source cover-frame scale after transparent rows
are trimmed, so a sparse upper truss does not expand merely because its empty
lower canvas was removed or because a generated seam bridge changed its repeat
width. Each transparent layer's `vertical_offset` is resolved by the producer
from the raster it received, through the same `resolve_layer_placement` the
platformer uses: a `screen_top` canopy is lifted so the first row every column
spans meets the edge, rather than its sparse vine fringe, and the manifest
publishes the measured fraction with `vertical_offset_source = "measured"`. An
authored override is honoured only when it still seals. Collectibles keep their authored collision cell while
presentation applies per-instance bob, horizontal flip, and a short glint.
Hazards preserve authored height, clamp visible width to the published collision
span, register surface obstacles to the footing line, and receive only a local
readability cue rather than a screen-wide warning. Hazard contact is resolved
per placement rather than per frame: overlap is a level that holds for the
whole crossing, and one prop costs at most one point however long that takes. These are consumer
presentation rules, not authored geometry and not generation prompts.

A survivable package draws its gauge as one capsule bar above the readout
band, in screen space rather than over the avatar: the avatar is pinned to a
fixed screen anchor and never moves, so a bar tracking it would hold still
while costing the downward glance a runner cannot afford. The bar dims with the
immunity window, so a blow that connected reads on the readout as well as on
the avatar. A package whose every consequence is terminal draws no bar, because
a bar that can only read full is a promise about mistakes the player does not
have.

A package that binds the `stage_start` moment is born in an `intro` phase: the
world is built, the avatar stands at its start, and nothing moves while the
generic `fx/moment` system plays the bound cut-in over the HUD — the frame
plate sweeps in, the portrait slides in behind the published mask polygon, the
stripes drift, the lettering (the track's and the game's display names) lands,
hold, tear away. The run-loop leaves `intro` on the system's `fx-released`
event, which the choreography raises as the tear-away begins, so the run starts
under the rip rather than after it. The intro plays once per boot; a restart
after a death goes straight to `running`, because a two-second overlay on every
death is the wrong feel for a runner. A package with no `fx.toml` is born
`running`, exactly as before.

The plate the encounter slams up is the **boss**, not the operator: the moment
announces what has arrived. A generated actor cannot be announced from authored
art, so the portrait takes its identity through a graph edge to the concept
plate this same run drew - `subject = { kind = "actor_concept_v1", actor_id }`,
resolved here to the boss concept node and refused for any other id. The plate
is re-drawn whenever the boss is, because the concept is its cache lineage
rather than a digest of words about it.

An encounter plays over a run that is already going. The boss cut-in does
**not** hold the simulation the way `stage_start` does: the avatar keeps
running over the arena's calm floor while the plate sweeps in, and the
director switches locomotion on the same `fx-released` the run-loop uses for
the intro. A package that binds no `encounter_start` goes straight to the
fight. The sealed order moved with it - the FX system is pinned behind the
avatar rather than behind vitals, because the director both consumes
`fx-released` and emits the `shot-contact` vitals consumes, and the old pin
would have closed a cycle.

Two reads in the director are deliberately undeclared feedback, in the pattern
the avatar already uses: the segment window (to ask which chunk the avatar
stands on, which a window streaming a viewport ahead cannot be wrong about)
and the run phase (to freeze the whole encounter while the run is dead or
holding). Declaring either would seal a cycle.

Keyboard play uses Space or Arrow Up to jump and holds Arrow Down to slide.
Holding the same jump control is what thrusts while a fight is on. Pointer play
divides the canvas into stable zones: the upper 68% jumps, holds thrust, and
restarts after death, while holding the lower 32% holds the slide until every
lower-zone pointer is released. The visible control hint states the lower-zone
mapping only when the manifest admits both a duck profile and slide motion;
pointer capture preserves release when a finger leaves the canvas.

## Machine-checked graph contract

The embedded contract is content-insensitive where content does not change
topology: a changed prompt or reference re-keys node cache identities and
`graph_sha256`, not `topology_sha256`. Adding a segment in structural-ground
mode, a layer, a motion state, a catalog entry, a soundtrack member, or a
generated-clip effect changes the topology and therefore this checked
snapshot. So does a binding-table route, because declared resources are part
of the topology; the `elevenlabs-sound-effect` resource below serves Iron
Petal's generated clips. So does a node type's contract version: the manifest
assembly moved to v8 when the audio block gained the music transitions, which
re-keyed this snapshot with no new node. The checked runner fixture is
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
  "topology_sha256": "c75f676d7f35580a4d63b18ff321dde978774b4838d615f1d3a03f088e6de4f0",
  "node_count": 105,
  "terminal_node_id": "manifest-assemble",
  "operation_counts": {
    "local": 53,
    "image_generation": 38,
    "structured_generation": 7,
    "tool_loop": 2,
    "music_generation": 2,
    "sound_effect_generation": 3
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
      "resource_id": "openrouter-tool-loop",
      "max_in_flight": null,
      "requests_per_minute": null,
      "rate_limit_owner": "none"
    },
    {
      "resource_id": "openrouter-music",
      "max_in_flight": null,
      "requests_per_minute": null,
      "rate_limit_owner": "none"
    },
    {
      "resource_id": "elevenlabs-sound-effect",
      "max_in_flight": null,
      "requests_per_minute": null,
      "rate_limit_owner": "none"
    }
  ]
}
```
<!-- pipeline-graph-contract:end -->

For the exact Iron Petal Unit fixture, the normal graph contains 52 first-pass
provider operations. Provider transport retries and later semantic
regenerations are reported by their owning node and are not extra graph nodes.
Two of those operations are *tool loops*: a bounded episode in which the
placement agent renders, looks, and adjusts before it submits — many model
turns, one operation, one attempt ledger.
Every provider node also publishes one attempt-ledger artifact that binds the exact graph-visible
prompt, records unsuccessful operations neutrally as `not_selected` when the failure stage is not
known, and distinguishes provider, fallback, local, or absent output selection. A selected provider
artifact carries its digest. A cache hit restores that original generation ledger byte-for-byte;
current hit/miss telemetry stays in the execution trace so it cannot perturb downstream cache
lineage.

| Domain | Concrete expansion | Image | Structured | Tool loop | Music | Sound | Local |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| World | 12 segments × (guide + structural paint + canonicalize) - the twelfth is the encounter's arena - one shared generated-apron seam bridge, plus 3 layers × (generate + loop + validate) | 18 | 0 | 0 | 0 | 0 | 28 |
| Avatar | One combined rider-machine concept, 5 motion strips and validations, two whole-silhouette motion-rebase judgements | 6 | 2 | 0 | 0 | 0 | 5 |
| Boss | One identity concept, 3 motion strips and validations, two whole-silhouette motion-rebase judgements; absent entirely for a member with no encounter | 4 | 2 | 0 | 0 | 0 | 3 |
| Catalog | 4 obstacles, 1 collectible, and 2 projectiles, each generated and locally validated | 7 | 0 | 0 | 0 | 0 | 7 |
| Soundtrack | 2 loop-ready tracks and technical validation | 0 | 0 | 0 | 2 | 0 | 2 |
| Sound effects | One generate-and-admit pair per `generated_clip_v1` effect; Iron Petal realizes its collect, hurt, and death cues this way | 0 | 0 | 0 | 0 | 3 | 3 |
| Screen FX | One cut-in frame plate and one portrait plate per bound moment (`stage_start` from authored references, `encounter_start` from the boss's own concept plate), each generated, admitted (mask polygon traced), and reviewed; each portrait placed inside the frame by one tool-loop episode before admission | 3 | 3 | 2 | 0 | 0 | 3 |
| Package | Captured-package barrier and terminal runtime assembly | 0 | 0 | 0 | 0 | 0 | 2 |
| **Total** | **105 nodes** | **38** | **7** | **2** | **2** | **3** | **53** |

## Resolution and admission

The container resolver resolves a declared runner member either alone or
alongside siblings, registers its files into the same exact closure
(missing/orphan/`closure_sha256`), and cross-validates before any spend:

- identity: every runner contract shares the container's `game_id`
  (`cross_game_identity`);
- audio: all eight semantic events bind to declared effects, every effect is
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
