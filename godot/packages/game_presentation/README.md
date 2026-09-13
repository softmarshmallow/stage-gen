# game_presentation

The presentation SDK for staged 2D scenes in Godot: dialogue camera, actor focus
and exits, Manpu, eye transitions and blackout, halo, refraction and corruption,
sprite bursts and emitters, text sets and intertitles, voice playback and
processing, fingertip contact, and a compatibility facade for confined content loading.

This is an independently usable package within the [Godot example project](../../CHARTER.md).
Its presentation contract is local to this package. It does not define Stage Gen's
asset contract or require other Godot frameworks to have the same scope.

The payload is [addons/game_presentation](addons/game_presentation/README.md):
version, public entry points and limits are in its README, its
[API](addons/game_presentation/API.md) and `sdk.json`; each component's contract
sits beside its script. The directory around the payload is the package's own
Godot project, so the payload can be opened, checked and tested without a game.

| Here | What it is |
| --- | --- |
| `addons/game_presentation/` | presentation payload; install with its declared `content_io` dependency |
| `tests/` | controller suites that need no game fixture |
| `tools/check_sdk_package.py` | closure, literal dependencies, unique UID sidecars |
| `docs/` | [terminology](docs/TERMINOLOGY.md), [character effects](docs/CHARACTER_EFFECTS.md), [packaging](docs/PACKAGING.md) |
| `history/` | the request ledger and frozen reviews of the line; see [history/README.md](history/README.md) |
| `AGENTS.md` | package-specific guardrails; games and other packages own their composition rules |

Local file access and media decoding live in the independent
[content_io package](../content_io/README.md). Its addon is declared in `sdk.json`;
the [Scenario starter assembler](../scenario_runtime/tools/README.md) copies and
verifies its complete declared addon closure. Presentation controllers
do not acquire a game or scenario dependency.

[Scenario](../scenario_runtime/README.md) owns VN-oriented sequence execution,
authoring and optional presenters over these mechanisms. Games invoke it through
declared bindings. This package remains directly usable for focused controller
studies and applications that do not need authored narrative progression.

Consumers in this repository link the payloads: `games/afterlight`,
`games/command_link` and `templates/vn` each have
`addons/game_presentation -> ../../../packages/game_presentation/addons/game_presentation`.

```sh
python3 godot/packages/game_presentation/tools/check_sdk_package.py
python3 godot/packages/scenario_runtime/tools/assemble_starter.py --output /private/tmp/my-next-vn
Godot --headless --path godot/packages/game_presentation --script res://tests/eye_transition_checks.gd
```
