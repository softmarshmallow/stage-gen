# Example: a game that builds its art with gnode

**The ask:** "My game, *Kitewharf*, keeps its levels in its own TOML files. My game code reads
them, and I won't change that format. For every level I want a ground plate, an icon for every
pickup and a looping sky, generated, cached, and copied into the Godot project. CI must check that
everything still plans, without spending."

```
kitewharf/                            # the game's repo
  godot/                              # the Godot project (art lands in godot/art/)
  levels/docks.toml, levels/cliffs.toml       # the game's own format
  assets/
    gnode.yaml
    level_art.py                      # a Python builder: the game's TOML → a gnode workflow
    workflows/icon.yaml               # a plain workflow file, used as a step
    workflows/looping-parallax.yaml   # copied from the looping-parallax example
    nodes/plate.py                    # the game's own node types
    level_art.takes.yaml              # chosen takes for level builds (next to the builder), committed
    workflows/icon.takes.yaml         # chosen takes for standalone icon runs
```

## Why this one uses a Python builder

The game's level format belongs to the game: its readers live in the game's code. A workflow
file's `inputs:` would mean converting it. A builder instead lets the game's own reader produce the
steps:

```python
# assets/level_art.py
from pathlib import Path
from gnode import Workflow
from kitewharf.levels import read_level  # the game's reader, unchanged


def build(level: str) -> Workflow:
    spec = read_level(Path(level))  # the game's own TOML schema
    wf = Workflow("kitewharf-level-art", title=f"Level art: {spec.name}")

    plate = wf.step(
        "plate",
        uses="./nodes/plate.py#ground_plate",
        with_={"material": spec.ground.material, "span_m": spec.ground.span_m, "light": spec.light},
        view=True,
    )
    icons = wf.step(
        "icon",
        for_each=[{"id": p.id, "name": p.look} for p in spec.pickups],
        key="${{ item.id }}",
        uses="./workflows/icon.yaml",
        with_={"name": "${{ item.name }}"},
    )
    sky = wf.step(
        "sky",
        uses="./workflows/looping-parallax.yaml",
        with_={"canvas": spec.sky.canvas, "layers": spec.sky.layers},  # the game's sky layer files
    )
    wf.outputs(plate=plate.outputs.image, icons=icons.all.outputs.icon, sky=sky.outputs.layers)
    return wf
```

The builder takes every workflow-file field, with the same names (`judges=`, `on_reject=`,
`regenerate=`, `takes=`, `budget=`, `assert_=`, `view=` ...), so nothing is YAML-only.

The builder runs only while planning. The values it puts in `with_` are what gnode keys on, so
the TOML file is never a hidden input: change a pickup's look and only that icon re-runs.

## Building

```bash
cd assets
gnode plan level_art.py:build --arg level=../levels/docks.toml
gnode run  level_art.py:build --arg level=../levels/docks.toml --live --max-usd 5 \
  --deliver plate=../godot/art/docks/ground.png \
  --deliver icons=../godot/art/docks/icons/{key}.png \
  --deliver sky=../godot/art/docks/sky/{key}.png
```

- **`--deliver`** copies declared outputs out of the run after it succeeds, and only then. Steps
  themselves never write outside gnode.
- **Delivery is idempotent:** unchanged files are not rewritten, so Godot doesn't re-import them.

Or from the game's own build script:

```python
import gnode
from level_art import build

for level in Path("../levels").glob("*.toml"):
    run = gnode.run(build(str(level)), live=True, max_usd=5)
    run.deliver(
        {
            "plate": f"../godot/art/{level.stem}/ground.png",
            "icons": f"../godot/art/{level.stem}/icons/{{key}}.png",
        }
    )
```

## CI, with no spend

```bash
gnode plan level_art.py:build --arg level=../levels/docks.toml --check --expect-cached
```

- **`--check`** fails on any error: a missing tool, an unknown node type, a failed assertion, a
  missing take.
- **`--expect-cached`** fails if anything would be generated. That catches "someone changed a
  level but didn't build its art". It needs the team cache (`cache:` in `gnode.yaml` pointing at
  shared storage), or it is skipped.

## What this example tests

- **A foreign authored format** through a Python builder, with no TOML rewrite. The builder emits
  the same graph a workflow file would.
- **Workflows used as steps,** shared with their standalone runs (the same cache entries).
- **Takes committed with the game,** so every teammate gets the same chosen pictures.
- **Delivery** across the consumer boundary.
- **Offline CI.**
