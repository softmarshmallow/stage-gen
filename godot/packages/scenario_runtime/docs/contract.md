# Scenario invocation contract

Status: current implemented v3 contract. The [compatibility reference](compatibility.md)
defines supported v2 inputs. [Verification](verification.md) separates executable
contract evidence from game rendering and listening review.

## Authority

Scenario is an embeddable, VN-oriented narrative presentation framework. The
game creates each invocation, binds speakers and objects, supplies time/input,
and grants capabilities. The game owns simulation, camera selection, world
objects, navigation, storage and consequences of narrative outcomes.

An invocation owns its sequence and granted presentation operations. Starting
one does not pause a SceneTree, replace a scene, claim a camera, capture all input
or instantiate a game. Host implementations dispatch declared capability types
and presentation data. They do not dispatch story or beat IDs to hidden direction.
New mechanisms are installed/versioned capabilities; content contains no code.

## Program and facts

A raw program has `kind: "scenario-program-v3"`, `schema_version: 3`, `scenario_id`,
`entry`, and a `nodes` array. Optional `speakers` contain `{id, display_name}`;
`facts` map names to boolean or finite-string declarations; `required_capabilities`
map installed type IDs to positive integer versions. Public fields use
`lower_snake_case`. Source maps and metadata are diagnostic, not executable.

Every node has a stable `id` and `kind`. Serial nodes have `next`; other outgoing
edges are explicit. The reader normalizes references and definitions before
execution. Admission checks field types, duplicate IDs, references, reachable
nodes/endings and invisible cycles. It does not prove that every user/host
interaction will eventually finish. Visible repetition is permitted; asynchronous
and settling work also have bounded runtime refusal paths.

| Kind | Consumed direction |
| --- | --- |
| `line` | `text` or `text_key`, optional speaker/expression, presentation, cues, gates, `advance_mode`, next |
| `choice` | Optional line-like prompt/presentation/cues/gates; stable options with text/key, target, condition and local assignments |
| `branch` | Ordered `{condition, target}` edges and a default target |
| `set` | Declared local fact values and next |
| `jump` | Target node |
| `effect` | Typed/preset effect, instance ID, target, scope, duration/clock and next |
| `stop` | Named effect instance and next |
| `wait` | Exactly one duration, operation instance or host event, then next |
| `end` | Named outcome |

Facts have `type`, `default`, optional finite string `values`, and optional
`external: true`. Conditions compare declared values. Local assignments cannot
write external facts; ordered host updates can. There is no arithmetic/expression
VM, arbitrary function call or discovery of game singletons.

A line defaults to `advance_mode: "manual"`. Ordered gates name host events and
whether an advance requests finishing that gate. `on_gates` requires at least one
gate and continues once all are satisfied. Choices always select an available
stable option ID; completion/advance cannot fabricate a required interaction.

## Effects, cues and catalogs

A reference is `{preset: "name", parameters: {...}}` or
`{type: "installed_type", parameters: {...}}`. Named and inline definitions
normalize to the same `{type, version, parameters}` after defaults and validation.
A running `instance_id` is separate from the reusable preset name.

Catalogs use `kind: "scenario-catalog"`, `schema_version: 1`, `catalog_id`, a
nonempty string `revision`, and `definitions`. A definition names its installed
`type`, configured `parameters`, and an `overrides` list of exposed parameters.
Undeclared overrides are refused. Installed schemas validate numbers, integers,
strings, booleans, arrays, objects and JSON; they can constrain ranges, enumerated
values, required/default fields and nested structures. Installed declarations are
validated even when unused; parameter schemas are closed, require explicit types,
and allow at most 64 levels of nesting. A catalog cannot add an
algorithm. Current catalog definitions directly configure primitives; bounded
sequence composition belongs to authoring expansion.

Effects use `scope: "node"` or `"sequence"`. Node exit cancels node work;
sequence work continues until its declared completion/stop or invocation exit.
Cues have stable IDs, an `at` time or `on` event with optional `after`, and the
same effect fields. `text_revealed` and `operation_completed:<instance_id>` are
useful declared events. Start/finish/stop address independently owned operations;
leaving a line does not silently finish every animation.

The three supplied clocks are `sequence`, `presentation` and `reading`. A numeric
`tick` advances all equally; a dictionary can supply separate finite nonnegative
deltas. Cue boundaries split elapsed time. Playback devices report actual voice
completion; there is no fourth implicit wall/audio clock. Reading/autoplay
transport is optional and requests actions subject to Session gates.

## Session and host

The pure `execution/session.gd` uses admitted dictionaries and a host policy.
It loads no media, polls no input, reads no clock and changes no scene tree.

| API | Responsibility |
| --- | --- |
| `start(program, catalog, policy, initial_facts)` | Validate invocation grants and enter the graph |
| `tick(delta, input_events)` | Advance supplied clocks and process ordered inputs |
| `submit(action)` | Advance, choose or report typed host/operation/fact updates |
| `suspend()` / `resume()` | Freeze/resume this invocation |
| `cancel(reason)` | Terminate once and cancel owned operations |
| `view()` / `drain_events()` | Inspect current presentation and ordered occurrences |
| `snapshot()` / `restore(program, catalog, policy, saved)` | Capture/admit compatible sequence state |

Policy names `session_id`, granted capability versions, channels and logical
binding IDs. Reports expose state, events and input consumption. Occurrences
carry session, node, visit and event identity plus supplied clocks. Operation
completions carry session and operation IDs; stale, duplicate or cross-session
results cannot progress current work. Host events may bind node/visit identity.

The optional `bindings/host.gd` exposes side-effect-free `prepare(document,
catalog_document, policy, bindings)` before `invoke`, registers capability adapters, validates their
bindings, binds surfaces and refuses concurrent writers on a granted channel.
Independent sessions can run concurrently on independent channels. It applies
ordered effect lifecycle events and releases only its own grants. Games needing
additional object/camera arbitration must grant it explicitly in their bindings;
the package does not infer a lock over every property of a target object.

## Presentation and game state

Speaker identity is independent of standing art, world entity, UI portrait and
voice. The stock `bottom` profile shows text and optional name, with no portrait.
Profiles support left/right portraits, narration, subtitles and anchored bubbles.
An omitted portrait reflows text unless reserved space is requested; a selected
missing portrait is an admission failure. Game presenters may define additional
typed layouts and use the same executor.

`bindings/anchor.gd` samples screen, world-2D or world-3D anchors in the host
viewport. 3D projection reads the host's active camera each sample. Behind-camera
anchors hide; offscreen anchors hide or clamp; lost anchors hide or refuse as
configured. Front-facing cast and portrait-feed presenters are optional adapters.
No five-slot or front-view restriction applies to v3 invocation.

The game owns durable saves and external side effects. Session snapshots bind
normalized program/catalog fingerprints, node/visit/choice history, clocks and
operations. Restore refuses inconsistent or incompatible state and requires
reconstructable active capabilities. It cannot rewind an unrelated game world or
provide durable exactly-once delivery of game actions. The game persists outcome
receipts and coordinates world state when that behavior is required.

Already compiled content needs neither Python nor Stage Gen. Local content-package
admission checks declared bytes, hashes, schemas and capabilities before replacing
the selected revision. Activation does not replace running sessions or generate
media. Network delivery and trust policy remain the application's responsibility.
