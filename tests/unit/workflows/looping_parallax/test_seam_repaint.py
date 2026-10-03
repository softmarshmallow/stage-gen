"""Seam-repainted layers: admitted first, repainted through the wrap, else reflected.

The paid edit goes through Stage Gen's real image handler and routed service; only the
provider client under them is fake, so no call leaves the machine.
"""

from __future__ import annotations

import base64
import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from PIL import Image

from gnode import (
    HostServices,
    ImageGenerationRequest,
    ImageGenerationResult,
    Plan,
    ProviderResponseMetadata,
    RouteContractV1,
    RunOutcome,
    WorkflowRun,
    plan_async,
)
from stage_gen.config import StageGenConfig
from stage_gen.media.codec import decode_rgba, encode_png
from stage_gen.orchestration.gnode_plugin import image_capabilities
from stage_gen.orchestration.image_routing import RoutedImageGenerationService

WIDTH, HEIGHT = 2048, 512
Painter = Callable[[Image.Image, Image.Image], Image.Image]


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("_STAGE_GEN_DISABLE_DOTENV", "1")


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


def _decode(url: str) -> Image.Image:
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
        assert isinstance(a, tuple) and isinstance(b, tuple)
        for x in range(left + 1, right):
            t = (x - left) / (right - left)
            target[x, y] = tuple(round(p + (q - p) * t) for p, q in zip(a, b, strict=True))
    return painted


class FakeClient:
    """The provider client under the routed service: answers each edit offline."""

    def __init__(self, route: RouteContractV1, paint: Painter | None, sent: list[Any]) -> None:
        self.provider = route.model.provider
        self.model = route.model.model
        self.adapter_id = route.adapter_id
        self.adapter_behavior_version = route.adapter_behavior_version
        self.paint = paint
        self.sent = sent

    def endpoint_for(self, request: ImageGenerationRequest) -> str:
        assert request.resolved_binding is not None
        return request.resolved_binding.route.endpoint

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        self.sent.append(request)
        conditioning = _decode(request.input_references[0].url)
        assert request.mask_reference is not None
        mask = _decode(request.mask_reference.url)
        returned = conditioning if self.paint is None else self.paint(conditioning, mask)
        return ImageGenerationResult(
            data=encode_png(returned),
            media_type="image/png",
            provider=self.provider,
            model=self.model,
            attempts=1,
            provenance_path="",
            response_metadata=ProviderResponseMetadata(usage={"cost": 0.2}),
        )

    async def aclose(self) -> None:
        return None


def _config() -> StageGenConfig:
    # Placeholders: the routed service admits a call only when its provider has a key.
    return StageGenConfig.model_validate(
        {"openai_api_key": "test-openai", "fal_key": "test-fal", "open_router_api_key": "test"}
    )


def _project(tmp_path: Path, source: bytes, **layer: Any) -> Path:
    (tmp_path / "gnode.yaml").write_text("gnode: project/v1\nruns: runs\ncache: cache\n")
    (tmp_path / "band.png").write_bytes(source)
    inputs = {
        "canvas": {"width": 640, "height": 360},
        "layers": [
            {
                "layer_id": "band",
                "file": "band.png",
                "parallax": 0.5,
                "loop_construction": "seam_repaint",
                **layer,
            }
        ],
    }
    path = tmp_path / "inputs.yaml"
    path.write_text(yaml.safe_dump(inputs))
    return path


async def _plan(tmp_path: Path, source: bytes, **layer: Any) -> Plan:
    inputs = _project(tmp_path, source, **layer)
    return await plan_async("looping-parallax", input_files=[inputs], cwd=tmp_path)


async def _run(planned: Plan, run_dir: Path, paint: Painter | None) -> tuple[RunOutcome, list[Any]]:
    sent: list[Any] = []
    store = planned.planner.store

    def factory(config: StageGenConfig) -> RoutedImageGenerationService:
        return RoutedImageGenerationService(
            config, service_factory=lambda route, _: FakeClient(route, paint, sent)
        )

    services = HostServices(
        store=store,
        capabilities=image_capabilities(_config(), store, factory=factory),
        live=True,
    )
    outcome = await WorkflowRun(planned, run_dir=run_dir, services=services).run()
    return outcome, sent


def _bytes(planned: Plan, file: Any) -> bytes:
    return planned.planner.store.file_path(file.digest).read_bytes()


def _layer(planned: Plan, outcome: RunOutcome) -> dict[str, Any]:
    manifest = json.loads(_bytes(planned, outcome.outputs["manifest"]))
    assert manifest["kind"] == "parallax-background-v2"
    layer: dict[str, Any] = manifest["layers"][0]
    return layer


async def test_a_repaint_through_the_wrap_keeps_the_drawn_period_and_is_reused(
    tmp_path: Path,
) -> None:
    planned = await _plan(tmp_path, _band(period=700))
    assert planned.ok, planned.problems
    outcome, sent = await _run(planned, tmp_path / "runs/first", _paint_through)

    assert outcome.ok, outcome.failed
    assert len(sent) == 1
    assert sent[0].size == f"1536x{HEIGHT}"
    assert "hard cut" in sent[0].prompt
    assert outcome.results["layer['band'].seam_ok#1"].verdict == "accept"
    layer = _layer(planned, outcome)
    assert (layer["construction"], layer["width"], layer["height"]) == (
        "seam_repaint",
        WIDTH,
        HEIGHT,
    )

    again, sent_again = await _run(
        await _plan(tmp_path, _band(period=700)), tmp_path / "runs/again", _paint_through
    )
    assert again.ok
    assert sent_again == []


async def test_a_repaint_that_leaves_the_cut_is_redrawn_once_then_reflected(
    tmp_path: Path,
) -> None:
    planned = await _plan(tmp_path, _band(period=700))
    outcome, sent = await _run(planned, tmp_path / "run", None)

    assert outcome.ok, outcome.failed
    assert len(sent) == 2
    assert outcome.results["layer['band'].seam_ok#1"].verdict == "reject"
    assert outcome.results["layer['band'].seam_ok#2"].verdict == "reject"
    layer = _layer(planned, outcome)
    assert (layer["construction"], layer["width"]) == ("mirror_repeat", WIDTH * 2)


async def test_a_layer_that_already_loops_is_published_untouched_without_a_call(
    tmp_path: Path,
) -> None:
    source = _band(period=1024)
    planned = await _plan(tmp_path, source)
    outcome, sent = await _run(planned, tmp_path / "run", _paint_through)

    assert outcome.ok, outcome.failed
    assert sent == []
    assert _bytes(planned, outcome.outputs["layers"].items[0][1]) == source
    assert _layer(planned, outcome)["construction"] == "admitted"


async def test_the_brief_is_identity_and_placement_is_not(tmp_path: Path) -> None:
    source = _band(period=700)

    def repaint(planned: Plan) -> str | None:
        found = next(i for i in planned.instances if i.id == "layer['band'].repaint#1")
        return found.identity

    base = repaint(await _plan(tmp_path, source))
    described = repaint(await _plan(tmp_path, source, description="Low green hills."))
    moved = repaint(await _plan(tmp_path, source, offset_y=12.0))
    assert base is not None
    assert described != base
    assert moved == base


async def test_seam_repaint_is_refused_where_it_cannot_run(tmp_path: Path) -> None:
    upright = await _plan(tmp_path, _band(period=700), repeat_y=True)
    assert any("repeats on x only" in problem.message for problem in upright.problems)
    narrow = encode_png(Image.new("RGBA", (1024, HEIGHT), (10, 20, 30, 255)))
    refused = await _plan(tmp_path, narrow)
    assert any("1536 px seam window" in problem.message for problem in refused.problems)
