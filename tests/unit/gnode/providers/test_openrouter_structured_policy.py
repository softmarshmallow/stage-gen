"""Credential-free HTTP contract checks against the ignored provider payload."""

from __future__ import annotations

import asyncio
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from gnode import (
    RetryPolicy,
    SoftwareIdentity,
    StructuredGenerationRequest,
    StructuredGenerationService,
    StructuredOutputSchema,
    StructuredReference,
)
from gnode.providers.openrouter import OpenRouterProviderRouting as Routing
from gnode.providers.openrouter import OpenRouterStructuredBackend as Backend
from gnode.providers.openrouter import OpenRouterStructuredRequestPolicy as Policy


def request(**kwargs: Any) -> StructuredGenerationRequest[object]:
    return StructuredGenerationRequest(
        prompt="Return an original, neutral test condition.",
        artifact_path="unused.json",
        schema=StructuredOutputSchema(
            name="test_condition",
            description="A bounded test condition",
            json_schema={
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            },
        ),
        parse=lambda value: value,
        **kwargs,
    )


def success() -> httpx.Response:
    return httpx.Response(
        200,
        headers={"x-openrouter-request-id": "request-test-id"},
        json={
            "choices": [{"message": {"content": '{"ok":true}'}}],
            "created": 1770000000,
            "usage": {"prompt_tokens": 17, "completion_tokens": 5},
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("with_image", [False, True])
async def test_defaults_preserve_existing_body_and_metadata(with_image: bool) -> None:
    captured: list[dict[str, Any]] = []

    def handler(incoming: httpx.Request) -> httpx.Response:
        captured.append(json.loads(incoming.content))
        return success()

    refs: tuple[StructuredReference, ...] = (
        (StructuredReference("data:image/png;base64,AAAA", "input.png"),) if with_image else ()
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = Backend(
            api_key="credential-must-not-enter-snapshot", model="author/text", client=client
        )
        result = await backend.generate_once(request(references=refs))
        assert backend.policy_snapshot() == {"provider": {"require_parameters": True}}
    assert len(captured) == 1
    body = captured[0]
    assert body["provider"] == {"require_parameters": True}
    assert "reasoning" not in body and "image_detail" not in body
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["name"] == "test_condition"
    if with_image:
        assert body["messages"][0]["content"][1]["image_url"] == {"url": refs[0].url}
    else:
        assert isinstance(body["messages"][0]["content"], str)
    assert result.decoded == {"ok": True}
    assert result.response_metadata.request_id == "request-test-id"
    assert result.response_metadata.created == 1770000000
    assert result.response_metadata.usage == {"prompt_tokens": 17, "completion_tokens": 5}


@pytest.mark.asyncio
async def test_explicit_settings_match_snapshot_without_mutating_request() -> None:
    captured: list[dict[str, Any]] = []
    policy = Policy(
        reasoning_effort="high",
        image_detail="high",
        provider=Routing(only=("openai",), allow_fallbacks=False),
    )
    refs = (
        StructuredReference("data:image/png;base64,AAAA", "one.png"),
        StructuredReference("https://example.test/two.png", "two.png"),
    )

    def handler(incoming: httpx.Request) -> httpx.Response:
        assert incoming.headers["authorization"] == "Bearer test-private-credential"
        captured.append(json.loads(incoming.content))
        return success()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = Backend(
            api_key="test-private-credential",
            model="author/vision",
            client=client,
            request_policy=policy,
        )
        supplied = request(
            references=refs, system="Structured test only.", max_tokens=1234, temperature=0, seed=9
        )
        before = repr(supplied)
        await backend.generate_once(supplied)
        snapshot = cast(dict[str, Any], backend.policy_snapshot())
        assert repr(supplied) == before
        assert backend.request_policy is policy
    assert len(captured) == 1
    body = captured[0]
    assert body["provider"] == {
        "require_parameters": True,
        "only": ["openai"],
        "allow_fallbacks": False,
    }
    assert body["reasoning"] == {"effort": "high"}
    assert "image_detail" not in body
    assert body["max_tokens"] == 1234 and body["temperature"] == 0 and body["seed"] == 9
    for part in body["messages"][1]["content"][1:]:
        assert part["image_url"]["detail"] == "high"
    assert snapshot == {
        "provider": body["provider"],
        "reasoning": body["reasoning"],
        "image_detail": "high",
    }
    serialized = json.dumps(snapshot)
    assert supplied.system is not None
    for private in (
        "test-private-credential",
        supplied.prompt,
        supplied.system,
        *(ref.url for ref in refs),
    ):
        assert private not in serialized
    snapshot["provider"]["only"].append("changed")
    snapshot["reasoning"]["effort"] = "low"
    assert cast(dict[str, Any], policy.snapshot()["provider"])["only"] == ["openai"]
    assert policy.snapshot()["reasoning"] == {"effort": "high"}


def test_policy_values_are_immutable() -> None:
    routing = Routing(only=("deepinfra/turbo", "google-vertex/us-east5"))
    policy = Policy(provider=routing)
    with pytest.raises(FrozenInstanceError):
        cast(Any, routing).only = ("changed",)
    with pytest.raises(FrozenInstanceError):
        cast(Any, policy).image_detail = "high"
    assert routing.snapshot()["only"] == ["deepinfra/turbo", "google-vertex/us-east5"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"reasoning_effort": "ultra"},
        {"reasoning_effort": True},
        {"reasoning_effort": []},
        {"image_detail": "medium"},
        {"image_detail": 1},
        {"provider": {"only": ["openai"]}},
    ],
)
def test_unsupported_policy_values_are_refused(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        Policy(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"only": ()},
        {"only": ["openai"]},
        {"only": ("",)},
        {"only": ("openai", "openai")},
        {"only": ("openai ",)},
        {"only": ("https://example.test/provider",)},
        {"only": (7,)},
        {"only": ("openai\nsecret",)},
        {"allow_fallbacks": 1},
        {"allow_fallbacks": "false"},
        {"require_parameters": False},
        {"require_parameters": 1},
    ],
)
def test_unsafe_or_mutable_routing_values_are_refused(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        Routing(**kwargs)


@pytest.mark.parametrize("effort", ["none", "minimal", "low", "medium", "high", "xhigh", "max"])
def test_documented_gateway_efforts_are_accepted(effort: Any) -> None:
    assert Policy(reasoning_effort=effort).snapshot()["reasoning"] == {"effort": effort}


@pytest.mark.parametrize("detail", ["auto", "low", "high", "original"])
def test_documented_image_details_are_accepted(detail: Any) -> None:
    assert Policy(image_detail=detail).snapshot()["image_detail"] == detail


@pytest.mark.asyncio
async def test_backend_has_one_attempt_and_safe_error_text() -> None:
    calls = 0
    secret, private_prompt = "private-credential-value", "private-prompt-value"
    ref = StructuredReference("https://example.test/private.png?token=sensitive", "input.png")

    def handler(incoming: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": (
                        f"Unsupported parameter response_format {secret} {private_prompt} {ref.url}"
                    ),
                    "type": "invalid_request_error",
                    "code": "invalid_json_schema",
                    "param": "response_format",
                    "private": secret,
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = Backend(
            api_key=secret,
            model="author/vision",
            client=client,
            request_policy=Policy(reasoning_effort="high", image_detail="high"),
        )
        supplied = request(references=(ref,))
        supplied = StructuredGenerationRequest(
            prompt=private_prompt,
            artifact_path=supplied.artifact_path,
            schema=supplied.schema,
            parse=lambda value: value,
            references=supplied.references,
        )
        with pytest.raises(ValueError) as raised:
            await backend.generate_once(supplied)
    assert calls == 1
    message = str(raised.value)
    assert "HTTP 400" in message and "invalid_json_schema" in message
    assert all(private not in message for private in (secret, private_prompt, ref.url, "sensitive"))


@pytest.mark.asyncio
async def test_service_owns_decode_retry_and_persists_snapshot(tmp_path: Path) -> None:
    calls = 0

    def handler(incoming: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"choices": [{"message": {"content": "not JSON"}}]})
        return success()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = Backend(
            api_key="test-secret",
            model="author/text",
            client=client,
            request_policy=Policy(
                reasoning_effort="high",
                image_detail="high",
                provider=Routing(only=("openai",), allow_fallbacks=False),
            ),
        )
        policy_snapshot = backend.policy_snapshot()
        identity = SoftwareIdentity(name="provider-policy-contract-test", version="1")
        service = StructuredGenerationService[object](
            backend,
            component=identity,
            tool=identity,
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        )
        supplied = request(metadata={"request_policy": policy_snapshot})
        result = await service.generate(
            StructuredGenerationRequest(
                prompt=supplied.prompt,
                artifact_path=tmp_path / "result.json",
                schema=supplied.schema,
                parse=supplied.parse,
                metadata=supplied.metadata,
            )
        )
    assert calls == result.attempts == 2
    meta = json.loads(await asyncio.to_thread(Path(result.provenance_path).read_bytes))
    assert meta["params"]["metadata"]["request_policy"] == policy_snapshot
    assert meta["params"]["require_parameters"] is True
    assert "test-secret" not in json.dumps(meta)
