# P92 Looping Manpu - native integration review

**PASS for the inspected native compositions and lifecycle checks.** The
renderer integrator authored this focused QA fixture; the coordinating
reviewer supplies the separate visual verdict. No artwork was generated or
changed. The existing nine raster marks remain the prepared art set.

## Focused evidence

[`looping_manpu_integration_checks.gd`](../looping_manpu_integration_checks.gd)
passes with **14 captures at 1280 x 900 and 2560 x 1800**, ten current runtime
source hashes, zero failed assertions and no script errors or leaked-object
warning. Logs are `/tmp/p92-loop-native.log` and
`/tmp/p92-loop-native-console.log`. The native capture helper explicitly draws
before reading the viewport so it also completes with a background macOS
window. Existing runtime PNG import/export warnings remain unchanged.

- The existing `no_ordinary_post` story cue holds its original mark pose for
  half of a 0.8-second cycle, then holds a 30-degree rotation at 0.8 scale.
  The loop continues beyond its first cycle. Pause, English/Korean switching
  and an actual Presentation Lab detour preserve the current phase. The
  following beat removes that cue.
- Afterlight rotates its TextureRect around the projected center. A 1.3x
  camera scale and translation apply once, with the pivot recomputed from the
  projected rectangle. Selecting a frame changes the raster while preserving
  the base cue ID used for attachment.
- An unavailable raster in a requested frame list rejects the entire
  Afterlight cue update before its clocks, active cues or texture change.
  The tactical host also reports unavailable frame art and surfaces authored
  cue validation errors.
- A persistent loop and an ordinary one-shot Sigh Puff coexist. The puff
  expires and releases its node while the loop remains alive. Replacing the
  cast clears persistent marks. A departing tactical owner removes its mark.
- The tactical CanvasItem renderer visibly changes the selected raster and
  pose in native pixels. Repeated synchronization preserves the loop clock;
  centered drawing restores the canvas transform after every mark.
- The study retains one controller while switching between 2D and 3D. At a
  25-degree camera angle, its Sprite3D plane faces the camera and preserves
  the sampled rotation around its center. Two- and three-frame modes render
  the selected texture from the study's own art bindings. Native 3D viewport
  size matches the window at both resolutions.
- Actual study controls replay and remove the loop, preserving explicit
  pause for replay. Reset clears both representations. Static, introduction
  shake and one-shot modes remain usable. Korean three-frame captures show
  the real mode label, live persistent-mark count, frame and fixture hint.

The existing
[`one_shot_manpu_integration_checks.gd`](../one_shot_manpu_integration_checks.gd)
also passes headlessly in `/tmp/p92-one-shot-regression-console.log`. Its 3D
assertion now checks the camera-facing basis rather than requiring automatic
billboarding, which would discard authored in-plane rotation. Its navigation
advances intervening clocks so a previous beat's intentionally surviving puff
does not contaminate a later emission check. This regression run is a state
and geometry check, not additional native visual evidence.

## Scope of the images

The story and study captures show normal authored hosts. The
`afterlight-frame-*` images are direct adapter fixtures: they deliberately
configure the cast renderer without updating the study's own status labels.
Their displayed zero-puff status therefore describes the study controls,
not the directly injected persistent mark.

The frame sequences intentionally reuse different existing marks to make
texture selection obvious. They demonstrate the timing and renderer contract,
not finished frame animation artwork. Camera composition is bounded to the
current translation and uniform-zoom hosts. The checks do not establish
arbitrary affine cameras, durable save compatibility or performance limits.

## Digest-bound captures

[The manifest](manifest.json) records all 14 capture hashes, ten runtime source
hashes, sample values and the empty error list. Every recorded source and
capture hash matches its final file. Its SHA-256 is
`994affa9fc7a6edcc931a8c18d98adcbcd14c245d19ccd415e85d3a4c58eaf99`.

| Capture | SHA-256 |
| --- | --- |
| [Story base pose](story-base-1.png) | `47eae0fe6a4c2f6b9b9c17e25d3d6156894dd06b4c9bdc4bbf89ab8bb1614be4` |
| [Story alternate pose](story-alternate-1.png) | `9a4c887986dd0816cfac98f8e848b60144970922b1a3c278dbf9a922df7fdf54` |
| [Story alternate pose at 2x](story-alternate-2.png) | `36ef3849cb177819095c0799b46479b2ee2ee386e9bd9fa660b0688376cd92ce` |
| [Direct Afterlight frame fixture](afterlight-frame-1.png) | `3d3f091b40591affb4fdad1148423b8d11083d487c3a0b1fdcfe7f89fea60097` |
| [Tactical frame and rotation](tactical-frame-rotation-1.png) | `49656daac5064748d0ee964da983b93914c77b8b64d954a2a001b8ad52598db2` |
| [Study stepped loop in 2D](lab-step-2d-en-1.png) | `b74ac3eac62038e47e1d6dbc33775d62438948f25b5d120115bbffa713a9e9ce` |
| [Study stepped loop with angled 3D camera](lab-step-3d-angled-en-1.png) | `e87b66664e9ff0e143342c78bea20e4d350b298fa895c5bd4051d005c010a36c` |
| [Korean three-frame study at 2x](lab-three-frame-ko-2.png) | `9230c8d0918de990d933b3826e62d777ee4f14b895171a36f94d10126264d1f1` |

## Independent visual verdict

**PASS — root reviewer, 2026-09-11.** Reviewed the native story base/alternate,
tactical frame/rotation, direct Afterlight frame fixture, English 2D stepped
loop, and angled 3D stepped loop at 1280×900. Also inspected the final Korean
three-frame study and alternate story pose at 2560×1800. The alternate story
mark is visibly smaller and rotated, with a stable character-relative anchor;
faces and dialogue remain readable. The 2D/3D mark orientations agree. Korean
controls and the full fixture hint fit, and the selected heart raster appears
beside the actor in the angled 3D preview. Direct adapter captures are renderer
proofs; their surrounding study status does not describe injected fixture cues.

This verdict binds the 14 captures and ten sources in manifest SHA-256
`994affa9fc7a6edcc931a8c18d98adcbcd14c245d19ccd415e85d3a4c58eaf99`.
Static captures establish appearance and layout; exact held-step timing and
loop continuity are established by the controller/native assertions above.
