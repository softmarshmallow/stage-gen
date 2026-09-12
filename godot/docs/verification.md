# Godot verification

The [Godot coordinator](../tools/check.py) owns the maintained project roster,
fixture preparation and execution adapters. It works from the Godot directory:

```sh
cd godot
../.venv/bin/python tools/check.py
```

The repository development environment supplies Python, the Stage Gen SDK,
Pillow and pytest. Afterlight's synthetic audio preparation checks also use FFmpeg. Set
`GODOT` to the engine executable when `godot` is not on `PATH`. From the repository
root, `uv run python scripts/check.py --scope godot` delegates to the same
coordinator and then runs the remaining root boundary tests. Neither command
uses providers or requires the optional game-preparation packages.

## What the default proves

The default runs credential-free headless checks. Every maintained owner is
accounted for, including checks that cannot run in this scope:

| Owner | Default execution | Additional prerequisites |
| --- | --- | --- |
| Private `demo_support` | Per-file native regression adapter | None |
| Bellweather | Per-file native regression adapter | Game visual/play evidence is separate |
| Iron Petal Unit | Per-file native regression adapter | Game visual/play evidence is separate |
| Ember Hollow | Per-file native regression adapter using an authored temporary run | Real-run assertions require `--run` |
| The Grain | Per-file native regression adapter | Game visual/play evidence is separate |
| Afterlight | Voice policy, synthetic voice preparation and content-copy checks | Prepared art and recordings for host integration; some suites need native rendering or audio |
| Command Link | Controller, bounds and synthetic-content checks | Prepared game media for composition and application checks; hologram checks need native rendering |
| `game_presentation` | Standalone mechanisms, dependency validation and Python starter assembly checks | Corruption raster checks need native rendering; halo raster branch stays visibly skipped headlessly |
| `scenario_runtime` | Independent program/state/action checks | None |
| `content_io` | Independent local-content checks | None |
| `sideview_rendering` | Layer, pixel and image-adapter checks with synthetic inputs | No game run or prepared art |
| VN template | Standalone story checks with procedural content | Optional capture mode requires native rendering |
| Asset consumer template | Temporary project copy, deterministic PNG preparation and actual scene consumption | None |
| Godot tooling | Python coordinator regression tests | Development pytest installation |

The four prepared-run games and private support retain
[`run_native_suite.py`](../tools/run_native_suite.py), which imports each owning
project and supervises each `test_*.gd` file in a separate process. Its authored
fixtures do not impersonate generated-art acceptance. Assertions pinned to a
real run remain visible in the coordinator report when no real run is supplied.

Presentation checks use explicit adapters from
[`check_suites.py`](../tools/check_suites.py). A `SceneTree` check runs with
`--script`. Command Link's `RefCounted` checks run through the game's existing
`--validate-*` application options. Four Afterlight compatibility entry points
are verified to remain pure aliases and are represented by their shared ensemble
suite. They do not inflate the executed suite count.

A zero process exit is insufficient for a native test pass: its declared success
marker must appear, and script errors fail the result. Missing source, an empty
native suite, an unknown check file or an unregistered project also fails. The
coordinator continues to the other owners after a failed owner.

## Coverage and return codes

The summary distinguishes `PASS`, `FAIL`, `BLOCKED` and `DEFERRED` outcomes.
`DEFERRED` means the suite is outside the requested scope, and its prerequisites
are printed. It is never counted as passed. Requesting a media-dependent suite
without its local media produces `BLOCKED`. Imports and fixture preparation are
reported separately from actual suite execution; importing a project alone
cannot produce an empty successful check run.

Return codes are `0` for the selected checks passing, `1` for failed checks or an
empty executable selection, and `2` for required checks blocked by prerequisites.
The default offline verdict is deliberately narrower than a complete rendered
gameplay verdict. Headless output never establishes pixel quality or listening
acceptance, even when an older suite's success message mentions its optional
capture branch.

```sh
# Inspect every adapter, including prerequisites outside the default scope.
../.venv/bin/python tools/check.py --list

# A specific owner, or one declared suite name.
../.venv/bin/python tools/check.py --owner command_link
../.venv/bin/python tools/check.py --owner command_link --only manpu_loop_checks

# Keep complete subprocess output and structured status for each outcome.
../.venv/bin/python tools/check.py --report /private/tmp/godot-checks.json

# Real Ember Hollow assertions in addition to its generic checks.
../.venv/bin/python tools/check.py --owner ember_hollow --run "$PWD/../out/ember-hollow-v13"
```

## Prepared media and native evidence

`--include-media` additionally requests headless host checks that use existing
game media. Afterlight's external-content comparison requires a separately
prepared copy. Preparation copies existing content and does not generate it:

```sh
../.venv/bin/python games/afterlight/tools/prepare_example_content.py \
  --output /private/tmp/afterlight-check-content
../.venv/bin/python tools/check.py --include-media \
  --afterlight-content-root /private/tmp/afterlight-check-content
```

Use a new destination for the preparation command. Missing catalog-bound art or
recordings are listed as prerequisites before the affected suites execute.
Presence checks are admission checks; the owning game tests still validate the
actual bindings and behavior. Media requirements follow each game's existing
catalogs and local conventions, not a new common gameplay manifest.

`--include-rendered` requests every registered suite, including those that need a
native renderer or audio device. It also includes prepared-media suites:

```sh
../.venv/bin/python tools/check.py --include-rendered \
  --afterlight-content-root /private/tmp/afterlight-check-content \
  --report /private/tmp/godot-native-checks.json
```

These suites can open windows and write evidence to their existing ignored output
locations. Some mixed suites have additional capture flags owned by their game;
the coordinator's rendered scope does not assert that every optional capture
branch was requested. Captures, game play-through and a human listening verdict
remain separately scoped evidence. A structural check never generates missing
media or changes its review/publication status.
