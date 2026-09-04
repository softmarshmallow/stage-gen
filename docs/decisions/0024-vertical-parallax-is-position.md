# 0024 — Vertical parallax is position; horizontal parallax cannot be

*Ruled 2026-09-03.*

## Fact

A layer's vertical scroll factor was a flat zero, so the near frame was glued to the bottom of
the screen while the player climbed past it.

## Challenge

Parallax is implemented once, on x, and the obvious symmetry is to apply the same mechanism on
y.

## Ruling

The two axes are not the same mechanism. Horizontally a layer repeats and slides inside
itself, so its scroll factor is a rate. Vertically a layer is exactly one texture tall, so
depth there has to be *position*: a layer's vertical scroll factor is its own parallax, drawn
from the distance the map already declares. Depth does not change with the axis you look
along. The walk-surface datum is the one exemption, because it is registered to terrain it was
measured against.

## Evidence

The sky at 0 holds still and the foliage frame at 1.42 falls away as the player climbs. A map
whose camera follows x alone has no vertical travel to multiply, so the village is untouched by
construction, and a test says so. The whole change cost two structured map reviews and no image
node.

## Falsifier

A layer that must repeat on y — a vertically scrolling loop — for which one texture height is
no longer the whole extent and position stops being expressible as a factor.
