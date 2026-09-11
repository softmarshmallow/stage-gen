# P91 Cast Pan - native integration and independent visual review

**PASS for the inspected story and laboratory compositions.** This reviewer
implemented the focused QA runner, not Layer Pan, the story integration or the
study controls. No artwork was generated or changed.

The reading-room exchange now moves the cast together to center Riko, then
Yuzu, then Riko again. The bookcase, fireplace and dialogue remain in place.
The selected speaker and neighboring actor stay readable; other actors can
move beyond the viewport as the group is reframed. Their local spacing and
scale remain intact. Riko's existing Restless Bounce and the replies' Speaker
Bounce remain composed with the group translation.

The dedicated Cast Pan study shows a smooth interrupted retarget and a return
home. Its English and Korean controls fit at both native sizes. A separate
sample composes a local Quick Approach with the group pan: Nami moves toward
Yuzu while the entire cast also translates over the stationary background.

## Focused evidence

[`cast_pan_integration_checks.gd`](../cast_pan_integration_checks.gd) passes
with **14 captures at 1280 x 900 and 2560 x 1800**, zero failed assertions,
and no script errors or leaked-object warning. Logs are
`/tmp/p91-cast-pan-native.log` and `/tmp/p91-cast-pan-native-console.log`.
Existing runtime PNG import/export warnings remain unchanged.

- The first story cue waits 0.35 seconds, then translates the cast by -390
  logical pixels over 0.45 seconds. Riko's presented center reaches X=640.
  Subsequent cues retarget the group to +390 for Yuzu and back to -390 for
  Riko, with no accumulated offset. The completed framing holds.
- Every actor retains its base local blocking rectangle. All actors receive
  the same X translation, and their actual presented rectangles match the
  composed world and pan transform of their current posed rectangles.
  Existing focus animation may change posed Y. Attached manpu receives the
  same transform while retaining its own introduction animation.
- Native background pixels match exactly before and during both pan
  directions: 524,800 pixels at 1x and 2,099,200 at 2x. For this comparison
  alone the cast is briefly hidden without advancing time, revealing the same
  background region; it is restored before every recorded frame. This avoids
  treating changed actor occlusion as background movement.
- An active story pan survives explicit pause, English/Korean switching and
  an actual detour to the independent Presentation Lab with identical pan
  state and presented actor geometry. The following monologue clears the
  cast and restores the pan to identity.
- The study retargets midway from an offset of -195 without a jump. Its
  active state survives pause and language switching; completion centers
  Nami, and Home restores identity. Reset clears both group and local motion.
- In the composed study sample, Quick Approach moves Nami's local center
  from X=250 toward X=360, reaching X=305 after 0.16 seconds. Yuzu and Sena
  retain their local rectangles. All three then receive the independent
  group transform exactly once; manpu follows and background pixels remain
  unchanged.

This proves the bounded 2D host compositions and in-session continuity.
Targets are resolved when the cue starts; this is not continuous target
tracking. It does not establish arbitrary scene-graph behavior, cross-version
save compatibility or a performance benchmark.

## Digest-bound captures

[The manifest](manifest.json) records all 14 capture hashes, six runtime source
hashes, state samples and the empty error list. All recorded source hashes
match the inspected final files. Its SHA-256 is
`6867abfc003dc96c77e037ea9fc04bc9a01ceaa71f89dc8697f168e1c02a6b56`.

| Inspected capture | SHA-256 |
| --- | --- |
| [Story before pan](story-before-1.png) | `8506a812047cdac640a0e4e3b171227449b22fc68dde3ed4baf7092807cca332` |
| [Riko centered](story-riko-centered-1.png) | `a447cff4364a66c225a84891ee8b958bf4b227b55bea942185ea15dcf9de7aed` |
| [Yuzu centered at 2560 x 1800](story-yuzu-centered-2.png) | `ac4a06b02c97060746f7219d4498cd3e80738e054d576183ee3635ab134ad3c0` |
| [Paused study retarget in English](lab-retarget-paused-en-2.png) | `49bc4d68575fbb9b3c876588806ec626e3af8ef0606d82a64b15d1b406d8d062` |
| [Local approach composed with group pan](lab-local-approach-composition-ko-1.png) | `0ea250d708a5ed640c18566024a7faffe557e39ec723a1bb0755cef8d912e390` |
