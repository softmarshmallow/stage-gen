# 0019 — Painted terrain is an opt-in ground mode, and collision stays authored

*Ruled 2026-09-03 after a four-operation spike.*

## Fact

A tile atlas cannot draw organic rock. The literal suggestion was one large painted sprite
with the geometry traced out of it afterwards.

## Challenge

Tracing geometry from the image is how a painting-first workflow normally works, and it is the
only way the art is guaranteed to match what the player collides with.

## Ruling

Authored occupancy owns collision; the image never does. Painted terrain is the runner's
shape applied one recipe further along — occupancy becomes a guide, a native-alpha edit paints
it, and the result is masked back — and it is a *mode*, a discriminated union on the prepared
map's ground with an offline eligibility gate that refuses a grid taller than the guide canvas
can carry *before* any spend. It is deliberately not the default, and no map declares it.

## Evidence

Collision is computed from the terrain artifact and nothing samples the image at any stage, so
the offline prover still proves rise tolerance, deck exposure and camera range from occupancy
alone. The graph branches per map — three guide, three generate and three canonicalize nodes
plus one compose, replacing the atlas pair — so a painted road plans at 238 nodes against 230.
Because no map declares the mode, the widening re-billed nothing: seven local and advisory
nodes moved on identity alone, proven by a plan diff against the cached world run. The manifest
publishes a cell size, a tolerance and an ordered segment array, and the consumer refuses a
manifest carrying both arms.

## Falsifier

A map whose art is only correct when the collision follows the paint — a silhouette no
authored occupancy can express — which would make the mask-back inversion the wrong way round.
