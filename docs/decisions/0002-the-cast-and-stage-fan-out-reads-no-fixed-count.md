# 0002 — The cast-and-stage fan-out reads no fixed count

*Ruled with M1 increment 3.*

## Fact

A visual novel's graph has to produce a backdrop per stage and an identity chain per drawable
actor, and the first package shipped one of each.

## Challenge

Two stages and one actor is what the demo needs; a fixed shape is smaller, cheaper to read,
and can be widened when a package asks.

## Ruling

The graph reads no fixed count. One backdrop per declared stage, and one
profile/plan/neutral/derive/canonicalize chain per drawable actor, derived from the authored
package rather than from a constant.

## Evidence

Larkfield ships three drawn actors across three stages and generated in one 38-node run of
15 provider images; nothing in the graph was edited to admit the second and third of either.

## Falsifier

A package whose stage or cast count forces a graph edit rather than a re-plan — for instance a
count that changes node identity rather than node multiplicity.
