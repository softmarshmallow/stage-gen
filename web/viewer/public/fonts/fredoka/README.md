# Fredoka runtime font

`fredoka-variable.ttf` is a static browser-demo dependency used for floating combat text. It is
not generated output and is not a visual-direction reference for image generation.

- Family: Fredoka
- Copyright: Copyright 2016 The Fredoka Project Authors
- License: SIL Open Font License 1.1; see `OFL.txt` in this directory
- Source: `google/fonts`, `ofl/fredoka/Fredoka[wdth,wght].ttf`
- Retrieved: 2026-08-24
- SHA-256: `2ba02e68b152868aef9ba28e24b3648c7d457fe6f25c761f2c2c53fb61a73fc8`

The complete upstream font is retained rather than a locally subsetted derivative. The web demo
loads weight 700 for damage numbers and must await the browser font load before constructing its
first combat-text object, so deterministic captures cannot silently fall back to a system font.
