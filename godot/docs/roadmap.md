# Godot roadmap

This document owns cross-project follow-up work. The [architecture](architecture.md)
describes current ownership, the [charter](../CHARTER.md) its purpose, and
[verification](verification.md) the evidence required for changes. Individual game
features and package behavior belong to their owners.

The organization pass establishes independent content, scenario and side-view
packages, private scene-navigation reuse, game-owned options, narrower preparation
and collection tooling, and a Godot verification coordinator. It preserves existing
inputs and game composition rather than introducing a common gameplay language.

## Remaining reviews

| Candidate | Next useful boundary | Decision before implementation |
| --- | --- | --- |
| Sprite playback | Frame clocks, anchors, rebasing and held frames | Separate these from calibration, `playerHeightTiles` and run manifests. Use synthetic textures and game integration evidence. |
| System scheduling | System declarations, stable order, explicit ticks and refusals | Establish a useful independent API before promoting the small scheduler closure. RNG, inventory and gauges need not join it. |
| Pose composition | Base rectangles plus controller samples | Extract only if a narrow helper preserves both games' framing, camera and clock behavior. Whole cast stages remain game-owned. |
| Python SDK dependencies | Declared public asset interfaces | Review remaining private imports separately; do not promote game schema policy or documentation helpers into Stage Gen for convenience. |
| Older Python tests and goldens | Tests beside their owning game/package | Move collection and fixture discovery together, preserving exact fixture bytes and test coverage. Root cross-product checks remain separate. |
| Private widgets and conventions | Honest internal presentation/simulation groupings | Keep style, inventory and combat policies private until a smaller independent contract is useful. |
| Active-audio shutdown | Playback ownership during application exit | Investigate MP3 stream/playback references reported on abrupt engine shutdown. Bellweather and runner reproduce the warnings with the previous loader too; separate engine behavior from game lifecycle before changing either. |
| Full game frameworks | Optional consumer contracts | Review concrete consumers; there is no requirement for one visual-novel engine or save model. |

Review the [existing game backlog](../games/TODO.md) item by item when taking its
work. Move a game feature to that game's notes as it is reviewed; retain historical
evidence rather than inferring completion from an old checkbox or directory name.
Existing whole-game TOML can be simplified locally as a game needs it, without a
repository-wide rewrite prerequisite.

Source and offline correctness, deterministic replay, visible rendering, listening
quality, portable packaging and release are separate verdicts. Native check suites
may expose old assumptions when coverage expands; correct the owning test or
implementation with evidence instead of excluding the suite to obtain a green gate.
