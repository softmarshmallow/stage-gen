# Scrolling-preview terrain sheet

This is a recipe contract for the optional side-view scrolling preview. It is
not a required asset family for every `stage-gen` pipeline and it does not make
tile coordinates, gravity, or a horizontal camera part of the reusable
component contract.

## Sheet geometry

- Output: `tileset_<tag>.png`.
- Recipe-normalized canvas: 2400 x 800. The deterministic browser-demo
  fixture uses the equivalent 384 x 128 delivery size; both preserve the
  exact 12 x 4 topology.
- Grid: 12 columns x 4 rows.
- Cell: square and exactly derived from the delivered dimensions (200 x 200
  for recipe-normalized output; 32 x 32 for the browser-demo fixture).
- Columns 0-3 are canonical roles; 4-7 and 8-11 repeat those four roles as
  visual variants.
- Every browser-demo cell has a 2-pixel transparent source gutter. The gutter
  isolates generated cells and is not drawable terrain content.

| Row | Columns 0-3 |
|---|---|
| 0 | top-left, top-middle, top-right, isolated top |
| 1 | slope-up, slope-down, inner top-left, inner top-right |
| 2 | side-left, side-right, bottom-left, bottom-right |
| 3 | interior fill, platform-left, platform-middle, platform-right |

The layout prior communicates cell boundaries, air, surface material, and
interior fill. Surface appearance comes from the recipe's concept reference;
the geometry remains stable enough to slice deterministically.

## Role behavior

- Air/outside regions use the recipe's background-removal/chroma convention.
- Interior fill is opaque edge to edge.
- Surface roles share a consistent ground line.
- Slopes express one-cell transitions for the preview's one-dimensional
  heightmap.
- Platform pieces share a top line and compatible left/middle/right edges.

The preview may deliberately consume only a validated subset when a generated
sheet does not satisfy every role. Such fallback is a preview-adapter decision
and must be recorded; it must not silently redefine the generator component.

## Generic seam

A reusable sheet generator accepts explicit rows, columns, semantic cell
descriptions, anchors, reference inputs, and output-validation rules. The
labels above are supplied by this recipe. Another recipe can use the same
component for top-down terrain, effects, portraits, or UI without inheriting
platformer role names.

The consumer maps semantic roles to cell rectangles through its own adapter.
No component imports the browser preview's heightmap or texture-registration
code.

## Browser terrain-consumer contract

`web/lib/runtime/tiles.ts` owns atlas geometry and role metadata;
`web/lib/runtime/terrain.ts` owns heightfield topology, placement, collision,
and culling. `scene.ts` only turns the resulting plan into Phaser objects.
This is the integration seam: generated atlas bytes and Python components do
not depend on browser terrain policy.

The browser adapter applies these rules in order:

1. Require exact 12 x 4 divisibility, a 2-pixel inset, nonempty cell content,
   and a fully opaque canonical fill interior.
2. Keep the approved source bytes unchanged. Build a temporary canvas whose
   gutters are copied only from the nearest edge pixel of the same cell. The
   browser registers that prepared canvas as a texture but does not register or
   render per-role atlas frames; terrain rendering uses only the separately
   derived textures described below. The prepared atlas retains same-cell
   sampling padding without changing the source bytes.
3. Read the canonical opaque `fill` interior as source material, but do not
   repeat its generated silhouette. Derive a runtime-only 512 x 512 toroidal
   material from that cell's luminance-sorted color palette and deterministic
   byte-derived seed. Domain-warped harmonic families at 3/7/19/43 cycles
   create globally phased, non-cell-periodic strata while every output color
   remains interpolated from the approved fill palette. The material remains
   fully opaque and is not a scene-background color. The approved atlas bytes
   remain unchanged.
4. Merge horizontally connected solid cells at each level into one fill run,
   then paint the derived material with one global world-coordinate phase.
   Connected terrain therefore samples the same material pixel at the same
   world position instead of restarting a motif at each 64-pixel boundary.
5. Extract a runtime-only 512 x 12 surface band from only the first five
   painted rows of the approved `top_single` cell. The extraction follows a
   periodic, mirror-safe source path and deliberately excludes the full-cell
   stem and body. Equal-height columns share one surface run, so flat ground
   does not stamp a full `top_mid` frame at tile cadence.
6. Never draw a full atlas cell. Extend each contour inward over the opaque
   fill with a separately generated, transparent approved-palette transition;
   its 3/7/19/43 world-space harmonics vary the fade depth without becoming a
   coverage primitive. Then extract runtime-only 12-pixel side bands from
   the outer five painted columns of the approved `side_left` and `side_right`
   cells. The typed render plan creates connected-run fill TileSprites first,
   inward transitions second, and narrow top, left-side, and right-side strips
   last along the collision contour. Corners and stepped slopes are
   intersections of those strips; decoration cannot extend a full tile into
   the solid body. Bottom/platform roles remain reserved because this
   heightfield is bottom-contiguous rather than floating.
7. Place nominal cells at integer world coordinates. Opaque fill may overlap
   one world pixel into an adjacent solid cell and one pixel downward; it must
   never extend above the collision surface or into an air-facing side.
8. Define actor, item, portal, and prop grounding through the same surface
   equation: `baselineY - columnHeight * tilePixels`. The painted top of each
   surface cell must equal that value exactly.
9. Cull connected fill runs, integration patches, and boundary strips by their
   column interval, using two columns of overscan. The supported camera range
   is zoom 1-2 and device-pixel ratio 1-4; continuous world coverage plus
   positive affine projection guarantees no uncovered ground pixel within
   that range.

For a surface column, signed neighbor deltas select one role: lower/lower is
`top_single`; lower/equal is `top_left`; equal/lower is `top_right`;
equal/equal is `top_mid`; lower/higher is `slope_up`; higher/lower is
`slope_down`; higher/equal is `inner_tl`; and equal/higher is `inner_tr`.
Buried cells use `side_left` or `side_right` only when that edge faces air,
otherwise `fill`.

## Validation

1. normalized dimensions and grid divisibility are exact;
2. every canonical cell exists;
3. required opaque/transparent regions meet the recipe contract;
4. anchors align across compatible roles;
5. provenance records prompt, references, normalization, and attempts; and
6. the runtime extrusion plan samples no neighboring cell and covers every
   derived destination pixel exactly once;
7. rasterized long/stepped heightfields remain gap-free at supported zoom/DPR
   combinations and their rendered top matches collision exactly;
8. flat, raised, and stepped spans collapse into connected bodies plus narrow
   contour strips, with no registered or rendered full-cell contour frame and
   no decoration beyond the configured boundary thickness;
9. the failed frame-450 camera range contains no boundary-detail role below a
   surface, and adjacent overlap pixels use one global material phase; and
10. a failed sheet is retried or reported, never accepted only because a file
   exists.

## Floating upper-platform consumer

The optional browser demo may derive a floating platform from the same
approved fill/cap/side materials without assigning new atlas roles. It paints
one connected body rectangle, one continuous cap strip, and endpoint side
strips only. It does not stamp `platform-middle` or any full atlas cell for
each source column. Collision remains the typed deck geometry in
`web/lib/runtime/vertical.ts`; rendered pixels, scale, zoom, and device pixel
ratio cannot move that deck.
