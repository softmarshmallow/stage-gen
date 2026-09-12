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
| `main.tscn`, `main.gd`, `roots.gd` | the shell: `--game command_link` (default) or `--game lab`, `--content-root` |
| `root.gd`, `game.gd`, `menu.gd`, `stage_profile.gd` | the mission composition, its game scene and menu |
| [presentation/](presentation/README.md) | the integration code the mission is staged with: stage, profile, actor overlay, opening, tactical theme, curve graph |
| `assets/` | the game's art, contact layout, Manpu marks and opening video; catalogs tracked, bytes local |
| `lab/` | the Command Link Lab: eleven fixture studies and their menu; see [lab/README.md](lab/README.md) |
| `tests/` | headless suites and review records; run one with `Godot --headless --path godot/games/command_link --script res://tests/<suite>.gd` |
| `art/`, `captures/` | local generation rounds and evidence, ignored |

History, exact prompts and the request ledger for both games live in the
package's [history](../../packages/game_presentation/history/README.md).

The application shell shares the private [scene lifecycle](../_shared/runtime/addons/scene_navigation/README.md)
with Afterlight through its explicit `addons/scene_navigation` dependency. This
keeps immediate input detachment and checkpoint copying consistent; routes,
mission state, preparation and resume defaults stay local.

Provider-free synthetic checks for the extracted boundaries:

```sh
Godot --headless --path godot/games/command_link --script res://tests/scene_navigation_checks.gd
Godot --headless --path godot/games/command_link --script res://tests/stage_seams_checks.gd
```
