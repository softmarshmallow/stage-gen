# 0028 — The selection grammar ships after the catalog is re-authored

*Ruled in review, before either shipped.*

## Fact

Difficulty progression in the shipped game was over in twenty seconds: the ceiling reaches 3 at
column 120, after which the pool is fully open and never changes again for the remaining 1800
columns of the speed ramp. The fix — a sliding band, anti-repeat, and a forced rest cadence —
was ready before the catalog was.

## Challenge

The grammar is contract-free, costs zero provider operations, and fixes a measured defect. The
re-authoring is a bigger change with authored bytes moving. Shipping the cheap half first is
the usual order.

## Ruling

The grammar ships *after* the re-authoring. Simulated against the shipped catalog of four
chunks at ranks 1, 2, 3 and 3, a sliding difficulty band has nowhere to slide to: it converts
"difficulty stops progressing after twenty seconds" into "the track becomes an empty flat
treadmill for the remaining four minutes of the speed ramp", which is strictly worse than
today.

## Evidence

No gate catches that regression: the web suites use their own fixtures and the Python gate
never touches runtime selection. The simulation was the only instrument that could see it.

## Falsifier

A catalog whose rank spread is wide enough that the band is well-defined at every distance —
at which point the ordering constraint is discharged rather than wrong.
