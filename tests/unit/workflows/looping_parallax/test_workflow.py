"""Looping parallax through gnode, offline: placement reruns only the compose step."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from PIL import Image

from gnode import RunResult, project_run, run_async, verify_run
from stage_gen.media.codec import encode_png


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("_STAGE_GEN_DISABLE_DOTENV", "1")


def _source() -> bytes:
    image = Image.new("RGBA", (8, 4), "#182d47")
    for x in range(4):
        for y in range(4):
            image.putpixel((x, y), (80, 120, 160, 255))
    return encode_png(image)


def _inputs(tmp_path: Path, name: str, **layer: Any) -> Path:
    (tmp_path / "clouds.png").write_bytes(_source())
    document = {
        "canvas": {"width": 32, "height": 8},
        "layers": [{"layer_id": "clouds", "file": "clouds.png", "repeat_y": True, **layer}],
    }
    path = tmp_path / name
    path.write_text(yaml.safe_dump(document))
    return path


async def _run(tmp_path: Path, inputs: Path) -> RunResult:
    return await run_async("looping-parallax", input_files=[inputs], cwd=tmp_path)


async def test_moving_a_layer_reuses_its_repeat_and_recomposes(tmp_path: Path) -> None:
    (tmp_path / "gnode.yaml").write_text("gnode: project/v1\n")
    first = await _run(tmp_path, _inputs(tmp_path, "first.yaml"))
    moved = await _run(tmp_path, _inputs(tmp_path, "moved.yaml", offset_x=3.0))

    assert first.ok and moved.ok
    caches = {node.node_id: node.cache for node in project_run(moved.run_dir).nodes}
    assert caches["layer['clouds'].mirror#1"] == "hit"
    assert caches["compose#1"] == "miss"
    manifest = json.loads(moved.outputs["manifest"].path.read_bytes())
    (layer,) = manifest["layers"]
    assert (layer["asset_ref"], layer["offset_x"], layer["construction"]) == (
        "parallax/layers/clouds.png",
        3.0,
        "mirror_repeat",
    )
    assert (layer["width"], layer["height"]) == (16, 8)
    assert verify_run(moved.run_dir) == []
