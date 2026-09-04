# 0016 — A damage number is a run of glyphs, not a text object

*Ruled 2026-09-03.*

## Fact

In the reference, no two digits of one damage number sit on the same line. A single text
object structurally cannot do that: a block of text can only pop as a block.

## Challenge

One text object per number is one draw, one pool entry and one measurement. Splitting a number
into digits multiplies every one of those by up to seven.

## Ruling

A number is a run of glyphs. The layout centres the row on the run from the advances the
renderer measured, falling back to nominal shares when it cannot measure, so a non-rendering
environment still lays out; each digit is then displaced from that anchor — invisible until
its own beat, arriving oversized and high, falling into a resting place that is a shallow arc
plus a jitter and a size variance hashed from the event id and the digit index. Hashed rather
than drawn at random, for the same reason every motion in that module is sampled from `nowMs`.
Every other measurement is a share of the font size — both outline widths, tracking, arc,
jitter, drop and stack step — because pixel displacements around a number two and a half times
larger read as a big number sitting perfectly still.

## Evidence

The pool is keyed by the exact glyph rather than by style alone, so a recycled `7` already
holds a rendered 7 and reuse costs no text re-render — which is what makes the per-digit shape
affordable. Verified as a rendered filmstrip in headless Chrome against the real module.
Tests pin the proportionality: a run at twice the size arcs and stacks twice as far.

## Falsifier

A profiled frame where per-glyph pooling is the cost, or a second desired number *feel* in one
library — which would make this presentation choice a package-facing named word rather than a
consumer decision.
