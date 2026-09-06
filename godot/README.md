# The Godot project

One Godot 4.7 project plays a run of any recipe. It is the consumer end of the
pipeline: a run directory is named on the command line and this project draws,
sounds and simulates it. **Nothing here is generated art** — no PNG, no MP3, no
run — which is what keeps the repository's media-location rule satisfied and
what lets one project play any run the pipeline emits.

What a host owes is [the host contract](../docs/spec/game/host-contract.md); the
operating manual is [Godot hosts](../docs/godot-host.md); the ruling that put
every genre here is
[decision 0061](../docs/decisions/0061-every-genre-runs-on-godot-and-web-is-the-viewer.md).

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
another implementation of itself. A Python contract test enforces the direction
and the deny-list; it lands with the kernel, and until then the rule is prose.

Every `class_name` carries its layer or genre: `Kernel*`, `Host*` for the shared
host half, and the recipe's own word for a genre and its host — `Survival*`,
`Runner*`, `Platformer*`, `Room*`, `Dialogue*`, `Case*`. One project means one
global class-name space, and a name that hid a native class is refused by the
engine.

## Running a host

```sh
Godot --path godot -- --run <absolute run directory>
```

Everything after the bare `--` belongs to the host; Godot swallows the rest.
Each host's own flags are in its README under `hosts/<recipe>/`.

## The suites

```sh
Godot --headless --path godot -s res://tests/run_tests.gd -- --run <absolute run directory>
```

Headless can never produce a picture: under the dummy renderer the frame's
post-draw signal never fires and a viewport texture reads back as nothing, so
every picture claim comes from the windowed capture harness instead.

```sh
tools/validate.sh --run <absolute run directory> --out <directory> [--ref <directory>]
```
