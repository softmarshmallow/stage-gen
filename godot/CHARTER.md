# Godot project charter

This repository contains two separately owned products. **Stage Gen is the main
asset-generation product. The Godot example project demonstrates how to consume
it in playable applications.** They share a repository, not a single application
architecture or mandatory game contract.

This charter states the continuing purpose and ownership of the Godot project.
It governs future work as well as the current layout. The names and arrangement
of directories inside this project can evolve while this boundary stays in place.
The [ownership migration record](../docs/plans/godot-consumer-layout.md) describes
one implementation of the boundary; it is not the permanent shape of this project.

## Two products, separate responsibilities

| Product | Purpose and responsibility |
| --- | --- |
| Stage Gen | The primary product: author, execute and inspect user-owned asset pipelines through the SDK, components, recipes and supporting tools. Its GNode and application layers remain defined by the [root architecture](../ARCHITECTURE.md). |
| Godot example project | The consumer product: turn selected assets into playable demonstrations, reusable Godot runtime packages and copyable starting projects. Own its gameplay, presentation, integration, tooling and development direction. |

In relation to Stage Gen, `godot/` is an examples directory with an engine-specific
name. Its games show ways to use the asset product; they do not define what every
Stage Gen user must build. An asset pipeline may serve another engine, a custom
application or a purpose unrelated to games.

Within its own scope, Godot is a maintained project. Example status does not make
its games disposable, its packages temporary or its implementation a second-class
codebase. The project can develop useful runtime SDKs and game frameworks for its
own consumers without becoming the main asset product. Their adoption is optional.

These are product and ownership boundaries within the current repository. They do
not require separate Git repositories, a new distribution or a release. Repository
contribution, verification, media and publication policies continue to apply.

## Goals

- Demonstrate useful assets in working games and show how preparation connects
  generated output to a real application.
- Give users understandable examples and starting points they can adapt, without
  requiring them to copy a complete game framework or adopt our gameplay formats.
- Maintain the retained games and their working preparation and playback paths.
- Develop Godot runtime and presentation capabilities where they have clear users,
  responsibilities and independently reviewable behavior.
- Let this project improve its own architecture without making Stage Gen depend
  on the internal arrangement of its examples.

## Ownership boundary

Stage Gen owns generation, validated artifacts, cache, provenance and asset
inspection. Godot preparation scripts consume those public APIs and artifacts;
the Godot project owns how assets become scenes, controls, cameras, animation,
story, combat, audio playback and a complete player experience.

Dependencies point from Godot consumers to Stage Gen. The asset product must
install, run and be useful without Godot or its game packages. Godot's internal
game formats must not become required inputs to public components or recipes.
The example project can also consume supplied assets and other asset sources.

Bounded asset contracts, such as sprite locomotion assets, looping parallax or
standalone scenario data, retain their own scope in Stage Gen. Their existence
does not imply a universal gameplay schema. A Godot adapter decides how to use
them and which gameplay assumptions to add.

An existing game's TOML belongs to its supported reader and consumer. A game can
keep it, simplify it, or replace parts with GDScript and Godot resources when that
improves its implementation. Neither a format rewrite nor a common game language
is a prerequisite for other work. Playing and replaying consume prepared content;
generation remains an explicit preparation action.

## Organization belongs to this project

The current [workspace guide](README.md) explains the actual directory tree and
commands. Its main owners are:

| Owner | Responsibility |
| --- | --- |
| `games/` | Named applications, with game-specific content, inputs, preparation, composition, gameplay and demonstrations. |
| `games/_shared/` | Private implementation reused by actual games, without promising an independently supported package API. |
| `packages/` | Independently reusable Godot capabilities or frameworks with their own documented contracts, dependencies, examples and checks. |
| `templates/` | Starting projects intended to be copied and customized. |
| `tools/` | Project-wide preparation, assembly, inspection and verification utilities. Game-specific tools stay with their game. |

Games choose their dependencies. Shared support and packages do not import a
named game, its story, asset bindings or mutable state. A package may use another
package through its declared interface; no package must depend on the entire
collection. Each game owns its final composition.

The recent promotion from the former legacy grouping established maintained game
ownership. It did not finish the Godot architecture or freeze the present split.
Private shared code can become a package, a package can be split, and an abstraction
can return to its game when that is the clearer owner. Each change needs evidence
about responsibilities and consumers, rather than a preference for more packages.

## Reviewing future changes

Further Godot organization is work on this project. For each candidate:

1. Identify its current callers, behavior and assumptions, including content,
   input, timing, state and lifecycle ownership.
2. Decide whether it is game-specific composition, private shared implementation,
   an independently reusable package, or a copyable starting point.
3. Define the smallest useful boundary and its explicit inputs, outputs and
   dependencies. Package extraction should let a consumer use it without importing
   a named game; a second complete game is not a prerequisite for proving that.
4. Review whether to keep, split, combine, promote or simplify it. Similar names
   or screens alone are insufficient reasons to combine implementations.
5. Make each change with its owning documentation and focused checks,
   preserving supported game behavior and prepared content compatibility unless
   the task explicitly changes them.

For example, the existing visual-novel and dialogue implementations may share
useful progression, staging, transition, choice or replay behavior. Review those
responsibilities individually. The outcome could be several packages, one optional
Godot framework, game-specific adapters, or a combination. There is no prior
requirement to make every game use one visual-novel engine. Such a framework and
its contract belong to this project, not to Stage Gen's asset-authoring contract.

Sharing a mechanism between games is not sufficient reason to move it into
Stage Gen. A candidate for the main product needs a separate asset-pipeline use
case and a bounded contract that works without a selected game or Godot runtime.
Changes to that public boundary are reviewed as Stage Gen work, independently of
the internal Godot refactor.

This charter defines the goal and review criteria. It does not select the next
extraction, merge the existing game systems, or prescribe a new directory tree.
Review and implement those changes one at a time within this scope.
