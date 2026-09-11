# Character hologram runtime review

Date: 2026-09-09
Engine: Godot 4.7.2, OpenGL compatibility renderer on Apple M4 Pro.

## Implementation

The fixed three-actor scene now uses one input-ignoring `TextureRect` per
actor and one separate `ShaderMaterial` instance per actor. The local overlay
canvas draws manpu and fingertip feedback above those sprites. The existing
background and interface keep their own canvases. Source artwork is unchanged.

Sera starts with Hologram at 80%; Mira and Lena start Normal. In dialogue,
**T** or the target button chooses an actor, **E** or the effect button toggles
Normal/Hologram, and the slider changes that actor's strength from 0% to 100%.
Controls occupy the old dialogue hint row. Settings persist through dialogue,
location, and mode changes; Restart restores the initial demonstration.
Mira's setting follows her registered blink pair and contact pose.

The shader preserves the source alpha silhouette, entry opacity, and speaker
tint. It combines cyan luminance mapping, modest translucency, horizontal
scanlines, a moving bright band, slow signal fluctuation, and sparse horizontal
sampling displacement. Zero strength takes an exact normal-color branch;
Normal removes the material. All animation uses an explicit local time uniform
so captures can freeze it. There is no screen texture, screen-wide filter,
audio behavior, new entry/exit choreography, or extracted module.

## Focused verification

`validation.log` records a successful headless check at 1280 x 900,
720 x 900, 960 x 580, and 640 x 560. macOS sandbox messages about the usual
user log directory and certificate lookup precede the pass; they are not shader
or script failures. The two unrestricted windowed capture runs also execute
all focused checks, and their logs contain no errors.

The added checks exercise independent material instances and strength values,
normal/zero behavior, input-ignoring sprite layers, overlay ordering, hidden
actors in the gallery, preserved blink/contact textures, effect settings across
mode/location/dialogue changes, entry alpha, restart defaults, and actual routed
mouse/key/slider controls. Existing actor framing, manpu, location titles,
fingertip mouse/touch, text fit, and dialogue progression checks still pass.

The real renderer completed all **30 states** at both 1280 x 900 (`normal/`)
and 640 x 560 (`smallest/`); both processes exited 0. This verifies actual GPU
shader compilation and rendering. Each PNG has JSON metadata recording actor
and control rectangles, effect settings, dialogue index, location, and time.

Paired effect evidence uses the same Sera line, cafe, entry, and blink state:
`effect_normal`, `effect_zero`, `hologram_sera`, `hologram_sera_later`,
`hologram_mira`, and `hologram_lena`. The second Sera frame changes only shader
time from 1.0 to 4.0 seconds. Further states cover Mira's blink and contact pose.

The runtime author inspected normal Sera, minimum-window Sera, Mira transfer,
and hologram contact. The projected cyan appearance is recognizable, while
faces, complete silhouettes, painted manpu, controls, and fingertip remain
readable. Fine facial detail is naturally smaller at the minimum viewport.
The parent owns the separate numerical scope comparison and independent visual
verdict; those should be read alongside this implementation review.
