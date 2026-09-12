# Godot game ownership layout

Implementation record, 2026-09-13. The named games own their inputs, preparation,
Godot projects and gameplay. This completes the ownership change proposed on
2026-09-12; the former `legacy` grouping and the empty `demos` tier are removed.
Verification results belong to the validation record below, separately from this
description of the source layout.

The asset product remains GNode, Stage Gen capabilities, recipes and authoring
harness. Games consume it. Existing TOML is maintained input for those games; it
is neither deprecated solely because of its age nor a required contract for a
new game. The earlier product split and its evidence remain recorded in
[the repository reshape](repository-reshape.md).

## The Godot tree

```text
godot/
├── README.md                          # Projects, launch and preparation entry points
├── games/                             # Named games, maintained as peers
│   ├── README.md                      # Game ownership and media availability
│   ├── TODO.md                        # Game work, separate from the product roadmap
│   ├── afterlight/                    # Existing authored adventure and its own Lab
│   ├── command_link/                  # Existing tactical story and its own Lab
│   ├── bellweather/                   # Platformer, including Waves
│   ├── iron_petal_unit/               # Runner
│   ├── ember_hollow/                  # Survival
│   ├── the_grain/                     # Case, rooms and dialogue together
│   └── _shared/                       # Private code with several game consumers
│       ├── runtime/
│       │   ├── project.godot          # Shared-support development and test project
│       │   ├── addons/demo_support/
│       │   │   ├── simulation/
│       │   │   │   ├── kernel/        # Reused deterministic primitives
│       │   │   │   └── families/      # Reused simulation and presentation mechanisms
│       │   │   ├── io/                # Media loading, paths and common runtime adapters
│       │   │   └── testing/           # Shared test harness; game fixtures are injected
│       │   ├── tests/
│       │   └── tools/
│       ├── python/
│       │   ├── pyproject.toml
│       │   └── src/demo_game_tools/
│       │       ├── input_formats/     # Captured game sources and shared readers
│       │       ├── media/             # Shared UI and soundtrack binding helpers
│       │       ├── io/                # Confined package capture
│       │       └── application/       # Preparation services used by several games
│       └── docs/                     # Formats shared by the existing game consumers
│           └── formats/
├── packages/
│   └── game_presentation/             # Independent presentation SDK
│       ├── addons/game_presentation/
│       ├── project.godot
│       ├── tests/
│       ├── tools/
│       ├── docs/
│       └── history/                   # Original request and design records
├── templates/
│   ├── asset_consumer/                # Minimal explicit asset preparation and display
│   └── vn/                            # Copyable presentation project
└── tools/
    ├── run_native_suite.py            # Native suites dispatched to their owning project
    ├── validate_game_package.py       # Explicit game input closure selection
    └── python/
        ├── pyproject.toml
        └── src/demo_game_collection/  # Collection CLI and cross-game fixture maintenance
```

`games/` is the single collection for named examples and games in development.
Afterlight and Command Link retain their working structure, including their
own Labs. A study that uses a game's cast, bindings or story state belongs to
that game. Package-specific examples can live with the package when they exist.
Templates remain distinct because they are intended to be copied.

## Inside a game

The four run-consuming games now have a project and preparation package of their
own. Bellweather illustrates the ownership in detail:

```text
games/bellweather/
├── README.md                          # Play, preparation and controls
├── project.godot                      # Renderer, main scene and local settings
├── main.tscn
├── main.gd                            # This game's entry point
├── gameplay/                          # Platformer simulation
│   └── support/                       # Exclusive gameplay dependencies
├── scenes/                            # Rendering, camera, controls and HUD
│   └── common/                        # Former shared-host leaves used only here
├── addons/
│   └── demo_support/                  # Installed/linkable private dependency closure
├── inputs/
│   ├── default/                       # Complete original Bellweather input closure
│   └── waves/                         # Complete original variant closure
├── pipeline/
│   ├── prepare.py                     # Offline plan by default, explicit variant/output
│   ├── pyproject.toml                 # Game-owned optional preparation package
│   └── src/bellweather_pipeline/
│       └── gameplay/                  # Retained Python gameplay input and validation
├── tools/                             # Map and terrain authoring, capture and parity
├── tests/                             # Native regression tests
└── docs/                              # Map formats, runtime and asset build graph
```

Iron Petal Unit and Ember Hollow likewise own their gameplay, scenes, inputs,
Python preparation package, tools, tests and docs. The Grain owns
`gameplay/{case,dialogue_scene,pointclick_room}` and the matching scene leaves
under its one project. The case main scene composes those leaves; room and
dialogue scenes remain explicitly launchable for focused work.

These directories describe existing ownership, not a mandatory schema for new
games. A simple game can use one GDScript and one preparation script. It need not
install the collection tools, adopt a base class or declare a universal manifest.

## Inputs and preparation

| Input owner before this change | Current owner |
| --- | --- |
| `legacy/inputs/bellweather` | `games/bellweather/inputs/default` |
| `legacy/inputs/bellweather-waves` | `games/bellweather/inputs/waves` |
| `legacy/inputs/iron-petal-unit` | `games/iron_petal_unit/inputs` |
| `legacy/inputs/ember-hollow` | `games/ember_hollow/inputs` |
| `legacy/inputs/the_grain` | `games/the_grain/inputs` |
| Repository `legacy/inputs/main.toml` | Removed; each game selects its inputs |

The input closures move together, including references, fonts, scripts, evidence
and internal relative paths. Persisted game IDs, schema identities and authored
source bytes do not change because the outer directory moved. Bellweather's
variants remain separate complete closures; no variant merge format is introduced.

From the repository root:

```sh
uv sync --frozen --group games
uv run --group games python godot/games/bellweather/pipeline/prepare.py
uv run --group games python godot/games/bellweather/pipeline/prepare.py --variant waves
uv run --group games python godot/games/iron_petal_unit/pipeline/prepare.py
uv run --group games python godot/games/ember_hollow/pipeline/prepare.py
uv run --group games python godot/games/the_grain/pipeline/prepare.py
```

The defaults plan or validate offline. `--dry-run --output <directory>` is an
explicit deterministic rehearsal for generation entry points. The Grain's default
case mode validates composition; room and dialogue preparation have their own
mode options, and case assembly takes explicit prepared leaf runs. Consult the
game's `--help` for its options. Paid generation requires explicit live opt-in.

Existing TOML readers preserve their input pairs. A later game change can replace
particular gameplay values with GDScript, resources or simpler local formats. That
change belongs to the game and does not require changing the asset SDK. Existing
`out/` runs stay where they are; `--run` selects one for play. Relocation requires
no new provider output and no promotion of ignored media.

## What is shared and what is independent

`packages/game_presentation` retains an independent public API, dependency closure
and checks. A future package earns the same position through bounded inputs and
behavior useful outside these games.

`games/_shared` serves the games in this repository. It contains reused simulation,
IO, input readers and media binding helpers. Single-game code moved to its caller:
platformer rules to Bellweather; runner rules, effects, voice and audio bindings to
Iron Petal Unit; survival and shell preparation to Ember Hollow; case and narrative
leaf builders to The Grain. No named game's project is another game's dependency.

The dependency direction is explicit:

- A game imports the public asset SDK, its own preparation code and private shared support.
- Shared support imports no named game.
- Collection tooling may import the named games for explicit dispatch and cross-game maintenance.
- The product imports no game or collection tooling.

Godot development links target the shared addon payload or an independent package
payload. Distribution assembly copies real files. Native resource paths and class
registration are updated for the split; the shared support project does not load
a game simply to discover a class.

The optional `games` Python group installs the preparation packages and collection
CLI, `demo-games`. Native engine verification remains the `godot` scope. The
product's default install and wheel do not acquire those optional dependencies.

## Documentation and verification ownership

Bellweather owns its generation/map format references; Iron Petal Unit owns runner,
audio, voice and effect references; Ember Hollow owns world/survival/shell/runtime
references; The Grain owns case, room and dialogue framing references. Shared game
input formats live in `_shared/docs`. Independent scenario and side-view map design
contracts remain in the product's `docs/spec` collection. Historical decisions and
research retain their original context, with links to the current owners.

Use [the owned gates](../../VERIFICATION.md) for Python game preparation, native
projects, the viewer, documentation and installed product isolation. The dedicated
native runner dispatches suites to the project that owns each implementation.

## Validation record

Native migration checks completed independently:

- 4,595 checks passed across 53 native test files in their owning projects.
- 1,860 replay frames matched the previous implementation's digests across platformer, runner, room, dialogue and case runs; sampled JSON fields also matched.
- Six existing-content boot paths completed: the four game main scenes plus The Grain's separate room and dialogue scenes.
- Four portable source-project assemblies imported independently with real addon files, outside the development links.
- Fourteen Python boundary/source dependency checks passed for the split native projects.
- All 204 tracked input files retained their original bytes after the move.
- Six optional Python wheels built offline. Each of the four game wheels planned from an isolated installed copy with sibling imports and network access blocked; each depends only on the product and shared game support.

Fresh projects require the one-time editor import documented in the
[launch guide](../../godot/README.md#play-a-game) before bare command-line launch.
These checks establish native behavior and packaging continuity. They do not
authorize new media or establish a new visual or listening verdict.

Final offline verification completed on the implemented layout:

- The standalone product gate passed all 14 steps, including installed-core isolation, public pipeline execution, cache reuse and distribution builds.
- The aggregate gate passed 39 of 40 steps. Its Python step passed 2,909 tests and found five UI tests still pointing to the moved input root. Those fixture paths were corrected; all five passed with `pytest --last-failed`, and the two affected files passed all 11 tests. The complete 2,914-test coverage therefore includes that focused rerun; the aggregate command was not rerun in full afterward.
- Strict mypy passed all 741 Python source files; Ruff formatting and lint passed.
- The viewer checks passed, with 168 Bun tests passing.
- All 18 game preparation/inspection commands passed, covering seven local plan/proof paths and three deterministic dry runs.
- The native suite passed again with 4,595 checks across 53 files. The presentation SDK package check passed.
- The documentation gate passed 301 Markdown files, 226 public text files and both declared generated-media entries.

No provider generation was performed. Existing local runs supplied the runtime
continuity evidence; media files were relocated without changing their bytes.
The earlier reshape's counts remain historical evidence and are not reused as
proof of this move.
