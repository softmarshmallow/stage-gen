# Command Link

A tactical, commander-led story: three actors, player choices, required
fingertip contact, and a looping video opening that continues only on an
explicit click or tap. It is a branded game built on the
[game_presentation](../../packages/game_presentation/README.md) package, which it
links at `addons/game_presentation`.

```sh
Godot --path godot/games/command_link
```

| Here | What it is |
| --- | --- |
| `main.tscn`, `main.gd`, `roots.gd` | the shell: `--game command_link` (default) or `--game lab`, `--content-root`, `--opening-variant a` or `b` |
| `root.gd`, `game.gd`, `menu.gd`, `stage_profile.gd` | the mission composition, its game scene and menu |
| `presentation/` | the integration code the mission is staged with: stage, profile, actor overlay, opening, tactical theme, curve graph |
| `assets/` | the game's art, contact layout, Manpu marks and opening video; catalogs tracked, bytes local |
| `lab/` | the Command Link Lab: eleven fixture studies and their menu; see [lab/README.md](lab/README.md) |
| `tests/` | headless suites and review records; run one with `Godot --headless --path godot/games/command_link --script res://tests/<suite>.gd` |
| `art/`, `captures/` | local generation rounds and evidence, ignored |

History, exact prompts and the request ledger for both games live in the
package's [history](../../packages/game_presentation/history/README.md).
