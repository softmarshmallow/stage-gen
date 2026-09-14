# Movie Sprite Actor

Pre-rendered body motion with independently controlled facial states. This Godot
addon plays prepared transparent PNG atlas frames indefinitely and applies
independent eye and mouth replacements on the same actor canvas. The host directs
blinks, speech, placement, pause and time. No rig, skeletal motion, provider,
generation tool, story framework or game is imported.

Copy this directory to `res://addons/movie_sprite_actor/` and the separately owned
`content_io` addon to `res://addons/content_io/`. Both payloads are required.
Development uses a sibling-package link; distributable projects copy real files.
The package project and its examples/tests are not runtime dependencies.

```gdscript
const Actor = preload("res://addons/movie_sprite_actor/movie_sprite_actor.gd")
const Content = preload("res://addons/content_io/local_content.gd")

var content := Content.new()
var actor := Actor.new()

func _ready() -> void:
    var errors := content.configure("/absolute/real/content", "files")
    if not errors.is_empty():
        push_error(str(errors))
        return
    add_child(actor)
    actor.playback_ready.connect(func(): actor.set_eye_state("eyes_closed"))
    actor.failed.connect(func(messages): push_error(str(messages)))
    errors = actor.configure(content, "actors/example.json")
    if not errors.is_empty():
        push_error(str(errors))

func _process(delta: float) -> void:
    actor.advance(delta)
```

The descriptor's texture paths are relative to the content root, not its own
directory. Bind only states the descriptor declares; `rest` always reveals the
unmodified current body frame within that channel. Applying a face state does
not seek or restart the body.

[API and representation contract](API.md) specifies admission limits, methods,
failure/buffering behavior, the supported fixed registered-face profile and the
preparation invariants. [sdk.json](sdk.json) declares the installable boundary.
The initial local package is a canary, not a published release or a claim of
Live2D format compatibility.

## Why this representation exists

The `movie_sprite` asset family can obtain already rendered motion from video
models and compatible facial states from image models. `movie_sprite_actor`
consumes prepared raster results without requiring manually authored deformation.
The same runtime also accepts non-AI assets satisfying its contract.

The neutral face is already in each body frame. Independent face textures replace
selected RGB while preserving that frame's body alpha. There is no separately
rendered neutral face plate in this profile. Runtime video decoding, moving-head
registration, anatomy annotation, phoneme synchronization and generation-module
promotion are outside this package.
