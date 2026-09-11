# P89 Background Blackout - native integration and visual review

**PASS for the inspected runtime compositions and focused native checks.**
This reviewer implemented the QA runner, not the shared transition, story cue,
or study interface. No artwork was generated or edited.

Yuzu's warning now settles into its close solo framing before the conservatory
fades away. Her pose, size, expression, surprise manpu and dialogue remain in
place against black. The environment's disappearance makes her warning more
isolated and dramatic. The next line restores the conservatory and the existing
two-character composition. The effect does not change the sprite into a
silhouette or darken her clothing as an actor treatment.

The dedicated study shows the same background-only fade beneath the stationary
Nami sprite. Blackout, restore, pause, reset and the duration slider remain
readable and usable in English/Korean at 1280 x 900 and 2560 x 1800. Native
captures retain proportional, sharp rendering at both sizes.

## Evidence

[The native runner](../background_blackout_integration_checks.gd) completed with
zero failed assertions and 24 captures. The focused menu follow-up replaces its
two menu captures and adds two English variants, yielding 26 final captures.
The log is `/tmp/p89-blackout-native.log`, with a console
copy at `/tmp/p89-blackout-native-console.log`. Existing warnings about loading
runtime PNGs remain; the final run has no script errors or leaked-object warning.

- The story uses the existing `the_warning` beat with Yuzu alone. Its camera and
  focus settle during the authored 1.0-second delay, followed by a 0.45-second
  fade. Camera transform and actor position, size, scale, rotation, material,
  modulation, texture pixels and visibility stay unchanged across that fade.
- Exposed scenery reaches exact RGB black. A partial study frame matches the
  controller's opacity blend within half an 8-bit channel step. The isolated
  study world, including sprite alpha edges, returns pixel-for-pixel to its
  original appearance after restoration.
- The prepared Nami and Yuzu images have a maximum alpha of 254/255, so their
  solid-looking interiors still retain a small background contribution. Their
  sampled core pixels change by at most 3/255 as the backdrop changes, within
  the source-alpha and texture/blend quantization bounds. No unexpected core
  changes were found among approximately 53,669 story samples and 28,400 study
  samples per resolution. The QA does not mistake those assets for fully opaque
  sprites or claim their composited pixels are identical.
- An independent native fixture supplies an actually opaque sprite core and
  partially transparent border. Its opaque region and later UI are exactly
  pixel-identical over the original and black backgrounds; restoring the
  background reproduces the complete fixture image exactly.
- The active story fade survives English/Korean switching, pause and a real
  application detour to Presentation Lab with the same sampled state. Full
  black holds until explicit continuation. The following beat restores the
  background, an early continuation reverses the unfinished fade, and restart
  clears blackout state.
- Actual mouse input operates the study's blackout, restore, pause and reset
  buttons. Keyboard input on its duration slider selects zero duration, proving
  immediate blackout/restoration without actor changes.

The initial two-column effects-menu capture exposed descriptions extending
under the Explore buttons. The menu host received a local sizing correction;
the focused follow-up rechecks seven card descriptions in both languages and
both native sizes without repeating unrelated story checks. Final visual review
confirms the descriptions wrap inside their columns without crossing buttons.
The follow-up log is `/tmp/p89-blackout-menu-native.log` and contains no errors.

This is native 2D composition evidence, not a general save-format, exported-build,
or performance claim. The source textures and their original alpha remain intact.

## Digest-bound captures

[The manifest](manifest.json) records source/capture hashes, timing and pixel
metrics, and the empty error list. [Menu-only follow-up](menu_validation.json)
records the final menu source and its four reviewed English/Korean captures.
The final manifest SHA-256 is
`010e53db1c85113dd155d32abbbce13925379f46d98861f1de5c94f90e5152a3`;
all five recorded runtime source hashes match the inspected final files.

| Inspected capture | SHA-256 |
| --- | --- |
| [Story before blackout](story-before-1.png) | `8839d793df9069e68b1d576f719bc00c19c30177f00ec73afb7d3029ae8c308d` |
| [Story partial fade](story-midpoint-1.png) | `026bd946b402eacc448614ec1d0fecfa3dec6aab9fac479c0080bfdc23e7cb40` |
| [Story against black](story-black-1.png) | `df785894986bdf84a2eb87bff1cb384f0665c8fae78425255f49881a73cdcd6e` |
| [Story scene restored](story-returned-1.png) | `097862dfeedad1b3c11170d14a998e6ce1a9bf6985272904007d48ac5efa8415` |
| [Story against black at 2560 x 1800](story-black-2.png) | `910d38b34de05934fb883ce3934b777040a5c705dc67a8fa13934e40113a50d9` |
| [Stationary Nami against black](lab-black-ko-1.png) | `57838101412889c9ef6fab472808c748bb27ac691ab24d4031a5660b8ab1462b` |
| [Study restored at 2560 x 1800](lab-restored-ko-2.png) | `da0b576491faa1009af3c3a92ebb2b49978d3209b1e36c03d99e35e5cb48caba` |
| [Corrected effects menu in Korean](lab-effects-menu-1.png) | `d2434eb34f7b6342d28a79ba63ecb4932f3ac63cc790a3f383d8431b6429da71` |
| [Corrected effects menu in English at 2560 x 1800](lab-effects-menu-en-2.png) | `5278711cc9868bc7be0c160008d36006a515e913143282494d9d44742a1803d2` |
