"""What a run carries beside its plan, including the rehearsal's."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from stage_gen.config import StageGenConfig
from stage_gen.recipes.storefront.storefront_executor import StorefrontExecutor
from stage_gen.recipes.storefront.storefront_request import apply_rerolls, empty_ledger
from tests.unit.recipes.storefront._fixture import write_package


def test_a_rehearsal_writes_the_ledger_it_was_planned_against(tmp_path: Path) -> None:
    """The reroll flow starts from a prior run's ledger, so a dry run must write one.

    Without this the cheapest way to try the flow — rehearse, then reroll — has
    nothing to point at, and the alternative is writing a ledger by hand, which
    is how a redraw silently becomes a cache hit.
    """

    package = write_package(tmp_path / "package")
    run_dir = tmp_path / "run"
    executor = StorefrontExecutor(
        StageGenConfig(), draws=apply_rerolls(empty_ledger("test_world"), ("icon",))
    )
    asyncio.run(
        executor.dry_run(
            package,
            run_dir=run_dir,
            cache_dir=tmp_path / "cache",
            invocation_id="rehearsal",
        )
    )
    ledger = json.loads((run_dir / "draw-ledger.json").read_text(encoding="utf-8"))
    assert ledger["storefront_id"] == "test_world"
    assert ledger["draws"] == {"icon": 1}


def test_the_identity_document_names_the_package_and_refuses_publication(
    tmp_path: Path,
) -> None:
    package = write_package(tmp_path / "package")
    run_dir = tmp_path / "run"
    asyncio.run(
        StorefrontExecutor(StageGenConfig()).dry_run(
            package,
            run_dir=run_dir,
            cache_dir=tmp_path / "cache",
            invocation_id="rehearsal",
        )
    )
    identity = json.loads(
        (run_dir / StorefrontExecutor.IDENTITY_DOCUMENT).read_text(encoding="utf-8")
    )
    assert identity["storefront_id"] == "test_world"
    assert identity["surface_ids"] == ["icon", "banner"]
    assert identity["publication_authorized"] is False


@pytest.mark.asyncio
async def test_live_execution_composes_the_binding_driven_image_router(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = write_package(tmp_path / "package")
    opaque_service_sentinel = object()
    structured_service_sentinel = object()
    calls: list[str] = []

    class FakeServices:
        async def __aenter__(self) -> FakeServices:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        def image(self) -> object:
            calls.append("image")
            return opaque_service_sentinel

        def structured(self) -> object:
            return structured_service_sentinel

    class FakeHandler:
        def __init__(
            self,
            *_args: object,
            image_service: object,
            structured_service: object,
            **_kwargs: object,
        ) -> None:
            assert image_service is opaque_service_sentinel
            assert structured_service is structured_service_sentinel

    executor = StorefrontExecutor(
        StageGenConfig(open_router_api_key="openrouter", openai_api_key=None)
    )
    monkeypatch.setattr(executor, "services", lambda: FakeServices())
    monkeypatch.setattr(
        "stage_gen.recipes.storefront.storefront_executor.StorefrontNodeHandler",
        FakeHandler,
    )

    async def fake_dispatch(*_args: object, **_kwargs: object) -> object:
        return object()

    monkeypatch.setattr(executor, "dispatch", fake_dispatch)
    await executor.run(
        package,
        run_dir=tmp_path / "run",
        cache_dir=tmp_path / "cache",
        invocation_id="opaque-route-test",
    )
    assert calls == ["image"]
