from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest

from gnode import (
    BackgroundRemovalRequest,
    BackgroundRemovalService,
    RetryPolicy,
)
from stage_gen.identity import BACKGROUND_REMOVAL_COMPONENT, STAGE_GEN_TOOL
from stage_gen.providers.fal import FalBackgroundRemovalBackend

from .._helpers import png_bytes


@pytest.mark.asyncio
async def test_fal_retries_and_downloads_image_and_mask_without_key(tmp_path: Path) -> None:
    provider_calls = 0
    download_authorization: list[str | None] = []
    image = png_bytes()
    mask = png_bytes(color=(255, 255, 255, 255))

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal provider_calls
        if request.url.host == "fal.test":
            provider_calls += 1
            if provider_calls == 1:
                return httpx.Response(503)
            body = json.loads(request.content)
            assert body["sync_mode"] is True
            return httpx.Response(
                200,
                json={
                    "data": {
                        "image": {
                            "url": "https://assets.test/out.png",
                            "content_type": "image/png",
                            "width": 2,
                            "height": 2,
                        },
                        "mask_image": {
                            "url": "https://assets.test/mask.png",
                            "content_type": "image/png",
                        },
                    }
                },
                headers={"x-request-id": "fal-1"},
            )
        download_authorization.append(request.headers.get("authorization"))
        return httpx.Response(
            200,
            content=mask if request.url.path.endswith("mask.png") else image,
            headers={"content-type": "image/png"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await BackgroundRemovalService(
            FalBackgroundRemovalBackend(
                api_key="fal-secret", base_url="https://fal.test", client=client
            ),
            component=BACKGROUND_REMOVAL_COMPONENT,
            tool=STAGE_GEN_TOOL,
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ).remove(
            BackgroundRemovalRequest(
                image_url="https://input.test/source.png?signature=private",
                artifact_path=tmp_path / "subject.png",
                output_mask=True,
                validate=lambda artifact, returned_mask: {
                    "mask_seen": returned_mask is not None,
                    "bytes": len(artifact.data),
                },
            )
        )
    assert provider_calls == result.attempts == 2
    assert download_authorization == [None, None]
    assert result.mask is not None
    sidecar_text = (tmp_path / "subject.png.meta.json").read_text()
    sidecar = json.loads(sidecar_text)
    assert sidecar["validation"]["mask_seen"] is True
    assert "signature=private" not in sidecar_text
    assert "fal-secret" not in sidecar_text


@pytest.mark.asyncio
async def test_fal_rejects_media_outside_png_webp_gif_allowlist() -> None:
    encoded = base64.b64encode(b"\xff\xd8\xffjpeg").decode()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "image": {
                    "url": f"data:image/jpeg;base64,{encoded}",
                    "content_type": "image/jpeg",
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = FalBackgroundRemovalBackend(api_key="secret", client=client)
        with pytest.raises(ValueError, match="PNG, WebP, or GIF"):
            await backend.remove_once(
                BackgroundRemovalRequest(
                    image_url="https://input.test/source.png",
                    artifact_path="unused.png",
                )
            )
