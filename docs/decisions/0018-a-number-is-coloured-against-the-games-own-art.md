# 0018 — A number is coloured against the game's own art, and a critical is that colour inverted

*Ruled 2026-09-03.*

## Fact

The numbers were judged against a dark test card, where gold looks superb. Measured off the
run's real layer images, gold sits at almost exactly the luminance of the stone it is drawn
over (0.65 against 0.48) and of the horizon (0.67), and it vanishes.

## Challenge

Colour is art direction, and art direction in this repository lives in the prompt rather than
in a test. Pinning hexes in a test freezes a taste decision.

## Ruling

Hue is chosen for contrast against the game's own art: magenta is the one saturated hue this
world does not contain, which is the same reason the arcade reference uses it. Damage taken
stays red, because which side a number belongs to outranks its contrast. A critical is the
number's own colour *inverted* — normal is the colour inside a white ring, critical is white
inside a ring of that colour — so the two share a hue and a silhouette and the brightest thing
on screen is the biggest hit. Tests assert the value *steps* (core-to-ring at least 3,
ring-to-edge at least 4, by WCAG relative luminance) rather than pinned hexes.

## Evidence

Four candidate hues were rendered over crops of the run's own layers against three bands. The
gold the eye had approved measured 1.7 on the core-to-ring step, and no pinned hex would ever
have said so. Tracking went from -2 to +2 in the same pass: tight tracking is what an arcade
number looks like *without* an outline, and with a heavy dark edge the packed silhouettes fuse
into one mass. Scale was measured against the reference too and deliberately stopped short of
it — a cap at just under a third of the player rather than four fifths, because the reference
is one boss taking one combo and this is a hunting map where a dozen creatures die at once.

## Falsifier

A game in this library whose palette already contains the chosen hue, which would move the
ruling from "magenta" to "the hue this package's art does not contain" and require the choice
to be per-package.
