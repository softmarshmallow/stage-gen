# Luckiest Guy runtime font

`LuckiestGuy-Regular.ttf` is a static browser-demo dependency used for floating damage numbers. It
is not generated output and is not a visual-direction reference for image generation.

- Family: Luckiest Guy
- Copyright: Copyright (c) 2010 by Brian J. Bonislawsky DBA Astigmatic (AOETI)
- License: Apache License 2.0; see `LICENSE.txt` in this directory
- Source: `google/fonts`, `apache/luckiestguy/LuckiestGuy-Regular.ttf`
- Retrieved: 2026-09-03
- SHA-256: `cfbdd68a039f92df51cf3721506af6242e64594c6325fe0bedbeff3fe385d980`

The complete upstream font is retained rather than a locally subsetted derivative. It is a
single-weight display face, so the web demo loads weight 400 and sets damage numbers at that
weight: asking a canvas for bold from a face that has no bold gets a synthesized one, whose
thickening is the browser's own and would move glyph metrics under deterministic captures.

Damage numbers are set in this face rather than in Fredoka because of the outline. An arcade
number carries a light ring inside a heavy dark edge, and a stroke eats into a glyph's counters
from both sides; Fredoka's counters close up well before the edge is heavy enough to read. This
face is drawn with open counters and thick strokes, so it carries the edge. The EXP stat log stays
on Fredoka, which is a text face and is set as running words rather than as numerals.
