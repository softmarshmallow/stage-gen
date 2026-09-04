# 0006 — A camera bound comes from the world's own geometry

*Ruled 2026-09-03.*

## Fact

`VERTICAL_CAMERA_MIN_SCROLL_Y`, a -512 clamp belonging to a demo scene that had already been
replaced by `web/lib/sideview-platformer/prepared-scene.ts`, was still the deck bound in
`createVerticalWorld`. The first shelves road, with decks reaching 21 tiles, threw on entry.
Two camera helpers of the deleted scene — `verticalCameraScrollY` and
`horizontalCameraScrollX` — survived it as orphans.

## Challenge

Deleting orphaned helpers is tidiness, and tidiness is the weakest reason to touch working
code; raising the constant would have unblocked the road in one line.

## Ruling

The bound is the grid's own top (`topY` on `VerticalWorldInput`, the same edge the camera
world bounds already use), passed in by the terrain projection. A camera bound is a property
of the world being drawn, never a constant inherited from a scene that no longer exists. Both
orphaned helpers and their dead-zone constants are deleted with their tests.

## Evidence

The failure was real rather than hypothetical: a legal authored map threw on entry. The
harness checkpoints named by the retired item no longer exist.

## Falsifier

A world whose drawable extent is genuinely not derivable from its own grid, so that a camera
bound has to be authored or constant to be correct.
