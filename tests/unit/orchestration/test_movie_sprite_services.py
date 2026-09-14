from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path

import httpx
import pytest
from PIL import Image

from gnode import NonRetryableError, RetryPolicy
from stage_gen.components.character_3d.budget_pool import BudgetPool
from stage_gen.config import StageGenConfig
from stage_gen.orchestration.movie_sprite_services import (
    MovieSpriteVideoService,
    movie_sprite_video_binding,
)

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


def _endpoint() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (16, 16), (10, 240, 20)).save(output, "PNG")
    return output.getvalue()


@pytest.mark.parametrize(
    "options",
    [
        {"duration_seconds": 2},
        {"duration_seconds": 11},
        {"duration_seconds": 4.5},
        {"duration_seconds": True},
        {"resolution": "8k"},
        {"aspect_ratio": "1:1"},
    ],
)
def test_route_rejects_unsupported_options_offline(options: dict) -> None:
    with pytest.raises(ValueError):
        movie_sprite_video_binding(**options)


def test_explicit_live_opt_in_precedes_provider_construction(tmp_path: Path) -> None:
    budget = BudgetPool(tmp_path / "budget", "fixture", "10")
    with pytest.raises(ValueError, match="live opt-in"):
        MovieSpriteVideoService(StageGenConfig(fal_key="secret"), budget, live=False)
    assert budget.snapshot()["reservations"] == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 422, 500])
async def test_budget_counts_actual_dispatches_retains_unknown_and_refuses_replay(
    tmp_path: Path,
    status: int,
) -> None:
    posts = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posts.append(json.loads(request.content))
            return httpx.Response(
                status,
                headers={"x-request-id": "safe-id"},
                json={
                    "video": {"url": "https://cdn.test/clip.mp4", "content_type": "video/mp4"},
                },
            )
        return httpx.Response(200, content=MP4, headers={"content-type": "video/mp4"})

    budget = BudgetPool(tmp_path / "budget", "fixture", "10")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = MovieSpriteVideoService(
            StageGenConfig(fal_key="secret"),
            budget,
            live=True,
            client=client,
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        )

        async def generate() -> object:
            return await service.generate(
                "A gentle idle.",
                _endpoint(),
                duration_seconds=8,
                resolution="360p",
                aspect_ratio="9:16",
                artifact_path=tmp_path / "clip.mp4",
            )

        if status == 200:
            await generate()
            assert posts[0]["image_url"] == posts[0]["end_image_url"]
            assert "image_urls" not in posts[0]
        else:
            from gnode import RetryExhaustedError

            with pytest.raises(NonRetryableError if status == 422 else RetryExhaustedError):
                await generate()
            assert not (tmp_path / "clip.mp4").exists()
        expected = 6 if status == 500 else 1
        assert len(posts) == service.provider_operations == expected
        assert service.known_cost_usd is None
        snapshot = budget.snapshot()
        assert float(snapshot["unresolved_liability_usd"]) == pytest.approx(expected * 0.30)
        with pytest.raises(NonRetryableError, match="already dispatched"):
            await generate()
        assert len(posts) == expected


@pytest.mark.asyncio
async def test_reported_cost_settles_and_ambiguous_transport_stops(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "usage": {"cost": "0.12"},
                    "video": {"url": "https://cdn.test/clip.mp4", "content_type": "video/mp4"},
                },
            )
        return httpx.Response(200, content=MP4, headers={"content-type": "video/mp4"})

    budget = BudgetPool(tmp_path / "budget", "fixture", "10")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = MovieSpriteVideoService(
            StageGenConfig(fal_key="secret"), budget, live=True, client=client
        )
        await service.generate(
            "Idle",
            _endpoint(),
            duration_seconds=8,
            resolution="360p",
            aspect_ratio="9:16",
            artifact_path=tmp_path / "clip.mp4",
        )
    assert calls == 2
    assert service.known_cost_usd == 0.12
    assert budget.snapshot()["unresolved_liability_usd"] == "0"

    calls = 0

    def interrupted(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("secret private request", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(interrupted)) as client:
        service = MovieSpriteVideoService(
            StageGenConfig(fal_key="secret"),
            budget,
            live=True,
            client=client,
            operation_id="second-candidate",
        )
        with pytest.raises(NonRetryableError, match="without a confirmed result"):
            await service.generate(
                "Idle",
                _endpoint(),
                duration_seconds=8,
                resolution="360p",
                aspect_ratio="9:16",
                artifact_path=tmp_path / "uncertain.mp4",
            )
    assert calls == service.provider_operations == 1
    assert budget.snapshot()["unresolved_liability_usd"] == "0.3"


@pytest.mark.asyncio
async def test_two_hosts_cannot_dispatch_the_same_candidate_concurrently(tmp_path: Path) -> None:
    started, finish = asyncio.Event(), asyncio.Event()
    posts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal posts
        if request.method == "POST":
            posts += 1
            started.set()
            await finish.wait()
            return httpx.Response(200, json={"video": {"url": "https://cdn.test/clip.mp4"}})
        return httpx.Response(200, content=MP4, headers={"content-type": "video/mp4"})

    budget = BudgetPool(tmp_path / "budget", "fixture", "10")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first, second = (
            MovieSpriteVideoService(
                StageGenConfig(fal_key="secret"), budget, live=True, client=client
            )
            for _ in range(2)
        )

        async def generate(service: MovieSpriteVideoService) -> object:
            return await service.generate(
                "Idle",
                _endpoint(),
                duration_seconds=8,
                resolution="360p",
                aspect_ratio="9:16",
                artifact_path=tmp_path / "clip.mp4",
            )

        pending = asyncio.create_task(generate(first))
        await started.wait()
        try:
            with pytest.raises(NonRetryableError, match="already running"):
                await generate(second)
            assert second.provider_operations == 0
        finally:
            finish.set()
            await pending
    assert posts == first.provider_operations == 1
