# 0021 — Painted structures are a separate asset family from painted terrain

*Ruled 2026-09-03, after the confusion cost two provider calls.*

## Fact

One word, "painted terrain", was carrying two different features: a bespoke painting per
segment of the authored terrain silhouette, and a large painted structure with an interior, a
balcony and a door in which only a few horizontal lines are standable.

## Challenge

Both are painted, both replace tiles, both need a guide, a source validator and a
canonicalizer. Serving the second as a variant of the first reuses all of it.

## Ruling

They are different families and are named apart. Painted terrain paints *the occupancy*, so
its output is a function of the grid: a grid of floating one-tile decks can only ever be
painted as floating one-tile decks. A structure is art in its own right, placed on a map,
carrying standable lines declared *on* it — and it is not a ground mode at all, because in the
reference the ground is still a tiled band and the house sits on it. Its home in the taxonomy
is its own segment, beside rather than inside the painted-terrain module.

## Evidence

The guide, source validator, canonicalizer and join machinery all transfer; what changes is
that the guide draws a bounding box with floor lines rather than an occupancy grid, and that
nothing is masked back — the art is free everywhere inside its box and only the declared lines
are validated. Collision stays authored either way, which is what separates this from the
paint-first suggestion the repository already refused. The lane record a standable line
becomes already exists, so mobs standing on a balcony come for free.

## Falsifier

A structure whose standable lines are only discoverable from the returned art, which would
collapse the distinction and put both features back on one guide.
