# 0022 — A checkpoint is scoped to what changed: the soundtrack slice

*Ruled 2026-09-03 with the hunting-music rewrite.*

## Fact

A track's cache identity is its own authored entry and the content contract, and it declares no
cache dependency on the package root, so rewriting one brief re-bills exactly one track. The
*content checkpoint*, however, is the whole content closure, and 55 of its 102 provider nodes
were already stale against contracts that had moved since the accepted content root.

## Challenge

The content checkpoint is the checkpoint that contains music. Running it is one command, and
the staleness it would resolve is real staleness.

## Ruling

A checkpoint takes its targets. Regenerating six mobs, four NPCs, the player and the interface
in order to change one piece of music would replace art that had already been reviewed, which
is a worse outcome than the staleness it fixes. The soundtrack gets its own bounded slice, and
a test pins that the slice reaches music nodes and nothing else.

## Evidence

Measured on the rerun: one music generation, zero images, zero structured calls; assembled
provider-free. The plan diff showed exactly one provider node moving.

## Falsifier

A slice whose bound is not derivable from the closure — a target set that has to be maintained
by hand and can silently omit a node the change actually invalidated.
