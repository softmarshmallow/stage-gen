# Scrolling-preview runtime

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

`combat-font.ts` loads the bundled Fredoka face and proves numeric glyph readiness before enabled
feedback starts. Outgoing values are ivory-gold, incoming values coral, and both use a deep outline.
Each world-space glyph gets a bounded scale punch and local micro-shake, rises, then fades on the
caller-supplied simulation clock. Reduced-motion mode is fade-only; the camera and actors never
shake.

`CombatTextSystem` follows `create -> update -> snapshot -> dispose`. The scene creates one for the
current stage, updates it after authoritative combat, exposes the deterministic snapshot to the
runtime probe, and disposes it before a portal rebuild or scene shutdown. Its active list and
reusable Phaser text pool are bounded, so rapid hits cannot leak objects across a stage.

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

## Canvas-only still capture

Build once, then capture the frame-zero route overview from the production
server. The command targets the Phaser canvas element itself, validates a clean
runtime probe, loaded traversal roles, at least three visible tiers plus one
ladder, one fully visible player and live mob at a minimum 64px projected
height, a fully visible portal and pickup, the foreground safe band, and the
HUD's 24px margin. Frame zero stages those real runtime subjects on the three
lowest distinct platform elevations, then restores their exact gameplay state
before frame one. The overview camera frames those three decks and the ladder
rather than the whole graph, because a branching layout can run far above and
past the route and fitting all of it would shrink every subject the still
exists to show. It writes an exact 1280x720 PNG and adjacent JSON evidence under
the ignored root report directory; the preview header, browser chrome, and
Next development overlay cannot enter the element screenshot.

```sh
cd web
bun run build
bun run gameplay:still -- \
  --tag whimsical-storybook-fantasy-6fa8e3e1-ai \
  --output output/playwright/whimsical-storybook-fantasy.canvas.png
```

Pure operations such as media inspection, alpha conversion, and generic grid
slicing may eventually move to reusable components. Phaser texture
registration, camera behavior, scene composition, and gameplay remain here or
in another consumer adapter.
