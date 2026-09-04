# 0023 — A screen-top layer's seal is a default, not a floor

*Ruled 2026-09-03.*

## Fact

A screen-top layer is lifted until the first row every column spans meets the frame edge. The
horizon layer is sparse for its top 61 per cent, so the clouds, the peaks and the castle were
pushed above the viewport and a flat plate of sky sat where the distance should have been.

## Challenge

The seal exists to stop a gap appearing between a layer and the frame, and a gap is a hole in
the world.

## Ruling

The seal is right at the *bottom* edge, where a gap is a hole in the world. At the top it
guards against nothing: the map contract makes every map declare exactly one opaque layer and
forces it to cover the canvas, so what a top-edge gap reveals is that full-bleed sky plate,
which is what belongs above a mountain. The measurement becomes a default rather than a floor,
and a map may author a vertical offset past it.

## Evidence

The resolved record still carries the computed minimum seal offset, so the composite says what
was overridden rather than silently forgetting it. Placement fields are excluded from a layer's
cache identity by design, so the whole correction cost no image spend.

## Falsifier

A map that declares no full-bleed opaque layer, or a contract change that stops forcing one —
at which point a top-edge gap reveals nothing and the floor has to come back.
