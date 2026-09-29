"""Seam-repainted supplied layers: admitted first, repainted through the wrap, else reflected."""

from __future__ import annotations

import asyncio
import base64
import json
import math
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from gnode import (
    BinaryArtifact,
    CacheDisposition,
    ImageGenerationRequest,
    ImageGenerationResult,
    ProvenanceInput,
    ProviderResponseMetadata,
    SoftwareIdentity,
    write_artifact_with_provenance,
)
from stage_gen.components.sideview_layers.parallax import ParallaxLayer, ParallaxSpec
from stage_gen.config import StageGenConfig
from stage_gen.media.codec import decode_rgba, encode_png
from stage_gen.pipeline import PipelinePlan, plan, run
from stage_gen.recipes.looping_parallax import create_pipeline

WIDTH, HEIGHT = 2048, 512


def _band(period: float) -> bytes:
    """An opaque band that varies smoothly across x; it loops only when ``period`` divides it."""

    image = Image.new("RGBA", (WIDTH, HEIGHT))
    pixels = image.load()
    assert pixels is not None
    for x in range(WIDTH):
        green = round(60 + 40 * math.sin(2 * math.pi * x / period))
        for y in range(HEIGHT):
            pixels[x, y] = (y // 2, green, 128, 255)
    return encode_png(image)


def _decode_reference(url: str) -> Image.Image:
    return decode_rgba(base64.b64decode(url.split(",", 1)[1]))


def _paint_through(conditioning: Image.Image, mask: Image.Image) -> Image.Image:
    """Carry each row straight across the masked span, as a provider that did its job would.

    The mask follows the edit endpoint's convention: transparent is editable.
    """

    editable = [x for x in range(mask.width) if mask.getpixel((x, 0))[3] == 0]  # type: ignore[index]
    left, right = editable[0] - 1, editable[-1] + 1
    painted = conditioning.copy()
    source = conditioning.load()
    target = painted.load()
    assert source is not None and target is not None
    for y in range(conditioning.height):
        a, b = source[left, y], source[right, y]
        for x in range(left + 1, right):
            t = (x - left) / (right - left)
            target[x, y] = tuple(round(p + (q - p) * t) for p, q in zip(a, b, strict=True))
    return painted


class FakeImages:
    """Answer an edit by carrying the art through the span, or by returning the canvas as sent."""

    def __init__(self, paint: Callable[[Image.Image, Image.Image], Image.Image] | None) -> None:
        self.paint = paint
        self.requests: list[ImageGenerationRequest] = []

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        self.requests.append(request)
        conditioning = _decode_reference(request.input_references[0].url)
        assert request.mask_reference is not None
        mask = _decode_reference(request.mask_reference.url)
        returned = conditioning if self.paint is None else self.paint(conditioning, mask)
        data = encode_png(returned)
        path = Path(request.artifact_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        provenance = await asyncio.to_thread(
            write_artifact_with_provenance,
            path,
            BinaryArtifact(data=data, media_type="image/png"),
            ProvenanceInput(
                component=SoftwareIdentity(name="@stage-gen/core", version="0.0.0"),
                tool=SoftwareIdentity(name="stage-gen", version="0.0.0"),
                schema_version=2,
                provider="fake",
                model="fake-image",
                prompt=request.prompt,
                attempts=1,
            ),
        )
        return ImageGenerationResult(
            data=data,
            media_type="image/png",
            provider="fake",
            model="fake-image",
            attempts=1,
            provenance_path=str(provenance),
            response_metadata=ProviderResponseMetadata(),
        )

    async def aclose(self) -> None:
        return None


def _spec(**layer: object) -> ParallaxSpec:
    return ParallaxSpec(
        width=640,
        height=360,
        layers=[
            ParallaxLayer(
                layer_id="band",
                source="band.png",
                parallax=0.5,
                loop_construction="seam_repaint",
                **layer,  # type: ignore[arg-type]
            )
        ],
    )


def _plan(tmp_path: Path, source: bytes, spec: ParallaxSpec | None = None) -> PipelinePlan:
    inputs = tmp_path / "inputs"
    inputs.mkdir(exist_ok=True)
    (inputs / "band.png").write_bytes(source)
    return plan(create_pipeline(spec or _spec(), config=StageGenConfig()), input_root=inputs)


def _run(planned: PipelinePlan, root: Path, name: str, images: FakeImages):  # type: ignore[no-untyped-def]
    return asyncio.run(
        run(
            planned,
            output_root=root / name,
            cache_root=root / "cache",
            services={"image": images},
            allow_provider_calls=True,
        )
    )


def _manifest_layer(run_dir: Path) -> dict[str, object]:
    manifest = json.loads((run_dir / "parallax/manifest.json").read_bytes())
    assert manifest["kind"] == "parallax-background-v2"
    assert "construction" not in manifest
    return manifest["layers"][0]


def test_a_repaint_the_wrap_admits_keeps_the_drawn_period_and_is_reused(tmp_path: Path) -> None:
    planned = _plan(tmp_path, _band(period=700))
    node = planned.graph.node("layer.band")
    assert not node.is_local
    assert node.card is not None and "hard cut" in (node.card.prompt or "")
    images = FakeImages(_paint_through)
    first = _run(planned, tmp_path, "first", images)
    assert first.summary.ok
    assert len(images.requests) == 1
    assert images.requests[0].size == f"1536x{HEIGHT}"
    report = json.loads((first.run_dir / "parallax/layers/band.loop.json").read_bytes())
    assert report["construction"] == "seam_repaint"
    assert report.get("rejected_construction") is None
    layer = _manifest_layer(first.run_dir)
    assert (layer["construction"], layer["width"], layer["height"]) == (
        "seam_repaint",
        WIDTH,
        HEIGHT,
    )
    edit_meta = json.loads((first.run_dir / "parallax/layers/band.edit.png.meta.json").read_bytes())
    assert edit_meta["provider"] == "fake"

    again = _run(planned, tmp_path, "again", images)
    assert again.summary.ok
    assert len(images.requests) == 1
    assert {item.node_id: item.cache for item in again.summary.nodes} == {
        "layer.band": CacheDisposition.HIT,
        "compose": CacheDisposition.HIT,
    }


def test_a_repaint_that_leaves_the_cut_falls_back_to_the_reflection(tmp_path: Path) -> None:
    images = FakeImages(None)
    completed = _run(_plan(tmp_path, _band(period=700)), tmp_path, "run", images)
    assert completed.summary.ok
    assert len(images.requests) == 1
    report = json.loads((completed.run_dir / "parallax/layers/band.loop.json").read_bytes())
    assert (report["construction"], report["rejected_construction"]) == (
        "mirror_repeat",
        "seam_repaint",
    )
    layer = _manifest_layer(completed.run_dir)
    assert (layer["construction"], layer["width"]) == ("mirror_repeat", WIDTH * 2)


def test_a_layer_that_already_loops_is_published_untouched_without_a_provider(
    tmp_path: Path,
) -> None:
    source = _band(period=1024)
    images = FakeImages(_paint_through)
    completed = _run(_plan(tmp_path, source), tmp_path, "run", images)
    assert completed.summary.ok
    assert images.requests == []
    assert (completed.run_dir / "parallax/layers/band.png").read_bytes() == source
    assert _manifest_layer(completed.run_dir)["construction"] == "admitted"
    node = next(item for item in completed.summary.nodes if item.node_id == "layer.band")
    assert node.provider_operations == 0


def test_the_brief_is_cache_identity_and_placement_is_not(tmp_path: Path) -> None:
    source = _band(period=700)
    base = _plan(tmp_path, source).graph
    described = _plan(tmp_path, source, _spec(description="Low green hills.")).graph
    moved = _plan(tmp_path, source, _spec(offset_y=12.0)).graph
    assert described.node("layer.band").cache_key != base.node("layer.band").cache_key
    assert moved.node("layer.band").cache_key == base.node("layer.band").cache_key


def test_a_mirrored_layer_keeps_the_identity_it_always_had() -> None:
    layer = ParallaxLayer(layer_id="hills", source="hills.png")
    assert layer.generation_identity("0" * 64) == {
        "source_sha256": "0" * 64,
        "repeat_x": True,
        "repeat_y": False,
        "construction": "mirror_repeat_v1",
    }


def test_seam_repaint_is_refused_where_it_cannot_run(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="repeats on x only"):
        ParallaxLayer(
            layer_id="band", source="band.png", loop_construction="seam_repaint", repeat_y=True
        )
    narrow = encode_png(Image.new("RGBA", (1024, HEIGHT), (10, 20, 30, 255)))
    with pytest.raises(ValueError, match="at least that width"):
        _plan(tmp_path, narrow)
