# Scrolling-preview runtime

This directory belongs exclusively to the optional browser preview. It is not
the authoritative runtime for generated assets and it is not imported by
`src/stage_gen/components/` or `src/stage_gen/recipes/`.

The current implementation deliberately owns one integration case: horizontal
camera/parallax, a one-dimensional heightmap, scrolling-recipe tile roles,
one-way upper platforms, ladder traversal, vertical camera follow, platformer
movement and gravity, combat, drops, inventory, and portals. Its
scene composition is explicit rather than free-form: `layers.ts` resolves the
canonical sky, distant, midground, terrain, actors/effects, near-foreground,
and HUD stack. `foreground.ts` measures and vertically trims the viewport-edge
overlay, then prepares one premultiplied periodic canvas so foreground
placement and repetition do not depend on paired full-screen sprites. Those
assumptions are useful preview tests, not reusable generation contracts. See
[`docs/scene-layers.md`](../../../docs/scene-layers.md).

Layer painter order (`renderDepth`) and physical horizontal motion
(`depthCoefficient`) are independent. The current near foreground uses a 1.8×
screen-velocity coefficient. Its closed-form tile phase compensates for uniform
camera zoom and source texture scale before device-pixel snapping, while its
measured bottom contact remains screen-anchored during vertical camera travel.
The live probe reads Phaser phase, scale, transform, depth, clip, visibility,
and sprite count and is checked against camera-derived motion rather than a
copied planned phase.

`vertical.ts` is the pure geometry boundary. It validates a four-tier branching
platform graph, proves fixed-step jump/drop reachability, resolves one-way deck
crossings, clamps ladder motion, selects the vertical camera deadzone, and
builds connected platform paint plans. `scene.ts`
owns Phaser objects; `player.ts` owns the explicit terrain/platform/ladder/air
support state machine. Decorative ladder alpha never changes collision.
Camera deadzone and culling math share Phaser's centered zoom projection, so
world visibility is independent of device-pixel ratio.
The selected world stays inactive until its ladder texture, required four-frame
climb strip, platform materials, and both render groups succeed as one
rollback-safe transaction. A missing traversal asset is surfaced as a load
error; it never leaves invisible collision or partial graph state.
Activation uses a typed 30px horizontal half-width and is vertically clamped
to explicit deck/terrain endpoints. The distinct typed 32px visual overshoot
does not expand collision; platform reservation covers its visual overhang.

New run manifests identify an `ai` or `chroma` transparency strategy and both
publish canonical alpha-bearing PNGs. The adapter preserves that alpha. Pixel
keying is a compatibility path only for legacy manifests with no strategy;
opaque concept and backdrop assets bypass either path.

Pure operations such as media inspection, alpha conversion, and generic grid
slicing may eventually move to reusable components. Phaser texture
registration, camera behavior, scene composition, and gameplay remain here or
in another consumer adapter.
