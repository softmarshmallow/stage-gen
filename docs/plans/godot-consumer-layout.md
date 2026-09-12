# Godot consumer layout proposal

Status: proposed, 2026-09-12. This document describes the next topology; source
directories and launch commands have not been changed by this proposal.

The games are maintained consumers of the asset SDK. Their location should express
that ownership. The previous move into `godot/legacy` established the product
boundary, but incorrectly made an implementation's history its permanent category.
Remove that category. Existing TOML readers can remain ordinary implementation
details of the games that use them.

## The proposed tree

```text
godot/
├── README.md                          # Project list, launch commands, preparation needs
│
├── games/                             # All named example games, maintained as peers
│   ├── afterlight/                    # Existing standalone project and its own Lab
│   ├── command_link/                  # Existing standalone project and its own Lab
│   ├── bellweather/                   # Platformer; includes the Waves variant
│   ├── iron_petal_unit/               # Runner
│   ├── ember_hollow/                  # Survival
│   ├── the_grain/                     # Investigation: case, rooms and dialogue together
│   └── _shared/                       # Private implementation used by these games
│       ├── runtime/
│       │   ├── addons/demo_support/   # Dependency-closed shared Godot code
│       │   │   ├── simulation/        # Reused deterministic primitives and systems
│       │   │   └── io/                # Shared media loading and path confinement
│       │   ├── project.godot          # Test project for the shared implementation
│       │   └── tests/
│       ├── python/
│       │   ├── pyproject.toml         # Optional demo tooling; depends on Stage Gen
│       │   └── src/demo_game_tools/
│       │       ├── input_formats/     # Retained TOML/package readers used by these games
│       │       ├── builders/          # Only build stages with actual shared callers
│       │       ├── io/                # Shared capture, packing and artifact handling
│       │       └── validation/        # Shared checks for those particular input formats
│       ├── tests/                     # Shared Python and integration regression checks
│       └── tools/                     # Cross-game fixture and identity maintenance
│
├── packages/                          # Independently usable Godot SDKs
│   └── game_presentation/
│       ├── addons/game_presentation/  # Existing reusable presentation implementation
│       ├── project.godot             # Package development and checks
│       ├── tests/
│       ├── tools/
│       ├── docs/
│       └── history/                   # Existing design and request records
│
├── templates/                         # Copyable starting projects
│   ├── asset_consumer/                # Minimal image import and display
│   └── vn/                            # The Signal Room starter
│
└── tools/                             # Workspace checks, assembly and asset inspection
```

These are proposed owners, not a requirement to create every illustrated folder.
The `_shared` subfolders are destinations for verified shared dependencies; a
module with one game consumer stays with that game. The optional Python package
name is a working name, not a new public SDK commitment.

`games/` is the single collection for playable examples and games in development.
Remove the empty `demos/` placeholder. Small examples for an independent package
can live under that package's `examples/` when they exist. A study that uses
Afterlight's cast, bindings or story state stays in Afterlight's `lab/`; the same
applies to Command Link. A template is retained because its purpose is to be
copied as a new project, even when it is also playable.

Afterlight and Command Link are the maintained standalone presentation examples.
The Grain owns the retained room/dialogue compositions; that behavior does not
belong in `_shared` merely because its implementation currently uses separate hosts.

## Inside a game

Bellweather illustrates the desired ownership. It is an example layout, not a
mandatory game schema or a requirement to rearrange the working Afterlight and
Command Link projects into identical folders.

```text
games/bellweather/
├── README.md                          # Play, prepare, controls and known limits
├── project.godot                      # This game's main scene, renderer and settings
├── main.tscn
├── main.gd                            # Composition and explicit content selection
├── gameplay/                          # Platformer simulation and game-specific systems
├── scenes/                            # Rendering, camera, HUD and interaction
├── content/                           # Game-owned interpretation and asset bindings
├── addons/                            # Installed shared code actually used by this game
│
├── inputs/
│   ├── default/                       # Existing Bellweather input closure, kept intact
│   └── waves/                         # Existing Waves closure, kept intact
├── pipeline/
│   ├── prepare.py                     # This game's explicit asset preparation entry point
│   ├── build.py                       # Composes Stage Gen capabilities for this game
│   └── adapters/                      # Retained input readers and Godot resource mapping
├── tools/                             # Map/terrain authoring and game-specific captures
├── assets/                            # Prepared local assets, under existing storage policy
├── tests/                             # Game simulation, preparation and native checks
└── docs/                              # This game's formats, decisions and authoring guide
```

`prepare.py` is a discoverable script convention. It does not introduce a required
Python base class, game registry, global selector or shared gameplay manifest.
Its command-line options belong to the game. It can invoke the public asset SDK,
reuse existing builders, or import already generated assets. Gameplay runs from
GDScript and prepared content; starting a game never initiates generation.

The current TOML closures stay intact during relocation, including their relative
member paths and source identity rules. Their gameplay parameters are game-owned
configuration. A later game change may move those values into GDScript, resources
or simpler files. There is no required conversion pass and no new universal
replacement format. A shared reader can support an existing file format without
making it the authoring contract for future games.

Existing media and outputs can be consumed at their current locations through
explicit game-local launch/preparation options. Moving ownership does not require
regeneration, copying all `out/` runs into game folders, or committing ignored media.

## Where the existing content goes

| Existing owner under `godot/` | Proposed owner | Treatment |
|---|---|---|
| `games/afterlight`, `games/command_link` | Same game roots | Keep their working project structure and game-local Labs |
| `legacy/inputs/bellweather` | `games/bellweather/inputs/default` | Preserve the complete authored closure |
| `legacy/inputs/bellweather-waves` | `games/bellweather/inputs/waves` | Same game identity; retain as a variant, without inventing a merge format |
| `legacy/inputs/iron-petal-unit` | `games/iron_petal_unit/inputs` | Runner inputs and bindings |
| `legacy/inputs/ember-hollow` | `games/ember_hollow/inputs` | Survival inputs and bindings |
| `legacy/inputs/the_grain` | `games/the_grain/inputs` | Keep its case, rooms, scenarios and story together |
| `legacy/inputs/main.toml` | Game-local selection in preparation scripts | Retire the global selected-game file after callers move |
| `legacy/runtime/genres/sideview_platformer`, matching host | `games/bellweather/gameplay` and game scenes | Game-owned simulation, renderer, camera and controls |
| `legacy/runtime/genres/sideview_runner`, matching host | `games/iron_petal_unit/gameplay` and game scenes | Runner-owned simulation and rendering |
| `legacy/runtime/genres/oblique_survival`, matching host | `games/ember_hollow/gameplay` and game scenes | Survival-owned simulation and rendering |
| Room and dialogue genres/hosts and their exclusive leaves | `games/the_grain/gameplay` and game scenes | The Grain is their remaining named game consumer; only dependencies used by other games belong in `_shared` |
| Case host and case orchestration | `games/the_grain` | The Grain owns episode progression and composition |
| `legacy/runtime/kernel`, `families`, common host utilities | `_shared/runtime` or the sole consuming game | Preserve algorithms and deterministic behavior; place by actual imports |
| `legacy/python/stage_gen_legacy` | Game `pipeline/` modules plus `_shared/python` | Move whole-game builders to their consumers; retain one copy of shared implementations |
| `legacy/tools` | Owning game's `tools/`, or `_shared/tools` | Platformer authoring follows Bellweather; survival goldens follow Ember Hollow |
| Game contract and host specifications | Game docs or `_shared` format documentation | Describe maintained consumer formats and their callers |
| `packages`, `templates`, `tools` | Same top-level owners | Keep independent responsibilities |
| Empty `demos` and emptied `legacy` | Removed | No placeholder or historical-status bucket remains |

Directory names use the existing Godot convention, such as `iron_petal_unit`.
Persisted game IDs, node identities, schema versions and artifact digests do not
change merely because a directory uses underscores.

## Reuse without another whole-game framework

`packages/game_presentation` remains an independently usable SDK. It has its own
public APIs, dependency closure and tests. A future runtime package earns the same
position through clear independent inputs and behavior.

`games/_shared` has a narrower audience: the games in this repository. Existing
shared gameplay code is useful and can remain maintained there. That does not make
its player model, genre list, package schema or UI a requirement of either Stage
Gen or a new Godot game. Keep the room/dialogue implementations with The Grain,
and extract only dependencies that the current graph proves other games use. Do
not promote the entire former runtime into a public `game_engine` package as part
of this move.

Each game imports shared code it needs. Shared code never imports a named game.
The Python game tooling imports the public Stage Gen SDK; the product imports no
game tooling. No game depends on another game's project root or mutable state.
Godot project assembly installs dependency-closed addon payloads. Development
links, if used for private addons, need an explicit extension of the current
package-link boundary check; distributable projects contain real source files.

## Making the move safely

This is more than removing the word `legacy`. The current runtime has one
`project.godot`, a shared global script-class namespace and fixed `res://` paths.
The Grain's Case host composes room and dialogue leaves. Splitting directories
alone would break those references and the existing test harness.

1. Establish the named game roots and move each complete input closure. Replace
   the global input selector with explicit game-local preparation entry points.
   Preserve existing readers and identify actual shared Python dependencies.
2. Separate the shared Godot dependency closure from each game's runtime code.
   Introduce a game-owned project and main scene for each migrated consumer,
   update resource paths and class discovery, and split regression suites by owner.
   Preserve the deterministic simulation layer where it already supplies useful
   parity guarantees; new game scripts are free to use ordinary Godot APIs.
3. Route existing generated runs through the corresponding game's adapter and
   verify them before retiring the single multi-genre project. Do not require
   fresh provider output to demonstrate that a relocation works.
4. Rename the optional Python package, installation group, CLI references and
   check scopes with the move. Use a `games` group for Python demo preparation,
   retain `godot` for native projects, and keep both out of the product default.
   Old command/import spellings may briefly forward during migration, but the
   published launch instructions point to game-local entry points.
5. Update current documentation, skills, path checks, packaging and CI together.
   Move maintained game-format documentation to its consumer owner. Preserve
   historical decision records as history. Remove the empty directories and
   temporary forwarding entry points after their remaining callers are gone.

Completion means Bellweather, Iron Petal Unit, Ember Hollow and The Grain keep
their existing working runs; Afterlight and Command Link keep their current
behavior; game preparation and native regression checks pass; and an installed
Stage Gen product still operates without any Godot game or optional game-tooling
package.
