# 0036 — Only `orthographic_v1` is served, and an absent projection block is not an identity

*Ruled 2026-09-02.*

## Fact

Ground art was being drawn without any declared projection, so a returned tile could be a flat
elevation or a receding slab and nothing said which was wanted. The plan called for a table
with two members and two numbers — a receding angle and a depth ratio.

## Challenge

An oblique member is what a designer would reach for first, and the two numbers are how every
other engine expresses it.

## Ruling

Only `orthographic_v1` is served: a flat front elevation with no top face, stated as a mandate
inside the ground prompt's hard contract — every edge horizontal or vertical, no vanishing
point, no receding edge, no visible top surface. It is the truthful projection for a strict
side view anyway. The oblique member is *blocked* rather than merely unwritten: the alpha
geometry validator requires every published cell to be exactly opaque or exactly transparent
against authored occupancy, and oblique depth spills into neighbouring cells, so serving it
needs a projection-aware expected mask and a canvas margin first. And field presence is not
identity: an absent block means orthographic, and the default is excluded from the ground
node's cache identity, so declaring it explicitly re-billed nothing.

## Evidence

The shipped package declares the mode deliberately rather than inheriting it, and the declared
run cost zero re-keys.

## Falsifier

A package whose ground genuinely reads better oblique, together with an expected-mask
formulation that keeps the exactness guarantee — which would make the block a limitation of
the validator rather than of the projection.
