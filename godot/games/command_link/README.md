# Command Link

A tactical, commander-led story: three actors, player choices, required
fingertip contact, and a looping video opening that continues only on an
explicit click or tap. It is a branded game built on the
[Scenario framework](../../packages/scenario_runtime/README.md) and the lower
[game_presentation](../../packages/game_presentation/README.md) mechanisms. It
owns its world/UI/resource/input policy and invokes the authored mission.

```sh
Godot --path godot/games/command_link
```

| Here | What it is |
| --- | --- |
| `main.tscn`, `main.gd`, `roots.gd` | the shell: `--game command_link` (default) or `--game lab`, `--content-root` |
| `root.gd`, `game.gd`, `menu.gd`, `stage_profile.gd` | the mission composition, its game scene and menu |
| [presentation/](presentation/README.md) | the integration code the mission is staged with: stage, profile, actor overlay, opening, tactical theme, curve graph |
| `narrative/` | authored mission `.scenario`, versioned catalog and compiled runtime program |
| `authoring/mission.map.json` | compiler source locations for authoring and verification |
| `presentation/scenario_capabilities.json` | installed mission capability parameter schema; player-owned, not downloadable content |
| `assets/` | the game's art, contact layout, Manpu marks and opening video; catalogs tracked, bytes local |
| `lab/` | the Command Link Lab: eleven fixture studies and their menu; see [lab/README.md](lab/README.md) |
| `tests/` | headless suites and review records; run one with `Godot --headless --path godot/games/command_link --script res://tests/<suite>.gd` |
| `art/`, `captures/` | local generation rounds and evidence, ignored |

The mission uses Scenario Session for progression, choices, gates and operation
lifetimes. `game.gd` binds the existing stage, resources, contact and controls; it
does not dispatch story IDs to hidden direction. Presentation Lab remains a direct
mechanism study with its own routes and state. Narrative source freshness is
checked beside the game, and `tools/` owns its deterministic compiler entry point.

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

Mission checkpoints use envelope version 2 and an exact Scenario snapshot. Resume
admits the envelope before activating the route: contact/choice observations,
location, cast handoff timing and camera state must agree with the admitted
sequence. Unsupported or inconsistent checkpoints remain intact and show a Menu
route for starting a new mission. The owned `scenario_binding_checks.gd` covers
both valid contact resumes and contradictory saved state.
