"""Stage Gen's ``agent.turn``: one turn of a node's agent, on the vision judge's settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from gnode import (
    CallRefused,
    ProviderResponseMetadata,
    ProviderToolLoopStep,
    Route,
    Store,
    ToolCall,
    ToolLoopStepRequest,
)
from stage_gen.config import load_config
from stage_gen.orchestration.gnode_plugin import agent_routes, agent_turn_job

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360f8cf000000020101a6f3f2660000000049454e44ae426082"
)


class FakeBackend:
    def __init__(self, **built: Any) -> None:
        self.built = built
        self.asked: list[ToolLoopStepRequest] = []

    async def step(self, request: ToolLoopStepRequest) -> ProviderToolLoopStep:
        self.asked.append(request)
        return ProviderToolLoopStep(
            text="",
            tool_calls=(ToolCall("c2", "submit", {"verdict": "accept"}),),
            response_metadata=ProviderResponseMetadata(usage={"cost": 0.02}),
        )

    async def aclose(self) -> None:
        return None


async def _turn(tmp_path: Path, route: Route, request: dict[str, Any]) -> tuple[Any, FakeBackend]:
    store = Store(tmp_path / "cache")
    backends: list[FakeBackend] = []

    def factory(**built: Any) -> FakeBackend:
        backends.append(FakeBackend(**built))
        return backends[-1]

    config = load_config().model_copy(update={"open_router_api_key": "test-key"})
    record = await agent_turn_job(config, store, factory=factory)(route, request, 1)
    return record, backends[0]


async def test_a_turn_carries_the_transcript_and_its_pictures(tmp_path: Path) -> None:
    store = Store(tmp_path / "pictures")
    picture = store.put_bytes(PNG, kind="image/png", name="front.png")
    request = {
        "system": "Judge the subject.",
        "messages": [
            {"role": "user", "content": "Look.", "images": [picture]},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "c1", "name": "render", "arguments": {"view": "back"}}],
            },
            {
                "role": "tool",
                "name": "render",
                "tool_call_id": "c1",
                "content": "back",
                "images": [picture],
            },
        ],
        "tools": [
            {
                "name": "render",
                "description": "Render one view.",
                "parameters": {"type": "object", "properties": {"view": {"type": "string"}}},
            }
        ],
        "tool_choice": "required",
        "max_tokens": 4000,
    }
    route = next(r for r in agent_routes() if r.model == "openai/gpt-6-astra")
    record, backend = await _turn(tmp_path, route, request)

    assert record.data == {
        "text": "",
        "tool_calls": [{"id": "c2", "name": "submit", "arguments": {"verdict": "accept"}}],
    }
    assert record.cost_usd == 0.02
    policy = backend.built["request_policy"]
    assert (policy.reasoning_effort, policy.image_detail) == ("high", "high")
    [step] = backend.asked
    roles = [message.role for message in step.messages]
    assert roles == ["system", "user", "assistant", "tool", "user"]
    assert len(step.messages[1].images) == 1 and step.messages[4].images
    assert step.messages[3].tool_call_id == "c1"
    assert step.max_tokens == 4000 and step.tool_choice == "required"
    # Strict tool schemas: every property required, nothing else allowed.
    assert step.tools[0].parameters["additionalProperties"] is False


async def test_a_turn_on_a_route_stage_gen_does_not_call_is_refused(tmp_path: Path) -> None:
    route = next(r for r in agent_routes() if r.model == "openai/gpt-6-astra")
    other = Route(
        capability="agent.turn", model="someone/else", provider="openrouter", price=route.price
    )
    with pytest.raises(CallRefused, match="not an agent route"):
        await _turn(tmp_path, other, {"messages": []})
