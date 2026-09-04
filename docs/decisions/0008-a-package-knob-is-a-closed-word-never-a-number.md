# 0008 — A package-facing knob is a closed word with a default, never a number

*Ruled 2026-09-02 with the reach thread.*

## Fact

Widening melee reach, target count and hits per swing looked like three numbers a designer
should be able to tune from `gameplay.toml`.

## Challenge

Numbers are the direct expression of the thing being tuned. A named class forces a code change
for every new value and makes the authored file less expressive than the feature it drives.

## Ruling

Python publishes a class *name*; the consumer owns the numbers. Reach arrived as
`melee_sweep_v1` in `web/lib/sideview-platformer/weapon-class.ts` and in the Python validator
list, exactly as the ranged class had. A numeric `[combat]` tuning block would be a separate
contract conversation and must not be smuggled in beside a vocabulary widening.

## Evidence

The developer kit picked the new class up for free because it iterates the published weapon
classes; nothing had to learn the number. Widening the vocabulary touched both Literal lists,
the runtime tuple, the contract test and the value list in the authored contract schema — a
closed set with one enumeration per side.

## Falsifier

A package whose correct value for a knob is genuinely continuous and package-specific, so that
the closed vocabulary would grow one member per package. That is the shape a tuning block is
for.
