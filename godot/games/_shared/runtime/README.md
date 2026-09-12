# Private demo support

`addons/demo_support` contains private implementation used by multiple maintained
games: deterministic simulation primitives, shared gameplay conventions, widgets,
token parsing and run-document adapters. Its content adapter uses `content_io`.
Single-game systems live in their game projects. This is private reuse, not
a canonical game SDK or a complete game runtime.

Scenario execution and side-view layer presentation have independent owners under
`packages/`. The sibling `addons/scene_navigation` is a small private lifecycle
helper for Afterlight and Command Link; those games do not import `demo_support`
to obtain it. Game-specific flags and defaults live with each game.

That describes this addon's current role. The [Godot project charter](../../../CHARTER.md)
allows future responsibilities to be reviewed and extracted into independently
usable packages within the Godot project.

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
