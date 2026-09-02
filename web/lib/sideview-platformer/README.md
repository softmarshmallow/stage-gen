# Side-view platformer runtime

This directory belongs exclusively to the optional browser preview. It is not
the authoritative runtime for generated assets and it is not imported by
`src/stage_gen/components/` or `src/stage_gen/recipes/`.

The current implementation deliberately owns one integration case: horizontal
camera/parallax, a one-dimensional heightmap, scrolling-recipe tile roles,
one-way upper platforms, ladder traversal, vertical camera follow, platformer
movement and gravity, combat, drops, inventory, and portals travelling between
an ordered set of stages. Its scene composition is explicit rather than
free-form: `layers.ts` resolves the canonical sky, distant, midground, terrain,
actors/effects, near-foreground, and HUD stack. `foreground.ts` measures and vertically trims the viewport-edge
overlay, then prepares one premultiplied periodic canvas so foreground
placement and repetition do not depend on paired full-screen sprites. Those
assumptions are useful preview tests, not reusable generation contracts. See
[`docs/scene-layers.md`](../../../docs/scene-layers.md).

## Level Profile adapter

`level-profile.ts` is the engine-neutral classification boundary for authored
`level-profile-v1` data. It validates scene role, orthographic side-on view, player-follow
dead-zone camera behavior, scroll axes, heightfield/one-way traversal, player affordances, and the
explicit encounter, combat, loot, interaction, and transition mechanisms. Validation of the
portable vocabulary is separate from `assertScrollingDemoLevelProfileSupported`, which fail-closes
unless the complete combination is one this demo implements.

`stages.ts` accepts only the current `game-map-book-manifest-v2` block inside a
current scrolling manifest. Every declared map carries a complete profile.
`buildStageBook` joins each profile to an allowlisted static blueprint keyed by
`map_id` and rejects a role, traversal, or mechanism declaration that
contradicts that geometry. A current manifest may omit the optional map book;
that selects the consumer's static stage plan rather than an older map schema.
Layout names, terrain seeds, platform graphs, mob stride, physics numbers, and
camera pixels remain consumer-owned. The map contract does not become a browser
scene graph.

`StageScene` is the explicit composition root. It orders terrain and traversal before population,
combat, and combat feedback, and rebuilds stage-scoped systems at portal travel. This directory
does not discover arbitrary plugins or use role names as hidden mechanism presets.

Layer painter order (`renderDepth`) and physical horizontal motion
(`depthCoefficient`) are independent. The current near foreground uses a 1.8×
screen-velocity coefficient. Its closed-form tile phase compensates for uniform
camera zoom and source texture scale before device-pixel snapping, while its
measured bottom contact remains screen-anchored during vertical camera travel.
The live probe reads Phaser phase, scale, transform, depth, clip, visibility,
and sprite count and is checked against camera-derived motion rather than a
copied planned phase.

`vertical.ts` is the pure geometry boundary. It validates a branching platform
graph, proves fixed-step jump/drop reachability, resolves one-way deck
crossings, clamps ladder motion, selects the vertical camera deadzone, and
builds connected platform paint plans. `scene.ts` owns Phaser objects;
`player.ts` owns the explicit terrain/platform/ladder/air support state machine. Decorative ladder alpha never changes collision.

Decks may share columns as long as their 32px bands do not intersect, so a
route can run above another one and a graph can branch instead of queueing
left to right. A drop route therefore resolves the deck it actually lands on
rather than always naming terrain. Layouts are declared as data
(`ascent`, `gauntlet`, `spires`) and each declares which edges need the air
jump; the builder proves both halves of that claim, rejecting a gate the
grounded jump already clears.

A struck mob turns to look at whoever swung: knockback points away from the
attacker, so facing is its negation, and the wander it resumes runs along that
same heading rather than snapping back on the next update.

Mobs walk under the same terrain rule the player does. Every move a mob makes -
patrol, chase, flee, and the knockback it is shoved through - goes through
`resolveTerrainWalk`, so a column standing above its feet is a wall it stops at,
and a patrol that runs into one turns rather than pressing against it for the
rest of the stage. A mob still walks off a ledge; it simply has no jump and so
no way back up. Previously each of those moves wrote `sprite.x` directly and
`snapFeet` then lifted the creature onto whichever column it had landed in,
which downhill reads as walking off a ledge and uphill as levitating up a cliff.
The chase was the behaviour that made it visible, being the only one that
travels far enough to cross a rise, but a wander lane wide enough would do it
too.

Movement adds a single mid-air jump. `PLATFORMER_AIR_JUMP_VELOCITY` is weaker
than the grounded launch on purpose: 520 clears 82px of rise on its own and the
440 follow-up reaches 154, so a two-tile step is exactly the gap the mechanic
opens. The budget resets on any non-air support.

Terrain is solid in both directions. A descent is a fall handed to gravity by
`resolveTerrainStep`; a rise is a wall, stopped by `resolveTerrainWalk` at the
column face whatever the foot is currently supported by, so the same face
refuses a walk, a jump that has not yet cleared it, and a drift into a cliff
mid-fall. This heightfield steps in whole tiles, so every rise is climbed
rather than walked — which is also why a `PLATFORMER_COYOTE_MS` grace window
exists: without it every jump pressed at a ledge would silently spend the air
jump instead of the grounded one.

`health-bar.ts` draws health under the body it belongs to, in world space rather than in a
screen corner: one flat rounded capsule over a red-to-green gradient, re-anchored to the sprite
every frame so it scrolls, zooms, and travels with the actor. The player and every mob use the
same widget at two sizes, the mob's smaller so several on screen never compete with the player's
own. Fill is a crop of a gradient baked once per size, so the colour under the leading edge is
the reading and a bar at half is the same amber however it got there; a living actor never
drains below one cap's width, and only death empties it. The bars sit at `actorHud` depth -
above the near foreground, because a readout hidden behind the fern its owner walks through has
stopped being one, and below `hud`, so the inventory panel and dialogue box still win. Knockback
moves bodies, so the player's bar is written after the combat exchange each frame and again
after a stage rebuild replaces the player object; a mob owns its own bar and retires it at the
killing blow rather than fading it out with the corpse.

A mob's bar is also revealed by damage rather than by existing: `healthBarRevealedByDamage`
holds it hidden while `hp` is full and shows it from the first blow onward, so a route lined
with creatures is not also lined with full capsules reporting that nothing has happened. The
player's own bar is unconditional - it is the one readout they are entitled to without having
to be hit for it. Defeat stays a separate gate, so the mob still hides its bar at the killing
blow for being dead rather than for being empty.

## Weapon class

`weapon-class.ts` holds one frozen record per published class name, in the same shape the
aggression and critical tables use: the generator names `melee_dps_v1` or `ranged_dps_v1` and the
artwork drawn for it, and every number is here. Before this table those numbers lived in three
files - the swing's damage and reach inline in the scene, its cadence on the controller, and the
bot's engage range restated a fourth time with a comment saying it had to agree. The melee record
reproduces all of them exactly and is pinned by test, so the table is a refactor for every package
already published and a feature only for the ones that name the new class.

Delivery is a discriminated union rather than a nullable projectile block, because a swing has a
reach and no travel and a throw has travel and no reach. `strike.ts` resolves the instant arm as a
pure function over positions; `projectile-flight.ts` resolves the thrown arm the same way, and
`projectiles.ts` holds only the sprite. Vertical reach is a two-arm union for the same reason: a
swing compares feet, and a thrown object is where it is. Mobs stay instant and foot-banded, so
relaxing the rule for the player's shot changes nothing about what can hit the player.

Neither class costs an extra *pose*. `basic_attack` and `skill_cast` are both already required
artwork for any combat-enabled package, so switching class re-renders no character strip. A throwing
class does owe one drawn object: the projectile is its own catalog subject with its own generated
sprite, one image and one review.

Changing class is still not free at the authoring level, though, and deliberately so. The player
catalog declares a closed `equipment` name, and package validation refuses a kit the drawn character
cannot use - a figure carrying a sword cannot be handed a throwing class. Bellweather is that case
and therefore swings.

`developer-kit.ts` is the switcher's vocabulary, and it only ever *selects*. Every class it offers
is a name Python published, every round is an entry the run's own manifest carries, and every
number still comes from the two tables above. It deliberately cannot express a binding the contract
could not have: a throwing kit is offered only when the run actually drew something to throw,
because a runtime that picked a round for you would be authoring `projectile_id`. The override
reaches `resolveWeaponClass` and `installProjectiles` and nothing else, so the parsed gameplay
contract stays the object the closure check validated. `switchDeveloperKit` is the single entry
point the `K` key and the console's buttons both call, and it re-enters the current map rather than
patching the scene - the weapon is read by the controller, the strike resolver, the projectile pool
and the bot band, and re-entry is the one path that rebuilds all four together.

Ammunition is built and not armed. `ammoKind` is null on both shipped records, and the selector,
the spend, the intent gate and the bot's decline are all in place and tested behind it. Arming it
needs a package whose loot rules actually sustain a throw - a class that needs two rounds per kill
against a drop economy yielding a fraction of one per kill is a game that throws twice and then
patrols forever - and loot rules cost nothing to retune.

## Projectile class

`projectile-class.ts` is the weapon table's counterpart, and the split between them is the point of
having both. The **weapon** is the character's business - which pose plays, how long the action
commits, what a blow is worth, how far a policy stands off. The **projectile** is the object's - how
fast it travels, whether it falls, how far it reaches, how big its box is, what its arrival resolves
against, and whether the sprite is aimed, mirrored, or spun. That is why one game can throw a slow
drifting orb and another a flat dart without either inventing a second weapon class.

The generator publishes three names per drawn object and no numbers: a `silhouette`, a `flight`, and
an `impact`. Three fields rather than one conflated class because the graph excludes a field from an
artwork's cache identity when the image model cannot draw it - and half of one string cannot be
excluded, so conflating them would price every gameplay retune as a full re-render.

Orientation is derived from the silhouette rather than authored, because the silhouette is already a
statement about the pixels: only a subject drawn with a leading end can be pointed anywhere, and only
one drawn without a direction can be spun without looking wrong. Nothing is both aimed and spun.

Projectile textures are the one catalog family loaded through `loadTrimmedSprite`. A whole-canvas
texture makes a display size a statement about the canvas, so the subject draws smaller than its
calibration says and rotation pivots on the middle of an empty frame rather than the middle of the
object. Trimming makes the frame the subject, which is what lets the published length mean the drawn
length and the origin mean the object's own centre.

## Floating combat text

`combat.ts` defines the authoritative `DamageResolution`: whether an attempt connected, attempted
and applied damage, HP before and after, and defeat state. `player.ts` and `mob.ts` return that
immutable outcome from the hit that commits health. `scene.ts` forwards the same resolution to
`combat-text.ts`; FCT never reconstructs damage from later HP. Rejected, invulnerable, already-dead,
and zero-applied attempts produce no glyph. A connected nonfatal player hit starts a fixed
invulnerability window; `player.ts` blinks the sprite while leaving movement and traversal live.
Only terminal defeat locks control.

`manifest.ts` parses `combat-text-v1` as an exact block-local `{ schema_version, kind, enabled }`
policy. GameContract v3 manifests carry it explicitly after default materialization. Any manifest
that does not declare the subsystem defaults on for this static gameplay UI. Explicit false
disables it, while malformed declared data throws. Font, palette, timing, pooling, and motion are
deliberately not TOML settings.

`combat-font.ts` commits two faces and proves numeric glyph readiness for both before enabled
feedback starts, and `PreviewCanvas` awaits it before the game boots: a Phaser text object
rasterises when it is constructed, so a number drawn before its face is usable is drawn in a
fallback and stays in it. Fredoka is a text face and carries the EXP stat log. Damage numbers are
set in Luckiest Guy, at weight 400 because that is the only weight it has - a synthesized bold is
the browser's own thickening, and that is a glyph metric decided outside the repository.

The face is chosen by the outline. A number is drawn as a sticker: a saturated core, a light ring
around it, and a heavier dark edge around that, which is two layers per glyph because canvas
strokes text once. How thick those rings may go is a property of the typeface - a stroke eats a
glyph's counters from both sides - and Fredoka's counters close up long before the edge is heavy
enough to read as arcade weight. Every dark edge is drawn below every coloured face, so a
neighbouring number's outline never covers a digit.

The palette is a contrast decision measured against this library's own art. Bellweather is painted
in warm ambers, tans and autumn orange under a blue sky, and a gold number sits at almost exactly
the luminance of the stone it is drawn over as well as of the horizon; magenta is the one
saturated hue the world does not contain, and it steps hard away from both the white ring above it
and every band of the art below it. Damage taken stays red, because which side a number belongs to
outranks its contrast. A critical is its own colour inverted rather than a second palette: a normal
number is its colour inside a white ring, a critical is white inside a ring of that colour, so the
two share a hue and a silhouette and the brightest thing on screen is the biggest hit. The tests
assert the value steps rather than the hexes, because a core-to-ring step of 1.7 is what a gold
number inside a white ring actually was, and it looked perfectly fine on a dark test card.

Size is the other half of the reference and the half that is easiest to under-do. The arcade
reference sets a digit at about four fifths of the player's height: the scale *is* the feedback,
and a tidy number beside a 154px character reads as a footnote however well it is drawn. These
sizes put a cap at just under a third of the player: short of the reference on purpose, because the
reference is one boss taking one combo and this is a hunting map where a dozen creatures die at
once, and at the reference's own scale four simultaneous deaths cover the fight. Every other measurement is a share of
that size -- both edges, the tracking, the arc, the jitter, the drop, and the stack step -- so
moving the size moves the whole number rather than producing a big number sitting perfectly still
inside pixel displacements that no longer fit it. The core is filled with a vertical gradient
rather than a flat colour, applied once per drawn glyph from the text object's own canvas context:
light collects along the top and the hue deepens into the foot, which is the difference between a
digit that reads as a decal and one that reads as an object.

Each world-space number gets a bounded scale punch and local micro-shake, rises, then fades on the
caller-supplied simulation clock. Reduced-motion mode is fade-only; the camera and actors never
shake.

A number is drawn one digit at a time. `combatTextGlyphLayout` lays the row out around its own
center from the advances the renderer measured, and `sampleCombatTextGlyph` displaces each digit
from there: it is invisible until its own beat, arrives oversized and high, and falls into a
resting place that is a shallow arc plus a jitter and a size variance hashed from the event id and
the digit's index. That is the difference between a damage number and a damage effect - one text
object can only pop as a block, while a row of digits arrives left to right with no two of them on
the same line. Every value is displacement around the run's own anchor, so the rise, shake, stack,
and fade are untouched by it, and reduced motion keeps the row while dropping the theatre.

`CombatTextSystem` follows `create -> update -> snapshot -> dispose`. The scene creates one for the
current stage, updates it after authoritative combat, exposes the deterministic snapshot to the
runtime probe, and disposes it before a portal rebuild or scene shutdown. Its active list and
reusable Phaser text pool are bounded, so rapid hits cannot leak objects across a stage. The pool is
keyed by the exact glyph rather than by style alone: a recycled `7` already holds a rendered 7, so
reuse costs no text re-render, which is what makes a glyph-per-digit renderer affordable.

`stages.ts` is the stage plan. One asset directory paints several stages: the
first keeps the run's own terrain seed, later ones salt it and switch platform
layout and mob density. `portal.ts` owns both ends of that travel. The exit
carries the player forward and wraps past the last stage, the entry carries
them back and is inert only on the opening stage, and contact is tested
against the portal's mouth in both axes rather than by column alone. Standing
in a portal is not using it: travel needs a deliberate Up/W press, so a route
can run past a portal, double back through one, or fight beside one without
the stage changing underneath the player. A prompt names the key above the end
that would answer it. An end the player is standing in still starts inert and
arms once they step clear. Travel is applied at the
end of the frame and then finishes that frame in the world that now exists,
because probes read live objects while the layer pass caches its result.

`soundtrack.ts` owns optional catalog audio consumption. It accepts only the
current `game-soundtrack-manifest-v2` block and its matching current map book,
waits for a real pointer or keyboard gesture, and exhausts a deterministic
shuffle bag before refilling it without an immediate repeat. It exposes current
and next stable track IDs to the runtime probe. `stages.ts` projects each
authored map's game-global track IDs and scene travel selects that pool; an
allowed current track continues, while an excluded track switches through the
same gesture-unlocked media element. Omitting the optional current soundtrack
block disables catalog playback; no older catalog shape is interpreted.

Camera deadzone and culling math share Phaser's centered zoom projection, so
world visibility is independent of device-pixel ratio.
The selected world stays inactive until its ladder texture, required four-frame
climb strip, platform materials, and both render groups succeed as one
rollback-safe transaction. A missing traversal asset is surfaced as a load
diagnostic; it never leaves invisible collision or partial graph state, and it
does not roll back independently valid ground paint. Production capture gates
still require both roles and therefore reject a diagnostic-only degraded run.
Activation uses a typed 30px horizontal half-width and is vertically clamped
to explicit deck/terrain endpoints. The distinct typed 32px visual overshoot
does not expand collision; platform reservation covers its visual overhang.

Current run manifests identify a `native`, `ai`, or `chroma` transparency strategy and all
publish canonical alpha-bearing PNGs. The adapter preserves that alpha. A
current v7 manifest selects native provider alpha, AI removal, or explicit
degraded chroma through `transparency_mode`; no missing-strategy manifest is
interpreted. Opaque concept and backdrop assets bypass transparency handling.

## Auto-play

`bot-*.ts` is a bot system rather than an auto-hunt script, and it is layered so the pieces that
would change under a different runtime are separable from the pieces that would not.

`bot-navigation.ts` is the bottom layer and the one everything else defers to. `MovementCapabilities`
states what a character can physically do — speeds, jump impulses, whether a second jump exists,
whether it may climb or drop through — and `buildNavGraph` derives a graph of level standing
surfaces joined by moves the supplied capabilities can actually perform. Terrain lanes come from
authored occupancy, decks and climbable zones from the map's own geometry, and every jump link is
admitted only after `simulatePlatformJump` proves the arc with the same fixed-step integration the
player controller runs. A character with no air jump does not get `double_jump` links, so a rise
that needs one is not somewhere it repeatedly fails to reach — it is somewhere that does not exist.
`navReach` answers cost and opening move for every node in one search, which is why no path is
stored between frames.

`bot-view.ts` is the perception boundary: a plain snapshot with no engine objects in it, so a
behaviour is a function of its inputs. `bot-behavior.ts` is the kernel — goals, proposals, explicit
serialisable memory, and a priority auction that picks one winner per frame with roster order as the
tiebreak. `bot-hunter.ts` is the first profile: stand down, heal, engage, collect, pursue, patrol.
`bot.ts` holds the two frames of state the pure functions need handed back and resolves who is
driving. `bot-adapter.ts` is the only file that reads scene vocabulary.

Where the bot stands is the weapon class's answer, not the hunter's. `BotWorldView` carries a
`weaponBand` - engage distance, approach distance, back-off floor, vertical tolerance, and whether
the class spends a round - projected by the adapter from the same record the scene resolves damage
from. `engageBehavior` reads it and knows nothing about which class it is holding: a swinging class
has a floor of zero so its back-off branch can never fire and it walks all the way in exactly as it
always has, and a throwing class stands off and steps away from anything that closes inside its
floor. A class that spends a round it is not carrying declines outright rather than proposing an
attack it cannot make, because engage outranks every other behaviour and a proposal that always
wins and never acts is a run that stands still with nothing logged.

Targeting also asks the ground. Distance and foot level say a creature is worth attacking and say
nothing about what stands between the two, so a creature on a ledge satisfied both while the ledge
face swallowed every throw - and because engage outranks pursuit, the run stood there firing into
the wall forever. `lineOfFireClear` samples the terrain profile per column at the flight height and
declines when it is blocked, which is what lets pursuit take the frame and walk the character
somewhere it can shoot from. A swing declares no release height and skips the test, because a swing
has no flight path. Measured over a minute of unattended play on the same route: 25 kills with the
test against 6 without it, and a worst stall of seven seconds against forty-nine.

Growth is by addition. A new behaviour is a value in a roster; a new traversal move is a link rule
and a steering branch that no behaviour mentions; a different character is a different
`MovementCapabilities`; a different personality is a `BotProfile`; switching a behaviour off is
`botProfileWithout`, because a roster is a list and no behaviour carries an enabled flag.

Nothing in the system reads a clock it was not handed or a random number, so a replayed view
sequence replays the same intents. Auto-play is on for an ordinary preview and off under fixed-frame
automation, where a second actor would make the transcript a recording of the bot.

## Canvas-only still capture

The frame-zero still capture that used to live here is gone with the gameplay
harness: its fixture wrote the retired scrolling manifest V7, which the
prepared-only scene cannot boot. Capturing a still from a published package
needs a new harness written against `prepared-game-runtime-v10`.

Pure operations such as media inspection, alpha conversion, and generic grid
slicing may eventually move to reusable components. Phaser texture
registration, camera behavior, scene composition, and gameplay remain here or
in another consumer adapter.
