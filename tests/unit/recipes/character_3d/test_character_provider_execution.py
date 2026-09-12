"""Committed dispatch receipt resumes as collection only, keeping prior files immutable."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest

from gnode import BindingTable, SoftwareIdentity
from stage_gen.components.character_3d.budget_pool import BudgetPool
from stage_gen.components.character_3d.io import digest
from stage_gen.orchestration.character_3d.bindings import application_bindings
from stage_gen.orchestration.character_3d.provider_execution import (
    ProviderRigExecutor,
    RigProviderFactory,
)
from stage_gen.providers.character_3d.rig import TripoRig
from tests.unit.recipes.character_3d.test_character_provider_rig import FAST, Provider, glb_fixture

JsonObject = dict[str, Any]


@dataclass
class FixtureRun:
    run_root: Path
    input_root: Path
    account: BudgetPool
    experiment: JsonObject
    live: bool = True

    def upstream_bindings(self) -> BindingTable:
        return application_bindings()

    def provider_key(self, name: str) -> str:
        assert name == "TRIPO_API_KEY"
        return "not-a-real-provider-key"

    def require_run_budget(self) -> BudgetPool:
        return self.account


@pytest.fixture
def setup(tmp_path: Path) -> tuple[FixtureRun, BudgetPool, JsonObject]:
    root = tmp_path.resolve()
    (root / "run").mkdir()
    glb_fixture(root / "source.glb")
    account = BudgetPool(root / "budget", "run_account", "5")
    run = FixtureRun(
        root / "run", root, account, {"rigging": {"reservation_usd": 1, "poll_interval_seconds": 0}}
    )
    source = {"path": "source.glb", "sha256": digest(root / "source.glb")}
    return run, account, source


def factory(provider: Callable[[httpx.Request], httpx.Response]) -> RigProviderFactory:
    def create(
        *,
        api_key: str,
        input_root: Path,
        output_root: Path,
        component: SoftwareIdentity,
        tool: SoftwareIdentity,
        bindings: BindingTable | None,
    ) -> TripoRig:
        return TripoRig(
            api_key=api_key,
            input_root=input_root,
            output_root=output_root,
            component=component,
            tool=tool,
            bindings=bindings,
            client=httpx.AsyncClient(transport=httpx.MockTransport(provider)),
            retry_policy=FAST,
        )

    return create


def test_resume_committed_receipt_uses_get_only_and_preserves_submission(
    setup: tuple[FixtureRun, BudgetPool, JsonObject],
) -> None:
    run, account, source = setup
    provider = Provider(riggable=False)
    first = ProviderRigExecutor(run, provider_factory=factory(provider))
    receipt = asyncio.run(first.submit(source, 1))
    # Persist/reload the receipt exactly as a completed host stage would do.
    receipt_path = run.run_root / "committed-submit.json"
    receipt_path.write_text(json.dumps(receipt))
    snapshot = receipt["submission_snapshot"]
    submitted = run.input_root / snapshot["path"]
    before = first._inventory(submitted)
    calls_at_commit = len(provider.calls)

    def get_only(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET", "Collection resume attempted another POST"
        return provider(request)

    resumed = ProviderRigExecutor(run, provider_factory=factory(get_only))
    result = asyncio.run(resumed.collect(json.loads(receipt_path.read_text())))
    assert result["status"] == "raw_rig_collected"
    assert result["known_cost_usd"] == "0.25"
    assert provider.count("/animations/rig") == 1
    assert all(method == "GET" for method, _, _ in provider.calls[calls_at_commit:])
    assert first._inventory(submitted) == before == snapshot["files"]
    assert json.loads((submitted / "state.json").read_text())["status"] == "submitted"
    assert "/collected/" in result["source"]["path"]
    calls = len(provider.calls)
    assert asyncio.run(resumed.collect(receipt)) == result
    assert len(provider.calls) == calls
    totals = account.snapshot()
    assert totals["known_actual_usd"] == "0.25"
    assert totals["unresolved_liability_usd"] == "0"


def test_changed_submission_snapshot_refuses_collection_before_http(
    setup: tuple[FixtureRun, BudgetPool, JsonObject],
) -> None:
    run, _, source = setup
    provider = Provider()
    executor = ProviderRigExecutor(run, provider_factory=factory(provider))
    receipt = asyncio.run(executor.submit(source, 1))
    state = run.input_root / receipt["submission_snapshot"]["path"] / "state.json"
    state.write_bytes(state.read_bytes() + b" ")
    calls = len(provider.calls)
    with pytest.raises(ValueError, match="snapshot changed"):
        asyncio.run(executor.collect(receipt))
    assert len(provider.calls) == calls
    assert not (executor.collected_root / receipt["plan"]["operation_id"]).exists()


def test_terminal_failure_retains_budget_and_never_reposts(
    setup: tuple[FixtureRun, BudgetPool, JsonObject],
) -> None:
    run, account, source = setup
    provider = Provider()
    executor = ProviderRigExecutor(run, provider_factory=factory(provider))
    receipt = asyncio.run(executor.submit(source, 1))

    def failed(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        if request.url.path.endswith("/tasks/rig-task"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {"task_id": "rig-task", "status": "failed", "credits_consumed": 0},
                },
            )
        raise AssertionError("Failed rig should not download a model")

    resumed = ProviderRigExecutor(run, provider_factory=factory(failed))
    with pytest.raises(ValueError, match="Provider rig terminated: failed"):
        asyncio.run(resumed.collect(receipt))
    totals = account.snapshot()
    assert totals["unresolved_liability_usd"] == "1"
    assert totals["reservations"]["body_rig_01"]["settlement"]["outcome"] == "interrupted"
    assert provider.count("/animations/rig") == 1


@pytest.mark.parametrize("value", ["0.25", "1", "1e1000", "NaN", "-1"])
def test_decimal_money_string_plan_boundary_keeps_provider_validation(
    setup: tuple[FixtureRun, BudgetPool, JsonObject],
    value: str,
) -> None:
    run, _, source = setup
    run.experiment["rigging"]["reservation_usd"] = value
    provider = Provider()
    executor = ProviderRigExecutor(run, provider_factory=factory(provider))
    if value in {"0.25", "1"}:
        plan = executor.plan(source, 1)
        assert plan["reservation_usd"] == float(value)
    else:
        with pytest.raises(ValueError):
            executor.plan(source, 1)
    assert provider.calls == []
