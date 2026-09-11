# game_presentation

The presentation SDK for staged 2D scenes in Godot: dialogue camera, actor focus
and exits, Manpu, eye transitions and blackout, halo, refraction and corruption,
sprite bursts and emitters, text sets and intertitles, voice playback and
processing, fingertip contact, and an optional confined content loader.

The payload is [addons/game_presentation](addons/game_presentation/README.md):
version, public entry points and limits are in its README, its
[API](addons/game_presentation/API.md) and `sdk.json`; each component's contract
sits beside its script. The directory around the payload is the package's own
Godot project, so the payload can be opened, checked and tested without a game.

| Here | What it is |
| --- | --- |
| `addons/game_presentation/` | the payload; the only thing a consumer installs or links |
| `tests/` | controller suites that need no game fixture, plus a python subdirectory for the assembler |
| `tools/check_sdk_package.py` | closure, literal dependencies, unique UID sidecars |
| `tools/assemble_starter.py` | builds a new project from `templates/vn` and this payload, copying real bytes |
| `docs/` | [terminology](docs/TERMINOLOGY.md), [character effects](docs/CHARACTER_EFFECTS.md), [packaging](docs/PACKAGING.md) |
| `history/` | the request ledger and frozen reviews of the line; see [history/README.md](history/README.md) |
| `AGENTS.md` | the guardrails that govern this package and the games built on it |

Consumers in this repository link the payload: `games/afterlight`,
`games/command_link` and `templates/vn` each have
`addons/game_presentation -> ../../../packages/game_presentation/addons/game_presentation`.

```sh
python3 godot/packages/game_presentation/tools/check_sdk_package.py
python3 godot/packages/game_presentation/tools/assemble_starter.py --output /private/tmp/my-next-vn
Godot --headless --path godot/packages/game_presentation --script res://tests/eye_transition_checks.gd
```
