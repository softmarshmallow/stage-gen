# 0037 — The projection gate refuses two projections in one tile and nothing subtler

*Ruled 2026-09-03.*

## Fact

The gate that was meant to measure a tile's lean measured nothing. Pillow's kernel filter
clamps into the source image's own range, so the 8-bit Sobel pair saturated on every strong
edge and dropped it into the 45-degree bin: synthetic families drawn at 20, 30, 45, 60 and 70
degrees all measured 45.0.

## Challenge

A gate that exists and passes is easily read as a gate that works, and the natural repair is to
tighten its tolerance.

## Ruling

The estimator reads signed gradients in 32-bit over a blurred copy, excluding the one-pixel
ring the filter fills with source luminance. Two further things were wrong once it could speak:
the lean was the modal histogram bin, which jumps between unrelated bins on honest art, and is
now the magnitude-weighted circular mean of the diagonal band; and the spread was a plain
maximum minus minimum on a circular quantity, reading +87 against -87 as 174 degrees of
disagreement rather than six, and is now the smallest arc covering the thirds. The tolerance is
*measured* rather than assumed, and both the constant and the genre specification say plainly
what the gate can see: two projections in one tile, and nothing subtler.

## Evidence

Resolved against the same synthetic families the fixed estimator lands within 0.2 degrees. The
twelve shipped tiles spread 7.2 to 59.6 degrees while being visibly correct front elevations,
and the same tiles hatched into an opposite-leaning splay spread 76.0 to 84.6, so the tolerance
moved to 68. The old spread refused a synthetic fixture outright the moment real angles
arrived.

## Falsifier

A tile drawn with a single receding top face that the gate passes and a reader rejects — which
is exactly the case the recorded scope says it cannot see, and needs a detector local to the
surface run rather than a statistic over the tile.
