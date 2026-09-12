# Private demo support

`addons/demo_support` contains the dependency-closed Godot implementation used
by multiple maintained games: deterministic simulation primitives, scenario
execution, side-view rendering helpers and confined run/media loading.
Single-game systems live in their game projects. This is private reuse, not
a canonical game SDK or a complete game runtime.

The game projects mount the addon through development links.
`godot/tools/package_game_project.py` produces movable projects with real files.
Shared code never imports a named game. Tests enforce actual multiple-game
callers for every shared production class.

Run the shared checks from the repository root:

```sh
python3 godot/tools/run_native_suite.py --project demo_support
```

The generic testing helpers are under `addons/demo_support/testing`; they have
no game imports. Ember Hollow injects its own manifest validator and fixture
selection through its local test entry point.
