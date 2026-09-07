"""The fal video route: one request, an allowlisted container, an unsigned download."""

from __future__ import annotations

import json

import httpx
import pytest

from gnode import VideoGenerationRequest, VideoReference
from gnode.providers.fal import FalVideoBackend

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64
PLATE = "data:image/png;base64,aGVsbG8="


def _request(**overrides: object) -> VideoGenerationRequest:
    fields: dict[str, object] = {
        "prompt": "the robot walks",
        "artifact_path": "clip.mp4",
        "references": (VideoReference(url=PLATE, provenance_ref="p.png"),),
        "duration_seconds": 10.0,
        "resolution": "720p",
        "aspect_ratio": "16:9",
    }
    fields.update(overrides)
    return VideoGenerationRequest(**fields)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_one_post_then_an_unauthenticated_download() -> None:
    posted: list[dict[str, object]] = []
    download_authorization: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posted.append(json.loads(request.content))
            assert request.headers["authorization"] == "Key fal-secret"
            return httpx.Response(
                200,
                json={
                    "video": {
                        "url": "https://cdn.fal.test/out.mp4",
                        "content_type": "video/mp4",
                    }
                },
            )
        download_authorization.append(request.headers.get("authorization"))
        return httpx.Response(200, content=MP4, headers={"content-type": "video/mp4"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = FalVideoBackend(api_key="fal-secret", base_url="https://fal.test", client=client)
        generated = await backend.generate_once(_request())

    assert generated.data == MP4
    assert generated.media_type == "video/mp4"
    assert generated.source_shape == "hosted-download"
    # The provider's own key is never handed to whatever host serves the result.
    assert download_authorization == [None]
    assert posted[0]["image_urls"] == [PLATE]
    assert posted[0]["duration"] == 10
    assert posted[0]["resolution"] == "720p"
    assert posted[0]["aspect_ratio"] == "16:9"


@pytest.mark.asyncio
async def test_a_container_the_host_cannot_open_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"video": {"url": "https://cdn.fal.test/out.webm", "content_type": "video/webm"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = FalVideoBackend(api_key="secret", client=client)
        with pytest.raises(ValueError, match="must be MP4"):
            await backend.generate_once(_request())


@pytest.mark.asyncio
async def test_a_route_that_refuses_the_ask_surfaces_its_status() -> None:
    """fal answers an over-long duration with 422 before it renders anything.

    The plan-time limit is what stops this being reached; the status is the
    backstop for a route whose ceiling moved since it was last verified.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": [{"ctx": {"le": 10}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = FalVideoBackend(api_key="secret", client=client)
        with pytest.raises(ValueError, match="HTTP 422"):
            await backend.generate_once(_request(duration_seconds=18.0))


@pytest.mark.asyncio
async def test_a_clip_needs_something_to_be_drawn_from() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))) as c:
        backend = FalVideoBackend(api_key="secret", client=c)
        with pytest.raises(ValueError, match="at least one reference"):
            await backend.generate_once(_request(references=()))


def test_the_key_is_registered_for_redaction() -> None:
    backend = FalVideoBackend(api_key="fal-secret")
    assert backend.secrets == ("fal-secret",)
    with pytest.raises(ValueError, match="api_key must be non-empty"):
        FalVideoBackend(api_key="  ")


@pytest.mark.asyncio
async def test_a_duration_the_route_cannot_express_is_refused_not_rounded() -> None:
    """Truncating would send an ask nobody made, and the answer would fail the gate.

    This is the six-attempt bug, pinned: `int(4.5)` sent 4, the route answered four
    seconds correctly, and the caller measured that against the 4.5 it had asked for.
    """

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))) as c:
        backend = FalVideoBackend(api_key="secret", client=c)
        with pytest.raises(ValueError, match="whole seconds"):
            await backend.generate_once(_request(duration_seconds=4.5))
