# 0052 — Applying a design to a shipped map is its own authorized operation

*Ruled with the map design module.*

## Fact

The shipped map TOMLs are pinned byte-for-byte, so a new occupancy matrix co-updates the
byte-level assertions in `tests/unit/components/platformer_map/test_prepared_game_map.py`. The
edit stays inside the map TOML, because the resolver computes every member digest at capture
time rather than reading an authored one.

## Challenge

A design run that produces a better map should apply it — running the designer and then
declining to use its output is a half-finished operation.

## Ruling

Applying a design to a shipped map is its own authorized operation, never a step inside a
design run. It moves pinned bytes, it re-bills the climbable atlas image for as long as the
placement-only cache split is open, and it must land as one reviewed change rather than two
partial ones. If a run intends to move placements, the cache split is sequenced first.

## Evidence

The design run and the apply have different blast radii: the first is structured calls against
a validator, the second moves digests that several tests pin and can cost image spend.

## Falsifier

A design apply that provably moves no pinned digest and re-bills no image — at which point it
is an ordinary step rather than an authorized operation.
