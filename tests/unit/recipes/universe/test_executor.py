"""Universe live composition uses the graph-bound image router."""

from __future__ import annotations

from pathlib import Path

import pytest

from stage_gen.config import StageGenConfig
from stage_gen.recipes.universe.universe_executor import UniverseExecutor
from tests.unit.recipes.universe._universe_fixture import materialize_semantic_run

FIXTURE = Path("library/games/lantern_ferry")
ADMITTED = Path("tests/contract/fixtures/universe/lantern_ferry.admitted-universe.json")


@pytest.mark.asyncio
async def test_live_gallery_composes_the_binding_driven_image_router(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_service_sentinel = object()
    structured_service_sentinel = object()
    calls: list[str] = []

    class FakeServices:
        async def __aenter__(self) -> FakeServices:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        def image(self) -> object:
            calls.append("image")
            return image_service_sentinel

        def structured(self) -> object:
            return structured_service_sentinel

        def adopt(self, _service: object) -> object:
            raise AssertionError("Universe must not compose a provider-specific image service")

    class FakeHandler:
        def __init__(
            self,
            *_args: object,
            image_service: object,
            structured_service: object,
            **_kwargs: object,
        ) -> None:
            assert image_service is image_service_sentinel
            assert structured_service is structured_service_sentinel

    executor = UniverseExecutor(StageGenConfig(open_router_api_key="openrouter"))
    semantic_run = materialize_semantic_run(
        tmp_path / "semantic",
        admitted=ADMITTED,
        poster=FIXTURE / "references/poster.png",
    )
    monkeypatch.setattr(executor, "services", lambda: FakeServices())
    monkeypatch.setattr(
        "stage_gen.recipes.universe.universe_executor.UniverseNodeHandler",
        FakeHandler,
    )

    async def fake_dispatch(*_args: object, **_kwargs: object) -> object:
        return object()

    def fake_close(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {}

    monkeypatch.setattr(executor, "dispatch", fake_dispatch)
    monkeypatch.setattr(executor, "_close_gallery", fake_close)

    await executor.run_gallery(
        FIXTURE,
        semantic_run=semantic_run,
        run_dir=tmp_path / "gallery",
        cache_dir=tmp_path / "cache",
        invocation_id="routed-image-test",
    )

    assert calls == ["image"]
