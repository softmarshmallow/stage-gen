# Optional web preview adapter

`web/` is the first consumer of generated output. It provides run controls,
artifact inspection, progress events, and a browser scene for a 2D scrolling
recipe.

Its assumptions are intentionally local:

- horizontal follow camera and parallax;
- one-dimensional terrain heightmap and fixed tile roles;
- side-view character movement, one-way upper platforms, ladder traversal,
  gravity, combat, drops, and portals;
- an allowlisted Level Profile adapter for the bundled social-hub and combat-field demo;
- browser texture registration and a fixed preview viewport.

The preview's typed semantic composition rules, canonical depth stack, ground
baseline, and zoom-safe parallax placement are documented in
[Browser scene-layer contract](scene-layers.md). Generated `z_index` values do
not directly become Phaser depths.

These belong in `web/lib/runtime/` and preview routes. They must not leak into
`src/stage_gen/components/`, the public CLI contract, or provider adapters.

The server-only adapter invokes the authoritative Python command from the
repository root. Its default launch is exactly:

```text
uv run stage-gen generate --recipe scrolling-preview --transparency <mode> <prompt>
```

The process API receives an executable and argument array with `shell: false`;
prompt text is never interpolated into a command string. The optional
`STAGE_GEN_EXECUTABLE` override accepts only `uv`, `stage-gen`, `stage-gen-py`,
or a normalized absolute path whose basename is one of those values. Output is
rooted at `STAGE_GEN_OUT_DIR` (default `out/`) for both processes. The adapter
consumes manifests, run summaries, SSE progress, and confined artifacts through
server routes. Browser code never receives provider credentials.

The Generate view exposes a three-way transparency strategy selector. `native`
is the default and asks GPT Image 2 to create alpha directly. `ai` is the
explicit compatibility path that generates opaque art and then calls FAL
background removal. `chroma` is the explicit degraded local-keying path.
Launches and per-asset retries preserve that choice; failures do not silently
change strategies.

The exact current `recipe_run_v3` summary must declare
`input.transparency_mode`. For `native`, `ai`, and `chroma`, the pipeline's
canonical image artifacts are already transparent PNGs, so the preview loads
their alpha normally and never performs runtime chroma keying. A missing or
invalid strategy fails closed because the adapter cannot reproduce the run's
generation policy.

The HTTP start body is `{ prompt, transparency_mode }`, where
`transparency_mode` is `"native"`, `"ai"`, or `"chroma"` and omitted means
`"native"`. The web adapter treats the returned run tag as opaque; it does not
assume equal prompts share a cache entry across strategies.

Static third-party background music is not part of this adapter. Generated
music is a headless component artifact and may be previewed only after its
provenance and media contract are present. The one current public projection is
`game-soundtrack-manifest-v2`: a game-global, gesture-gated shuffle bag whose
track identities remain owned by the game catalog. The current authored map
book narrows that catalog to each map's referenced pool; travel keeps an
allowed current track or switches when the destination excludes it. See
[Authored game soundtracks](game-soundtrack.md).

The browser gameplay implementation remains optional. All Node and TypeScript
code is confined to `web/`; the headless implementation is Python.

## Level Profiles and component topology

Authored [`game-map-v2`](game-maps.md) sources publish one complete
`level-profile-v1` per map. The profile classifies view projection and viewpoint, camera tracking
and framing, traversal capabilities, and gameplay mechanisms. It does not publish Phaser scene
objects or geometry.

The preview consumes that contract through a narrow adapter:

1. The manifest parser requires parent scrolling manifest V7 and, when `map_book` is declared,
   accepts only exact `game-map-book-manifest-v2`; every entry requires a complete Level Profile.
2. `level-profile.ts` validates the portable taxonomy and separately checks the complete profile
   against the scrolling demo's allowlisted support matrix.
3. `stages.ts` joins the profile to a consumer-owned static blueprint with the same `map_id` and
   rejects semantic/geometry contradictions.
4. `StageScene` remains the composition root for terrain, traversal, population, combat, feedback,
   and portal lifecycle.

Map identity therefore selects only known demo geometry. The Level Profile supplies scene role and
mechanism semantics; neither one turns the Python core into a side-scrolling action-RPG engine.
Layout names, terrain seeds, collision, physics constants, spawn-point projection, and camera
pixels remain inside the browser adapter. A missing profile cannot produce scrolling-demo
capabilities, and a malformed, unsupported, or contradictory current projection fails closed.

## Vertical gameplay adapter

The model demo selects a reserved branching graph before placing props or mobs.
The approved seed's opening stage owns columns `19..58`, disjoint from
opening-encounter columns `0..13`. Its ascending spine is launch `[1280,1664]`
at y `528`, transfer `[1728,2112]` at y `464`, bridge `[2176,2560]` at y `400`,
and summit `[2624,3008]` at y `336`. Two further decks are stacked over that
spine — a ledge `[2304,2560]` at y `208` and a cap `[2688,2944]` at y `144` —
and a forward chain continues past the summit at y `336`, `208`, and `208`.
Each body/cap is connected terrain-depth paint; the one decorative summit
ladder renders at prop depth on x `2976` and connects the summit to terrain
y `592`. Geometry, not image alpha, is authoritative.

Decks may share columns while their 32-pixel bands stay disjoint. That is what
makes a branch possible: a route can run above another one instead of queueing
left to right, and a drop route resolves the deck it actually lands on rather
than always naming terrain.

Along the spine every adjacent rise and gap is 64 pixels. With the runtime's
shared 30Hz semi-implicit physics (520px/s jump, 1500px/s² gravity, 540px/s
run), a rising deck is crossed on step 15 after 270 horizontal pixels; each
jump therefore has 206 pixels of range margin. The jump-only chain reaches all
four tiers without the ladder. Two edges into the stacked branch are 128-pixel
rises, past the 82-pixel grounded apex and inside the 154-pixel double-jump
apex, so the air jump is required rather than decorative; the graph builder
rejects any edge declared as a gate that a single jump already clears. The
ladder is a direct safe shortcut, while Down+Space exposes drop-through
recovery below every platform source column.

Ladder activation uses a typed 30-pixel horizontal half-width and is vertically
clamped to the explicit deck/terrain endpoints. The approved 80x320 raster has
a separate typed 32-pixel visual overshoot above and below the 256-pixel climb
span; visual bounds never expand the climb zone. Ladder texture, the required
four-frame `character_climb` strip, platform materials, both render groups,
graph routes, reservations, and collision commit as one transaction; any
failure rolls everything back and surfaces an asset error.

Player support is exactly one of `terrain`, `platform`, `ladder`, or `air`.
Terrain is solid in both directions: a descending column is a fall resolved by
gravity rather than a snap onto the new surface, and a rising column is a wall
that stops horizontal motion a pixel short of its face. Every step in this
heightfield is a whole tile, so the only way up is a jump — the grounded jump
clears 82 pixels against a 64-pixel step, and the two-tile faces the route
crosses need the air jump. A 90ms coyote window keeps a jump pressed at a ledge
a grounded jump. One mid-air jump is available between supports at 440px/s and
resets on any non-air support.
Up enters the summit shortcut from terrain; Down enters from its owning deck.
While attached, gravity and horizontal movement are suppressed, releasing the
vertical key holds position and pauses the deterministic rear-facing/no-flip
climb loop, and Space jumps off. Down+Space on a deck drops through when no
ladder entry applies. The camera follows feet through a
zoom-aware screen deadzone from 420 to 528 pixels and clamps world scroll Y to
`[-512, 0]`. Its projection uses Phaser's centered camera origin:
`screenY = originY + (footY - scrollY - originY) * zoom`; culling uses the
matching zoomed half-extents around `scroll + viewport/2`, not `scroll` as the
world-view top-left. On profiled maps, horizontal follow holds camera X while
the player remains inside the 37.5%-62.5% viewport soft zone, advances only when
the player crosses a boundary, and applies the same zoom-aware projection and
center-origin world clamping. Social-hub profiles keep vertical scroll at zero;
combat-field profiles enable the bounded vertical follow described above. HUD
and near-foreground remain screen-composited.

## Stages and portals

One asset directory paints the ordered maps in the exact current map-book V2
projection. Each `map_id` joins to one allowlisted browser blueprint; the
authored order and display names are preserved. The first hunting map keeps the
run's terrain seed, while later hunting maps salt it and select their own
platform layout. Textures, animations, the inventory HUD, and the player's
health bar are loaded once and survive travel; terrain, platforms, props, mobs,
drops, portals, and the player controller are rebuilt.

Both portal ends are live. The exit carries the player forward and wraps past
the last stage; the entry carries them back and is inert only on the opening
stage. An inert end is drawn exactly as its art was authored and simply does
not fire; dimming it made the first thing on screen read as a broken asset. Arriving through one end places the player at
the matching end of the destination. Contact is tested against the portal's
mouth in both axes, so a deck that merely shares the portal's column is not the
portal, and an end the player is standing in starts inert until they step
clear.

Entering is a deliberate press of Up or W, not a tripwire. Standing in the
mouth raises a prompt naming the key and nothing else happens, so a route may
run past a portal, double back through one, or fight beside one without the
stage changing underneath the player; the press is edge-triggered, so holding
the key cannot re-enter the end it just came out of.

Travel is applied at the end of the frame that triggered it and then
finishes that frame in the new world, so one frame never reports a mixture of
both. Each transition emits `stage-advance` and `stage-enter` and dispatches a
`stage-advance` window event carrying the source and destination stage.

## Mob movement

Mobs are bound by the same heightfield rule as the player: a terrain column
standing above their feet is a wall. Patrol, chase, flee, and knockback all
resolve through it, so a mob walks off a ledge but never up one — it has no
jump, and the shelf it spawned on is the ground it fights on. A patrol that
meets a face turns around instead of pressing into it. Reaching high ground is
therefore a real way to break contact, and a mob held at the foot of a rise
keeps facing the player standing above it rather than turning away from a fight
it cannot reach.

## Hunting-ground population director

A `game-contract-v3` run may publish `gameplay.mob_population`. The preview
treats that block as an authored population contract, not as presentation metadata. Each hunting
stage selects its
`map_id`, intersects every spawn zone's half-open column range with flat walkable terrain, removes
vertical reservations, and hands the remaining columns to a pure `MobPopulationDirector`.

The director performs an initial fill and then maintains each zone's target population. A killing
blow emits one idempotent death notification, immediately opens one vacancy, and schedules one
respawn ticket in simulation time. Eligible tickets are processed in stable order under the
authored spawn cadence and batch budgets. A failed placement keeps the ticket and retries after
`retry_delay_ms`; it never busy-loops or silently spawns on top of the player. Weighted spawn-table
selection and respawn variance use a run/map/zone-seeded PRNG, terrain candidates are sorted, and
the scene assigns monotonic instance IDs. The same transcript therefore produces the same
population trace without `Math.random()` or wall-clock timers.

Live actors and pending spawn reservations count against `population_cap`. Per-archetype
`min_alive` requirements are satisfied before weighted selection, and `max_alive` remains a hard
ceiling. Offscreen and distance policies are checked against the current camera and player before
a reservation is issued. A mob keeps its home-zone ownership if it chases, and its authored patrol
radius and pursuit leash bound movement around that home lane.

Portal travel disposes the director, reservations, and respawn tickets before the stage's actors
are destroyed. No timer or population state survives map teardown. The runtime publishes a
per-zone snapshot with alive, reserved, scheduled, and effective counts, per-archetype counts,
reservations, respawn tickets, and retry attempts in the scene probe. A declared population block
is authoritative. Its map IDs must exactly equal the current map-book V2 entries whose Level
Profile declares `encounter_model = "continuous_population"`; missing, duplicate, or unexpected
entries fail during local resolution, final manifest composition, and scene boot. A game with no
population policy therefore cannot be paired with a current combat-field book.

## Floating combat text

Floating combat text (FCT) is a stage-scoped presentation component, not a second combat
authority. Both player and mob damage paths return one immutable, runtime-only
`DamageResolution` containing `connected`, `attemptedAmount`, `appliedAmount`, `hpBefore`,
`hpAfter`, and `defeated`. Those camelCase names are internal TypeScript fields, not persisted
manifest keys. The scene passes that resolution directly to FCT at the same hit edge that commits
health. It never infers a number later by observing mutable HP or an animation state. Misses,
invulnerability rejections, already-defeated targets, and resolutions with zero applied damage
emit nothing; overkill displays only the amount actually removed.

`game-contract-v3` publishes the block-local policy:

```toml
[gameplay.combat_text]
schema_version = 1
kind = "combat-text-v1"
enabled = true
```

Version 3 materializes that exact enabled block when the author omits it, so the default is visible
in canonical game data and manifest v7. `enabled = false` disables the feedback and clears any
active glyphs. A scrolling manifest that declares a game contract must carry the exact V3
projection and its `gameplay.combat_text` block; omission or malformed content fails the current
manifest envelope. The standalone consumer resolver defaults an entirely absent game policy on,
but it does not admit an older game-contract schema.

The policy intentionally stops at on/off. Presentation remains a static part of this demo:

- outgoing damage uses warm ivory-gold `#FFF0A6`; incoming damage uses coral `#FF6B6B`;
- both use a deep `#24110D` five-pixel outline and bold, bundled Fredoka, with rounded-display
  system fallbacks;
- the glyph starts with a short scale punch, applies at most two pixels of deterministic local
  micro-shake, rises 32 world pixels, and fades during a 640ms lifetime;
- shake affects only the glyph. It never moves the actor or camera;
- `prefers-reduced-motion: reduce` retains the number and fade while removing shake, displacement,
  and scale animation.

The bundled face is loaded before enabled combat feedback starts and must prove usable numeric
glyphs. The text is world-space UI anchored above the struck actor, above near-foreground content
and below screen HUD. Incoming and outgoing hits use distinct directions but the same deterministic
caller-supplied simulation clock; no random offsets, Phaser tweens, wall-clock timers, or camera
effects enter the result.

Lifecycle is explicit: `buildStageWorld` creates the system, the fixed gameplay update samples it,
the runtime probe publishes its snapshot, and stage teardown disposes every active and pooled
Phaser object before portal travel rebuilds the next world. Scene shutdown is idempotent. The
active set and reusable pool are both bounded at 24 by default; a pathological burst recycles the
oldest entry so new combat feedback remains visible without unbounded object growth.

## Health readouts

Health is drawn under the body that owns it rather than in a corner of the
screen: one flat rounded capsule over a red-to-green gradient, anchored to the
actor in world space so it scrolls, zooms, and travels with them. The player and
every mob share the widget at two sizes, the mob's smaller, so a fight reads the
same way from both sides without the two competing. The fill is a crop of the
gradient, so the colour under its leading edge is the reading — a bar running out
green is healthy, one guttering at red is a body about to drop — and half a bar
is the same amber whether it got there in one blow or four. A living actor never
drains below one rounded end's width, so nearly dead still looks different from
dead; only death empties the bar, and a mob's is retired at the killing blow
rather than fading out with the corpse. The bars paint above every world layer,
including the near foreground the actors walk behind, and below the inventory
panel and dialogue box, which remain screen furniture.

## Village hub

A current game-directed village run publishes the exact village manifest V2
block and nine further `runtime_assets` roles. The same scrolling manifest V7
also carries the exact map-book V2 projection. The scene requires these sources
to agree: a book for a village run contains exactly one `social_hub` map, while
a village-less run contains none. An asset/book mismatch fails boot instead of
constructing an empty town or silently changing map order. Its per-asset grids
and runtime roles are the
[village hub asset contracts](spec/asset-contracts.md#village-hub-opt-in-family).

The bundled map book opens with `village-hub`, followed by the three authored
combat maps. Portal semantics use that exact order: the entry is sealed on the
first map, the village exit leads to the first hunting ground, and the final
hunting exit wraps back to the village. The village blueprint has a non-zero
terrain salt; zero remains reserved for the first hunting map's generated
terrain.

A village stage is flat and has no vertical features. It builds a constant
heightmap, runs no platform-graph transaction, places no ladders or upper decks,
and spawns no mobs at all — the mob loop is skipped outright rather than strided
to find nothing. It places the run's village fixture sheet through the same
per-cell path the obstacle sheets use, and stands its residents on the ground
between the two portals.

Resident placement is deterministic and pure, so the town looks the same on
every visit and a probe can assert it without a screenshot. Only flat columns
are candidates, under the same slope test obstacle and mob placement already
use, and reserved columns are skipped through the same gate, so nobody is placed
under a deck or across a ladder axis. Six columns at each end are excluded: the
portals stand at column 3 and at `last - 4`, each roughly two tiles wide and 3.6
tiles tall, and a resident inside a portal mouth would be overlapped by its art
and close enough that the talk prompt competes with the stage-advance trigger.
The rest are spread evenly by candidate index rather than by column, so a
heightmap whose flat ground is bunched at one end still yields residents the
player walks past one at a time. A town with fewer candidates than residents
returns fewer placements; two residents are never stacked on one column.

Each resident is anchored feet-down on the terrain surface at content depth and
drawn from its one-cell, forward-facing still. The runtime registers no
animation and does not mirror front-facing artwork. A world-space name label is
placed above the one displayed frame; mobs remain independently animated.

Drawn size comes from the still's required head-matched `scale_reference`
against the player's required idle reference. It does not normalize the whole
portrait canvas to a guessed height, and there is no approximate-size fallback:
a missing or stale measurement fails the current manifest/runtime closure.

Talking is a separate control from every existing one. Within 96 world pixels —
one and a half tiles — a `▲ Talk` prompt appears above the nearest resident in
range, and only ever above one of them; ties resolve to the earlier slot so a
player standing between two residents does not watch the prompt flicker. **`E`
or `Enter`** opens the dialogue box on that resident's first line, each further
press advances one line, and the press after the last line closes it. `Up`/`W`
is climb and `I` is inventory, so neither is reused. The box is screen-fixed at
HUD depth across the bottom of the viewport and shows the speaker's name and one
line, wrapped to the panel rather than truncated because the recipe's 160-
character line overruns one row at that size and a line clipped mid-word is
indistinguishable from a generation fault in a capture. While the box is open
the player's input is gated — no movement, no attack — rather than a panel being
drawn over a still-playable game. A resident whose run published no lines never
opens the box at all, so the gate cannot latch on somebody with nothing to say.

Probes report the stage kind on every stage and, on a village, the settlement
name, one snapshot per resident (slot, name, world position, and whether they
are the current interaction target), and the dialogue box's open state, speaker,
line, line index, and line count. That is deliberate: the hub is assertable in
the gameplay harness without a screenshot, and the talk prompt's visibility is
the same condition a probe reads.

This adapter draws only what a validated run publishes. Nothing in this section
is a review, approval, or publication verdict for generated media.
