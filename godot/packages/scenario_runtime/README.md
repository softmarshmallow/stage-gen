# Scenario runtime

Scenario is an embeddable, VN-oriented narrative presentation framework owned by
[the Godot project](../../CHARTER.md). A game invokes a sequence and grants its
presentation capabilities. The game keeps its world, objects, input, camera,
resources, navigation and saves. The sequence owns its dialogue, branches,
authored direction, cues, waits and outcomes during that invocation.

The current execution contract is **`scenario-program-v3`**. Existing
`scenario-program-v2` content remains supported through a compatibility reader
that translates to the same Session executor. This is a local source package;
its version metadata does not claim a published or stable release.

- [Invocation contract](docs/contract.md): authoritative semantics and limits.
- [Directory preview](docs/layout.md): implemented owners at a useful review level.
- [Authoring](docs/authoring.md): compiler, syntax, catalogs and source identity.
- [Embedding](docs/embedding.md): runnable host integration and presentation choices.
- [Compatibility](docs/compatibility.md): v2 inputs, capabilities, content and saves.
- [Verification](docs/verification.md): owned checks and evidence boundaries.

## Install and play

Copy `addons/scenario_runtime/` and its declared `game_presentation` and
`content_io` dependencies into a Godot 4.7 project's `addons/`. Preserve each
payload's license, JSON data and source UIDs. The pure program/session scripts
load no game or media; the full addon also supplies optional presenters and
bindings over Game Presentation. Playback needs neither Python nor Stage Gen.

For a complete copyable consumer, assemble the [Signal Room starter](../../templates/vn/README.md)
from the repository root into a fresh directory:

```sh
python godot/packages/scenario_runtime/tools/assemble_starter.py --output /private/tmp/my-scenario-game
godot --path /private/tmp/my-scenario-game
```

The independent procedural examples require no generated media:

```sh
godot --path godot/packages/scenario_runtime res://examples/combat_dialogue/main.tscn
godot --path godot/packages/scenario_runtime res://examples/world_bubbles/main.tscn
godot --path godot/packages/scenario_runtime res://examples/catalog_effects/main.tscn
```

These demonstrate an ongoing host simulation during dialogue, moving projected
3D actor bubbles, and named/inline particle definitions. Their small simulation
is illustrative; this addon implements no combat or world simulation.

## Author and consume

The independently installable Python distribution lives at
[`authoring/`](authoring/README.md), imports as `scenario_authoring`, and exposes
`scenario-authoring`. It compiles stable-ID `.scenario` source to explicit JSON,
validates typed catalogs/capabilities, emits source maps and packages existing
content. It does not generate assets or execute source code from content.

The game installs capability implementations and their parameter schemas. Its
catalog gives those mechanisms reusable names and permitted parameter overrides.
A new ember preset can be content; a new particle algorithm needs an installed
capability. Presentation profiles can select a bottom panel, optional portrait,
narration, subtitle or bubble. Front-facing cast staging is an optional adapter.

Afterlight, Command Link and the VN starter author v3 content. Bellweather and
The Grain retain their v2 inputs and prepared programs through the compatibility
boundary. Each game owns its asset preparation and presentation bindings. See
[Godot verification](../../docs/verification.md) for the current gate roster;
source and headless correctness do not establish visual or listening acceptance.
