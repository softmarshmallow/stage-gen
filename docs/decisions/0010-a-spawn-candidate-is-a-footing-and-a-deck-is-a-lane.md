# 0010 — A spawn candidate is a footing, and a deck is a lane

*Ruled 2026-09-03 with the mobs-on-decks thread.*

## Fact

Creatures could stand only on base terrain. Admitting decks meant three layers had to learn
something: the director's candidate set, the creature's notion of where it may walk, and the
authored permission that says which surfaces a zone may use.

## Challenge

The direct reading is that a deck is another kind of ground and a spawn candidate is a column,
as it always was; a column under a deck is simply a column that is now taller.

## Ruling

A candidate is a *place to stand*, not a column: the uniqueness key is the pair (column,
`deck_id`), so a column under two storeys offers three footings. A deck is a *lane*: its two
edges bound patrol, pursuit and knockback alike, the edge holds against a blow, and re-homing
never happens — a deck-bound creature can neither jump nor climb back up, so shoving it off
the end would strand it. The authored word `terrain_and_decks` is a *permission*, not an
instruction: a zone says which surfaces its creatures may use, the consumer decides where each
body lands, and a zone naming decks on a map that has none simply populates its floor.

## Evidence

Rejecting the second footing in a column as a duplicate would have silently discarded every
deck above the first. Nothing in mob behaviour learned about decks: wander, chase,
return-home, facing and knockback are unchanged, and the strike constraint already refuses a
blow across a level. Measured on the reassembled run, the road's zones went from 36 places to
stand to 73 with every population cap unchanged.

## Falsifier

A creature that must path between decks — at which point the lane abstraction is hiding a
graph, and cross-deck navigation has to exist.
