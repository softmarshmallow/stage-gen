# Scenario runtime

An optional Godot interpreter for `scenario-program-v2`: admitted program + state
+ action → next state + events. It owns no scene tree, input device, clock, media
loader, generation, game manifest, case ordering or save-file policy.

The installable payload is `addons/scenario_runtime/`. Copy that directory into
any Godot 4.7 project, then preload the scripts explicitly. There are no global
`class_name` declarations or other addon dependencies, and an editor import is
not required to use it. Bellweather and The Grain select this package; other
games need not use its scenario vocabulary.

The payload includes its [BSD 3-Clause license](addons/scenario_runtime/LICENSE).

```gdscript
const Program = preload("res://addons/scenario_runtime/program.gd")
const Runtime = preload("res://addons/scenario_runtime/runtime.gd")
const Refusal = preload("res://addons/scenario_runtime/refusal.gd")

func begin(document: Dictionary) -> Dictionary:
    var program: Variant = Program.parse(document)
    if Refusal.is_refusal(program):
        return program
    return Runtime.initial_turn(program)
```

## Admission and execution

`Program.parse(document)` accepts the interpreter's version-2 document vocabulary.
It checks consumed field types, duplicate declarations, statement kinds, five
actor slots, expressions, and references to actors, blocks, flags, stages, tracks
and endings. Unknown metadata is ignored. This is not a complete producer JSON
schema, asset validator or provenance verifier. A document does not need a game
identifier, assets, or any Stage Gen installation.

Successful parsing preserves the existing normalized program representation.
Runtime calls require that parsed program, unchanged by the caller. State arguments
must come from this runtime or `restore`, also unchanged. The package does not
revalidate its entire normalized program/state on every action. Consumers reading
untrusted save data must pass it through `restore` before execution.

Supported statements are `line`, `choice`, `show`, `hide`, `stage`, `audio`, `set`,
`jump`, `branch` and `end`. The reducer settles invisible statements before
returning a line, available choice or ending. Conditions use declared `requires`
and `forbids` flags. Audio actions are `play` and `stop`; actual playback belongs
to the consumer. Visible loops remain valid.

Admission does not prove every flag-dependent execution path. Each turn retains
the established deterministic limit: statement count + block count + 2 settling
iterations. A path exceeding that limit, falling off a block without transferring
control, or reaching a choice with no available options fails explicitly.

| API | Successful result |
| --- | --- |
| `Program.parse(document)` | Normalized program dictionary |
| `Runtime.initial_turn(program, carried)` | `{state, events}`; only declared imported flags are carried |
| `Runtime.reduce_turn(program, state, action)` | `{state, events}`; unsupported actions and unavailable option indices are no-ops |
| `Runtime.initial_state(...)`, `Runtime.reduce(...)` | State-only convenience forms |
| `Runtime.view(program, state)` | Current line, available choice or ending |
| `Runtime.actor(state, actor_id)` | Staged actor, or an empty dictionary |
| `Runtime.progress(program, state)` | `{seen, total}` for visible statements |
| `Runtime.statement_id(label, index)` | Stable `label#index` identifier |
| `Runtime.is_finished(state)` | Whether the state has an outcome |
| `Runtime.restore(program, snapshot)` | Compatible normalized state, or `null` |

`advance`, `choose` with a zero-based available-option index, and `restart` are
the accepted actions. Restart resets carried facts as it did before extraction.
A no-op has no events. State, statement identifiers, event order and event payloads
retain the existing game/replay representation, including its established field
spelling. The parser is the explicit adapter from document `lower_snake_case` to
that retained runtime representation; this extraction does not introduce a new
save format.

## Failures

Parse and execution failures return only:

```gdscript
{"error": {"code": "scenario/nonsettling", "message": "...", "path": "block#3"}}
```

Check `Refusal.is_refusal(result)` before reading successful fields. `Refusal.line`
formats the error for a consumer. The package never logs failures itself. A failed
turn publishes neither partial state nor accumulated events, and leaves the
previous state unchanged. Game adapters decide whether to refuse loading, show a
message or retain the current view.

Stable code families are `scenario/program-kind`, `scenario/entry`,
`scenario/malformed`, `scenario/unresolved`, `scenario/action`,
`scenario/nonsettling` and `scenario/no-options`. Document paths name consumed
fields; runtime paths name the current statement. `restore` retains its separate
null-on-incompatibility contract so consumers can choose a fresh start for stale
saves. It validates consumed snapshot shapes and declared references; it does not
prove that the snapshot was reached by playing or authenticate save files.

## Minimal example and checks

From the repository root:

```sh
godot --headless --path godot/packages/scenario_runtime --script res://examples/minimal/run.gd
godot --headless --path godot/packages/scenario_runtime --script res://tests/run_checks.gd
```

The original synthetic example needs no assets or providers. Checks exercise
admission, transactional failures, visible/invisible loops, staging, expression
changes, branches, carried flags, snapshots and exact event sequences. Game-owned
fixtures and replay checks remain with their games. These checks establish
interpreter behavior, not visual or audio acceptance.

To exercise this package outside the checkout, copy only `project.godot`, `addons/`,
`examples/` and `tests/` to a fresh directory and run the same commands with that
`--path`. No shared game runtime or named game files are required.
