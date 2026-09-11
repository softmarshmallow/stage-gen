# The Godot project

One Godot 4.7 project plays a run of any recipe. It is the consumer end of the
pipeline: a run directory is named on the command line and this project draws,
sounds and simulates it. **Nothing here is generated art** — no PNG, no MP3, no
run — which is what keeps the repository's media-location rule satisfied and
what lets one project play any run the pipeline emits.

What a host owes is [the host contract](../../docs/spec/game/host-contract.md); the
operating manual is [Godot hosts](../../docs/godot-host.md); the ruling that put
every genre here is
[decision 0061](../../docs/decisions/0061-every-genre-runs-on-godot-and-web-is-the-viewer.md).

## The layers

```text
kernel/            engine-free, genre-free primitives
families/          a slice, its systems, its events, its port, the block it parses
genres/<recipe>/   a composition: world, parser, roster, its own systems, its tables
hosts/common/      what every host shares: the run root, the args, the latch, the loop,
                   the bridge, the interface kit, the capture harness
hosts/<recipe>/    one genre's host: main scene, frame owner, view, hud, audio, shaders,
                   devtools, shot table, template declaration
tests/             the headless suites and the fixtures they read
tools/             the harnesses a person runs: capture, smoke, parity, validate
```

Dependencies point inward and a layer never names one outside it. Only files
under `hosts/` may extend a scene node, touch the filesystem, read the wall
clock, draw an unseeded random number, or use an engine vector type; simulation
state is scalars, arrays and dictionaries, so a world can be compared against
another implementation of itself. `tests/contract/test_godot_boundaries.py`
enforces the direction, the deny-list, the name prefixes, one scene per host and
a `.uid` beside every script.

Every `class_name` carries its layer or genre: `Kernel*`, `Host*` for the shared
host half, and the recipe's own word for a genre and its host — `Survival*`,
`Runner*`, `Platformer*`, `Room*`, `Dialogue*`, `Case*`. One project means one
global class-name space, and a name that hid a native class is refused by the
engine.

## Running a host

```sh
Godot --path godot/runtime -- --run <absolute run directory>
```

Everything after the bare `--` belongs to the host; Godot swallows the rest. The
project's own main scene is the survival host, so every other host is named:

| Genre | Scene | A run that opens |
| --- | --- | --- |
| oblique survival | (the main scene) | `out/ember-hollow-v13` |
| sideview runner | `res://hosts/sideview_runner/main.tscn` | `out/iron-petal-c1-parity` |
| sideview platformer | `res://hosts/sideview_platformer/main.tscn` | `out/bellweather-c6-parity` |
| point-and-click room | `res://hosts/pointclick_room/main.tscn` | `out/the-grain-window-a4` |
| dialogue scene | `res://hosts/dialogue_scene/main.tscn` | `out/the-grain-scene-a`, with `--scenario e1_office` |
| the case | `res://hosts/case/main.tscn` | `out/the-grain-episode-one` |

Each host's own flags are in its README under `hosts/<recipe>/`. The case plays
the room's and the scene's leaves rather than a game of its own, which is why
both live in `hosts/common/`.

## The suites

```sh
Godot --headless --path godot/runtime -s res://tests/run_tests.gd -- --run <absolute run directory>
```

One process over every file, which is how it is run by hand. Under a gate it is
run one process *per* file instead:

```sh
python3 tools/run_suite.py --run <absolute run directory> [--timeout 180] [--jobs 4]
```

The supervisor exists because two failures are invisible to a single process. A
file that dies hard takes the whole run with it and every file after it goes
unreported, so the suite says nothing rather than saying which file; and a file
that *hangs* is indistinguishable from a slow one, because `--quit-after` ends
the process at an iteration count and names nothing. A process per file makes a
crash cost one file's results and a hang a named, killed file. `--only` on
`run_tests.gd` is what makes that possible, and without it the runner behaves
exactly as it always has.

Both forms want a run, and `out/` is not in the repository — so the repository
writes one:

```sh
python3 tools/make_fixture_run.py <directory>
```

A hand-authored survival package thirty-two metres across, with its plates
synthesised at the sizes its own manifest declares, from the standard library
alone. That is what the locked offline gate `uv run python scripts/check.py`
points the suite at, and it is the only run a fresh clone has. A count a
*producer* decided — how many things a world placed, how wide its plates came
out — is guarded by `TestHarness.pinned()` and read only when the suite is
pointed at a real run; every guarded block that goes unread is named at the end
of the output rather than passed over. See
[decision 0068](../../docs/decisions/0068-the-suite-reads-a-world-the-repository-can-write.md).

Headless can never produce a picture: under the dummy renderer the frame's
post-draw signal never fires and a viewport texture reads back as nothing, so
every picture claim comes from the windowed capture harness instead.

```sh
tools/validate.sh --run <absolute run directory> --out <directory> [--ref <directory>]
```
