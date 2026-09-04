# 0030 — Hazard height is proved against the arc, and the telegraph is a refusal

*Ruled with admission hardening II.*

## Fact

Terrain was proved offline and props were not: the member validator never read a prop's height,
which the content model bounds only between 0.05 and 32.0, so a hazard's height had never been
checked against the arc that must clear it. From the now-published arithmetic, a hazard box is
crossed in 0.2167s at base speed, and the shipped `toppled_cart` at height 1.00 cleared for
0.2736s — a 3.4-frame press window at 60Hz, in the run that was playable at the time. Anything
above 1.146 is physically unjumpable and was admitted silently.

## Challenge

Recalibrating the cart is a one-number authoring edit; a proof is a new refusal that will
eventually reject a prop somebody likes.

## Ruling

The proof lands against a minimum clear time of 0.15s (nine frames) and the cart is
recalibrated to 0.85, which yields 10.4 frames. The designer's rule goes into the genre
specification in the same change, because the first time a beautiful prop fails admission
somebody will quietly edit the threshold: **if the silhouette is wanted at full height, the
correct fix is a taller jump profile, not a lowered threshold.** The telegraph becomes a
refusal too — under the declared pickup-arc telegraph, every chunk carrying a pit or interior
rise must place at least three pickups on cells the declared arc passes through, using the same
closed-form sampling the clearance proof uses. The escape hatch is a different declared
telegraph name, so a deliberately unsignposted chunk is a declared intent rather than a
violation.

## Evidence

The recalibration is free on the art side, because the prop's height is absent from the catalog
image node's input digests, so the generated image stays a cache hit and needs no new semantic
review. The hardening is deliberately one increment *after* the authoring: the authoring tells
us what the predicate should be, and an unenforced authoring habit rots.

## Falsifier

A chunk that is provably clearable and telegraphed, and is refused anyway — or an unclearable
one that passes, which would mean the closed form does not model the arc the player flies.
