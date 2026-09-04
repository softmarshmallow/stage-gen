# 0051 — No profile declares biomes until a ground mode can consume them

*Ruled with the map design module.*

## Fact

The design module can already express per-region appearance: the tag is physics-neutral,
membership and paintable span are validated, and per-chunk tagging lands switches on landmarks
for free. But the map contract binds exactly one terrain atlas per map and exposes no
per-region style surface.

## Challenge

The expressive half is free and already built, so declaring biomes now costs nothing and lets
designers start authoring against a capability the consumer will grow into.

## Ruling

No profile declares biomes until a ground mode can consume them. A profile that declares them
first lets the designer make a claim no consumer can honour, and the failure surfaces as *wrong
art* rather than as a rejected package — the one failure mode this repository's fail-closed
discipline exists to prevent. The prerequisite is a new mode under the ground block with its
producer, validation, manifest and consumer paths implemented, exactly as the map contract
requires of every future ground mode.

## Evidence

The map contract already states the four-path requirement for a ground mode, and the painted
ground mode was admitted under it; biomes have none of the four.

## Falsifier

A per-region style surface that reaches the consumer through an existing published field —
which would mean the mode already exists under another name.
