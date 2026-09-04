# 0043 — Locomotion is a profile with its own admission arithmetic

*Ruled with the thrust locomotion.*

## Fact

The genre's one mechanism was running, and every admission proof was written against a jump
arc. Flying is a different mechanism over the same authored terrain.

## Challenge

A flying avatar is not bound by gaps or rises, so the simplest reading is that admission does
not apply to it and the override is a runtime concern.

## Ruling

Locomotion is a named profile carrying its own admission arithmetic, and the hard constraint
held: the encounter's three proofs — lane, dodge, winnable — are closed form and run offline
before any spend, reusing the placement profile's own reaction constant for the dodge.

## Evidence

One thing the design note did not predict: the dodge proof bounds the band from **above** as
well as below. A taller band takes longer to cross while the shot's flight time is fixed, so
twelve rows over a walk surface at nine refuses where eleven over eight passes. A proof that
only bounded from below would have admitted an undodgeable arena.

## Falsifier

A locomotion whose fairness cannot be settled offline in closed form — which would put the
proof back into playtesting and break the genre's defining property.
