"""The free standard node types, run through the engine on pictures drawn here."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from gnode import WorkflowRun, make_plan
from tests.unit.gnode.workflow._project import FakeProvider, planner, project


def _png(size: tuple[int, int], color: tuple[int, int, int, int]) -> bytes:
    picture = Image.new("RGBA", size, color)
    picture.putpixel((0, 0), (255, 0, 0, 255))
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG")
    return buffer.getvalue()


def _image(path: str | None) -> Image.Image:
    assert path is not None
    with Image.open(path) as picture:
        picture.load()
        return picture.copy()


async def test_mirror_resize_crop_and_alpha_run_as_written(tmp_path: Path) -> None:
    path = project(
        tmp_path,
        """
        gnode: workflow/v1
        id: flow
        title: Flow
        inputs:
          layer: { type: file, kind: image }
        steps:
          mirror:
            uses: gnode/image.mirror_repeat@1
            with: { image: "${{ inputs.layer }}", axis: x }
          small:
            uses: gnode/image.resize@1
            with: { image: "${{ steps.mirror.outputs.image }}", longest_side: 40 }
          corner:
            uses: gnode/image.crop@1
            with: { image: "${{ inputs.layer }}", box: [0, 0, 0.5, 0.5] }
          alpha:
            uses: gnode/image.check_alpha@1
            judges: mirror
            with: { image: "${{ steps.mirror.outputs.image }}", expect: transparent }
            on_reject: continue
        outputs:
          mirror: ${{ steps.mirror.outputs.image }}
          small: ${{ steps.small.outputs.image }}
          corner: ${{ steps.corner.outputs.image }}
        """,
        **{"layer.png": _png((20, 10), (0, 0, 255, 0))},
    )
    built = planner(path, layer="layer.png")
    outcome = await WorkflowRun(
        await make_plan(built),
        run_dir=tmp_path / "runs/a",
        services=FakeProvider(built.store).services(),
    ).run()

    assert outcome.ok, [outcome.results[i].error for i in outcome.failed]
    mirror = _image(outcome.outputs["mirror"].location)
    assert mirror.size == (40, 10)
    assert mirror.getpixel((39, 0)) == (255, 0, 0, 255), "the right half is the reflection"
    assert _image(outcome.outputs["small"].location).size == (40, 10)
    assert _image(outcome.outputs["corner"].location).size == (10, 5)
    assert outcome.results["alpha#1"].verdict == "accept"
