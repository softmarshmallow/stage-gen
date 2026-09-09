"""Offline confinement, complete checkpoints and interrupted-provider guards."""

from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from gnode import (
    AbortError,
    Node,
    NodeExecutionContext,
    NodeExecutionError,
    Port,
    RetryExhaustedError,
    RetryOwner,
    SoftwareIdentity,
)
from stage_gen.components.portrait_motion.models import PortraitMotionSpec, StageReceipt
from stage_gen.components.portrait_motion.nodes import PortraitMotionHandlers, StageOutput
from stage_gen.components.portrait_motion.storage import RunStore, confined
from stage_gen.orchestration.portrait_motion import RuntimeProfile, _Budget

from .test_models import specification


def node(
    name: str = "admission",
    *,
    depends_on: tuple[str, ...] = (),
    provider: bool = False,
    max_attempts: int = 6,
) -> Node:
    return Node(
        node_id=name,
        type_id=f"2d/portrait_motion/{name}",
        domain="portrait_motion",
        description="Synthetic storage contract node",
        params={"stage": name},
        depends_on=depends_on,
        operation="structured_generation" if provider else "local",
        resource_id="test",
        provider="test-provider" if provider else None,
        model="test-model" if provider else None,
        retry_owner=RetryOwner.COMPONENT if provider else RetryOwner.NONE,
        max_attempts=max_attempts if provider else 1,
        cache_key="a" * 64,
        ports=(
            Port(
                port_id="result",
                artifact_ref=f"{name}/result.json",
                sidecar_ref=f"{name}/result.json.meta.json",
                kind="test-receipt",
            ),
        ),
        estimated_duration_seconds=0.0,
        estimated_cost_low_usd=0.0,
        estimated_cost_high_usd=0.0,
    )


@pytest.fixture
def store(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path, tool=SoftwareIdentity(name="storage-contract-test", version="1"))


def artifact(store: RunStore, ref: str, current: Node, *, inputs: list[str] | None = None) -> None:
    store.write_json(
        ref,
        {"synthetic": ref},
        inputs=inputs or [],
        params={"node_cache_key": current.cache_key},
        prompt="Synthetic artifact.",
    )


def source_artifact(store: RunStore, current: Node) -> None:
    stream = io.BytesIO()
    Image.new("RGB", (128, 128), (80, 100, 120)).save(stream, "PNG")
    store.write(
        "inputs/source.png",
        stream.getvalue(),
        "image/png",
        inputs=[],
        params={"node_cache_key": current.cache_key},
        prompt="Synthetic opaque source for an offline provider-boundary test.",
    )


def checkpoint(store: RunStore, current: Node) -> StageReceipt:
    refs = [f"{current.node_id}/decision.json", f"{current.node_id}/request.json"]
    for ref in refs:
        artifact(store, ref, current)
    store.write_json(
        refs[0],
        {
            "schema_version": 1,
            "subject_count": 1,
            "subject_unambiguous": True,
            "image_readable": True,
            "features": [
                {
                    "feature_id": feature,
                    "route": "direct",
                    "source_state": "rest" if feature == "mouth" else "open",
                    "reason": "clear_feature",
                    "evidence": "Synthetic readable feature with a complete boundary.",
                    "confidence": "high",
                }
                for feature in specification()["requested_features"]
            ],
        },
        inputs=[],
        params={"node_cache_key": current.cache_key},
        prompt="Synthetic valid admission checkpoint.",
    )
    return store.finish(current, status="passed", reason="Synthetic checkpoint", files=refs)


def handlers(store: RunStore, service: Any = None) -> PortraitMotionHandlers:
    return PortraitMotionHandlers(
        SimpleNamespace(
            store=store,
            spec=PortraitMotionSpec.model_validate(specification()),
            image_service=None,
            structured_service=service,
            request_policy={},
            max_provider_operations=24,
            max_tokens=1000,
            timeout_seconds=1.0,
        )
    )


def context() -> NodeExecutionContext:
    return NodeExecutionContext("synthetic-test", "a" * 64, {})


def test_clean_checkpoint_roundtrip_requires_content_and_sidecars(store: RunStore) -> None:
    current = node()
    assert store.receipt(current) is None
    written = checkpoint(store, current)
    assert store.receipt(current) == written
    assert set(written.files) == {
        "admission/decision.json",
        "admission/decision.json.meta.json",
        "admission/request.json",
        "admission/request.json.meta.json",
    }
    handlers(store)._validate_receipt(current, written)


@pytest.mark.parametrize(
    "missing",
    [
        "admission/decision.json",
        "admission/decision.json.meta.json",
        "admission/request.json",
        "admission/result.json.meta.json",
    ],
)
def test_missing_checkpoint_member_cannot_be_reused(store: RunStore, missing: str) -> None:
    current = node()
    checkpoint(store, current)
    store.path(missing).unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        store.receipt(current)


def test_orphan_receipt_sidecar_is_not_a_clean_unstarted_stage(store: RunStore) -> None:
    current = node()
    checkpoint(store, current)
    store.path("admission/result.json").unlink()
    with pytest.raises(ValueError, match="Incomplete"):
        store.receipt(current)


@pytest.mark.parametrize(
    "changed", ["admission/decision.json", "admission/decision.json.meta.json"]
)
def test_artifact_or_sidecar_tampering_invalidates_cache(store: RunStore, changed: str) -> None:
    current = node()
    checkpoint(store, current)
    store.path(changed).write_text('{"changed": true}')
    with pytest.raises(ValueError):
        store.receipt(current)


def test_input_lineage_tampering_invalidates_cache(store: RunStore) -> None:
    current = node()
    artifact(store, "inputs/source.json", current)
    artifact(store, "admission/decision.json", current, inputs=["inputs/source.json"])
    store.finish(
        current, status="passed", reason="Synthetic lineage", files=["admission/decision.json"]
    )
    store.path("inputs/source.json").write_text('{"different": true}')
    with pytest.raises(ValueError, match="lineage"):
        store.receipt(current)


def test_rehashed_but_incomplete_stage_receipt_is_refused(store: RunStore) -> None:
    current = node()
    artifact(store, "admission/decision.json", current)
    incomplete = store.finish(
        current,
        status="passed",
        reason="Incomplete synthetic checkpoint",
        files=["admission/decision.json"],
    )
    with pytest.raises(ValueError, match="Incomplete admission"):
        handlers(store)._validate_receipt(current, incomplete)


def test_successful_dependency_cannot_be_marked_skipped(store: RunStore) -> None:
    first = node()
    checkpoint(store, first)
    later = node("guide", depends_on=(first.node_id,))
    skipped = store.finish(later, status="skipped", reason="Invalid skip", files=[])
    with pytest.raises(ValueError, match="Cannot skip"):
        handlers(store)._validate_receipt(later, skipped)


@pytest.mark.parametrize(
    "reference",
    [
        "",
        ".",
        "..",
        "../escape.json",
        "/absolute.json",
        "a/../escape.json",
        "a//b.json",
        "a/./b.json",
        "a\\b.json",
        "folder/",
    ],
)
def test_traversal_and_noncanonical_references_are_refused(store: RunStore, reference: str) -> None:
    with pytest.raises(ValueError):
        store.path(reference)


def test_root_and_nested_symlinks_are_refused(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError):
        confined(alias, "artifact.json")
    with pytest.raises(ValueError):
        confined(tmp_path, "alias/artifact.json")


def test_reserved_attempts_bound_the_whole_run_before_dispatch(store: RunStore) -> None:
    first, later = node(provider=True), node("geometry", provider=True)
    store.reserve(first, {"synthetic": True}, max_operations=6)
    with pytest.raises(ValueError, match="budget"):
        store.reserve(later, {"synthetic": True}, max_operations=6)
    assert not store.path("geometry/submission.json").exists()


def test_interrupted_submission_never_automatically_rebills(store: RunStore) -> None:
    current = node(provider=True)
    store.reserve(current, {"prompt": "First immutable intent"}, max_operations=24)
    before = store.path("admission/submission.json").read_bytes()
    with pytest.raises(ValueError, match="resubmission"):
        store.reserve(current, {"prompt": "A second attempt"}, max_operations=24)
    assert store.path("admission/submission.json").read_bytes() == before


@pytest.mark.parametrize("reserved", [-6, True, 0, 7, "6"])
def test_corrupt_reserved_attempt_count_fails_closed(store: RunStore, reserved: Any) -> None:
    first, later = node(provider=True), node("geometry", provider=True)
    store.reserve(first, {"synthetic": True}, max_operations=24)
    record = store.read("admission/submission.json")
    record["reserved_attempts"] = reserved
    store.path("admission/submission.json").write_text(json.dumps(record))
    with pytest.raises(ValueError):
        store.reserve(later, {"synthetic": True}, max_operations=24)
    assert not store.path("geometry/submission.json").exists()


@pytest.mark.asyncio
async def test_handler_pending_submission_stops_before_service_call(store: RunStore) -> None:
    current = node(provider=True)
    artifact(store, "inputs/source.png", current)
    store.reserve(current, {"synthetic": True}, max_operations=24)
    service = SimpleNamespace(generate=AsyncMock())
    with pytest.raises(ValueError, match="resubmission"):
        await handlers(store, service)._structured(
            current,
            prompt="Synthetic request",
            schema={"type": "object"},
            parse=lambda value: value,
            refs=["inputs/source.png"],
            name="decision.json",
        )
    service.generate.assert_not_called()


@pytest.mark.asyncio
async def test_failed_provider_attempts_are_reported_to_scheduler(store: RunStore) -> None:
    current = node(provider=True)
    source_artifact(store, current)
    service = SimpleNamespace(
        generate=AsyncMock(
            side_effect=RetryExhaustedError(
                "Synthetic provider",
                ValueError("Synthetic transport failure"),
                attempts=3,
            )
        )
    )
    with pytest.raises(NodeExecutionError) as raised:
        await handlers(store, service)(current, context())
    assert raised.value.attempts == raised.value.provider_operations == 3
    service.generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_public_pending_submission_reports_no_new_operations(store: RunStore) -> None:
    current = node(provider=True)
    source_artifact(store, current)
    store.reserve(current, {"synthetic": True}, max_operations=24)
    before = store.path("admission/submission.json").read_bytes()
    service = SimpleNamespace(generate=AsyncMock())
    with pytest.raises(NodeExecutionError) as raised:
        await handlers(store, service)(current, context())
    assert raised.value.provider_operations == 0
    assert store.path("admission/submission.json").read_bytes() == before
    service.generate.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("dispatches", [0, 1])
async def test_durable_dispatch_count_corrects_service_abort_attempts(
    store: RunStore, dispatches: int
) -> None:
    current = node(provider=True)
    source_artifact(store, current)
    counted = 0

    async def abort(_request: object) -> None:
        nonlocal counted
        counted = dispatches
        raise AbortError("Synthetic budget stop", provider_operations=dispatches + 1)

    service = SimpleNamespace(generate=AsyncMock(side_effect=abort))
    handler = handlers(store, service)
    handler.host.operation_count = lambda: counted
    with pytest.raises(NodeExecutionError) as raised:
        await handler(current, context())
    assert raised.value.provider_operations == dispatches


@pytest.mark.asyncio
async def test_checkpoint_failure_keeps_actual_completed_provider_count(
    store: RunStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = node(provider=True)
    counted = 0

    async def completed(_node: Node) -> StageOutput:
        nonlocal counted
        store.reserve(current, {"synthetic": True}, max_operations=24)
        counted = 3
        return StageOutput("passed", "Synthetic provider completed", [], 3)

    def cannot_finish(*_args: object, **_kwargs: object) -> None:
        raise ValueError("Synthetic checkpoint persistence failure")

    handler = handlers(store)
    handler.host.operation_count = lambda: counted
    monkeypatch.setattr(handler, "_admission", completed)
    monkeypatch.setattr(store, "finish", cannot_finish)
    with pytest.raises(NodeExecutionError) as raised:
        await handler(current, context())
    assert raised.value.provider_operations == 3


@pytest.mark.parametrize("usage", [None, {}, {"cost": None}, {"cost": -1}, {"cost": True}])
def test_unknown_or_invalid_cost_retains_full_reservation(
    store: RunStore, usage: dict[str, Any] | None
) -> None:
    budget = _Budget(store, RuntimeProfile())
    index = budget.reserve("structured_generation")
    budget.settle(index, usage)
    record = store.read("budget.json")["attempts"][index]
    assert record["charged_usd"] == 1.5
    assert record["reported_cost_usd"] is None
    assert record["status"] == "returned"


def test_reported_cost_updates_reservation_and_is_durable(store: RunStore) -> None:
    profile = RuntimeProfile()
    budget = _Budget(store, profile)
    budget.settle(budget.reserve("structured_generation"), {"cost": 0.125})
    resumed = _Budget(store, profile)
    assert resumed.reserve("image_generation") == 1
    ledger = store.read("budget.json")
    assert ledger["attempts"][0]["charged_usd"] == 0.125
    assert ledger["attempts"][1]["charged_usd"] == 1.5


def test_unknown_cost_budget_stops_before_new_attempt(store: RunStore) -> None:
    budget = _Budget(store, RuntimeProfile(budget_usd=3.0))
    assert budget.reserve("structured_generation") == 0
    assert budget.reserve("image_generation") == 1
    before = store.path("budget.json").read_bytes()
    with pytest.raises(AbortError) as raised:
        budget.reserve("structured_generation")
    assert raised.value.provider_operations == 0
    assert store.path("budget.json").read_bytes() == before


@pytest.mark.parametrize(
    "patch",
    [
        {"charged_usd": -100},
        {"charged_usd": True},
        {"charged_usd": "0"},
        {"charged_usd": float("nan")},
        {"charged_usd": float("inf")},
        {"reported_cost_usd": -1},
        {"reported_cost_usd": True},
        {"status": "missing"},
        {"operation": "unknown"},
    ],
)
def test_corrupt_budget_attempt_is_refused_before_dispatch(
    store: RunStore, patch: dict[str, Any]
) -> None:
    budget = _Budget(store, RuntimeProfile())
    budget.reserve("structured_generation")
    ledger = store.read("budget.json")
    ledger["attempts"][0].update(patch)
    store.path("budget.json").write_text(json.dumps(ledger))
    before = store.path("budget.json").read_bytes()
    with pytest.raises(ValueError):
        budget.reserve("image_generation")
    assert store.path("budget.json").read_bytes() == before


@pytest.mark.parametrize("patch", [{"schema_version": 2}, {"limit_usd": 100.0}])
def test_budget_header_cannot_change_between_invocations(
    store: RunStore, patch: dict[str, Any]
) -> None:
    budget = _Budget(store, RuntimeProfile())
    budget.reserve("structured_generation")
    ledger = store.read("budget.json")
    ledger.update(patch)
    store.path("budget.json").write_text(json.dumps(ledger))
    with pytest.raises(ValueError):
        budget.reserve("image_generation")
