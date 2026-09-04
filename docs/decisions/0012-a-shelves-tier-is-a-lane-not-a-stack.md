# 0012 — A shelves tier is a lane, not a stack

*Ruled 2026-09-03 while reshaping the hunting map.*

## Fact

The chunk grammar's chunks were horizontal slots, so decks could not stack in the same columns
except along a diagonal hop chain. The first `shelves` word stacked wide decks over one
footprint; played, it read as one narrow tower rather than as a level, and the map was too
tall to read at 24 rows.

## Challenge

A storey is a stack of platforms; making it a lane sounds like a different feature, and the
grammar had just been widened once already.

## Ruling

A shelves tier is a LANE: `decks` decks of `platform_width` split by a `gap` the player hops,
so a storey is walkable end to end the way the floor is. Consecutive storeys are offset half a
deck-and-gap period, which does two jobs at once — it is the hole the player jumps up through,
and it is the headroom to stand, because the figure is taller than the tier spacing and a deck
directly overhead would clip it. The lane's gap is bounded by the level-crossing reach rather
than the rise-to-the-next-tier reach, because hopping along a storey is a level crossing.

## Evidence

Regenerated with four structured calls, no images and no design retry, the road became a flat
bank under three interlocking storeys at heights 5, 7 and 9, eleven decks in all, fed by three
climbables, at 56x14 — about one and a quarter screens of height instead of two and a fifth.
An advisory schema minimum let the first live design take four-tile decks, so a validated
minimum width read off the reference ledge is now a rule the prompt states.

## Falsifier

A map whose storeys are genuinely towers rather than levels — a climbing map — where a lane
that must be walkable end to end forbids the shape the design wants.
