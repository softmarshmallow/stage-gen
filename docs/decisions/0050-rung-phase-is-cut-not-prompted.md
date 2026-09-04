# 0050 — Rung phase is cut deterministically, not constrained in the prompt

*Ruled while measuring the climbable band atlas.*

## Fact

The model reliably obeys countable direction — how many rungs, which cells carry them — and
unreliably obeys proportional direction such as "one quarter of the cell height". About one
band in three places its rungs so that every stacked join is 34-38% wider than the spacing
inside a band, roughly 14-18px at the runtime visual width.

## Challenge

The defect is a prompt-following failure, so the direct repair is a tighter prompt.

## Ruling

Constraining the rung count in the prompt is *not* the fix: it corrected phase direction but
pushed rung spacing to 0.88 of the ladder width against 0.74-0.77 for the accepted baseline,
which reads as a ladder no one could climb. Cutting one rung period out of the band removes the
defect deterministically. But that changes the repeat unit from an authored band to a *measured
rung gap*, so it lands together with the world-unit mapping rather than as a patch.

## Evidence

The deterministic cut applied to 16 of 16 sampled ladders. The prompt constraint was measured
against the accepted baseline's own spacing ratio rather than judged by eye, which is what
exposed the regression it caused.

## Falsifier

A prompt formulation that fixes phase without moving rung spacing off the accepted baseline —
which would make the measured repeat unit unnecessary.
