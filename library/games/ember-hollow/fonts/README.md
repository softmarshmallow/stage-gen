# Ember Hollow shell typeface

`fredoka-variable.ttf` is the face the shell's composited strings are set in — the game's
name on the title screen, the opening's cards, the loading tips. It is an authored package
input under [decision 0063](../../../../docs/decisions/0063-a-typeface-is-a-package-input.md),
not generated output and not a visual-direction reference for image generation.

- Family: Fredoka
- Copyright: Copyright 2016 The Fredoka Project Authors
- License: SIL Open Font License 1.1; see `OFL.txt` beside this file
- Source: `google/fonts`, `ofl/fredoka/Fredoka[wdth,wght].ttf`
- Retrieved: 2026-08-24
- SHA-256: `2ba02e68b152868aef9ba28e24b3648c7d457fe6f25c761f2c2c53fb61a73fc8`

The complete upstream file is retained rather than a subset, matching the two faces the
web viewer already carries.

**This face is a placeholder and it is the wrong one.** Ember Hollow's style is "flat
inked cutout survival"; Fredoka is a rounded storybook text face chosen for a chibi
platformer's running text. It is here because it is already in the repository under a
licence that permits redistribution, so the pipeline could be proved without a download.
Swapping it costs one file, one digest and zero provider operations — the wordmark is
composited by the host, never drawn into a plate, so no art re-bills when the face changes.
