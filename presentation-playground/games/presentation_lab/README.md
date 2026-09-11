# Presentation Lab

A separate demonstration game with two collections: **Command Link** and
**Afterlight**. The actual games contain their stories and small navigation
menus; focused feature controls live here.

```sh
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/presentation-playground -- --game presentation_lab --language ko
```

Twenty-four focused studies are available; collection/menu routes are navigation,
not extra effect demonstrations. The Command Link collection offers eleven raster/art, dialogue, contact,
focus, exit, cast, camera, location, manpu, and hologram workbenches.
The Afterlight collection offers Walking Approach, Eye Transitions, Intertitle,
Camera Drift, Actor Halo, Actor Motion, Sigh Puff, Radial Sprite Burst,
Background Blackout, Cast Pan, Ominous Effects, Ambient Particles, and
Transmission Voice Processing studies: thirteen Afterlight studies in total.
The lab navigation and Ominous Effects study are English; the other Afterlight
study text supports English/Korean.
The [current project inventory](../../CURRENT_STATUS.md) records remaining
mechanisms separately from these study routes. A route count is not a module
or effect count.

[root.gd](root.gd) binds fresh prepared fixtures. It may reuse the games' art
bindings without accessing their running scenes. The moved Afterlight study
host and route UI live under [afterlight/](afterlight/); the earlier tactical
workbenches remain under [demos/](../../demos/). These are demo integrations,
not shared production UI or a second story runtime.

Visits preserve each game's separate in-session checkpoint. Changing lab
sliders, guest selection, background, or study language does not change a game.
Old `--route demos/*` and Afterlight study links redirect into this root for
compatibility. New links should use `--game presentation_lab` explicitly.

The Actor Motion study isolates Walk-Away in both directions and Restless
Bounce. Choose an actor and a preset, then play or replay it. Pause holds the
current pose and timeline. Restore actor cancels the motion and returns the
actor to a visible, centered stance. Mode and actor changes also restore that
neutral stance. Restless Bounce changes only the vertical pose; it leaves the
actor in the scene. Language changes preserve the active motion.

Quick Approach uses two visible actors in this same study. The selected actor
approaches the next guest in the fixture; choose left/right approach, duration,
center spacing and linear/eased/spring interpolation. Play captures a destination
and holds it after completion. Parameter changes and replay restore the pair's
starting composition. This is an Actor Blocking preset over Motion Curve,
separate from the first-person Walking Approach camera study.

```sh
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/presentation-playground -- --game presentation_lab --route actor_motion_study --language ko
```

The Cast Pan study treats three actors and their attached manpu as one visual
layer over fixed scenery. Choose a target to center it, then choose another
while moving to test continuous retargeting. Duration and curve configure future
pans; changing the anchor retargets the current selection. Home animates back,
Reset returns immediately, and pause/language changes preserve state. These
controls change layer framing, not the actors' local blocking coordinates.

```sh
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/presentation-playground -- --game presentation_lab --route cast_pan_study --language ko
```

The Manpu animation study compares a persistent static mark, a shake
introduction, independently expiring one-shot puffs, a stepped transform loop,
and two- or three-frame loops. Frame examples use existing different marks as
explicit timing fixtures, not newly generated animation artwork. Triggering again in
one-shot mode creates another instance while the first keeps its own time.
That mode offers Sigh Puff (mouth, outward/upward) and Sweat Drop (temple,
downward) using the same event API. Changing variants clears events and rebinds
the attachment; language and 2D/3D changes retain the selected variant and phase.
Replay rewinds an active persistent mark, or replaces transient puffs with one
fresh emission. Remove clears all marks without changing pause.
Pause freezes all current instances. Reset, actor changes, and mode changes
clear marks and events. Language and 2D/3D presentation changes preserve them.

Its 3D preview is a bounded rendering proof: a real `Sprite3D` character and
`Sprite3D` puffs inside an orthographic `SubViewport`, over the same flat indoor
background. It reads the same controller samples used by the 2D cast, without
owning another clock. Mark offsets use the original mark height and are mapped
through the billboard's camera-facing plane. The camera angle toggle proves
the attachment survives a different 3D view. The subviewport renders at native
output resolution, including a 2x window. This does not add a 3D story game or
environment. See Godot's [SpriteBase3D](https://docs.godotengine.org/en/stable/classes/class_spritebase3d.html)
and [Camera3D](https://docs.godotengine.org/en/stable/classes/class_camera3d.html)
APIs for the concrete renderer used here.

```sh
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/presentation-playground -- --game presentation_lab --route sigh_puff_study --language ko
```

The Ominous Effects study compares Barrier Distortion, Heat Haze, Ominous
Corruption, and a combined treatment. Choose either of two existing sprites,
a neutral rectangle, or full-screen coverage. The source sprite supplies only
its alpha mask; the fields can also run without a sprite. A runtime
`NoiseTexture2D` toggle compares an optional reusable input with procedural
shader noise. Both fields follow one host clock and retain it when targets,
strength, or the noise source change. Pause freezes that clock and the camera.
Reset returns the clock and Impact Shake to their starting frame while keeping
selected controls. Zero strength disables both passes and their screen copies.

The Impact button starts or retriggers a heavier finite shake. Its final camera
transform preserves background coverage and is applied once to world targets;
full-screen contamination and laboratory controls remain in screen space.
`qa/ominous_vfx_checks.gd` checks lifecycle, target-independent source binding,
layer order, coverage, and native 1x/2x rendering. Add `--capture-ominous` to its
native run to write local PNG evidence under `qa/ominous-vfx/`.

```sh
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/presentation-playground -- --game presentation_lab --route ominous_study
```

The Radial Sprite Burst study emits independently expiring groups of prepared
sparkle, heart, or mixed sprites. Sprite selection leaves the emission seed,
outward movement, pop, spin, and fade unchanged. Count, duration, and travel
distance affect future emissions; existing groups retain their settings.
Emit again to overlap groups, pause to freeze their clocks and camera shake,
or clear to cancel all groups. Language changes preserve active groups.

The host chooses an origin near Nami's chest and owns two effect layers around
the actor. Behind starts close to that origin on the rear layer. In front uses
the same origin on the front layer; Around uses that layer with a wider initial
ring. These are host placement choices over the same shared burst. Zoom and
finite Impact Shake apply the same world camera to background, actor, and
sprites, while the controls stay still. A burst is a finite emission; the
Ambient Particles study below demonstrates sustained emission.

```sh
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/presentation-playground -- --game presentation_lab --route sprite_burst_study --language ko
```

The Background Blackout study places a black layer after the scenery and before
Nami. Blackout fades that layer in and holds it; Restore background fades it
out to reveal the same unchanged scenery. The actor's texture, transform,
opacity, color, and material stay untouched. Duration controls the next fade,
including an immediate transition at zero. Reversing direction starts from
the current strength. Pause freezes the transition clock; Reset immediately
clears the layer and resumes. Language changes preserve the fade.

```sh
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/presentation-playground -- --game presentation_lab --route background_blackout_study --language ko
```

The Ambient Particles study compares quiet interior dust with an infernal mix
of smoke, embers, and sparks. These host-owned atmosphere profiles compose
independent instances of the shared Sprite Particle Emitter. Density changes
restart the selected profile with matching capacity; Replay restores its seeded
initial state. Stop emission lets existing particles finish their lifetimes.
Pause freezes emission and camera motion, while language changes leave both
unchanged. Background and particles receive the same final Impact Shake camera;
the controls remain still. Procedural raster fallbacks supply the sprite inputs,
which the emitter can replace without changing its motion contract.

```sh
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/presentation-playground -- --game presentation_lab --route ambient_particles_study --language ko
```

The Transmission Voice Processing study uses Eira's existing localized recording
and prepared floating display. Play starts the line; Original and Processed
toggle the same private voice bus while the source continues from its current
position. The strength slider changes the treatment without replaying the clip.
Pause, Stop and Replay control only this study's player. Switching language
replaces an active clip from the beginning and retains pause. Leaving the route
stops playback and removes its private bus. The study performs no generation and
does not claim a listening verdict. Missing prepared audio disables playback.

```sh
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/presentation-playground -- --game presentation_lab --route transmission_voice_study --language ko
```

`qa/ambient_voice_lab_checks.gd` checks both studies at 1x/2x with actual button
input, seeded replay, draining, camera attachment, prepared voice playback,
dry/wet continuity, pause/language behavior, and private-bus cleanup. Add
`--capture` to a native run for local visual evidence under
`qa/ambient-voice-lab/`.
