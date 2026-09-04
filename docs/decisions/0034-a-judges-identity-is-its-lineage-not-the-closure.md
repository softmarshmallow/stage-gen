# 0034 — A judge's cache identity is its lineage, not the package closure

*Ruled with the rebase-judge fix.*

## Fact

The two rebase nodes declared the package's whole closure digest as their input, so **any**
authored edit anywhere in the package re-billed two structured operations: editing a track
chunk, moving a pickup, or bumping a prop's height all re-ran a judge that never looks at the
track. Several pure-authoring increments each paid that toll.

## Challenge

The closure digest is the safe over-approximation. Narrowing an identity risks a stale
artifact, which is worse than an unnecessary bill.

## Ruling

An identity is what the node actually reads. The rebase pass reads the motion atlases and
nothing else, so its identity is the motion-validate lineage it already depends on. The graph
contract and its cache-identity assertions move in the same change as the identity, never
after it.

## Evidence

This is the same over-broad-digest defect as the still-open climbable placement fields one
recipe further along: placement is consumed downstream of generation, so digesting it re-bills
an image that would return byte-identical. Related and found while there: only seven of the
twelve image nodes are barrier-cut, so a change to the avatar concept prompt re-bills four
image operations rather than one.

## Falsifier

An input a judge reads that is reachable only through the closure — which would mean the
narrow identity is missing an edge and can serve a stale verdict.
