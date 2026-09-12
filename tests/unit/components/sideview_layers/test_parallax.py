"""A complete supplied-layer recipe, including independently reusable image caches."""

import asyncio
import json
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from gnode import CacheDisposition
from stage_gen.components.sideview_layers.parallax import (
    ParallaxLayer,
    ParallaxSpec,
    prepare_parallax,
    render_parallax,
)
from stage_gen.media.codec import decode_rgba, encode_png
from stage_gen.pipeline import inspect, plan, run
from stage_gen.recipes.looping_parallax import create_pipeline


def _source() -> bytes:
    image = Image.new("RGBA", (8, 4), "#182d47")
    for x in range(4):
        for y in range(4):
            image.putpixel((x, y), (80, 120, 160, 255))
    return encode_png(image)


def _spec(offset_x: float = 0.0) -> ParallaxSpec:
    return ParallaxSpec(
        width=32,
        height=8,
        layers=[
            ParallaxLayer(
                layer_id="clouds",
                source="clouds.png",
                parallax=1.0,
                offset_x=offset_x,
                repeat_y=True,
            )
        ],
    )


def test_constructed_repeat_has_exact_edges_and_periodic_playback() -> None:
    spec = _spec()
    prepared = prepare_parallax(spec, lambda _ref: _source())
    image = decode_rgba(prepared["clouds"].data)
    assert image.size == (16, 8)
    assert image.crop((0, 0, 1, 8)).tobytes() == image.crop((15, 0, 16, 8)).tobytes()
    assert render_parallax(spec, prepared) == render_parallax(spec, prepared, scroll_x=16)
    assert render_parallax(spec, prepared) != render_parallax(spec, prepared, scroll_x=4)


def test_layer_request_rejects_traversal_and_nonfinite_placement() -> None:
    with pytest.raises(ValidationError):
        ParallaxLayer(layer_id="clouds", source="../clouds.png")
    with pytest.raises(ValidationError):
        ParallaxLayer(layer_id="clouds", source="clouds.png", parallax=float("inf"))
    spec = _spec()
    spec.layers[0].parallax = 1e308
    prepared = prepare_parallax(spec, lambda _ref: _source())
    with pytest.raises(ValueError, match="finite coordinate"):
        render_parallax(spec, prepared, scroll_x=1e308)


def test_position_change_reuses_prepared_assets_and_preview_survives_reinspection(
    tmp_path: Path,
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "clouds.png").write_bytes(_source())
    first_plan = plan(create_pipeline(_spec()), input_root=inputs)
    moved_plan = plan(create_pipeline(_spec(offset_x=3.0)), input_root=inputs)
    assert (
        first_plan.graph.node("layer.clouds").cache_key
        == moved_plan.graph.node("layer.clouds").cache_key
    )
    assert first_plan.graph.node("compose").cache_key != moved_plan.graph.node("compose").cache_key
    first = asyncio.run(
        run(first_plan, output_root=tmp_path / "first", cache_root=tmp_path / "cache")
    )
    assert first.summary.ok
    moved = asyncio.run(
        run(moved_plan, output_root=tmp_path / "moved", cache_root=tmp_path / "cache")
    )
    assert moved.summary.ok
    cached = {node.node_id: node.cache for node in moved.summary.nodes}
    assert cached == {"layer.clouds": CacheDisposition.HIT, "compose": CacheDisposition.MISS}
    manifest = json.loads((moved.run_dir / "parallax/manifest.json").read_bytes())
    assert manifest["layers"][0]["asset_ref"] == "parallax/layers/clouds.png"
    refreshed = inspect(moved.run_dir)
    artifacts = [
        artifact
        for node in refreshed.model_dump(mode="json")["nodes"]
        for artifact in node["artifacts"]
    ]
    preview = next(item for item in artifacts if item["artifact_ref"] == "parallax/manifest.json")
    assert preview["preview"]["kind"] == "parallax-background-v1"
