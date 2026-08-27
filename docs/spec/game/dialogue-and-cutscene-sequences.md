# Dialogue and cutscene sequence contract

> **Contract maturity: proposed TO-BE.**
>
> This specification defines the target semantic contract for authored dialogue
> sequences, cutscenes, scripted transitions, branching, temporal cues, control
> handoff, and asset coverage. It does not claim an implemented sequence engine,
> describe migration work, or serve as a project plan.

The [Game contract](../../game-contract.md) owns sequence composition within a
game. The [Game view and style taxonomy](view-and-style-taxonomy.md) owns camera,
framing, subject-view, and presentation-profile terms. Existing dialogue-scene
bundles remain governed by their implemented
[asset contract](../dialogue-scene-assets.md); this proposal does not reinterpret
that wire format.

## Purpose

A dialogue scene is not merely a camera profile, and a cutscene is not merely a
video asset. Both are authored sequences whose meaning spans several domains:

- ordered and branching narrative events;
- speakers, utterances, expressions, poses, and motion;
- shots, framing, camera behavior, blocking, and transitions;
- music, voice, sound, and visual-effect cues;
- player-agency and input policy;
- gameplay events, conditions, and effects;
- skip, interruption, resume, and completion behavior; and
- the assets required to realize each visible or audible state.

Those semantics belong to a portable game contract. A recipe may generate the
required assets, and a consumer may play the sequence, but neither may invent
missing narrative structure or redefine the authored control flow.

The words **MUST**, **MUST NOT**, **SHOULD**, and **MAY** below are normative for
future contract design. They do not alter current runtime behavior.

## Canonical terminology

### Sequence

A **sequence** is a versioned, addressable composition of a semantic control-flow
graph and an orthogonal presentation program. It has one declared entry and one
or more declared exits. A sequence may be linear, branching, timed, interactive,
or composed from those behaviors.

A sequence is not synonymous with a timeline. Graph edges define semantic
control flow. Presentation tracks coordinate camera, blocking, motion, audio,
and UI cues against semantic boundaries or integer time. Neither hierarchy is
derived from the other.

### Node

A **node** is the smallest addressable unit of sequence control flow. Every node
has a stable `node_id`, one declared node kind, and explicit outgoing behavior.
Nodes do not inherit a next sibling from file order.

Initial target node kinds are:

| Node kind | Meaning |
| --- | --- |
| `dialogue` | Presents one authored utterance and its associated character/presentation state. |
| `choice` | Presents authored options and selects one explicit outgoing edge. |
| `branch` | Selects the first satisfied condition edge without presenting a player choice. |
| `action` | Requests a semantic actor, environment, or UI action. |
| `wait` | Waits for a declared duration, cue, condition, or host event. |
| `gameplay_gate` | Suspends sequence progress until an authored gameplay condition resolves. |
| `sequence_call` | Invokes another sequence through a declared call/return boundary. |
| `exit` | Terminates through a named outcome. |

Node kinds are semantic. They MUST NOT contain executable source code, engine
object paths, or untyped command strings.

### Beat

A **beat** is a meaningful change in narrative or presentation state. A dialogue
node normally represents one dialogue beat. Beats and shots are orthogonal: one
shot may span several beats, and one beat may contain several camera cuts.

A beat has no implicit duration, frame index, or animation meaning. Advancing
between expression variants changes state; it does not turn those variants into
animation frames.

### Utterance

An **utterance** is speaker-attributed language presented as text, voice, or
both. It has a stable identity independent from its localized text. A dialogue
node references one utterance and may additionally direct expression, pose,
framing, and advance policy.

### Choice and branch

A **choice** is a set of player-visible authored options. Each option has a
stable option ID, display content, an explicit target node, and optional
condition/effect references.

A **branch node** is non-interactive control flow. It evaluates an explicitly
ordered list of condition edges through the authoritative host and selects the
first satisfied edge. It MUST declare a default target so consumer behavior does
not depend on an empty match. A **branch edge** is the selected outgoing edge
from either a choice or branch node.

Choice order is presentation data and MUST be preserved unless the contract
explicitly allows deterministic randomization. The consumer does not generate
choice text, outcomes, conditions, or effects.

### Shot

A **shot** is an uninterrupted camera and framing interval in the presentation
program. It declares a presentation profile, camera behavior, framing, visible
participants, blocking, and activation/completion policy. It is addressable by
shot ID but is not inherently a control-flow node.

A camera cut starts another shot. A character expression change or sound cue
inside the same camera interval does not necessarily do so. Shot activation may
be synchronized to node entry/exit, a named cue, or an integer timeline tick.

### Cue and track

A **cue** is a typed request scheduled at a semantic boundary or integer time.
A **track** is an ordered collection of cues for one responsibility. Initial
track families are:

- `camera`;
- `actor`;
- `dialogue`;
- `audio`;
- `music`;
- `environment`;
- `visual_effect`;
- `user_interface`; and
- `gameplay_event`.

A consumer may support different concrete implementations, but it MUST preserve
the declared ordering, synchronization, and completion semantics.

### Blocking

**Blocking** is the authored placement, facing, look target, pose, and movement
of participants within a shot. Blocking uses semantic anchors and roles. It
MUST NOT persist Phaser objects, Unity transforms, Godot node paths, or another
consumer's scene graph.

### Cutscene

A **cutscene** is a sequence interval in which authored presentation temporarily
controls some combination of camera, actors, UI, audio, and player input. It may
contain dialogue and choices.

“Cutscene” does not imply pre-rendered video. Realization is declared separately:

| Realization | Meaning |
| --- | --- |
| `runtime_staged` | Consumer camera, actors, animation, audio, and effects realize the sequence. |
| `sprite_staged` | Pre-rendered 2D actors and backgrounds are composed and cued at runtime. |
| `illustrated_sequence` | Authored still images or panels realize successive shots or beats. |
| `pre_rendered_video` | One validated video asset realizes a timed interval. |
| `hybrid` | A declared combination of runtime and pre-rendered elements is used. |

**Cinematic** is an aesthetic or staging description, not a wire-contract type.

## Contract composition

```text
sequence catalog
└── sequence
    ├── identity and version
    ├── sequence kind and realization
    ├── participants and required capabilities
    ├── semantic control-flow graph
    │   ├── entry node and explicit edges
    │   ├── dialogue, choice, and branch nodes
    │   ├── action, wait, and gameplay-gate nodes
    │   ├── sequence calls
    │   └── named exits
    ├── orthogonal presentation program
    │   ├── shots and transitions
    │   ├── camera, actor, audio, and UI tracks
    │   ├── typed cues
    │   └── semantic and timed synchronization points
    ├── control and agency policy
    ├── skip, interruption, and checkpoint policy
    ├── asset and contract references
    ├── named outcomes
    └── rights and provenance
```

The catalog owns stable sequence identity and exact source digests. Individual
sequence files own graph and presentation semantics. `game.toml` or another
game-level composition contract references the catalog; it does not embed every
line, shot, and cue in one growing table.

## Library location

The target authored layout is:

```text
library/games/<game_id>/sequences/index.toml
library/games/<game_id>/sequences/<sequence_id>.toml
```

`index.toml` is an ordered, digest-locked catalog. Each entry binds one stable
sequence ID to exact source bytes. A sequence declares the same `game_id` and
`sequence_id` implied by its confined path.

Sequences may reference portable game-owned identities such as cast roles, maps,
presentation profiles, motions, soundtrack tracks, and generated asset roles.
They MUST NOT reference another run directory, a private absolute path, a signed
URL, or an engine object.

## Sequence kinds

| Sequence kind | Primary purpose | Default agency |
| --- | --- | --- |
| `dialogue_sequence` | Speaker-attributed beats, expressions, and optional choices | Dialogue advance and authored choices |
| `cutscene_sequence` | Authored shots, blocking, cue tracks, and temporary control | Contract-declared limited or locked input |
| `scripted_gameplay_sequence` | Coordinates authored events while gameplay remains active | Gameplay with declared restrictions |
| `transition_sequence` | Moves between maps, scenes, modes, or major presentation states | Usually locked during the transition |
| `composite_sequence` | Calls or combines the other kinds through explicit boundaries | Declared per called interval |

Sequence kind describes semantic intent. It does not select a rendering medium,
camera projection, or output container.

## Dialogue nodes

A dialogue node MUST identify:

- its stable `node_id` and utterance identity;
- one speaker role or an explicit narrator/system role;
- localized text identity or explicitly authored inline source text;
- text and voice synchronization policy when voice is present;
- expression, pose, and motion state references when visually represented;
- subject view, slot, and framing overrides when they differ from the active
  shot;
- advance policy; and
- its next node or choice node.

Target advance policies are:

| Policy | Completion condition |
| --- | --- |
| `manual` | An accepted dialogue-advance input occurs. |
| `after_duration` | A declared integer tick duration elapses. |
| `after_voice` | The validated voice cue completes. |
| `after_cue` | A declared synchronization cue completes. |

Every expression, pose, motion, portrait, and voice reference MUST resolve
before playback. Missing assets do not silently fall back to neutral, idle, or
text-only presentation unless that fallback is explicitly authored.

The contract distinguishes:

- **speaker** — who owns the utterance;
- **visible subject** — who is currently shown;
- **focus subject** — whom framing emphasizes; and
- **listener** — an optional addressed participant.

Those roles often coincide but MUST NOT be inferred from one another.

## Choices, conditions, and effects

A choice node MUST contain at least two unique options. Every option declares:

- stable option identity;
- caller-authored display content;
- one resolvable target node;
- optional availability condition references;
- optional effect references applied on selection; and
- optional presentation metadata such as order and disabled-state explanation.

Conditions and effects are portable references to separately typed game-state
contracts. They are not JavaScript, Python, expression-language snippets, or
engine callbacks embedded in the sequence file.

The host owns authoritative game state. The sequence controller asks the host
to evaluate declared conditions and apply declared effects, records the selected
option and resulting target, and then advances deterministically. A presentation
adapter may display choices, but it does not own relationship state, inventory,
quests, or branch persistence.

A non-interactive branch node evaluates its ordered condition edges through the
same host boundary and follows the first satisfied edge. If none match, it
follows its required default target. Conditions MUST be free of mutation; only
the selected edge's declared effects may change authoritative state.

## Shots and camera direction

Shots live in the presentation program and are activated by typed cues. They do
not define narrative progression. This separation permits a shot to continue
across several dialogue nodes and permits several cuts during one long
utterance without manufacturing narrative nodes for camera mechanics.

Every shot MUST declare or inherit:

- a presentation-profile reference;
- a camera-pose/framing directive compatible with that profile;
- camera behavior, such as fixed, tracking, rail, or authored move;
- visible participants and semantic blocking anchors;
- depth and occlusion policy where the profile permits alternatives;
- entry transition;
- activation and completion conditions; and
- exit transition or persistence policy.

Shot framing uses the canonical terms and measurements from the
[view and style taxonomy](view-and-style-taxonomy.md). “Close-up,” “top-down,”
“three-quarter,” and “isometric” MUST NOT be used as unqualified camera
instructions.

A shot may override presentation for its interval, but it does not mutate the
referenced profile. The consumer either supports the complete shot contract or
rejects the sequence during preflight.

## Timeline and timebase

Timed presentation intervals use an integer timebase:

```text
time_seconds = tick / timebase_hz
```

`timebase_hz` is a positive integer. Every timed cue tick is a nonnegative
integer, so tick `0` is the valid start of an interval. Persisted contracts MUST
NOT use floating-point seconds as event identity. Dialogue nodes that wait for
manual advance do not acquire an invented duration merely because nearby
presentation cues are timed.

Presentation cues may instead bind to semantic synchronization points such as
`node_enter`, `node_exit`, `utterance_start`, `utterance_complete`,
`choice_presented`, or `outcome_selected`. A cue uses one timing model: semantic
or tick-based. Mixing both without a declared precedence is invalid.

Within one timed track, cues are ordered by `(tick, explicit_order, cue_id)`.
Semantic-trigger cues use `(trigger, phase, explicit_order, cue_id)`. Identity
is therefore only the final stable tie-breaker, never the primary execution
order. Two cues that write the same state in one phase are rejected unless the
contract declares one deterministic conflict-resolution policy.

When cues on different tracks share a tick or semantic trigger, the sequence
contract MUST define deterministic phase ordering, for example:

1. state and gameplay events;
2. actor and environment state;
3. camera and visual effects;
4. audio and music; and
5. dialogue and UI publication.

The exact phase vocabulary belongs to the eventual wire schema. A consumer may
execute internal work differently only when the externally observable result is
equivalent.

## Actor direction and motion coverage

Actor cues reference semantic cast roles and motion states. They may direct:

- spawn or reveal;
- semantic anchor placement;
- subject-facing or look target;
- pose or expression state;
- locomotion or action motion;
- visibility and layer/depth policy; and
- release back to gameplay control.

Every requested visual transition requires compatible asset coverage for the
active view, direction, and style profile. A cutscene cannot request player
`hurt`, an NPC turn, a mob attack, or a speaking expression that the bound cast
package does not provide.

Motion completion policy MUST state whether the sequence waits for completion,
continues concurrently, loops until another cue, or interrupts at a declared
semantic boundary.

## Audio, music, and voice

Audio tracks reference stable game-owned cue identities. They distinguish:

- voice utterance playback;
- sound effects;
- ambient loops;
- soundtrack selection or transition; and
- silence or deliberate suppression.

A sequence may request that the current soundtrack continue, duck, pause,
crossfade, or change to a declared track. The soundtrack catalog continues to
own the track asset and playback constraints. The sequence owns only the timed
request and restoration policy.

Voice is optional. Text-only dialogue remains a complete authored mode. When
voice exists, its digest, language, speaker identity, duration, rights, and
utterance binding must validate before `after_voice` can be used.

## Player agency and control leases

A sequence explicitly acquires and releases **control leases**. Initial lease
domains are:

- player locomotion;
- player actions and combat;
- world interaction;
- camera;
- dialogue UI;
- general HUD;
- world simulation clock;
- soundtrack transition; and
- scripted actor control.

Target agency policies are:

| Policy | Meaning |
| --- | --- |
| `locked` | Gameplay input is suppressed except declared sequence controls. |
| `dialogue_only` | Dialogue advance and authored choices remain available. |
| `limited_gameplay` | Only an explicit allowlist of gameplay actions remains available. |
| `gameplay_active` | Sequence cues run while normal gameplay continues. |

Back navigation is a separate policy:

| Policy | Meaning |
| --- | --- |
| `disabled` | No back action is exposed. |
| `history_only` | The player may inspect prior text without rewinding sequence or game state. |
| `checkpoint_rewind` | Back restores one declared semantic checkpoint, including its host-state revision. |

World simulation is also explicit:

| Policy | Meaning |
| --- | --- |
| `continues` | Physics, AI, combat, and world time continue normally. |
| `paused` | The sequence holds the world-simulation-clock lease and pauses the declared simulation domain. |
| `selective` | A typed allowlist continues while all other declared simulation systems pause. |

Input agency and world simulation MUST NOT be inferred from one another. A
dialogue may lock the player's controls while the world continues, or leave
limited player control while an authored simulation subset is paused.

The consumer snapshots the state required by the acquired leases and restores
it on every declared exit, skip, cancellation, and recoverable failure. A
cutscene MUST NOT leave movement, camera tracking, HUD visibility, or audio
state accidentally changed after it returns control.

Only one sequence may hold an exclusive lease domain at a time unless an
explicit composition contract defines arbitration. Parallel effects within one
sequence use tracks; they are not silently implemented as competing sequences.

Every lease declares its scope: complete sequence, called-sequence interval, or
one node interval. Leases are acquired atomically in canonical domain order
before their scope begins and released in reverse order after restoration is
complete. A nested sequence call may reuse an inherited lease, request an
explicit subset, or perform a declared transfer; it MUST NOT deadlock by
silently reacquiring an exclusive domain already held by its caller.

## Skip, interruption, resume, and checkpoints

A sequence MUST declare its interruption policy:

| Policy | Meaning |
| --- | --- |
| `uninterruptible` | Only fatal consumer failure can terminate the interval. |
| `cancel_to_outcome` | Cancellation follows one declared named outcome. |
| `checkpoint_resume` | Playback can serialize and resume from declared checkpoints. |
| `restart_node` | Recovery restarts the current node from its entry state. |

Skip policy is separate:

| Policy | Meaning |
| --- | --- |
| `not_skippable` | No user skip route is exposed. |
| `skip_to_outcome` | Skip follows one declared exit and applies its declared effects. |
| `skip_seen_only` | Skip is available only when authoritative game state records the sequence as seen. |
| `fast_forward` | The consumer accelerates eligible intervals without omitting required effects. |

A skip MUST NOT merely jump the rendering cursor. It must deterministically
apply or explicitly waive every required state effect, restore every control
lease, and select one named outcome.

A checkpoint records semantic state, never renderer internals. The default is a
declared semantic boundary such as node entry, node exit, or named sync point.
At minimum it binds sequence identity and digest, current node, completed
one-shot and persistent cue state, selected branches, active calls, and the
host-state revision required for safe resume.

Mid-interval checkpoints are valid only when they additionally record the
sequence tick, active shot, active tracks, pending completion conditions, and
all persistent presentation state needed to reproduce the same observable
result. Otherwise a contract MUST checkpoint only at semantic boundaries.

## Entry, exit, triggers, and outcomes

Sequences have one entry and named exits such as `completed`, `declined`,
`interrupted`, or game-specific outcomes. The names are authored identifiers;
consumers do not infer success from reaching the last array element.

A game may trigger a sequence from a map interaction, gameplay event, explicit
host request, or another sequence call. Trigger contracts reference a sequence
ID and entry, not a consumer function.

Every exit declares:

- effects that must already have been applied or must be applied atomically;
- the destination sequence, scene, map, or gameplay continuation when any;
- control-lease restoration;
- presentation restoration or replacement; and
- completion/seen-state publication.

## Preflight validation

Before asset generation or playback, validation MUST reject:

- duplicate sequence, node, edge, option, cue, track, utterance, or outcome IDs;
- a missing entry or exit;
- unresolved targets, sequence calls, participants, profiles, motions, assets,
  conditions, effects, soundtrack tracks, or voice cues;
- unreachable nodes, unless explicitly retained as an authored disabled branch;
- non-exit dead ends;
- an unconditional cycle without an explicit bounded or host-conditioned loop
  policy;
- a call cycle without a declared recursion bound;
- ambiguous cue ordering;
- overlapping exclusive control leases;
- a timed cue outside its shot duration;
- `after_voice` without a validated voice cue;
- a skip or cancellation route that leaks a lease or omits required effects;
- a visible actor state without compatible asset coverage; and
- a sequence whose declared realization is unsupported by the selected consumer.

Validation is transactional. A malformed declared sequence is rejected as a
whole; a consumer does not play the reachable prefix and ignore the rest.
Preflight computes the dependency closure across every reachable branch,
sequence call, outcome, and presentation cue, not only the path selected during
one execution. Deferring branch assets requires an explicit streaming contract
with equivalent digest, rights, failure, and prefetch guarantees.

## Illustrative target shape

The following example communicates the proposed boundaries. It is not an
implemented schema and reserves no final field layout:

```toml
schema_version = 1
kind = "game-sequence-v1"
game_id = "example-game"
sequence_id = "village-gate-warning"
revision = 1
sequence_kind = "dialogue_sequence"
entry_node_id = "warning-line"

[control]
agency = "dialogue_only"
back_navigation = "disabled"
world_simulation = "paused"
leases = [
  "camera",
  "player_locomotion",
  "player_actions_and_combat",
  "world_interaction",
  "dialogue_ui",
  "general_hud",
  "world_simulation_clock",
]
skip_policy = "skip_to_outcome"
skip_outcome = "warning-heard"

[[participants]]
role_id = "player"

[[participants]]
role_id = "gate-keeper"

[[presentation.shots]]
shot_id = "gate-two-shot"
presentation_profile_id = "lateral_orthographic_side_plane_v1"
camera_behavior = "fixed"
framing = "full_shot"

[[presentation.cues]]
cue_id = "show-gate-two-shot"
track = "camera"
trigger = "node_enter"
node_id = "warning-line"
action = "activate_shot"
shot_id = "gate-two-shot"

[[nodes]]
node_id = "warning-line"
kind = "dialogue"
speaker_role_id = "gate-keeper"
utterance_id = "warning-before-ruins"
expression_state = "concerned"
advance_policy = "manual"
next_node_id = "warning-choice"

[[nodes]]
node_id = "warning-choice"
kind = "choice"

[[nodes.options]]
option_id = "continue"
text_id = "choice.continue_to_ruins"
target_node_id = "accept-warning"

[[nodes.options]]
option_id = "return"
text_id = "choice.return_to_village"
target_node_id = "return-to-village"

[[nodes]]
node_id = "accept-warning"
kind = "exit"
outcome_id = "warning-heard"

[[nodes]]
node_id = "return-to-village"
kind = "exit"
outcome_id = "warning-declined"
```

## Relationship to current repository capabilities

The implemented [dialogue-scene recipe](../dialogue-scene-assets.md) currently
carries a linear list of one to twelve caller-authored beats. Each beat has a
speaker, text, and one locked static expression state. The optional
[preview](../../dialogue-scene-preview.md) advances linearly and does not own
narrative state, branch persistence, timed shot tracks, actor blocking, or a
general cutscene controller.

The scrolling
[dialogue-character projection](../../dialogue-character-runtime-pipeline.md)
imports reviewed expression assets and ordered beats into a screen-fixed
overlay. Its movement lock and beat cursor prove one consumer integration, not
the general sequence contract proposed here.

The current prepared gameplay consumer accepts sequence and NPC-expression
projections only inside `prepared-game-runtime-v4` and validates each declared
block as one unit. An NPC exposes interaction only when gameplay binds it to a
resolved sequence. A malformed declared sequence fails closed and does not
substitute unrelated dialogue. A future sequence extension must either preflight
its complete required projection or carry an explicit authored fallback node or
outcome.

The current dialogue asset recipe also receives and persists its own copy of
caller-authored beats. A future sequence-aware recipe must instead consume a
digest-bound projection of canonical sequence, node, and utterance identities.
Dialogue text and beat order cannot be authored independently in both the
sequence catalog and an asset-generation request because those copies can drift
while their images continue to validate.

The exact compilable subset for the existing rich gameplay overlay is therefore
a linear chain of one to twelve dialogue nodes with unique IDs, static supported
expression states, manual forward advance, one bound resident identity, and no
choices, conditional branches, effects, voice synchronization, timed cues,
shot program, checkpoint rewind, or cutscene realization. A compiler MUST refuse
anything outside that subset instead of erasing the unsupported semantics.

The current prepared sequence and runtime shapes remain valid only as the exact
`prepared-game-runtime-v4` projection. They MUST NOT silently acquire unsupported
shot, timeline, or cutscene semantics. A future adapter must either emit the
exact supported subset or fail; it cannot erase authored semantics to fit a
different consumer shape.

## Ownership boundaries

| Owner | Owns | Does not own |
| --- | --- | --- |
| Game sequence contract | Semantic graph, authored dialogue, choices, shots, cues, agency, outcomes, and cross-contract references | Engine nodes or generated media bytes |
| Game-state contracts | Condition evaluation, effects, persistence, and seen/completion state | Dialogue layout or camera implementation |
| Recipes | Generation and validation of sequence-required visual/audio assets | Narrative branch invention or runtime playback |
| Consumer sequence controller | Deterministic playback, timing, input leases, checkpointing, and engine translation | Canonical sequence meaning or missing-content fallback |
| Presentation adapter | Dialogue UI, subtitles, choice UI, camera/render translation | Story state, condition evaluation, or effect ownership |
| Web preview | Optional demonstration of supported sequence subsets | Core sequence authority or a second authoring system |

## Namespace rules

| Namespace | Responsibility |
| --- | --- |
| `game_sequence_*` | Portable graph, node, edge, cue, outcome, and checkpoint contracts |
| `game_dialogue_*` | Utterances, speakers, expression/pose direction, choices, and dialogue advance |
| `game_cutscene_*` | Shots, blocking, temporal tracks, transitions, agency, and control leases |
| `game_sequence_adapter_*` | Consumer-specific compilation and playback translation |

Modules that merely render text or process video are not sequence owners. A
generic media transform MUST NOT gain a `game_cutscene_*` prefix unless it owns
cutscene semantics rather than reusable media behavior.

## Verification target

An eventual implementation requires focused tests that prove:

- canonical graph identity and digest stability;
- strict lower-snake-case parsing and unknown-field rejection;
- reachability, target, loop, call, and outcome validation;
- deterministic choice and cue ordering;
- condition/effect delegation without embedded code;
- complete participant, motion, expression, shot, audio, and asset resolution;
- exact control-lease acquisition and restoration on completion, skip, cancel,
  and failure;
- checkpoint round-trip and source-digest refusal after contract changes;
- equivalence of uninterrupted and resumed playback at the same semantic state;
- skip application of required effects without replaying optional presentation;
- consumer rejection of unsupported realizations or presentation profiles; and
- independent semantic review and rights gates for every generated visual,
  audio, or video asset selected by the sequence.

## Technical references

- [Yarn Spinner: Dialogue Runners and Systems](https://docs.yarnspinner.dev/components/dialogue-runner)
  is a representative narrative boundary that delivers authored lines, options,
  and commands to separate presenters and game integrations.
- [Unreal Engine: Sequencer Overview](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-sequencer-movie-tool-overview)
  is a representative cinematic boundary built from independently authored
  tracks, cameras, keyframes, animations, playback policy, control takeover, and
  state restoration.
- [Unreal Engine: Camera Cut Track](https://dev.epicgames.com/documentation/en-us/unreal-engine/cinematic-camera-cut-track-in-unreal-engine)
  illustrates shot/camera activation as a presentation track rather than
  narrative graph structure.

## Non-goals

This specification does not:

- generate story text, dialogue choices, or narrative outcomes;
- define a full quest, relationship, inventory, or save-game model;
- select a game engine or scripting language;
- require cutscenes to be video or require dialogue to be static;
- make the current dialogue-scene preview a production sequence engine;
- prescribe implementation order or migration tasks; or
- authorize generated assets for publication.
