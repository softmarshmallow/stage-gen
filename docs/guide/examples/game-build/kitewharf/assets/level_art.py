"""The game's level TOML into a gnode workflow: the game's reader, unchanged, makes the steps."""

from pathlib import Path

from kitewharf_levels import read_level  # the game's reader (installed with the game)

from gnode import Workflow


def build(level: str) -> Workflow:
    spec = read_level(Path(level))
    wf = Workflow("kitewharf-level-art", title=f"Level art: {spec.name}")

    plate = wf.step(
        "plate",
        uses="./nodes/plate.py#ground_plate",
        with_={
            "material": spec.ground["material"],
            "span_m": spec.ground["span_m"],
            "light": spec.light,
        },
        view=True,
    )
    icons = wf.step(
        "icon",
        for_each=[{"id": p["id"], "name": p["look"]} for p in spec.pickups],
        key="${{ item.id }}",
        uses="./workflows/icon.yaml",
        with_={"name": "${{ item.name }}"},
    )
    sky = wf.step(
        "sky",
        uses="./workflows/looping-parallax.yaml",
        with_={"canvas": spec.sky["canvas"], "layers": spec.sky["layers"]},
    )
    wf.outputs(plate=plate.outputs.image, icons=icons.all.outputs.icon, sky=sky.outputs.layers)
    return wf
