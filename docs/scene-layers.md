# Browser scene-layer contract

> **CURRENT consumer contract.** The inference rules below remain executable
> for manifest V7. The ratified
> [Authored map-generation contract](spec/game/map-generation-contract.md)
> makes layer plane and order explicit per map; the implementation cutover will
> remove browser inference from opaque/parallax thresholds and select each
> map's own generated layer bundle.

The optional Phaser preview composes generated art through a typed semantic
layer contract in `web/lib/runtime/layers.ts`. Generation still publishes the
portable `id`, `z_index`, `parallax`, and `opaque` fields; the browser adapter
validates those fields and resolves their complete presentation contract before
creating a texture. A manifest may carry the same resolved contract as
`scene_layer`, but it must match the adapter's canonical result exactly.

This is a browser-consumer rule. It is not part of the Python component or
provider APIs.

## Canonical stack

The order is back to front. Depth bands leave room for multiple layers of the
same semantic kind without crossing another kind.

| Kind              | Coordinate space | Depth band | Placement                      |
| ----------------- | ---------------- | ---------: | ------------------------------ |
| `sky`             | screen           |          0 | opaque viewport cover          |
| `distant`         | parallax         |        100 | ground-baseline viewport cover |
| `midground`       | parallax         |        200 | ground-baseline viewport cover |
| `world-terrain`   | world            |        500 | world grid                     |
| `actors-effects`  | world            |        700 | surface/world anchors          |
| `near-foreground` | parallax         |       1200 | viewport-edge contact overlay  |
| `screen-hud`      | screen           |       2000 | fixed screen anchors           |

Actor content uses stable slots inside the actors/effects band: portals 720,
props 740, mobs 800, items 850, player 900, and effects 950. HUD content begins
at 2000.

## Required semantics

Each resolved layer has an explicit kind, coordinate space, anchor, baseline,
`renderDepth`, `depthCoefficient`, repeat and cull policies, opacity and blend
modes, safe bounds, and placement mode. `renderDepth` is painter order only;
it cannot affect motion. `depthCoefficient` is horizontal screen velocity
relative to the gameplay plane; it cannot affect painter order. The runtime
rejects duplicate ids, a missing or ambiguous sky, invalid parallax ranges,
generated art bound to gameplay/HUD kinds, or an explicit contract that
differs from canonical placement.

The sole opaque layer is `sky` with coefficient 0. Transparent layers at
`0 < parallax <= 0.5` are distant, those at `0.5 < parallax <= 1` are
midground, and those above 1 are near foreground. This preserves old manifests
while removing `z_index` arithmetic and free-form placement from the renderer.
The portable `parallax` value maps to `depthCoefficient`; the current preview
foreground intentionally declares `1.8` so it reads as a physical near plane.

`repeat-x-seam-overlap` remains an explicitly temporary legacy preview
fallback for a distant or midground alpha layer only when no verified loop artifact
exists. Near foreground never uses that two-sprite fallback. It is converted
at load time into one premultiplied overlap-add canvas with overlap `F=256` and
period `P=W-F` (`sourceWidthPx - 256`). Columns `F..P-1` are copied
byte-for-byte. Columns `0..F-1`
combine source head and tail pixels with exact complementary integer weights;
the alpha channel is weighted first and RGB is combined in premultiplied
space. The result is one periodic TileSprite, so two viewport-wide foreground
copies can never ghost over one another. Runtime preparation does not modify
the source artifact.

Opaque layers use ordinary `repeat-x` without a partner. A selected verified
repeat unit uses its exact declared period and makes any legacy fallback
ineligible.

## Grounding and camera transforms

For the 1280×720 preview, the world ground baseline is y=720. Distant and
midground covers use that world baseline. The full-width foreground art is a
viewport-edge overlay, not a local collision surface: following the player's
changing terrain height would make the strip float.

The foreground loader measures pixels with alpha greater than 64. It retains
the full source width, trims only transparent rows, records raw painted bounds,
records the bounds of rows covering at least 25 percent of the width as
meaningful content, and finds the contiguous dense contact strip at the bottom. For the
approved 1280×720 source, the last painted contact row is source y=653. The
runtime places that measured row at screen y=704, caps uniform source scale at
0.75, clips at screen y=720, and keeps meaningful foreground coverage at or
below y=540. Thus y<540 remains the actor-safe lane. These values are explicit
scene-context inputs rather than inferred from a copied safe-bounds rectangle.

Phaser uses one uniform camera zoom around the viewport centre.
Screen-composited objects use inverse zoom for position and scale, so their
projected safe bounds remain integer screen pixels at zoom 1 and at the
deterministic encounter zoom. Legacy distant/midground layers retain their
existing source-phase behavior. For near foreground, with camera X `C`, zoom
`Z`, coefficient `K`, screen pixels per source pixel `S`, source repeat period
`P`, and device-pixel ratio `D`, the closed-form phase is:

```text
projectedCameraTravelScreenPx = C * Z * K
rawPhaseSourcePx = mod(projectedCameraTravelScreenPx / S, P)
phaseSourcePx = round(rawPhaseSourcePx * S * D) / (S * D)
```

Rounding that reaches `P` wraps to zero. Positive camera X produces positive
TileSprite sampling phase, so painted features move left: their signed screen
displacement is `-delta(C) * Z * K`. The current `K=1.8` is therefore exactly
1.8 times terrain speed regardless of viewport scale, zoom, or DPR. This is an
absolute pose function, not an accumulator, so hidden updates and repeat
re-entry cannot drift. The exact period remains `P=W-F=1024` source pixels.

Horizontal physical depth deliberately does not move this asset vertically.
`scrollY` contributes neither phase nor screen Y because the foreground is a
bottom-contact framing overlay, not collision terrain. Its one TileSprite is
inverse-zoomed around the viewport centre, preserving contact y=704, clip
y=720, and the actor-safe y<540 lane while the camera follows upper tiers.

`SceneProbes.sceneLayers` is built after each transform update from live Phaser
objects rather than from the planned layout alone. It reads position, scale,
display bounds, origin, Phaser scroll factors, tile phase and scale,
visibility, render depth, texture frame dimensions, viewport clip, and the
number of live TileSprites using that layer texture. A foreground probe derives
`observedPhaseScreenPx` from the live tile phase and live source scale and
exposes the coefficient and projected camera travel separately. Probe creation
recomputes the canonical physical phase from camera state and rejects a live
transform, phase, texture, clip, or sprite count that diverges; the foreground
count must be one and Phaser scroll factors remain `(0,0)`.

Pure raster tests prove the exact complementary weights, premultiplied alpha,
byte-preserved middle band, local seam gradients, and `W-F` period. Layout
tests cover 1280×720 and 960×540, zoom 1/1.2, DPR 1/1.25/2/3/4, negative and
long camera traversal, exact wrap, and periodic re-entry. The 900-frame browser
replay includes the normalized live foreground probe in every transcript row,
independently recomputes physical phase from camera and live scale, and checks
per-step plus cumulative 1.8× displacement before comparing transcripts and
bounded canvas hashes in two fresh browser contexts.
