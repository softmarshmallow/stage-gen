# Scenario source assembly

`assemble_starter.py` copies the [VN starter](../../../templates/vn/README.md)
and the complete Scenario/Game Presentation/Content IO addon closure into a fresh
standalone Godot project. It verifies real source bytes, preserves licenses and
UIDs, writes `assembly.json`, and atomically installs the completed tree.
It does not copy symlinks, import caches, generated media or provider credentials.

```sh
python godot/packages/scenario_runtime/tools/assemble_starter.py --output /private/tmp/my-vn
```

`preview.gd` opens compatible `program.json`/`catalog.json` through the same
procedural Host/Session used by the examples. Its installed vocabulary is particle
v1 with bottom/portrait/bubble presentation. Controls inspect and step time or
restore a validated visited checkpoint; there is no arbitrary positional seek.

```sh
godot --path godot/packages/scenario_runtime --script res://tools/preview.gd -- --content /absolute/content
```

Optional `--checkpoint /absolute/snapshot.json` restores compatible state;
`--check` performs finite headless admission/stepping. New capability code is never
loaded from the content directory.

The installed `scenario-authoring` CLI separately compiles narrative and assembles
explicit data packages; see [authoring](../authoring/README.md). Game-specific art
preparation remains with its game. Neither tool generates content during playback.
