# 0007 — The hunting-ground reference is adopted for feel and refused for interface

*Ruled at the opening of the platformer hunting-ground pass.*

## Fact

The reference for the platformer's hunting map is a MapleStory hunting map. Decomposed without
its UI or skill systems it is six ingredients — density, reach, feedback, mob surfaces, number
scale and terrain silhouette — and the shipped game was measured against every one of them.

## Challenge

The honest way to chase a reference is to port its systems; adopting the feel while refusing
the systems is how a comparison becomes unfalsifiable.

## Ruling

The goal statement is "make it look more like this, while keeping the system agnostic, and
evolve the system until it can generate this". Its interface and skill systems are explicitly
refused: this is not an apples-to-apples comparison and the deliverable is a version of that
feel without the UI, not a port. Each of the six axes becomes its own thread with its own
measurement.

## Evidence

The axis table records both sides — 154 px of 720 against ~12%, 5-6 mobs per zone against ~12
on screen, 1.4 tiles of reach against ~3 — so every thread has a number to move rather than an
impression. Threads that turned out to be consumer-only shipped first, free of provider spend.

## Falsifier

An axis on the table that cannot be moved without adopting the reference's interface or skill
model, which would mean the decomposition was wrong and the systems are not separable.
