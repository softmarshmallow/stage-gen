# 0056 — The style plate is split from the identity plate, not swapped

*Ruled while auditing the visual novel's package.*

## Fact

One package points both its art-direction style reference and a cast member's identity
reference at the same image, so its style plate shows one specific character. The two ids are
independent by contract: a plate bound by nobody validates, and the "has identity plate" flag
then goes false for every actor, so a character-free art-direction plate is already fully
expressible with no code change.

## Challenge

The obvious repair is a swap: point the style reference at a new character-free plate and
leave everything else alone.

## Ruling

A swap alone would leave the actor's identity binding pointing at nobody. The fix is a
*split*: declare a character-free style plate, and let the actor keep the current image as her
own identity plate. This is authoring in one package, not a system defect — but the style
plate's digest is in every image node's cache identity, so it re-bills all fifteen images and
is batched with the next run that regenerates anyway.

## Evidence

Nothing is broken today, because the prompt clauses were split so only the one actor is held
to the plate's identity. The cost is a second scene: a package reusing this one would inherit
that actor's face as its house style.

## Falsifier

A package that wants its house style to *be* a character — at which point the two references
coinciding is authoring intent rather than a defect.
