# 0017 — The arcade numeral face is Luckiest Guy, and outline weight is a typeface constraint

*Ruled 2026-09-03.*

## Fact

An arcade number is a sticker: saturated core, light ring, heavier dark edge. That is two
Phaser objects per glyph, because a canvas strokes text once. Set in Fredoka, the ring closed
the counters of 8, 9 and 0 at six pixels — well before the edge was heavy enough to read as
arcade weight.

## Challenge

Ring thickness looks like a free visual parameter to sweep, and the repository already shipped
Fredoka for its running text.

## Ruling

Thickness is a *typeface* question, not a free choice: a stroke eats a glyph's counters from
both sides. The numerals moved to Luckiest Guy in `web/public/fonts/luckiest-guy/`, Apache-2.0
— not OFL, which is what the upstream repository filing it under an `apache` directory told us
— set at weight 400 because that is the only weight it has, since bold synthesized from a face
with no bold thickens by an amount decided outside this repository. Sizes rose about a quarter
because a condensed cap-height display face sets smaller per pixel. The stat log stays on
Fredoka: it is running words, not numerals.

## Evidence

Thickness and size were swept as rendered strips and read off rather than guessed. One real
bug fell out: the committed font had no caller and there was no font face declared in the
app's CSS, so every damage number ever drawn was set in the first fallback the machine had.
The preview canvas now awaits the faces before it boots the game, which is what the module's
own README always claimed happened.

## Falsifier

A face with real weights whose counters survive an arcade-weight ring, which would make the
constraint a property of Fredoka rather than of stroked display type.
