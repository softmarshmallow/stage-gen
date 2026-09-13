# 0070 — The game invokes Scenario

*Ruled 2026-09-13 with the Godot Scenario promotion.*

## Fact

The repository separates its main Stage Gen asset product from a maintained
Godot example project. Scenario's old Python parser/compiler remained in the
asset component tree while its Godot reducer served Bellweather and The Grain.
Afterlight, Command Link and the VN starter independently directed richer scenes
with presentation mechanisms. That split left narrative progression and timed
direction with competing owners.

## Challenge

Expanding a flat dialogue format can recreate a universal game schema, make
small choreography edits harder than code, and turn every game-specific noun
into a runtime release. Keeping code directors would avoid those authoring costs
but retain multiple execution models and make content-only updates incomplete.

## Ruling

Promote Scenario as a Godot-owned, embeddable VN-oriented presentation framework.
**The game owns and invokes the scenario.** One execution model owns sequence
progression, branching, gates, cues, operations and outcomes. Games own worlds,
input routing, camera/resource bindings, persistence and narrative content.
A conversation can run during combat or appear on bubbles attached to existing
2D/3D actors. Front-facing staging and portraits are optional presentation choices.

The standalone Python compiler belongs to that Godot package. Game asset briefs,
input resolution and production metadata stay with game preparation adapters.
`game_presentation` remains an independent lower dependency for concrete motion,
effect, text and audio mechanisms. It imports no Scenario framework or game.

Content remains data. Game catalogs configure installed, versioned capability
types and expose typed numeric overrides. New nouns can be content revisions;
new algorithms require installed code. A story-ID callback is not an alternate
instruction model. Existing v2 sources and prepared programs stay supported
through compatibility translation into the same Session executor.

This supersedes [0001](0001-scenario-is-a-component.md)'s Stage Gen component
ownership and [0005](0005-one-narrative-contract-deleted-not-aliased.md)'s deletion
policy where it would discard supported v2 input instead of adapting it. It also
supersedes any universal reading of
[0008](0008-a-package-knob-is-a-closed-word-never-a-number.md)'s ban on numeric
configuration and [0014](0014-every-presentation-effect-is-a-pure-sampler.md)'s
single simulation-clock/pure-sampler requirement for this framework. Those
records retain their historical combat-consumer scope. Explicit clocks, typed
parameters and declared lifecycle now define Scenario's contract.
[0009](0009-a-consumer-policy-proves-itself-before-it-is-authored.md)'s requirement
for consumer evidence and [0066](0066-a-state-proof-is-not-a-picture-proof.md)'s
distinction between state and visual proof remain applicable.

## Evidence

The [current contract](../../godot/packages/scenario_runtime/docs/contract.md),
[compiler](../../godot/packages/scenario_runtime/authoring/README.md) and
[owned verification](../../godot/packages/scenario_runtime/docs/verification.md)
ship together. Cross-language fixtures execute the same typed source/IR;
procedural examples exercise continuing host simulation, moving 3D bubbles and
named/inline particles. Content checks admit two revisions using fixed installed
capabilities. The ownership move preserved all 14 recorded v2 production scenario
programs byte for byte, without provider calls or media regeneration.

Whole-game integration, native rendering and listening remain distinct evidence
with their owners. The current [coordinator](../../godot/docs/verification.md)
reports those scopes rather than treating a passing compiler as visual acceptance.

## Falsifier

A promised presentation behavior that requires story-specific execution code
outside the declared capability/presentation contract, or a content update that
silently installs code or takes ownership of unrelated game state, would violate
this boundary. Fix or narrow the owned contract with concrete consumer evidence;
do not introduce a second hidden sequence director.
