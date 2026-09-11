# Character visual effects: working vocabulary

The projected-character look is called **hologram** or **holographic projection**
in this spike. The broader working category is **character visual effect**.
These names describe the experience and its scope; they do not decide module
boundaries or establish a universal industry taxonomy.

This is established effect vocabulary: Unity's official
[hologram shader lesson](https://learn.unity.com/course/get-started-with-shader-graph/unit/hologram-and-vertex-displacement-shaders?version=6.3)
also describes moving scanlines and flicker as holographic-display techniques.
The broader grouping used here is a project working choice.
The broader [terminology dictionary](TERMINOLOGY.md) and
[current status](CURRENT_STATUS.md) also cover camera, screen, and narrative
effects introduced after the hologram proof.

## Terms to keep distinct

| Term | Meaning here |
| --- | --- |
| Character visual effect | A visual treatment applied to a particular actor; the umbrella for this experiment. |
| Presentation Animation | Shared scalar keyframe sampling for position offset, scale, opacity, and brightness. Target controllers own their cues and clocks; see the [common local contract](presentation/animation/README.md). |
| Actor Focus | Working umbrella for speaker emphasis, triggered by a change of speaking actor. Its interchangeable presets include motion, enlargement, dimming, fading, and none; see the [local contract](presentation/focus/README.md). |
| Manpu Introduction | A local animation for each newly visible actor/mark pair, composed with its owner's motion. It uses the shared sampler with independent clocks; see the [local contract](presentation/manpu/README.md). |
| Hologram / holographic projection | The named look: a projected transmission with cyan tint, partial transparency, scanlines, and subtle signal distortion. |
| Actor Halo / Outer Glow | A soft colored outline outside a sprite's alpha silhouette, rendered behind the unchanged source. Its [contract](presentation/effects/ACTOR_HALO.md) owns source geometry, padding, color, radius, intensity, and strength. |
| Ominous Corruption | A screen-reading treatment with darkening, mist/aura, motes, mild refraction, and red glow. An actor's alpha can define coverage, but areas or the full screen also work. [Contract](presentation/effects/SCREEN_FIELDS.md). |
| Effect preset | A named treatment and its settings. The material demo offers Normal and Hologram; Actor Focus has separate animation presets for speaker emphasis. |
| Material effect / shader effect | Rendering technique that changes the character's pixels through a material. A shader is an implementation tool, not the name of the experience. |
| Post-processing | Processing an already-rendered image, which may be a whole scene or an isolated character render target. |
| Character transition | A timed entrance, exit, or change of visual state. It may animate an effect's strength or other settings. |
| Character Exit | Working umbrella for a per-actor departure lifecycle and its interchangeable color/coverage presets; see the [local contract](presentation/transitions/README.md). |
| Cast Transition | Working umbrella for a sequential cast handoff: departure, optional survivor repositioning, then arrival. The pattern owns this order; see the [local contract](presentation/transitions/CAST_TRANSITIONS.md). |
| Motion curve | A function mapping phase time to translation progress, with Linear, Ease in / out, and adjustable Spring options. The runtime and graph share its samples; opacity keeps separate bounded tracks. |
| Silhouette Fade | A two-phase exit: color fades into an alpha-shaped black silhouette at retained source coverage, then the black silhouette's opacity fades. Opacity Fade is the comparison preset. |
| Overlay / attached visual | A separately drawn element associated with an actor, such as manpu. |
| Effect cue | A working name for an authored instruction to apply, change, or clear a treatment on a named actor. No new public cue contract is defined. |

**CRT effect** is a more specific display-emulation description: scanlines,
phosphor/mask patterns, curvature, and similar television artifacts. Scanlines
can contribute to a hologram, while the overall appearance here represents a
projected character. The selected components and intensity are demonstration
choices, open to the user's visual review.

## How the current proof is applied

Godot's documented 2D mechanism is a `canvas_item` shader attached through a
`ShaderMaterial`. Each actor can use the same shader program with separate
material parameters; sharing one mutable material would share those changes
between actors. See [CanvasItem shaders](https://docs.godotengine.org/en/stable/tutorials/shaders/shader_reference/canvas_item_shader.html)
and [ShaderMaterial](https://docs.godotengine.org/en/stable/classes/class_shadermaterial.html).

The hologram proof shades the actor's own sprite texture. Godot separately offers
[screen-reading shaders](https://docs.godotengine.org/en/stable/tutorials/shaders/screen-reading_shaders.html)
for processing already-rendered screen content. That extra image-processing
stage is not needed for the hologram. P74's Refraction Field and Ominous
Corruption do use screen reads, with a BackBufferCopy before each pass. The host
owns which earlier world pixels are affected and places its UI afterward.

Keep three questions separate during later review:

1. **What changes?** The actor's appearance, an attached graphic, or the scene.
2. **When does it change?** A persistent state, a reaction beat, or a transition.
3. **How is it drawn?** A material, animation, overlay, or composited render target.

This avoids treating every visual feature as a shader or every shader as a
module. The games already compose several effects through explicit host draw
order and clock ownership. This does not define a universal composition policy,
general effect stack, or approved module extraction.

P63 composes Actor Halo with Camera Drift in Afterlight's portrait detail shot.
The halo is a separate `TextureRect` and material behind the source sprite,
following the same full source rectangle and camera offset. The renderer adds
padding for the glow; a host clip defines the visible shot. Cropping the source
alpha into a rectangular image would create an unwanted glowing cut edge, so
the full texture remains bound. The halo changes no source-art pixels and does
not move the camera. It has no clock; the host can animate its strength.

That demonstrated order is explicit: background, halo, character, then the
host's screen UI. It does not establish a universal shader stack. Lens Flare
belongs to the projected scene lighting. P99 adds sustained Ambient Particles through a separate Sprite Particle Emitter;
Ominous Corruption's procedural motes remain local to that shader treatment.

## Matching voice processing (P99)

**Audio Effects → Voice Processing → Transmission Voice** is the separate audio
umbrella and preset. It is coordinated with a visual effect by the host, not
embedded in a character shader or in TTS generation. The [processor contract](presentation/audio/VOICE_PROCESSING.md)
owns band filtering, mild distortion, strength, true bypass, an isolated audio
bus, reset and cleanup. It knows no character, dialogue or projection state.

Afterlight's root marks Eira's framed projection with `voice_effect:
"transmission_voice"` and selects strength 0.65. Its story applies processing
only when the actual voiced speaker is currently staged as that projection.
The four existing Eira recordings in each language remain unchanged; her two
protagonist replies are explicitly unvoiced and use the dry typing fallback.
Physical speakers, offscreen voices, and the return intertitle stay dry.
Language switching, replay and Lab restoration rebind the current ready clip;
advancing stops it before resetting the processor. The Lab supplies dry/wet
comparison, strength, pause and language controls without generation.

P95/P96 installed localized voiceovers with explicit no-voice policy and
recording revisions. Runtime processing does not alter those revisions or
request regeneration. Native DSP measurements and lifecycle checks pass;
listening quality is unreviewed. See [audio evidence](qa/transmission-audio/REVIEW.md).

## Request and evidence

The user's exact wording is [P16](USER_PROMPTS.md#p16); the short outcome belongs
in [REQUESTS.md](REQUESTS.md). [README.md](README.md) describes the playable
controls and [QA.md](QA.md) records validation and visual evidence.

## Framed transmission in Afterlight (P81/P82)

Afterlight now gives Eira a dedicated private six-turn conversation in its
Relay Laboratory. The existing hologram shader treats a clean portrait feed
inside a floating code-drawn screen. Her technical researcher design and the
scientific environment support that framing; Riko remains physically present
in the ensemble. The local transmission display adapter owns frame geometry,
clipping and presentation from the host clock. It introduces no new global
effect policy. P99 coordinates the separate Transmission Voice processor with this display state.

## Stronger default treatment (P83)

The shared shader now uses higher-contrast four-pixel scanlines, a brighter
rolling band, stronger signal fluctuation, and sparse horizontal displacement.
These cues distinguish a transmission even when its source art is already blue.
The shader and actor presenters default to 90% strength; Afterlight's framed
portrait uses a host-selected 70%. Strength zero retains the original texture
and modulation, and each material remains independent. Frame, background and
dialogue pixels remain outside the feed treatment. No new asset is needed.
