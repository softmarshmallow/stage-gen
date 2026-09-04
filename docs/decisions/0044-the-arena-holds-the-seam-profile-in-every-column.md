# 0044 — The arena holds the seam profile in every column

*Ruled with the boss encounter.*

## Fact

A boss fight has no fixed length, and the runner's seam rule says any chunk may follow any
chunk, so no chunk may carry state about what came before it.

## Challenge

A fight that outlasts one chunk needs either a chunk sequence — which the seam rule forbids —
or an exception to the seam rule for arena chunks.

## Ruling

No exception. The arena chunk holds the *seam profile in every column*, so one authored chunk
holds a fight of any length: the track can stay in it, or leave it at any column, and the join
is legal either way. The seam rule is intact rather than bent.

## Evidence

Projectiles were reused verbatim from the platformer, the boss catalog is its own content
contract, and the encounter start moment was promoted from reserved to served — so the fight
added a role and a catalog rather than a second selection mechanism.

## Falsifier

An encounter whose columns must differ from one another — a scripted arena — which cannot hold
the seam profile everywhere and therefore needs a mechanism the seam rule does not have.
