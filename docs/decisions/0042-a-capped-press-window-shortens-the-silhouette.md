# 0042 — A capped press window is fixed by shortening the silhouette, not by lowering the threshold

*Ruled with the faster base speed.*

## Fact

A faster base speed shipped as a new named locomotion value — a union widening with no schema
bump — and every press window scales as the inverse of that base. One package's tallest hazard,
at 0.68 player heights, capped its track below the new speed.

## Challenge

The clearance threshold is a constant in the SDK table, and raising the speed while relaxing
the threshold by the same fraction keeps every existing chunk admitted.

## Ruling

The threshold does not move. The package was re-authored to a shorter silhouette, which is the
same rule the genre specification already states for hazards drawn too tall: if the silhouette
is wanted at full height, the fix is a taller jump profile, never a lowered threshold. Here the
silhouette was not wanted at full height, so it shrank.

## Evidence

The caveat bit exactly as predicted rather than as a surprise, and the whole change cost zero
provider re-keys.

## Falsifier

A package whose silhouette is load-bearing at its authored height *and* whose speed is
load-bearing — which would mean the two are genuinely in tension and the profile, not either
number, is what has to change.
