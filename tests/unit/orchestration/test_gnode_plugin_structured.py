"""Stage Gen's ``structured.generate``: each route's request settings, and how it shows pictures."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from gnode import (
    BinaryArtifact,
    CallRefused,
    ProviderResponseMetadata,
    Route,
    Store,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from stage_gen.config import load_config
from stage_gen.orchestration.gnode_plugin import _opaque, structured_job, structured_routes

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"status": {"type": "string"}},
    "required": ["status"],
}


class FakeService:
    """Answers once and remembers how it was built and what it was asked."""

    def __init__(self, **built: Any) -> None:
        self.built = built
        self.asked: list[StructuredGenerationRequest[Any]] = []

    async def generate(self, request: StructuredGenerationRequest[Any]) -> Any:
        self.asked.append(request)
        return StructuredGenerationResult(
            value=request.parse({"status": "located"}),
            raw_text="{}",
            provider="openrouter",
            model=str(self.built["model"]),
            attempts=1,
            provenance_path="",
            response_metadata=ProviderResponseMetadata(usage={"cost": 0.07}),
        )

    async def aclose(self) -> None:
        return None


def _picture(size: tuple[int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", size, (200, 40, 40, 128)).save(buffer, format="PNG")
    return buffer.getvalue()


def _routes() -> dict[str, Route]:
    return {route.model: route for route in structured_routes(load_config())}


async def _ask(tmp_path: Path, route: Route) -> tuple[FakeService, bytes]:
    store = Store(tmp_path / "cache")
    picture = _picture((2400, 3000))
    request = {
        "prompt": "Where is the face?",
        "schema": store.put_bytes(json.dumps(SCHEMA).encode(), kind="json", name="s.json"),
        "context": [store.put_bytes(picture, kind="image/png", name="face.png")],
        "matte": "#ffffff",
    }
    services: list[FakeService] = []

    def factory(**built: Any) -> FakeService:
        services.append(FakeService(**built))
        return services[-1]

    config = load_config().model_copy(update={"open_router_api_key": "test-key"})
    handler = structured_job(config, store, factory=factory)
    record = await handler(route, request, 1)
    assert record.data["json"] == {"status": "located"} and record.cost_usd == 0.07
    return services[0], picture


def test_the_vision_judge_route_carries_its_request_settings() -> None:
    routes = _routes()
    astra = routes["openai/gpt-6-astra"].contract
    assert astra["request_policy"] == {
        "provider": {"require_parameters": True, "only": ["openai"], "allow_fallbacks": False},
        "reasoning": {"effort": "high"},
        "image_detail": "high",
    }
    assert astra["pictures"] == "unchanged"
    assert routes[load_config().text_model].contract == {
        "adapter": "openrouter-structured",
        "adapter_behavior": 1,
    }


async def test_the_vision_judge_is_shown_each_picture_exactly(tmp_path: Path) -> None:
    service, picture = await _ask(tmp_path, _routes()["openai/gpt-6-astra"])
    policy = service.built["request_policy"]
    assert (policy.reasoning_effort, policy.image_detail) == ("high", "high")
    [reference] = service.asked[0].references
    assert base64.b64decode(reference.url.split(",", 1)[1]) == picture


async def test_the_text_model_is_shown_a_reduced_flattened_picture(tmp_path: Path) -> None:
    service, _ = await _ask(tmp_path, _routes()[load_config().text_model])
    assert service.built["request_policy"] is None
    [reference] = service.asked[0].references
    with Image.open(io.BytesIO(base64.b64decode(reference.url.split(",", 1)[1]))) as sent:
        assert (sent.size, sent.mode) == ((1280, 1600), "RGB")


async def test_a_route_stage_gen_does_not_call_is_refused(tmp_path: Path) -> None:
    other = Route(
        capability="structured.generate",
        model="someone/else",
        provider="openrouter",
        price=_routes()["openai/gpt-6-astra"].price,
    )
    with pytest.raises(CallRefused, match="not a structured route"):
        await _ask(tmp_path, other)


def test_an_opaque_picture_with_transparency_is_drawn_again() -> None:
    opaque = io.BytesIO()
    Image.new("RGB", (4, 4), (1, 2, 3)).save(opaque, format="PNG")
    assert _opaque(BinaryArtifact(opaque.getvalue(), "image/png")) == {"opaque": True}
    with pytest.raises(ValueError, match="transparent"):
        _opaque(BinaryArtifact(_picture((4, 4)), "image/png"))
