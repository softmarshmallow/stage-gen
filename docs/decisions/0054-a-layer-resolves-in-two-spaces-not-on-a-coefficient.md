# 0054 — A layer resolves in two spaces, not on a coefficient between them

*Ruled with the layer contract.*

## Fact

The layer contract resolves in two spaces, world and screen. A world layer moves with the
world; a screen layer does not move at all. Neither needs vertical slack.

## Challenge

Partial parallax — a coefficient between the two — is what a general depth model would offer,
and it is one number.

## Ruling

The coefficient is not taken until a layer needs it, because it would need slack that does not
exist. Map layers are painted at 1536x1024 and scaled by the viewport ratio, so they are
exactly one viewport tall: a partial factor would expose the plate beneath. Scaling to fill
width instead would yield 133px of slack with no regeneration, at the cost of an 18 per cent
change in apparent scale and therefore a fresh semantic review of every map layer. That is the
price, and it is paid when a layer needs the slack rather than in advance.

## Evidence

The same arithmetic bounds the camera: a consumer zoom below 1 exposes the sky plate beneath
every layer for exactly this reason, so the constraint is one fact with two consequences rather
than two independent limitations.

## Falsifier

A map whose layers are painted taller than one viewport, which supplies the slack and makes the
coefficient expressible at no review cost.
