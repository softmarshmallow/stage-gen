# Movie Sprite Actor

Independent Godot playback of pre-rendered transparent body motion with
host-controlled facial states. This package owns the atlas clock/cache,
compositor, descriptor admission and scene lifecycle. Games own preparation,
assets, cast direction, speech, UI and transforms.

The installable payload is [addons/movie_sprite_actor](addons/movie_sprite_actor/README.md).
Its [API contract](addons/movie_sprite_actor/API.md) and
[SDK descriptor](addons/movie_sprite_actor/sdk.json) document the supported fixed
registered-face atlas representation, resource limits and public lifecycle.
Install the separately owned [content_io](../content_io/README.md) payload too.
This package imports no game, Scenario or generation module.

The local package project and its tests/examples are development support;
consuming games copy only the declared addon payloads. Preserve the source UID
sidecars when copying. `addons/content_io` is a development link to the sibling
package, not a distributable symlink.

The initial extraction preserves existing prepared version-1 assets while
accepting other bounded frame sizes, timebases and atlas layouts, including
single-page bodies and partial final pages. It does not import animation rigs,
decode runtime video or implement a separate neutral face plate. The name links
this runtime responsibility to the `movie_sprite` asset family; it does not
promote its generation pipeline.

## Independent checks and consumer

[tests/run_checks.gd](tests/run_checks.gd) exercises the package with synthetic
assets and different canvases, frame counts, rates and page layouts. Run from
the repository root:

```sh
godot --headless --path godot/packages/movie_sprite_actor --script res://tests/run_checks.gd
```

[examples/standalone](examples/standalone/main.gd) is a small independent consumer
with code-authored raster fixtures, not a copy of a named game. Its assembler
copies the complete addon and `content_io` dependency into a new standalone
project; the destination must not already exist:

```sh
python3 godot/packages/movie_sprite_actor/tools/assemble_standalone.py --output /private/tmp/my-movie-sprite-consumer
godot --path /private/tmp/my-movie-sprite-consumer
```

The consumer's `-- --smoke --capture-dir /private/tmp/my-movie-sprite-proof`
arguments run native rendering/lifecycle checks and save inspection captures.
Synthetic pixel checks establish compositing behavior; they do not approve any
generated character artwork, registration or loop quality.

The [repeatable consumer check](tools/check_standalone.py) makes a fresh source
copy outside the checkout, runs the game there, and verifies source hashes and
its execution report. `GODOT` or `--engine` selects the engine executable.
Use `--capture-dir /absolute/new/directory` to retain evidence; an existing
capture directory is refused.

```sh
python3 godot/packages/movie_sprite_actor/tools/check_standalone.py
python3 godot/packages/movie_sprite_actor/tools/check_standalone.py --rendered
```

The Godot coordinator registers package checks, assembly tests and both consumer
modes. `--owner movie_sprite_actor` runs offline checks; add `--include-rendered`
for native pixels. Current local verification on Godot 4.7.2/Apple M4 Pro passed
247 package assertions, 13 assembly/runner tests, 15 copied-consumer headless
checks and 24 native checks. The inspected procedural figures demonstrate
framing, independent feature placement and preserved transparency. Afterlight
owns its separate real-art integration and review; these synthetic checks make
no artwork or listening claim. Exported executables and other platforms were
not tested by this source-assembly pass.
