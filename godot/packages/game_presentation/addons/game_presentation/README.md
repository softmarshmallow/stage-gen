# Game Presentation SDK

A code-first Godot presentation toolkit extracted directly from the existing game
implementation. Copy this directory to `res://addons/game_presentation/` and its
declared `content_io` dependency to `res://addons/content_io/` in a Godot project.
No editor plugin activation, Python runtime, provider credentials,
Scenario parser, example assets, or shared game UI is required. The directory and
its BSD license are the presentation payload; each dependency includes its license.

This initial package is **0.1.0-canary.1**, a local development version, not a
published release. The [API inventory](API.md) names the supported canary script and shader
entry points; underscore-prefixed helpers are private. No stable release is
advertised yet. Consumers pin the complete payload and upgrade deliberately.
Future stable and canary releases must name their supported surfaces and changes;
Scenario compatibility is not a prerequisite for changing SDK behavior.

## Install and compose

Keep the install path fixed, including shaders, includes, neutral preset JSON and
source `.uid` sidecars. Godot regenerates `.godot/` caches. Do not copy those
caches or discard source UIDs. Run a headless editor import before a first command
line launch of a clean copy. The tested baseline is Godot 4.7.2 with the desktop
Compatibility renderer. Other renderers/platforms need their own verification.

Each host preloads the components it needs. There is no mandatory game superclass
or facade. This complete frame example moves a host-provided world layer while
its UI stays outside that layer:

```gdscript
extends Control

const DIALOGUE_CAMERA = preload("res://addons/game_presentation/camera/dialogue_camera.gd")
var camera = DIALOGUE_CAMERA.new()
var world := Node2D.new()
var paused := false

func _ready() -> void:
    add_child(world)
    # Place your background and actors under world; author your UI separately.
    # The background must cover this declared rectangle before the transform.
    var errors = camera.initialize(Vector2(1280, 900), Rect2(-128, -90, 1536, 1080))
    assert(errors.is_empty(), str(errors))
    errors = camera.focus("guest", Vector2(640, 300), Vector2(640, 340), 1.2, 0.7)
    assert(errors.is_empty(), str(errors))

func _process(delta: float) -> void:
    if not paused:
        camera.advance(delta)
    var pose = camera.sample()
    world.scale = Vector2.ONE * float(pose.zoom)
    world.position = Vector2(float(pose.offset_x), float(pose.offset_y))
```

The source files expose defaults, validation ranges, return shapes and per-method
contracts. Check returned errors before committing related host state. The
inventory links every public method to its owning source.

## Responsibilities

| Directory | Supplied behavior | Host responsibility |
| --- | --- | --- |
| `motion/` | Track sampling, configurable motion curves, layer translation | Target membership, base pose, draw order, choreography |
| `actors/` | Actor Focus, Manpu animation, character exit, bounded cast handoff | Actor IDs, art, anchors, applying color/matte/transform samples |
| `camera/` | Dialogue focus, establishing shot, walking approach, drift, impact shake | World bounds, target choice, composition order and scene timing |
| `transitions/` | Eye Opening/Closing/Blink and Background Blackout | Screen mask/background plane, scene swap and user input |
| `effects/` | Actor Halo, refraction/corruption fields and shader inputs | Layer placement, masks, source textures and artistic presets |
| `effects/particles/` | Radial Sprite Burst and sustained Sprite Particle Emitter | Interchangeable sprites, world region, timing and density |
| `text/` | Stable-ID text lookup and intertitle reveal state | Languages, font/layout, monologue intent and navigation |
| `audio/` | Supplied voice/typing playback and isolated voice-processing bus | Voice policy, line binding, stale-audio decisions and advancement |
| `interaction/` | Point Contact hit testing and one-shot confirmation | Gesture, target location, UI feedback and story outcome |
| `content/` | Compatibility facade over the `content_io` addon | Catalog shape, IDs, directory layout, approval and freshness policy |

Automatic sprite blinking, location labels, looping title videos, Quick Approach,
Cast Pan, autoplay, story decisions and whole UI remain host compositions.
Walk-Away, Restless Bounce and Sigh Puff/Sweat motion are reusable presets;
their semantic use in a scene does not create another module. The bundled neutral
catalogs in `actors/presets/` are usable defaults, not game content schemas.

## Time, geometry and lifecycle

Most controllers are `RefCounted` samplers. Call `advance(delta)` once per host
frame; pause by withholding time. Rebuild the result from base geometry each frame,
then apply samples. Do not accumulate camera or actor offsets onto the previous
rendered pose. A sample does not navigate the story. Completion and required input
are host decisions; voice completion never automatically advances anything.

Effect `Control` nodes own their rendering/material instances, not story time.
Refraction/corruption use explicit `set_time`, strength and rectangle setters.
Particle nodes separate `advance` from `present(camera)`; supply the final world
camera, including shake, once. Do not also parent an already transformed particle
layer under that camera. Screen-space particles use the identity transform.
Audio nodes own engine playback and DSP bus cleanup; use `set_paused` and `stop`
as well as pausing visual clocks. Never layer typing over supplied voice.

Use each component's actual interruption API (`clear`, `reset`, `stop`, replacement
`start`, or individual cancellation). There is no common lifecycle superclass.
Some controllers provide `restore`; others expose inspection snapshots only.
Do not assume `get_state` is a portable save format. Checkpoints are currently
in-session; durable cross-version game saves need a host migration policy.

Coordinates are 2D logical canvas pixels unless a parameter says otherwise;
UV anchors are normalized to the supplied full source texture, with top-left
origin and positive Y downward. Camera transforms supported by the current
composition are positive, axis-aligned uniform scale plus translation. Hosts own
trim/crop mapping, explicit face/contact/Manpu anchors and any artistic offset.
Alpha bounds do not establish anatomy or body size. Automatic anatomy annotation
and standing framing calibration are not implemented by this SDK.

Bounds checks in camera controllers apply to the declared background rectangle.
The host remains responsible for coverage after composing drift, walking motion
and impact shake, as well as any untransformed/fixed background choice. Actor
Halo uses source alpha and a displayed source rectangle; it does not infer anatomy.
Field shaders need appropriate `BackBufferCopy`/screen-capture ordering when
composed; distortion must sample the intended world layer before UI is drawn.

The cast-transition controller intentionally retains its tested **three registered
actors, two occupied slots and 1280-wide logical stage** contract. Use independent
actor motion or host choreography for a different topology. It is not a general
cast scheduler. Eye Transition's `reached_closed` reports a sampled phase boundary;
a large time step can pass it without presenting a black frame. Hold/render a
closed frame before swapping scenery when visible concealment is required.

## Content and export

The optional [local content loader](content/local_content.gd) takes an explicit
root and backend. All bindings are relative, with no traversal, absolute path,
scheme, backslash or symlink. Returned dictionaries contain `errors` plus `value`,
`resource`, `bytes` or `path`; failures do not trigger generation or networking.

- `resources`: root `res://` (or a project subdirectory), available source bytes
  first to preserve pixels; imported resources when those bytes are absent. JSON
  and other raw documents must be explicitly included in exports.
- `files`: normalized absolute local directory, decoded PNG/JPEG/WebP textures,
  MP3/WAV/Ogg audio, JSON and Ogg Theora `.ogv` video. This is also usable beside
  an exported game. The selected backend does not fall back to another content root.

The loader accepts prepared media only, never scenes or scripts. It is a local
file boundary, not an OS sandbox against concurrent filesystem replacement.
Video decoding happens in `VideoStreamPlayer`; an accepted OGV container still
requires a playback check. Audio SHA-256 verifies original compressed source bytes;
MP3 bytes remain available after Godot import, whereas other imported formats may
need explicitly retained source files for that optional check.

Hosts export their JSON and runtime-loaded media explicitly. Shader dependencies
are preloaded inside the addon. Do not assume dynamically named assets are found
by Godot's dependency scan. The SDK carries no generation code, recordings,
example artwork, game-specific voice manifest or mandatory catalog schema.
Only code and package documentation are covered by the included [LICENSE](LICENSE).
