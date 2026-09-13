# Presentation package status

This package remains the maintained code-first presentation addon. Its
[API inventory](../addons/game_presentation/API.md) and
[component contracts](../addons/game_presentation/README.md) define its supported
local canary surface. No stable release or publication is implied.

The local-content implementation belongs to the independent `content_io` addon;
the presentation path remains a compatibility facade. The Scenario-owned starter
assembler copies its complete declared closure with licenses, source UIDs and a
byte inventory.

Afterlight and Command Link are separately owned games. Their routes, narrative
content, UI, art, voice policy and checkpoints belong to them. They invoke the
[Scenario framework](../../scenario_runtime/README.md), which owns shared sequence
execution, timing, capability lifecycle, compiler and optional presenters. Episode
direction is data; Game Presentation supplies the underlying mechanisms. Shared
application navigation remains private Godot support.

The [Godot coordinator](../../../docs/verification.md) owns the current verification
entry point and coverage accounting. Historical proof records remain under
`history/`; they do not replace a fresh check of changed code. Standing framing
calibration and anatomy inference remain outside the implemented package contract.

Use the [Godot roadmap](../../../docs/roadmap.md) for cross-project changes and this
package's contracts for individual controller work. Scenario consumes this package;
this package does not acquire a dependency on Scenario.
