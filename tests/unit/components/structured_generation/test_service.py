from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from stage_gen.components.structured_generation import (
    StructuredGenerationRequest,
    StructuredGenerationService,
    StructuredOutputSchema,
    StructuredReference,
)
from stage_gen.providers.openrouter import OpenRouterStructuredBackend
from stage_gen.reliability import RetryExhaustedError, RetryPolicy


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "temperature", "expected_temperature"),
    [
        ("openai/gpt-5.6", None, None),
        ("legacy/text", 0, 0),
    ],
)
async def test_structured_payload_preserves_model_temperature_capabilities(
    model: str,
    temperature: float | None,
    expected_temperature: float | None,
) -> None:
    bodies: list[Any] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok":true}'}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = OpenRouterStructuredBackend(api_key="secret", model=model, client=client)
        await backend.generate_once(
            StructuredGenerationRequest(
                prompt="return ok",
                artifact_path="unused.json",
                schema=StructuredOutputSchema(
                    name="ok",
                    json_schema={"type": "object", "required": ["ok"]},
                ),
                parse=lambda value: value,
                temperature=temperature,
            )
        )

    assert len(bodies) == 1
    body = bodies[0]
    assert body["model"] == model
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "ok",
            "strict": True,
            "schema": {"type": "object", "required": ["ok"]},
        },
    }
    assert body["provider"] == {"require_parameters": True}
    if expected_temperature is None:
        assert "temperature" not in body
    else:
        assert body["temperature"] == expected_temperature


@pytest.mark.asyncio
async def test_structured_retries_envelope_and_schema_failures(tmp_path: Path) -> None:
    calls = 0
    bodies: list[Any] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        bodies.append(json.loads(request.content))
        content = "" if calls == 1 else json.dumps({"count": "bad" if calls == 2 else 3})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}], "usage": {"total": 4}},
        )

    def parse(value: object) -> dict[str, int]:
        if not isinstance(value, dict) or not isinstance(value.get("count"), int):
            raise ValueError("bad count")
        return {"count": value["count"]}

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await StructuredGenerationService[dict[str, int]](
            OpenRouterStructuredBackend(api_key="secret", model="author/text", client=client),
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ).generate(
            StructuredGenerationRequest(
                prompt="return a count",
                artifact_path=tmp_path / "value.json",
                references=(StructuredReference("data:image/png;base64,AAAA", "reference.png"),),
                schema=StructuredOutputSchema(
                    name="count",
                    json_schema={
                        "type": "object",
                        "properties": {
                            "count": {"type": "integer", "default": 0},
                            "detail": {
                                "type": "object",
                                "properties": {
                                    "label": {
                                        "type": "string",
                                        "default": "count",
                                        "minLength": 1,
                                        "pattern": "^[a-z]+$",
                                    }
                                },
                            },
                        },
                    },
                ),
                parse=parse,
                seed=731,
            )
        )
    assert calls == result.attempts == 3
    assert result.value == {"count": 3}
    assert json.loads((tmp_path / "value.json").read_text()) == {"count": 3}
    assert bodies[-1]["response_format"]["json_schema"]["strict"] is True
    sent_schema = bodies[-1]["response_format"]["json_schema"]["schema"]
    assert sent_schema == {
        "type": "object",
        "properties": {
            "count": {"type": "integer"},
            "detail": {
                "type": "object",
                "properties": {"label": {"type": "string"}},
                "required": ["label"],
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
        "required": ["count", "detail"],
    }
    assert bodies[-1]["provider"] == {"require_parameters": True}
    sidecar = json.loads((tmp_path / "value.json.meta.json").read_text())
    assert sidecar["seed"] == 731
    assert sidecar["params"]["schema"] == sent_schema
    assert sidecar["validation"]["schema"] == "caller-validated"


@pytest.mark.asyncio
async def test_structured_publishes_caller_canonical_value_and_validation(
    tmp_path: Path,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"parallax":1.2}'}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await StructuredGenerationService[dict[str, float]](
            OpenRouterStructuredBackend(api_key="secret", model="author/text", client=client),
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ).generate(
            StructuredGenerationRequest(
                prompt="return parallax",
                artifact_path=tmp_path / "value.json",
                schema=StructuredOutputSchema(name="parallax", json_schema={}),
                parse=lambda value: {"parallax": 1.8, "input": value["parallax"]},  # type: ignore[index]
                artifact_value=lambda value: {"parallax": value["parallax"]},
                validate=lambda value: {
                    "normalization": {
                        "input": value["input"],
                        "output": value["parallax"],
                    }
                },
            )
        )

    assert result.value == {"parallax": 1.8, "input": 1.2}
    assert json.loads((tmp_path / "value.json").read_text()) == {"parallax": 1.8}
    sidecar = json.loads((tmp_path / "value.json.meta.json").read_text())
    assert sidecar["params"]["artifact_value"] == "caller-canonicalized"
    assert sidecar["params"]["validated"] is True
    assert sidecar["validation"]["normalization"] == {"input": 1.2, "output": 1.8}


@pytest.mark.asyncio
async def test_structured_rejects_nonfinite_json_on_all_six_attempts(tmp_path: Path) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            content=b'{"choices":[{"message":{"content":"{\\"count\\":NaN}"}}]}',
            headers={"content-type": "application/json"},
        )

    def parse(value: object) -> object:
        return value

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = StructuredGenerationService[object](
            OpenRouterStructuredBackend(api_key="secret", model="author/text", client=client),
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        )
        with pytest.raises(RetryExhaustedError, match="invalid JSON content"):
            await service.generate(
                StructuredGenerationRequest(
                    prompt="return a finite count",
                    artifact_path=tmp_path / "value.json",
                    schema=StructuredOutputSchema(name="count", json_schema={}),
                    parse=parse,
                )
            )
    assert calls == 6
    assert not (tmp_path / "value.json").exists()


@pytest.mark.asyncio
async def test_structured_http_failure_keeps_only_bounded_safe_provider_detail(
    tmp_path: Path,
) -> None:
    calls = 0
    prompt = "private prompt content"
    api_key = "sk-or-1234567890"
    signed_url = "https://private.example/schema.json?signature=do-not-persist"
    private_path = "/Users/private/project/schema.json"

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raw = {
            "error": {
                "message": (
                    "Invalid schema for response_format: required must include every key; "
                    f"prompt={prompt}; credential={api_key}; source={signed_url}; "
                    f"path={private_path}"
                ),
                "type": "invalid_request_error",
                "code": "invalid_json_schema",
                "param": "response_format",
                "unrelated": "must-not-survive",
            }
        }
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "Provider returned error",
                    "metadata": {
                        "raw": json.dumps(raw),
                        "headers": {"authorization": api_key},
                        "unrelated": "must-not-survive",
                    },
                },
                "unrelated_response": "must-not-survive",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = StructuredGenerationService[object](
            OpenRouterStructuredBackend(api_key=api_key, model="author/text", client=client),
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        )
        with pytest.raises(RetryExhaustedError) as raised:
            await service.generate(
                StructuredGenerationRequest(
                    prompt=prompt,
                    artifact_path=tmp_path / "value.json",
                    schema=StructuredOutputSchema(name="value", json_schema={}),
                    parse=lambda value: value,
                )
            )

    message = str(raised.value)
    assert calls == 6
    assert "HTTP 400" in message
    assert "invalid_json_schema" in message
    assert "required must include every key" in message
    assert prompt not in message
    assert api_key not in message
    assert signed_url not in message
    assert private_path not in message
    assert "https://" not in message
    assert "/Users/" not in message
    assert "must-not-survive" not in message
    assert len(message) < 1000
    assert not (tmp_path / "value.json").exists()
