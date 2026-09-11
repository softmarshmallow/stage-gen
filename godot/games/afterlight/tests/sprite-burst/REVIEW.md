# P88 Radial Sprite Burst - native integration and independent visual review

**PASS for the inspected final captures and focused native runtime checks.**
The integration reviewer did not implement the shared effect, story cue, or
laboratory route. This is a review of runtime composition using already
prepared sprites; no artwork was generated or replaced.

Sena's repaired-ward cue now produces a visible group of golden sparkles that
emerges from behind her and spreads into the surrounding space. At the early
sample most particles remain hidden by her sprite; the 0.35-second sample
clearly exposes the dispersing group around the hair and shoulders. The later
0.95-second sample is wider and fainter, and the 1.45-second sample is clear
again. The story's face and dialogue remain unobscured at both native sizes.
The individual sparkle input contains several small glints, but its displayed
size is restrained and does not read as repeated oversized manpu.

The laboratory makes the host's depth choice legible: behind placement is
occluded by the character, around placement starts on a wider ring, and front
placement visibly overlaps her. Hearts and mixed sprites use the same motion
without code changes. The overlapping front-layer stress example intentionally
places some sprites over the face; this is confined to the explicit laboratory
selection. Default story placement keeps the face clear. English/Korean control
labels and the six-row effects menu are readable without overlap in the
inspected captures. At doubled resolution, the character, sprites, and UI remain
sharp and proportional.

## Focused runtime evidence

[The native runner](../sprite_burst_integration_checks.gd) completed with 36
captures at 1280 x 900 and 2560 x 1800 and zero failed assertions. The final log
is `/tmp/p88-burst-native-final.log`; it contains the existing runtime-image
export warnings but no script errors or ObjectDB leak warning.

- The story waits for its authored 0.85-second delay, emits once at the actor's
  world anchor, uses the final camera transform, expires, and never respawns.
  Advancing early cancels the previous beat's particles immediately.
- English/Korean switching, pausing, and a real application detour to the
  Presentation Lab preserve an active story burst's timing and motion samples.
- Isolated native pixel measurements verify world translation, position/size
  scaling under 2x camera zoom, fixed UI pixels, sampled fade alpha, and
  pixel-identical retention of the last valid camera after invalid input.
  Translation moved the measured particle centroid by approximately (48, 32)
  logical pixels; doubled camera zoom produced approximately four times the
  rendered sprite area at both window resolutions.
- One, another, and mixed sprite inputs preserve the same seeded motion,
  rotation, pop, and fade samples. Overlapping events finish independently,
  and cancellation removes the last visible event.
- Actual mouse input operates Lab placement/texture selectors and
  emit/pause/zoom/shake/clear buttons at both resolutions. During active shake,
  the actor and both burst layers receive the same changing world transform,
  background coverage is preserved, and the interface remains fixed.

The capture series and numeric checks support the displayed behavior. This
review does not claim native 3D integration, a general continuous emitter,
GPU performance benchmarking, or user approval of newly generated artwork.

## Digest-bound evidence

[The final manifest](manifest.json) records capture and source hashes, event
samples, coordinate metrics, and the empty error list. Its SHA-256 is
`2187c8787a5f81f98d7a62c239de9be3ca8ead243bd218604ca706ce5ac0d191`.

| Inspected capture | SHA-256 |
| --- | --- |
| [Story, early pop, 1280 x 900](story-age-0.08-1.png) | `df709921781aea01045a9643b54248c6895ecbbccdbcd15afa1d3eb365b88c26` |
| [Story, outward dispersion, 1280 x 900](story-age-0.35-1.png) | `c604d21e229e93b85a94def0421b5e93579139cbed52ebc24b6e1e961a4a6faa` |
| [Lab, behind actor, Korean](lab-behind-ko-1.png) | `e38fb6ac0a55ac54f26f17bd63a6a2aeb1d26fb98c11831dea73b3945723f090` |
| [Lab, around actor, Korean](lab-around-ko-1.png) | `ebc855b47c89df240b6397d7a05ed89c87a012bba4284e481de7e7647463228a` |
| [Lab, hearts in front, English](lab-front-en-1.png) | `f996d18e0b130b7670c6918134f82c5f5bccdd5533adbfc7175a59b6bf723a3d` |
| [Lab, six-row effects menu](lab-effects-menu-1.png) | `f4ce1230c3770ae922aa1860cf8e5a87a7984464cc7af2be4f0c62f7d0f3fe69` |
| [Story, outward dispersion, 2560 x 1800](story-age-0.35-2.png) | `e07ce839d14d0e86f90bda7cc825b00e969e7be9bf2d55da7da9d2d5ecc3332f` |
| [Story, fading, 2560 x 1800](story-age-0.95-2.png) | `23881e545c1b77f8e6c912c33c890dd1c26b944e3bac3f2ba597af5014ecd590` |
| [Story, expired, 2560 x 1800](story-age-1.45-2.png) | `3d71b074b5ae63047a6f9665e4cf707eb069790fac548542191f83982cb7e7da` |
| [Lab, overlapping sprites during paused shake and zoom](lab-shake-zoom-paused-2.png) | `9f11d1ad1da9b5220d398fdf2bbdeedb8f53c12a6eaba87bc2b01bc60ad5d941` |
