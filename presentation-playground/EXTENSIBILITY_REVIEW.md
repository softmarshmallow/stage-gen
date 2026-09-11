# Extensibility review

Historical preparation record: P43, with P45/P47 follow-through. Its scene and
evidence counts describe those passes. [Current status](CURRENT_STATUS.md) tracks
the later three-root project, current ensemble and implemented effects. The
practical ownership decisions below remain guidance; this is not a live backlog.

## Preparation decision, P43

Ready to continue with the next requested gameplay or presentation feature.
The preparation review is complete. This means the existing components provide
a practical starting point for these related games; it does not mean that a
second playable game or a universally agnostic framework has been proved.

P42 identified real concentrations of responsibility, but treated extracting
dialogue controls and separating the stage's rendering layers too strongly as
prerequisites. P43 corrects that assessment: integration belongs in a concrete
presenter or game director, and its amount alone is not a defect. Flexibility
and the practical cost of change govern the decision. The findings below remain
visible, with concrete triggers for revisiting them.

No readiness-blocking code defect was identified in this scoped review. This
pass updates the architecture guidance and request history; it makes no runtime
changes and implements none of the five proposed features.

## UI ownership clarification, P45

The host/route owns its complete UI and configures it manually per game. This
includes controls, hierarchy, layout, styling/assets, and action wiring. Shared
code is limited to optional utilities and independently reusable mechanisms.
There is no requirement for games to implement a common UI/view contract or
select a skin for a shared game interface. This supersedes the shared-view
proposal discussed after P44's request for an answer before implementation.

Command Link already owns its playable controls and menu. The stage and opening
still contain tactical UI integration; this documentation change does not move
that code. The next customization should put those interface responsibilities
with the host while retaining useful rendering/playback mechanisms. Similar
layouts are legitimate authored code, not sufficient reason for a shared view.

## First concrete follow-through, P47

[Bishōjo: Afterlight](games/bishoujo_afterlight/README.md) now supplies a second
authored scene: a walking approach, meeting, reply choice, and separate camera
study. Its host owns the complete UI and composes the new Walking Approach
controller with the existing scalar animation sampler. It imports neither the
tactical stage nor the Command Link game. Independent copied placeholders keep
future art replacement local to this game. The original stage's UI integration
remains unchanged; the new host does not require that interface.

## What independence means here

A reusable component owns one behavior and its state, exposes its inputs and
outputs, and declares its dependencies. Its consumer can use it without loading
Command Link's story, cast, controls, or another game's root. Depending on Godot
or another declared presentation component is compatible with that scope.

The existing animation, focus, manpu, exit, cast-transition, and camera code
provides that kind of reuse within this project. Their scope and lifecycle
contracts are indexed in [the topology](TOPOLOGY.md#component-contracts).
They are not independently distributed packages. In particular, Cast Transition
is explicitly limited to three actors and two positions.

The stage is a **concrete integrated presenter**. It binds those controllers to
artwork, coordinate spaces, timing, materials, interaction geometry, and the
current tactical view. Reuse of its controllers does not require inheriting
that entire presenter. Calling the whole stage an agnostic scene runtime would
overstate the current implementation.

## Review findings and practical decisions

| Area | Evidence in the current code | Decision and trigger for change |
| --- | --- | --- |
| Game and asset isolation | Explicit roots; injected stage profiles; shared presentation imports no game root. Composition checks use renamed actors, different cast counts, optional contact, and independent instances. | Keep this dependency direction. A reusable component needing a particular story or cast is a reason to repair its boundary. |
| Game direction and dialogue | Command Link's `game.gd` owns story, choices, input gates, handoff choreography, resume, and its playable controls. | The host/route owns the complete UI. Reuse useful utilities and independent behavior while manually composing each game's controls and layout; no shared dialogue-view framework is required. Avoid inheriting the tactical mission to obtain a mechanism. |
| Stage and rendering | The stage owns controller clocks, dialogue-camera policy, world framing, fixed chrome, and workbench controls. Some world and UI items share a drawing node. | Keep this concrete integration for now. Introduce a focused attachment or rendering boundary when a requested effect requires it, especially if a transform would also move fixed UI. Shared integration changes are expected when adding a capability. |
| Authoring entry point | Each game has a root; Command Link delegates to its game script and prepared profile. | One discoverable master composition per game is the goal. Supporting files and explicit wiring are allowed wherever they improve flexibility or readability. A file-count or line-count limit would hide useful decisions. |
| Evidence for another game | Afterlight plays a short arrival/choice scene with its own host UI and a separate camera study; composition and native input checks cover both roots. | This is concrete evidence for reuse of camera/animation mechanisms and host UI ownership. It remains one small scene, not proof of a universally agnostic game system. |

## How the next feature should land

Start with the requested experience and identify what the game directs, what
the mechanism owns, and how the presenter applies its result. Reuse an existing
contract when it fits. Extend or extract a component when the concrete behavior
requires it; allow deliberate integration work in the presenter and root.

For example, a background-only approach can introduce a camera controller and
its stage integration while the game chooses when to play it. Its coordinate
space, time ownership, completion, interruption, and coverage limits must be
clear. The renderer may need changes to apply that shot; unrelated story
decisions and actor focus should remain unaffected. The feature is still only
a recorded hint, not an implementation in this pass.

The useful measure is whether a change has understandable owners and effects.
Warning signs are duplicated behavior, hidden dependency on a game, shared
mutable state, conflicting clocks, or an effect changing unrelated controls.
The quantity of glue is not that measure. A focused demo and checks at the
changed boundary should make both the new behavior and existing play reviewable.

No universal game schema, generic effect registry, package extraction, or
upstream migration is required before the next feature. The current fixed
canvas, tactical skin, and narrower controller limits remain explicit scope
choices. Future requirements can justify changing them locally.

## Evidence and limits

P43 re-inspected the roots, routing, profile injection, Command Link direction,
stage composition, and component APIs, with an independent source review.
The existing composition checks were rerun; their scope is alternate bindings
and instance isolation. Earlier native game and effect results remain recorded
in [QA.md](QA.md). This pass makes no new visual-quality, export-portability,
second-game, or production-readiness claim.

[Local development guidance](AGENTS.md) carries these decisions into subsequent
feature work. P42's original request and outcome remain in the prompt archive
and ledger; this document also records P45's subsequent UI ownership decision.
