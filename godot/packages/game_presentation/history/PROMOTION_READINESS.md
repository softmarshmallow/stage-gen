# Promotion readiness and composition review

**Superseded scope, P102–P106:** the [code-first SDK successor design](../../../../docs/research/game-presentation-sdk-design.md)
replaces this document's promotion destination and prerequisite recommendations.
Legacy point-and-click/room compatibility and Scenario parity are not gates.
Historical observations remain evidence; no runtime migration has occurred.

Historical proposal with follow-up decisions through P47. See
[current implementation and open items](CURRENT_STATUS.md) for the P79 audit.
Later ensemble, lab and lifecycle work adds evidence; this document's proposed
proofs and migration steps have not become automatic implementation requirements.

Date: 2026-09-10. Request: [P29](USER_PROMPTS.md#p29).
Status: recommendation only. No new experiment, runtime migration, module
extraction, or canonical contract change was performed.

**Historical direction, P39:** [continue gameplay development in the spike](#p39-continue-the-spike-review-contracts-before-migration),
then separately review upstream's ratified contracts before deciding migration
or replacement. This supersedes P38's sibling-first recommendation.

**P40 location update:** this same experimental project now lives at
repository-root `godot/games/playground/`, with source under Git. The intact
move changes version control and path only. P39's gameplay-first scope and
deferred production-contract review still apply; no module promotion or runtime
integration has occurred. Generated media and working output remain local.

**P41 local organization:** [Game roots and shared presentation](TOPOLOGY.md)
records the implemented separation inside this experiment. Two explicit Godot
roots share presentation code; Command Link remains playable and the dating
root initially awaited its brief. P47 now activates it as
[Bishōjo: Afterlight](../../../games/afterlight/README.md), with an independently
authored UI and a walking approach. This does not ratify public modules or
replace upstream.

This qualifies the [P28 promotion review](PROMOTION_REVIEW.md): the existing
runtime is an incumbent to assess and preserve behavior against, not an
automatically correct destination. The proposed taxonomy remains provisional.

## Readiness judgment

We have enough examples to identify candidate responsibilities and design the
next experiments. Freezing public contracts or reorganizing the whole runtime
would be premature. More visual presets alone provide diminishing architectural
evidence; examples that change composition, ownership, and lifecycle are more
useful now.

The spike was appropriate for discovering behavior without negotiating every
experiment through an existing public contract. Choosing it does not prove all
incumbent code is unsuitable. Conversely, incumbent tests and established paths
do not prove the existing abstraction boundaries are right for the new use cases.
TOML is a serialization choice; the architectural issue is what its contract
requires and which component owns those requirements.

There is concrete coverage still missing:

- [Cast Transition](../../../games/command_link/presentation/transitions/CAST_TRANSITIONS.md) assumes three registered
  actors and two occupied positions. During the main handoff, dialogue, Actor
  Focus, and manpu are held out. It does not demonstrate arbitrary simultaneous
  composition or retargeting while a handoff runs.
- [Dialogue Camera](../../../games/command_link/presentation/camera/DIALOGUE_CAMERA.md) restores its saved motion, while
  [Actor Focus](../../../games/command_link/presentation/focus/README.md) and [Manpu Introduction](../../../games/command_link/presentation/manpu/README.md) resume
  the main story in settled states. Those explicit choices need a common policy
  boundary before reuse; all capabilities need not choose identical policies.
- The fingertip target has not been transferred into a non-conversation context
  with another system owning input, gameplay state, and camera behavior.

## What agnostic should mean here

A game can still be packaged and exported. The reusable unit should be a
capability with a contract, rather than an indivisible genre template. Authored
game content declares required behavior, roles, and cues. A composition layer
binds compatible implementations and validates their dependencies. That layer
must know which implementations will run; the story need not name them.

The proposed separation is:

```text
Authored content and capability requirements
                    |
           Composition and validation
                    |
       Implementations and explicit adapters
                    |
                Game export
```

Modules should be independent of a particular story, genre template, and asset
producer. They still have a domain: an actor presenter legitimately understands
actors and poses; an input target understands hit geometry. Godot adapters
legitimately understand Godot. Agnosticism does not require erasing those useful
responsibilities or introducing dynamic plugin discovery.

## Existing architecture is part of the review

There are concrete assumptions worth challenging:

- The [host contract](../../../../docs/spec/game/host-contract.md) defines a template
  as one genre's code and dependencies with a main scene. That is the current
  deployment model, not proof of a capability-based authoring/composition model.
- The [case host](../../../runtime/hosts/case/main.gd) explicitly selects room or
  dialogue leaves. That finite composition works for its present domain; its
  extension policy needs review before treating it as a general game composer.
- The shared [dialogue leaf](../../../runtime/hosts/common/dialogue_leaf.gd) loads a
  specific dialogue bundle and requires generated panel/button art. Rendering
  behavior, asset binding, and UI appearance have separable responsibilities
  even though the current entry point couples them.

The existing [Scenario contract](../../../../docs/spec/game/scenario.md) and family
dependency boundaries already provide useful separation. Evaluate each part
as retain, adapt, replace, or leave as a specific composition. Do not make folder
names the evidence either for reuse or for a rewrite. No production behavior
should be discarded merely because its current container needs to change.

## A bounded next step

Recommend one more spike pass with three questions, reusing prepared assets:

| Experiment | Question it should answer |
| --- | --- |
| A room/prop interaction opens a short conversation and returns to the room. | Can presentation be embedded with explicit input and camera ownership, without taking over the whole game or requiring a VN template? |
| A directed sequence combines camera movement, actor effects, reactions, and an exit, then exercises pause, interruption, and restoration. | Are composition order and lifecycle policy explicit, or do route-specific special cases decide the result? Deliberately unsupported combinations may be rejected. |
| The same small scene receives equivalent roles and cues from a plain prepared fixture and an adapter over an existing bundle. | Can asset loading and packaging change without edits to the story or presentation core, and without generation? |

These are proposed proofs, not an instruction to implement a new room engine,
plugin registry, whole-game schema, or generation pipeline. They may share one
small scenario; no additional character art is necessary to answer them.

Use the evidence to revise the candidate contracts. Readiness means an
independent context can use them without adding genre-specific branches to
shared code, lifecycles have explicit owners, and existing behavior can be
adapted with understood compatibility costs. It is not a count of effects.

Then choose one small migration that tests the proposed boundary against an
incumbent consumer. Broad runtime redesign, contract replacement, generation
changes, and spike promotion should not be one combined change. A topology
decision may follow the evidence without implementing the whole destination at
once.

This P29 review inspected source and local contracts only. No game tests were
rerun. The recommendation is to gather targeted composition evidence before
committing to public boundaries.

## P38: Maintained sibling before the next feature batch

Historical recommendation, superseded by P39 below.

The user is considering keeping this implementation and replacing upstream
parts incrementally. Recommend giving it a maintained, independent sibling
home before the next five to ten gameplay/effect additions. The exact kit path
and packaging remain undecided. This is advice, not authorization to move,
commit, publish, or replace anything.

The spike is the richer reference for the desired presentation experience.
That does not establish feature parity with the existing Scenario, room, and
case runtimes. The current game has authored story dictionaries and in-memory
route resume; upstream also owns narrative validation/restoration, room puzzles
and inventory, and cross-scene progress. Assess those capabilities individually.

The initial move should preserve the standalone Godot project, playable story,
prepared assets, demo routes, and regression checks. Resolve path assumptions,
document how to run and verify it, and make one location authoritative for
ongoing development. Keep an archived baseline instead of two evolving copies.
Carry required media lineage across the ownership boundary; raw generation
attempts and historical captures need not become runtime package contents.
Relocation does not itself authorize generated-media publication.

Do not make the move depend on adapting to the old generated-bundle contract,
extracting a module library, changing generation, or reorganizing the incumbent
Godot project. A sibling can contain provisional APIs and game-specific code.
Command Link remains its reference game and the demos remain its verification
surface; neither needs to define the reusable kit's final shape.

Then implement new gameplay and effects there, with local separation where a
feature needs it. The stage currently mixes rendering, loading, interface,
interaction, and QA, so new responsibilities should not all accumulate there.
The composition proofs proposed for P29 still help choose later boundaries.

When a real consumer needs a replacement, select one behavior, assess the old
implementation as retain/adapt/replace, and prove it using that consumer's input
and lifecycle. Where useful, an adapter can connect existing Scenario semantics
to the new presentation. Preserve the old path until the replacement has
accepted behavior and compatibility evidence. Do not duplicate all upstream
systems in anticipation of needing them.

If establishing the sibling requires substantial runtime redesign, keep the
current project working and narrow the move. Public contract stabilization and
production replacement have higher evidence requirements than establishing a
maintained project. The proposed order is sibling ownership, continued gameplay
development, then replacement one capability at a time.

P38 inspected current local source and prior review records. No native runtime
tests were rerun for this recommendation; only documentation changed.

## P39: Continue the spike; review contracts before migration

The user reversed the proposed order to avoid combining ongoing feature work
with migration and to allow careful review of the production version's ratified
contract. Continue the next gameplay and effect demonstrations in this spike.
Keep recording exact requests, demonstrated behavior, and implementation
limitations; local cleanup can support those features without fixing public
module boundaries.

Before deciding a move or replacement, conduct a separate review of the
applicable ratified contracts, their consumers, and the implementation. Identify
which guarantees must be preserved, where implementation differs from the
contract, and which changes would require an explicit contract revision. Better
presentation alone does not resolve those questions. A sibling location remains
an option after that review, not the immediate next step.

The earlier recommendation underestimated the coordination cost of establishing
a new maintained project while continuing feature discovery. The current order
is gameplay evidence here, focused contract review, then a bounded migration or
replacement decision. This does not require exhausting every possible effect.

P39 updates direction and the request record only. No production contract review,
contract amendment, relocation, or runtime change was performed in this turn.
