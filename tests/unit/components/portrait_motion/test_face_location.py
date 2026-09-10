"""Credential-free locator contract, service retries, and durable resume checks."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from PIL import Image

from gnode import (
    AbortError,
    ArtifactProvenance,
    BinaryArtifact,
    ProvenanceInput,
    ProviderStructuredOutput,
    RetryPolicy,
    SoftwareIdentity,
    StructuredGenerationRequest,
    StructuredGenerationService,
    write_artifact_with_provenance,
)
from gnode.providers.openrouter import OpenRouterStructuredBackend
from stage_gen.components.portrait_motion.face_location import COMPONENT, validate_location
from stage_gen.orchestration import portrait_face_location as locator
from stage_gen.orchestration.portrait_motion import request_policy


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path.resolve() / "source.png"
    output = io.BytesIO()
    Image.new("RGBA", (128, 384), (30, 90, 180, 0)).save(output, "PNG")
    write_artifact_with_provenance(
        path,
        BinaryArtifact(data=output.getvalue(), media_type="image/png"),
        ProvenanceInput(
            provider="local",
            model="original-test-drawing",
            prompt="Original test pixels.",
            component=SoftwareIdentity(name="test", version="1"),
            tool=SoftwareIdentity(name="test", version="1"),
            attempts=1,
        ),
    )
    return path


def _service(
    client: httpx.AsyncClient, *, model: str | None = None
) -> StructuredGenerationService[dict[str, Any]]:
    return StructuredGenerationService(
        OpenRouterStructuredBackend(
            api_key="mock-locator-secret",
            model=model or locator.ROUTE_MODEL,
            request_policy=request_policy(),
            client=client,
        ),
        component=COMPONENT,
        tool=locator.TOOL,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )


def _response(value: object) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "locator-test",
            "choices": [{"message": {"content": json.dumps(value)}}],
            "usage": {"cost": 0.0123, "prompt_tokens": 100, "completion_tokens": 30},
        },
    )


def test_prepare_retains_rgba_and_original_provenance(source: Path, tmp_path: Path) -> None:
    run = source.parent / "run"
    plan = locator.prepare_locator(source, run)
    assert plan["source"]["width"] == 128
    assert plan["image_jobs"] == 0 and plan["structured_jobs"] == 1
    assert (run / "inputs/source.png").read_bytes() == source.read_bytes()
    copied = ArtifactProvenance.model_validate_json(
        (run / "inputs/source.png.meta.json").read_bytes()
    )
    original = ArtifactProvenance.model_validate_json(Path(str(source) + ".meta.json").read_bytes())
    assert copied.rights == original.rights
    assert str(tmp_path) not in (run / "plan.json").read_text()
    assert "data:image" not in (run / "plan.json").read_text()
    assert "mock-locator-secret" not in (run / "plan.json").read_text()
    _, _, graph = locator.load_locator_plan(run)
    assert len(graph.nodes) == 1
    assert graph.nodes[0].max_attempts == 6
    assert graph.nodes[0].type_id == "2d/portrait_motion/face_location"
    assert "spike" not in (run / "graph.json").read_text()


def test_verify_requires_a_completed_decision(source: Path) -> None:
    run = source.parent / "run"
    locator.prepare_locator(source, run)
    with pytest.raises(ValueError, match="completed decision"):
        locator.verify_locator(run)
    assert not (run / "locator/submission.json").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    [
        {
            "status": "located",
            "bbox_xyxy": [1, 1, 2, 2],
            "reason": "Tiny stylized face with closed eyes under a hat.",
        },
        {
            "status": "located",
            "bbox_xyxy": [300, 80, 750, 320],
            "reason": "Principal face among multiple characters; one eye hidden.",
        },
        {
            "status": "not_locatable",
            "bbox_xyxy": None,
            "reason": "No face is visible in this landscape.",
        },
    ],
)
async def test_located_and_refused_are_cacheable_terminal_decisions(
    source: Path, tmp_path: Path, value: dict[str, Any]
) -> None:
    run = source.parent / "run"
    locator.prepare_locator(source, run)
    calls: list[Any] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return _response(value)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await locator.run_locator(run, service=_service(client))
        cached = await locator.run_locator(run)
    assert {key: result[key] for key in value} == value
    assert cached["provider_operations_this_invocation"] == 0
    verified = locator.verify_locator(run)
    assert verified == cached
    assert result["provider_operations_this_invocation"] == 1
    assert result["provider_attempts"] == 1
    assert result["reported_cost_usd"] == 0.0123
    assert len(calls) == 1
    assert calls[0]["max_tokens"] == 2500
    assert calls[0]["reasoning"]["effort"] == "high"
    assert calls[0]["provider"]["allow_fallbacks"] is False
    assert "data:image" not in (run / "locator/request.json").read_text()
    assert "mock-locator-secret" not in (run / "locator/location.json.meta.json").read_text()


@pytest.mark.asyncio
async def test_schema_retries_are_service_owned_and_semantic_refusal_is_not_retried(
    source: Path, tmp_path: Path
) -> None:
    run = source.parent / "run"
    locator.prepare_locator(source, run)
    replies = iter(
        [
            {"status": "located", "bbox_xyxy": [100, 50, 40, 200], "reason": "Inverted box."},
            {"status": "not_locatable", "bbox_xyxy": None, "reason": "No recognizable face."},
        ]
    )
    calls: list[Any] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _response(next(replies))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await locator.run_locator(run, service=_service(client))
    assert len(calls) == 2
    assert result["status"] == "not_locatable"
    assert result["provider_attempts"] == 2


@pytest.mark.asyncio
async def test_no_uncached_offline_dispatch_or_wrong_injected_route(
    source: Path, tmp_path: Path
) -> None:
    run = source.parent / "run"
    locator.prepare_locator(source, run)
    with pytest.raises(ValueError, match="explicit live opt-in"):
        await locator.run_locator(run)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: pytest.fail("Unexpected dispatch"))
    ) as client:
        with pytest.raises(ValueError, match="prepared binding"):
            await locator.run_locator(run, service=_service(client, model="wrong/model"))
    assert not (run / "locator/submission.json").exists()


@pytest.mark.asyncio
async def test_ambiguous_submission_never_rebills(source: Path, tmp_path: Path) -> None:
    run = source.parent / "run"
    locator.prepare_locator(source, run)
    count = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        return httpx.Response(503, json={"error": "test service unavailable"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        service = _service(client)
        with pytest.raises(ValueError, match="node failed"):
            await locator.run_locator(run, service=service)
        assert count == 6
        with pytest.raises(ValueError, match="Unresolved provider submission"):
            await locator.run_locator(run, service=service)
        assert count == 6


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tamper", ["source", "decision", "graph", "plan", "request", "receipt", "origin", "rights"]
)
async def test_tamper_refused_before_provider_submission(
    source: Path, tmp_path: Path, tamper: str
) -> None:
    run = source.parent / "run"
    locator.prepare_locator(source, run)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: _response(
                {"status": "located", "bbox_xyxy": [100, 20, 900, 200], "reason": "Face at top."}
            )
        )
    ) as client:
        await locator.run_locator(run, service=_service(client))
    path = (
        run
        / {
            "source": "inputs/source.png",
            "decision": "locator/location.json",
            "graph": "graph.json",
            "plan": "plan.json",
            "request": "locator/request.json",
            "receipt": "locator/result.json",
            "origin": "inputs/source-origin.json",
            "rights": "inputs/source.png.meta.json",
        }[tamper]
    )
    if tamper in ("source", "decision", "request", "receipt", "origin"):
        path.write_bytes(path.read_bytes() + b"\n")
    else:
        data = json.loads(path.read_text())
        if tamper == "rights":
            data["rights"] = {
                "status": "unreviewed",
                "reviewed_at": None,
                "basis": ["Altered source rights"],
            }
        else:
            data["kind"] = "tampered"
        path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        locator.verify_locator(run)
    with pytest.raises(ValueError):
        await locator.run_locator(run)


@pytest.mark.asyncio
async def test_live_requires_environment_opt_in_before_key_loading(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = source.parent / "run"
    locator.prepare_locator(source, run)
    monkeypatch.delenv("STAGE_GEN_RUN_LIVE", raising=False)
    monkeypatch.setattr(
        locator, "load_provider_dotenv", lambda path: pytest.fail("No key loading before opt-in")
    )
    with pytest.raises(ValueError, match="STAGE_GEN_RUN_LIVE"):
        await locator.run_locator(run, live=True, dotenv=tmp_path / "absent")
    assert not (run / "locator/submission.json").exists()


@pytest.mark.parametrize(
    "value",
    [
        {
            "status": "located",
            "bbox_xyxy": [True, 0, 100, 100],
            "reason": "Boolean is not a coordinate.",
        },
        {"status": "located", "bbox_xyxy": [0, 0, 1001, 100], "reason": "Outside the image."},
        {"status": "not_locatable", "bbox_xyxy": [0, 0, 100, 100], "reason": "Contradictory box."},
    ],
)
def test_location_bounds_are_syntax_checks_only(value: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        validate_location(value)


@pytest.mark.asyncio
async def test_live_budget_reserves_each_attempt_before_transport(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = source.parent / "run"
    locator.prepare_locator(source, run)
    store, _, _ = locator.load_locator_plan(run)
    backend = locator._BudgetedBackend(
        store, api_key="mock-budget-secret", model=locator.ROUTE_MODEL
    )
    count = 0

    async def generate_once(
        self: OpenRouterStructuredBackend, request: StructuredGenerationRequest[object]
    ) -> ProviderStructuredOutput:
        nonlocal count
        count += 1
        ledger = store.read("budget.json")
        assert ledger["attempts"][-1]["status"] == "reserved"
        raise RuntimeError("Ambiguous test transport failure")

    monkeypatch.setattr(OpenRouterStructuredBackend, "generate_once", generate_once)
    try:
        for _ in range(6):
            with pytest.raises(RuntimeError, match="transport failure"):
                await backend.generate_once(cast(StructuredGenerationRequest[object], None))
        with pytest.raises(AbortError, match="budget exhausted"):
            await backend.generate_once(cast(StructuredGenerationRequest[object], None))
        assert count == 6
        assert sum(item["charged_usd"] for item in store.read("budget.json")["attempts"]) == 3.0
    finally:
        await backend.aclose()
