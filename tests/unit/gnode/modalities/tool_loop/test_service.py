from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest

from gnode import (
    RetryPolicy,
    Tool,
    ToolInvocationError,
    ToolLoopExhausted,
    ToolLoopReference,
    ToolLoopRequest,
    ToolLoopService,
    ToolResult,
)
from gnode.providers.openrouter import OpenRouterToolLoopBackend
from stage_gen.identity import STAGE_GEN_TOOL, TOOL_LOOP_COMPONENT

_PIXEL = "data:image/png;base64,iVBORw0KGgo="


def _turn(*calls: tuple[str, str, dict[str, object]], usage: int = 10) -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(arguments)},
                        }
                        for call_id, name, arguments in calls
                    ],
                }
            }
        ],
        "usage": {"total_tokens": usage},
    }


def _render_tool(seen: list[Mapping[str, object]]) -> Tool:
    def render(arguments: Mapping[str, object]) -> ToolResult:
        seen.append(arguments)
        scale = arguments["scale"]
        if not isinstance(scale, int | float) or scale <= 0:
            raise ToolInvocationError("scale must be positive")
        return ToolResult(text=f"rendered at scale {scale}", images=(_PIXEL,))

    return Tool(
        name="render",
        description="Render the composition at a scale.",
        parameters={"type": "object", "properties": {"scale": {"type": "number"}}},
        handler=render,
    )


def _request(
    tmp_path: Path, seen: list[Mapping[str, object]], **overrides: Any
) -> ToolLoopRequest[dict[str, float]]:
    def parse(value: object) -> dict[str, float]:
        if not isinstance(value, dict) or not isinstance(value.get("scale"), int | float):
            raise ValueError("submit needs a numeric scale")
        return {"scale": float(value["scale"])}

    def validate(value: dict[str, float]) -> dict[str, object]:
        if value["scale"] > 1:
            raise ValueError("scale must be at most 1")
        return {"scale_within_unit": True}

    fields: dict[str, Any] = {
        "instructions": "Fit the face in the band, then submit.",
        "artifact_path": tmp_path / "placement.json",
        "tools": (_render_tool(seen),),
        "submit_schema": {"type": "object", "properties": {"scale": {"type": "number"}}},
        "parse": parse,
        "validate": validate,
        "artifact_value": lambda value: {"scale": value["scale"], "kind": "placement-v1"},
        "system": "You are an art director.",
        "references": (ToolLoopReference(_PIXEL, "run://fx/portrait.png"),),
        "max_steps": 4,
    }
    fields.update(overrides)
    return ToolLoopRequest(**fields)


def _service(client: httpx.AsyncClient) -> ToolLoopService[dict[str, float]]:
    return ToolLoopService[dict[str, float]](
        OpenRouterToolLoopBackend(api_key="secret", model="author/vision", client=client),
        component=TOOL_LOOP_COMPONENT,
        tool=STAGE_GEN_TOOL,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )


@pytest.mark.asyncio
async def test_tool_loop_runs_tools_feeds_images_back_and_persists_the_admitted_submit(
    tmp_path: Path,
) -> None:
    bodies: list[Any] = []
    seen: list[Mapping[str, object]] = []
    turns = [
        _turn(("c1", "render", {"scale": 0.9})),
        _turn(("c2", "submit", {"scale": 0.45})),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200, json=turns[len(bodies) - 1], headers={"x-request-id": f"r{len(bodies)}"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _service(client).run(_request(tmp_path, seen))

    assert result.value == {"scale": 0.45}
    assert result.steps == 2
    assert result.attempts == 1
    assert result.total_tokens == 20
    assert seen == [{"scale": 0.9}]
    assert [entry.outcome for entry in result.trace] == ["ok", "accepted"]
    assert result.trace[0].arguments == {"scale": 0.9}

    first, second = bodies
    assert first["tool_choice"] == "required"
    assert [tool["function"]["name"] for tool in first["tools"]] == ["render", "submit"]
    assert first["tools"][1]["function"]["parameters"] == {
        "type": "object",
        "properties": {"scale": {"type": "number"}},
        "required": ["scale"],
        "additionalProperties": False,
    }
    assert first["tools"][0]["function"]["strict"] is True
    assert first["messages"][0] == {"role": "system", "content": "You are an art director."}
    assert first["messages"][1]["content"][1] == {"type": "image_url", "image_url": {"url": _PIXEL}}
    # The second turn carries the assistant's call, the tool's text, and the image it rendered.
    roles = [message["role"] for message in second["messages"]]
    assert roles == ["system", "user", "assistant", "tool", "user"]
    assert second["messages"][2]["tool_calls"][0]["function"] == {
        "name": "render",
        "arguments": '{"scale":0.9}',
    }
    assert second["messages"][3] == {
        "role": "tool",
        "tool_call_id": "c1",
        "content": "rendered at scale 0.9",
    }
    assert second["messages"][4]["content"][1]["image_url"] == {"url": _PIXEL}

    assert json.loads((tmp_path / "placement.json").read_text()) == {
        "scale": 0.45,
        "kind": "placement-v1",
    }
    sidecar = json.loads((tmp_path / "placement.json.meta.json").read_text())
    assert sidecar["attempts"] == 1
    assert sidecar["prompt"] == "Fit the face in the band, then submit."
    assert sidecar["refs"] == ["run://fx/portrait.png"]
    assert sidecar["params"]["max_steps"] == 4
    assert sidecar["params"]["artifact_value"] == "caller-canonicalized"
    assert sidecar["params"]["validated"] is True
    assert [tool["name"] for tool in sidecar["params"]["tools"]] == ["render", "submit"]
    assert sidecar["validation"] == {
        "submitted": True,
        "json": "parsed",
        "schema": "caller-validated",
        "scale_within_unit": True,
    }
    assert sidecar["response"]["steps"] == 2
    assert sidecar["response"]["request_ids"] == ["r1", "r2"]
    assert sidecar["response"]["total_tokens"] == 20
    assert [entry["outcome"] for entry in sidecar["response"]["trace"]] == ["ok", "accepted"]
    assert "images" not in json.dumps(sidecar["response"]["trace"])


@pytest.mark.asyncio
async def test_tool_loop_feeds_refusals_back_and_accepts_the_corrected_submit(
    tmp_path: Path,
) -> None:
    bodies: list[Any] = []
    seen: list[Mapping[str, object]] = []
    turns = [
        _turn(("c1", "render", {"scale": -1})),
        _turn(("c2", "submit", {"scale": 3})),
        _turn(("c3", "measure", {})),
        _turn(("c4", "submit", {"scale": 0.5})),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=turns[len(bodies) - 1])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _service(client).run(_request(tmp_path, seen))

    assert result.value == {"scale": 0.5}
    assert [entry.outcome for entry in result.trace] == ["error", "rejected", "error", "accepted"]
    # The last turn's transcript carries every reply the model was shown.
    tool_replies = [
        message["content"] for message in bodies[-1]["messages"] if message["role"] == "tool"
    ]
    assert tool_replies[0] == "render refused: scale must be positive"
    assert tool_replies[1] == "submit rejected: scale must be at most 1"
    assert tool_replies[2].startswith("unknown tool measure; available: render")


@pytest.mark.asyncio
async def test_tool_loop_refuses_when_the_step_budget_ends_without_a_submit(
    tmp_path: Path,
) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_turn((f"c{calls}", "render", {"scale": 0.5})))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ToolLoopExhausted, match="no admitted submit within 2 steps"):
            await _service(client).run(_request(tmp_path, [], max_steps=2))

    assert calls == 2
    assert not (tmp_path / "placement.json").exists()


@pytest.mark.asyncio
async def test_tool_loop_refuses_when_the_token_budget_is_spent(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_turn(("c1", "render", {"scale": 0.5}), usage=900))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ToolLoopExhausted, match="900 tokens against a budget of 500"):
            await _service(client).run(_request(tmp_path, [], max_total_tokens=500))


@pytest.mark.asyncio
async def test_tool_loop_retries_a_failed_step_transport_within_the_owner(tmp_path: Path) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500, json={"error": {"message": "upstream"}})
        return httpx.Response(200, json=_turn(("c1", "submit", {"scale": 0.5})))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _service(client).run(_request(tmp_path, []))

    assert calls == 2
    assert result.steps == 1
    assert result.value == {"scale": 0.5}


@pytest.mark.asyncio
async def test_tool_loop_nudges_a_turn_that_called_nothing(tmp_path: Path) -> None:
    bodies: list[Any] = []
    turns: list[dict[str, object]] = [
        {"choices": [{"message": {"content": "Let me think."}}]},
        _turn(("c1", "submit", {"scale": 0.5})),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=turns[len(bodies) - 1])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _service(client).run(_request(tmp_path, []))

    assert result.steps == 2
    nudge = bodies[1]["messages"][-1]
    assert nudge["role"] == "user"
    assert "Every turn must call a tool" in nudge["content"]


def test_tool_loop_request_refuses_a_reserved_or_duplicate_tool_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="reserved"):
        Tool(
            name="submit",
            description="x",
            parameters={"type": "object"},
            handler=lambda arguments: ToolResult(text="x"),
        )
    seen: list[Mapping[str, object]] = []
    with pytest.raises(ValueError, match="unique"):
        _request(tmp_path, seen, tools=(_render_tool(seen), _render_tool(seen)))
    with pytest.raises(ValueError, match="max_steps"):
        _request(tmp_path, seen, max_steps=0)
