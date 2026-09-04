# 0039 — A bare rim is refused by identity with the deterministic base

*Ruled 2026-09-03, after two wrong turns.*

## Fact

A returned painting that leaves a slab's top cells bare publishes a band of the deterministic
base, and that band cannot be repaired after the fact: against a genuinely eight-pixel bare
rim every underlay radius is wrong the same way, because the nearest paint at a slab's edge is
its dark ink contour, so widening the reach only trades a lilac band for a dark one.

## Challenge

The natural measure is coverage over the source cell, derived from how far publication can
reach, and thresholded.

## Ruling

The rule cares about whether *guide material reaches the published raster*, so the validator
canonicalizes the painting it is admitting and refuses any row that is still untouched
deterministic base. Identity with the base, not nearness to a guide colour: proximity can only
speak about the cap, because the guide's fill is the material's own dark and honest art wears
it.

## Evidence

The coverage floor derived from publication reach landed at 0.90625, exactly where a normal
four-to-five-pixel alpha ramp lands, so it refused correct paintings about half the time and
one tile spent a whole retry budget under it. Counting proximity to the fill put a third of a
correct row in breach; not counting it left the same defect invisible at the *bottom* edge —
of the twelve tiles that shipped, one published a fourteen-pixel band of base along its last
rows and another published its final row, neither visible to a cap test. Across both shipped
runs the identity measure reads 0.0000 to 0.0021 and refuses exactly the tiles with a real
band. The prompt was the other half: asking for every solid cell to be painted edge to edge,
hard-edged, moved top-cell coverage from 0.92 typical to 0.88-0.9996.

## Falsifier

A published tile whose base is genuinely visible and whose rows are all non-identical to the
base — for instance a base the painting tints rather than replaces.
