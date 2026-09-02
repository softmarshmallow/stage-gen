from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from gnode import ToolCall, ToolLoopMessage, ToolLoopStepRequest, ToolSpec
from gnode.providers.openrouter import OpenRouterToolLoopBackend

_SPEC = ToolSpec(
    "render", "Render.", {"type": "object", "properties": {"scale": {"type": "number"}}}
)


def _step(messages: tuple[ToolLoopMessage, ...]) -> ToolLoopStepRequest:
    return ToolLoopStepRequest(messages=messages, tools=(_SPEC,), temperature=0.2, max_tokens=800)


@pytest.mark.asyncio
async def test_tool_loop_backend_maps_the_transcript_and_parses_tool_calls() -> None:
    bodies: list[Any] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        assert request.headers["Authorization"] == "Bearer secret"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": [{"type": "text", "text": "Looking."}],
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "render", "arguments": '{"scale": 0.4}'},
                                }
                            ],
                        }
                    }
                ],
                "usage": {"total_tokens": 42},
            },
            headers={"x-request-id": "req-1"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = OpenRouterToolLoopBackend(api_key="secret", model="author/vision", client=client)
        step = await backend.step(
            _step(
                (
                    ToolLoopMessage("system", "Be brief."),
                    ToolLoopMessage("user", "Place it.", images=("data:image/png;base64,AAAA",)),
                    ToolLoopMessage(
                        "assistant",
                        "",
                        tool_calls=(ToolCall("c0", "render", {"scale": 1}),),
                    ),
                    ToolLoopMessage("tool", "rendered", tool_call_id="c0"),
                )
            )
        )

    assert step.text == "Looking."
    assert step.tool_calls == (ToolCall("call_1", "render", {"scale": 0.4}),)
    assert step.response_metadata.request_id == "req-1"
    assert step.response_metadata.usage == {"total_tokens": 42}
    body = bodies[0]
    assert body["model"] == "author/vision"
    assert body["temperature"] == 0.2
    assert body["max_tokens"] == 800
    assert body["tool_choice"] == "required"
    assert body["provider"] == {"require_parameters": True}
    assert body["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "render",
                "description": "Render.",
                "parameters": {
                    "type": "object",
                    "properties": {"scale": {"type": "number"}},
                    "required": ["scale"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        }
    ]
    assert body["messages"] == [
        {"role": "system", "content": "Be brief."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Place it."},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
            ],
        },
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c0",
                    "type": "function",
                    "function": {"name": "render", "arguments": '{"scale":1}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c0", "content": "rendered"},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ({"content": "x", "tool_calls": "nope"}, "malformed tool calls"),
        (
            {"content": "x", "tool_calls": [{"id": "", "function": {"name": "render"}}]},
            "without an id",
        ),
        (
            {
                "content": "x",
                "tool_calls": [{"id": "c", "function": {"name": "render", "arguments": "{"}}],
            },
            "invalid JSON tool arguments",
        ),
        (
            {
                "content": "x",
                "tool_calls": [{"id": "c", "function": {"name": "render", "arguments": "[1]"}}],
            },
            "non-object tool arguments",
        ),
        (
            {
                "content": "x",
                "tool_calls": [
                    {"id": "c", "function": {"name": "render", "arguments": '{"scale": NaN}'}}
                ],
            },
            "invalid JSON tool arguments",
        ),
    ],
)
async def test_tool_loop_backend_refuses_malformed_tool_calls(
    message: dict[str, object], expected: str
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": message}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = OpenRouterToolLoopBackend(api_key="secret", model="author/vision", client=client)
        with pytest.raises(ValueError, match=expected):
            await backend.step(_step((ToolLoopMessage("user", "go"),)))


@pytest.mark.asyncio
async def test_tool_loop_backend_reports_http_failures_without_the_prompt() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"error": {"message": "invalid schema for secret-prompt", "code": 400}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = OpenRouterToolLoopBackend(api_key="secret", model="author/vision", client=client)
        with pytest.raises(ValueError) as failure:
            await backend.step(_step((ToolLoopMessage("user", "secret-prompt"),)))

    text = str(failure.value)
    assert text.startswith("OpenRouter tool loop returned HTTP 400")
    assert "invalid schema" in text
    assert "secret-prompt" not in text
