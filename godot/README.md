# The Godot tree

One directory of Godot 4.7 projects, in three tiers. The rule is in the
[topology proposal](../docs/research/game-presentation-sdk-topology.md); this
tree is its first enforcement, dogfooded by the next game rather than by
rebuilding the existing ones.

```text
packages/    shared code. Each package is an addon project: project.godot,
             the payload at addons/<name>/, its own tests and tools.
templates/   agnostic starting points, one per recipe; each plays a run of
             its recipe and is what a branded game is copied from. (none yet)
games/       branded games. Complete, free to consume any package, consumed
             by nothing.
runtime/     the existing run consumer, moved here intact: one project with a
             host per genre. Its README is the operating manual. It will be
             carved into packages/game_runtime and templates/<recipe> later.
```

A game or template never contains a package. It links the payload into its own
`addons/` directory:

```text
games/<id>/addons/<name> -> ../../../packages/<name>/addons/<name>
```

Godot follows the link and Git tracks it; a checkout on Windows needs symlink
support. The starter assembler copies real bytes at the ship boundary, so a
shipped project carries no link. `tests/contract/test_godot_boundaries.py`
refuses a link that points anywhere but a package payload.

| Project | Run it |
| --- | --- |
| `runtime/` | `Godot --path godot/runtime -- --run <absolute run directory>`; see [runtime/README.md](runtime/README.md) |
| `games/playground/` | `Godot --path godot/games/playground -- --game bishoujo_afterlight --language ko`; see [games/playground/README.md](games/playground/README.md) |
| `packages/game_presentation/` | `python3 godot/packages/game_presentation/tools/check_sdk_package.py`; see [its README](packages/game_presentation/README.md) |
