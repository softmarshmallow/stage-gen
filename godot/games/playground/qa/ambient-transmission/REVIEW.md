# Ambient Particles and Transmission Voice — P99

Verified 2026-09-11 with Godot 4.7.2, against the source hashes in
[validation.json](validation.json). The native run has three completed host
check groups, eight final captures, no script errors and no failed assertions.
No provider operations or media generation occurred.

## Main-story behavior

- Quiet interiors contain sustained warm dust; the relay uses cool dust.
  The Keeper hall composes smoke, rising embers and faster sparks. Each layer
  has a seeded bounded lifetime and independently supplied raster textures.
- Every ambient layer receives the world camera including Walking Approach,
  zoom and Impact Shake. Cast Pan moves characters without dragging this field.
  Particles draw behind the scenery blackout and actors; dialogue remains above.
- Ordinary dialogue preserves the emitter clock. Pause, locale changes,
  existing-history replay and an actual Lab round trip preserve the field.
  Returning to the reading room removes the infernal emitters.
- Existing Eira recordings in both languages receive transmission filtering
  only when she is the actual speaking projection. Ready voices still reveal
  full text; protagonist replies remain `none` and typing stays dry. Physical
  voices and call cleanup bypass the processor. Pause, language changes, replay
  and Lab restoration retain the intended binding and lifecycle.
- Audio stops before its private bus is removed during reverse child teardown.
  Host destruction returns the audio bus count to its initial value.

## Rendered review

Root inspected the native main-story and Lab captures. The Keeper's hall has
elongated ember/spark accents and soft smoke without covering her face or the
subtitles. Dust is deliberately restrained in bright interiors. The framed
transmission remains readable, with the existing contained hologram treatment.
Both 1280×900 and 2560×1800 capture groups retain the intended composition.

Main-story views: [quiet](no_ordinary_post-1280.png),
[Keeper](the_keeper-1280.png), [Eira](the_return_channel-1280.png),
[waking return](a_hand_to_hold-1280.png), and their `-2560` counterparts.
The [Lab evidence](../ambient-voice-lab/validation.json) adds eight native
captures of the two independent studies and expanded effects menu at both sizes.

## Component and regression evidence

[Sprite Particle Emitter checks](../ambient_particle_checks.gd) pass seeded
seek/step equivalence, bounded sampling, replaceable textures, camera admission,
pause, warmup, stop/drain, reconstruction and rejected-input atomicity.
[Native audio evidence](../transmission-audio/REVIEW.md) confirms exact dry/zero
bypass, frequency filtering, dry typing, no clipped output, unchanged EN/KO
recording hashes, isolated buses and cleanup. This is DSP measurement, not a
listening verdict.

[Regression records](regression-validation.json) retain fresh autoplay and
voiceover results without overwriting prior evidence. Autoplay traverses all
57 beats with one required contact; all 80 recordings remain ready and the 36
intentional exclusions remain valid. The existing Text Reveal Audio regression,
full ensemble check at both sizes, and all 24 Lab study routes also pass.
All 288 pre-existing EN/KO values, authored beats, voice policy/casting/manifest,
and standing-cast source remain unchanged. Twenty-four additive Lab UI keys
bring each language to 312 values. Documentation and whitespace checks pass.

## Limits

Listening quality and pronunciation remain unreviewed. Procedural raster inputs
are replaceable demonstration art; the implementation is a 2D canvas renderer,
not a proven 3D particle adapter or collision simulation. Desktop native checks
do not establish mobile performance or export packaging. Existing direct-image
import warnings and headless macOS certificate diagnostics remain. The legacy
accelerated full-ensemble check additionally reports two ObjectDB instances at
exit; the new focused native integration has no exit leak warning.

Standing-cast framing parameters remain explicitly deferred. This pass changes
neither generated source media nor upstream contracts or module packaging.

```sh
/Users/universe/.local/bin/Godot --path godot/games/playground --log-file /tmp/ambient-transmission-native.log --script res://qa/ambient_transmission_integration_checks.gd -- --game bishoujo_afterlight --language ko --capture-atmosphere
```
