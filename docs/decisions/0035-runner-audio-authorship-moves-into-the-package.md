# 0035 — Runner audio authorship moves into the package; the event set stays the vocabulary

*Ruled with the runner audio pass.*

## Fact

The web consumer hard-coded every oscillator parameter behind the runner's semantic runtime
events, and the package could say nothing about its own sound.

## Challenge

Synthesized cues are presentation, and presentation is the consumer's. Moving parameters into
the package makes authors responsible for numbers a designer would rather not see.

## Ruling

The seven semantic runtime events remain the stable *trigger* vocabulary; what moves into the
package is the binding from event to named effect, and the effect's own parameters. The
realization boundary is explicit, so generated-file sound effects can extend it later without
remapping gameplay events. Music is authored the same way — the package declares its
loop-ready tracks, which activates the existing music graph.

## Evidence

The cutover moved the package root and the runtime manifest together, with the manifest
assembly cache re-keyed, and no provider operation is part of the authored change: producing
and listening-reviewing the tracks is a separate live gate.

## Falsifier

An event whose correct sound depends on consumer-side state the package cannot name, which
would put the binding back on the consumer's side of the boundary.
