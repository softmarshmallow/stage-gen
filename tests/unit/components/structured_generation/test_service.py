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
                    json_schema={"type": "object", "required": ["count"]},
                ),
                parse=parse,
                seed=731,
            )
        )
    assert calls == result.attempts == 3
    assert result.value == {"count": 3}
    assert json.loads((tmp_path / "value.json").read_text()) == {"count": 3}
    assert bodies[-1]["response_format"]["json_schema"]["strict"] is True
    assert bodies[-1]["provider"] == {"require_parameters": True}
    sidecar = json.loads((tmp_path / "value.json.meta.json").read_text())
    assert sidecar["seed"] == 731
    assert sidecar["validation"]["schema"] == "caller-validated"


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
