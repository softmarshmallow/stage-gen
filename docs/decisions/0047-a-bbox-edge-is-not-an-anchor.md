# 0047 — A bounding-box edge is not an anchor

*Ruled when the first non-grounded state failed.*

## Fact

The sprite pipeline has never had an anchor point. Registration is inferred from an
alpha-bounding-box edge: the repacker aligns each crop against a cell edge, and the runtime
places the sprite at the bottom of the cell.

## Challenge

Bottom-anchoring had been correct for every state that ever shipped, so the edge rule looked
like an anchor system that simply had not been named yet.

## Ruling

A bbox edge is not an anchor. It is a property of whatever pixels happen to be painted, so it
moves whenever a limb extends past its previous extreme, and it cannot express a registration
point that sits inside the figure — which is where a 2D animator actually pins: the pelvis for
most locomotion, the contact foot for a walk cycle, the grip for anything hanging. Three
consequences are ruled with it. **The acquisition method is the open question and must be
scoped before anything is built** — authored anchors, a prompted visible marker, a labelling
pass after generation, a geometric estimate from the silhouette, or a fitted skeleton; the
prompted and labelled options both need an accuracy budget in pixels against hand-labelled
truth, and both add a per-frame failure mode the edge rule does not have. **Whatever wins is a
contract change on both sides**, persisted in the artifact contract and the runtime manifest
and consumed in place of the published foot origin. **It must be re-applied at draw time, not
only baked into the packing**, because the loader re-measures every cell and registers each
frame as a tight alpha crop, so the producer's offsets are gone before a sprite ever draws.

## Evidence

The gap stayed invisible because every state until now kept its feet on the ground, where the
bbox bottom is within a few pixels of the true anchor — right by luck rather than by contract.
The first state whose stable point is not its feet failed loudly: with bottom anchoring the two
climb cells agreed on the feet to the pixel and disagreed on the head by 751px, a quarter of
the figure, which read in play as bouncing rather than climbing. A neighbouring state sat at
58px and looked fine, which is exactly why nothing caught it earlier — the defect scales with
how far a state's true anchor sits from its bbox edge. A first attempt at the fix packed the
artifact correctly and changed nothing on screen, which is what proved the draw-time half. The
repository has already learned the same lesson once for *scale*: a figure's painted height is a
property of its pose rather than its build, so the runtime sizes every sheet against the idle
head — a stable interior feature — while registration still uses an unstable outer edge. The
interim `anchor` word on motion presentation, authored per motion as `bottom` or `top`, is a
stopgap that inherits every limitation above and must not be mistaken for the anchor system: it
can only pin an extreme.

## Falsifier

A measurement showing that an interior anchor cannot be acquired within a usable pixel budget
by any of the five candidate methods — which would make the edge rule the best available and
the stopgap the answer.
