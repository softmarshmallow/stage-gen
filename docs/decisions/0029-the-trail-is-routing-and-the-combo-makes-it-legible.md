# 0029 — The collectible trail is routing, and a breaking combo makes the ground line legible

*Ruled with the track re-authoring.*

## Fact

The shipped track was 8 rows deep with five rows of air, 12- to 16-column chunks, and a single
pickup token over a three-column pit. Twelve columns is 2.0s at base speed — too short to hold
a setup-then-payoff motif, and too short to afford the apron, which leaves such a chunk two
authorable columns.

## Challenge

A collectible is a score item. Making it carry routing information is a second job for one
object, and a flat score per token is simpler to reason about.

## Ruling

Every pit and hazard gets an arc sampled from the *real* parabola, leaving the ground two
columns before takeoff so the player is committed to the ascent when the hazard arrives — the
takeoff cue expressed as geometry rather than as a warning icon. Safe stretches get a ground
line one row above the surface, so a jump forfeits about 84% of a jump's worth of tokens: that
is the crouch gate. And the pickup chain multiplier is folded in rather than deferred, because
it is the missing *instrument* — a flat score makes an 84% forfeiture nearly invisible, while
a breaking multiplier makes it legible to the player and measurable by us.

## Evidence

The depth and width moves are inside today's contract bounds, and the overhead half of the
obstacle space is free to author now and expensive to retrofit once the catalog grows. The
combo was free to add: the per-frame collected count is already published and the score has a
single writer. Per-event audio one-shots landed in the same pass through the existing view
injection seams, at zero provider cost — the rhythm reference's actual trick, which is that the
cue is specific to *how* you avoided the obstacle.

## Falsifier

A measurement showing the ground-line chain does not change how often a good player is
airborne — which would mean the trail is decoration after all.
