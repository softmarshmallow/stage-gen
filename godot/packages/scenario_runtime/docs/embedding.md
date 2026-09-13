# Embedding Scenario in a game

The game invokes an admitted sequence when its own rules say a conversation or
presentation is relevant. Combat can continue underneath it. The game decides
whether an input reaches Scenario, whether a camera is granted, and what a
returned outcome means. The [contract](contract.md) defines that boundary.

## Smallest host

This complete `Control` script uses the optional stock surface and host. It has
no installed effects or media dependencies. Attach it in a project containing
the declared addon closure:

```gdscript
extends Control

const Host = preload("res://addons/scenario_runtime/bindings/host.gd")
const Surface = preload("res://addons/scenario_runtime/presentation/dialogue_surface.gd")
var host = Host.new()
var surface = Surface.new()

func _ready() -> void:
    add_child(surface)
    surface.action_requested.connect(_submit)
    host.bind_surface("dialogue", surface)
    var catalog := {
        "kind": "scenario-catalog", "schema_version": 1,
        "catalog_id": "game", "revision": "1", "definitions": {},
    }
    var program := {
        "kind": "scenario-program-v3", "schema_version": 3,
        "scenario_id": "warning", "entry": "hello",
        "nodes": [
            {"id": "hello", "kind": "line", "text": "Keep moving.",
             "presentation": {"channel": "dialogue", "profile": "bottom"},
             "next": "done"},
            {"id": "done", "kind": "end", "outcome": "heard"},
        ],
    }
    var result := host.invoke(program, catalog, {
        "session_id": "warning_1", "capabilities": {},
        "channels": ["dialogue"], "bindings": [],
    })
    if result.has("error"):
        push_error(str(result.error))

func _process(delta: float) -> void:
    host.tick("warning_1", delta)
    # The game processes outcomes here and keeps its own simulation running.
    for event: Dictionary in host.drain_events():
        if event.type == "scenario/ended":
            print(event.outcome)

func _unhandled_input(event: InputEvent) -> void:
    if event.is_action_pressed("ui_accept"):
        var result := host.submit("warning_1", {"kind": "advance"})
        if result.get("consumed", false):
            get_viewport().set_input_as_handled()

func _submit(action: Dictionary) -> void:
    host.submit("warning_1", action)

func _exit_tree() -> void:
    host.cancel("warning_1", "game_scene_exit")
```

A production game checks every admission result and gives each invocation a fresh
ID. The host retains completed session records; it does not permit reusing an ID.
Games can also consume Session reports through their own admitted presenter.
That is the same progression engine and event contract, not a story-specific
alternative director. A game presenter must not interpret node IDs as behavior.

## Capabilities, resources and channels

`host.prepare(document, catalog_document, policy, bindings)` performs admission
without creating a session or changing presentation. `invoke` repeats this check
at activation so intervening channel conflicts cannot bypass it.

Before invoking, register each mechanism with
`host.register_capability(type_id, schema, adapter)`. The schema contains its
version and typed parameters. An adapter implements `start(event, bindings)`,
`advance(operation_id, delta)` and `cancel(operation_id)`. A `finishable` capability
also implements `finish`; a `reconstructable` capability implements
`restore(event, bindings, elapsed)`. Optional admission checks validate the game
objects and resources. See the working
[particle adapter](../addons/scenario_runtime/presentation/particle_adapter.gd).

An adapter returns `running`, `completed` or `failed` status and optional result
data. The host associates feedback with the correct operation/session. A finish
request targeting `operation_completed:<instance_id>` can finish an eligible
operation; other declared finish requests remain observable to the game. It applies
node/sequence cleanup and passes only granted bindings. The game supplies texture,
audio and object references; authored JSON contains logical IDs and parameters.
Neither a catalog nor a source file can load GDScript or install a capability.

A surface implements `admit(program, channel)`, `present(view)` and `clear()`.
`bind_surface` installs it on a named channel. A second writer on an occupied
channel is refused before presentation. Camera and object arbitration beyond
those channels is game binding policy; registering an object does not lock the
whole world or every one of its properties.

## Dialogue, portraits and world actors

The stock `DialogueSurface` defaults to a bottom panel without a portrait. Supply
localized strings in `translations`, speaker names/portrait IDs in `speakers`,
textures in `portraits`, and actual objects in `anchors`. Profile definitions can
select `bottom`, `narration`, `subtitle` or `bubble`, choose portrait `none`,
`left` or `right`, and configure typography, geometry and overlap.

A speaker may have an off-stage portrait. A staged actor may speak without one.
Portrait omission reflows the text; `reserve_portrait` requests a reserved area.
The game supplies an explicit portrait ID or expression mapping; selected art
must exist. All reachable presentation is admitted before the host starts.

World anchors use `screen`, `world_2d` or `world_3d` bindings. 2D sampling includes
the canvas transform; 3D sampling follows the viewport's current camera. This
supports 2.5D games and 3D characters without giving Scenario camera ownership.
Offscreen anchors hide or clamp, behind-camera anchors hide, and lost anchors
hide or refuse. The game decides whether loss should also cancel the invocation.
See [world_bubbles](../examples/world_bubbles/) for a moving host-owned 3D actor.

## Time, input and interruption

Supply deltas to `tick`: one number advances all three clocks; a dictionary can
advance `sequence`, `presentation` and `reading` independently. A game can stop
narrative presentation while its combat ticks continue. Suspension freezes the
invocation and its adapter-owned work, not the SceneTree. Hosts report actual
text reveal, interaction and audio completion; content declares which events
are gates. Reading transport only requests an action; gates retain authority.

Route input once. A modal game can explicitly hold world updates; a bark can
consume no gameplay input. Cancel on scene exit or lost required context. Cancel
and completion release owned operations/channels without deleting the host's
actors or restoring a stale world snapshot. Adapters that own audio must implement
their actual stop/suspend behavior.

The game owns saves and outcome receipts. Use `snapshot` and
`restore(document, catalog, policy, bindings, saved)` for compatible invocations,
rebinding actual objects. Coordinate the saved game-world revision separately.
A content update never silently migrates an active session. The
[compatibility guide](compatibility.md) specifies the supported limits.
