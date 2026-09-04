# 0014 — Every presentation effect is a pure sampler over simulation time

*Ruled 2026-09-02 with the hit-feedback thread.*

## Fact

Hit feedback wanted a flash, a spark, a hitstop, a kill shake, a death burst and a coin pop —
exactly the list an engine's tweens, timers and particle emitters exist to serve.

## Challenge

Phaser ships all of them. Re-implementing tween and timer semantics as pure functions is more
code for the same picture.

## Ruling

Every effect is a pure sampler over a caller-supplied `nowMs`, in the shape the combat text
already used: no `scene.tweens`, no `time.delayedCall`, no particle emitters. Directions come
from the blow seed rather than from a random draw, so two captures of one run draw the same
shards. Hitstop is a scene-level deadline that scales the delta handed to actors, and must not
touch the director's clock or the combat text. A kill shake is a scroll offset applied after
camera follow, not the camera's own shake, which runs on its own clock.

## Evidence

The fixed-frame automation pins frame counts such as the death and drop delays and those
captures must stay byte-stable; an engine clock would desynchronise them. The rule is what let
the same module be verified as a rendered filmstrip offline in headless Chrome rather than by
eye in the game.

## Falsifier

An effect whose correct behaviour genuinely depends on wall-clock time — and which therefore
cannot appear in a deterministic capture at all.
