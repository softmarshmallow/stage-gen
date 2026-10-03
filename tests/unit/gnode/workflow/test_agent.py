"""An agent sees pictures, answers through ``submit``, and keeps its requests small."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from gnode import CallRecord, HostServices, Route, WorkflowRun, make_plan
from tests.unit.gnode.workflow._project import planner, project

FLOW = """
gnode: workflow/v1
id: flow
title: Flow
steps:
  look:
    uses: ./nodes/agents.py#look
"""

AGENTS = '''
from gnode import Ctx, ToolReply, node, tool

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360f8cf000000020101a6f3f2660000000049454e44ae426082"
)


@tool
def render(ctx: Ctx, view: str) -> ToolReply:
    """Render one view of the subject."""
    return ToolReply(f"{view} rendered", [ctx.out.bytes(PNG + view.encode(), "image/png")])


@node("look", outputs={"answer": "json"}, calls={"agent.turn": 6})
async def look(ctx: Ctx) -> dict:
    agent = ctx.agent(system="Judge the subject.", tools=[render], recent_images=2)
    answer = await agent.run(
        "Look, then submit.",
        max_steps=6,
        images=[ctx.out.bytes(PNG, "image/png")],
        submit={
            "type": "object",
            "properties": {"verdict": {"type": "string", "enum": ["accept", "reject"]}},
            "required": ["verdict"],
            "additionalProperties": False,
        },
        check=lambda value: None if value["verdict"] == "accept" else _no(),
    )
    return {"answer": ctx.out.json(answer)}


def _no() -> None:
    raise ValueError("only an accepted subject passes here")
'''

Turn = Callable[[list[Mapping[str, Any]]], Mapping[str, Any]]


def _script(turns: list[Turn], seen: list[Mapping[str, Any]]) -> Any:
    async def turn(route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
        seen.append(dict(request))
        return CallRecord({}, dict(turns[len(seen) - 1](request["messages"])), 0.01)

    return turn


def _call(name: str, **arguments: Any) -> Turn:
    return lambda _: {
        "text": "",
        "tool_calls": [{"id": f"c{name}", "name": name, "arguments": arguments}],
    }


async def test_an_agent_sees_pictures_and_finishes_through_submit(tmp_path: Path) -> None:
    built = planner(project(tmp_path, FLOW, **{"nodes/agents.py": AGENTS}))
    plan = await make_plan(built)
    assert plan.ok, plan.problems
    seen: list[Mapping[str, Any]] = []
    turns = [
        _call("render", view="front"),
        _call("render", view="back"),
        _call("render", view="left"),
        _call("submit", verdict="maybe"),
        _call("submit", verdict="reject"),
        _call("submit", verdict="accept"),
    ]
    services = HostServices(
        store=built.store, capabilities={"agent.turn": _script(turns, seen)}, live=True
    )
    outcome = await WorkflowRun(plan, run_dir=tmp_path / "runs/one", services=services).run()

    assert outcome.ok, outcome.failed
    first = seen[0]["messages"][0]
    assert first["role"] == "user" and len(first["images"]) == 1
    assert seen[0]["tool_choice"] == "required"
    assert [tool["name"] for tool in seen[0]["tools"]] == ["render", "submit"]
    # The window keeps the two newest pictures and says how many it left out.
    shown = [image for m in seen[3]["messages"] for image in m.get("images", [])]
    assert len(shown) == 2
    assert "1 older picture(s) not shown" in seen[3]["messages"][0]["content"]
    refusals = [m["content"] for m in seen[5]["messages"] if m.get("name") == "submit"]
    assert refusals[0].startswith("refused: verdict: 'maybe' is not one of")
    assert refusals[1] == "refused: only an accepted subject passes here"
    assert [m["tool_call_id"] for m in seen[1]["messages"] if m["role"] == "tool"] == ["crender"]


async def test_a_resumed_agent_replays_its_paid_turns_with_their_pictures(tmp_path: Path) -> None:
    built = planner(project(tmp_path, FLOW, **{"nodes/agents.py": AGENTS}))
    turns = [_call("render", view="front"), _call("submit", verdict="accept")]
    first: list[Mapping[str, Any]] = []
    plan = await make_plan(built)
    services = HostServices(
        store=built.store, capabilities={"agent.turn": _script(turns, first)}, live=True
    )
    assert (await WorkflowRun(plan, run_dir=tmp_path / "runs/one", services=services).run()).ok

    again: list[Mapping[str, Any]] = []
    rebuilt = planner(project(tmp_path, FLOW + "\n", **{"nodes/agents.py": AGENTS}))
    replan = await make_plan(rebuilt)
    services = HostServices(
        store=rebuilt.store, capabilities={"agent.turn": _script(turns, again)}, live=True
    )
    outcome = await WorkflowRun(replan, run_dir=tmp_path / "runs/two", services=services).run()
    assert outcome.ok and again == [] and len(first) == 2


DECLARED = """
import base64

from gnode import Ctx, Tool, ToolResult, node

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360f8cf000000020101a6f3f2660000000049454e44ae426082"
)


async def measure(args: dict) -> ToolResult:
    picture = "data:image/png;base64," + base64.b64encode(PNG).decode()
    return ToolResult(f"{args['part']} is 2 m", (picture,))


MEASURE = Tool(
    "measure",
    "Measure one part.",
    {"type": "object", "properties": {"part": {"type": "string"}}, "required": ["part"]},
    handler=measure,
)


@node("look", outputs={"answer": "json"}, calls={"agent.turn": 3})
async def look(ctx: Ctx) -> dict:
    agent = ctx.agent(system="Measure.", tools=[MEASURE])
    answer = await agent.run(
        "Measure the body, then submit.",
        max_steps=3,
        submit={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
    )
    return {"answer": ctx.out.json(answer)}
"""


async def test_a_tool_declared_by_its_schema_shows_its_pictures(tmp_path: Path) -> None:
    built = planner(project(tmp_path, FLOW, **{"nodes/agents.py": DECLARED}))
    plan = await make_plan(built)
    assert plan.ok, plan.problems
    seen: list[Mapping[str, Any]] = []
    turns = [_call("measure", part="body"), _call("submit", ok=True)]
    services = HostServices(
        store=built.store, capabilities={"agent.turn": _script(turns, seen)}, live=True
    )
    outcome = await WorkflowRun(plan, run_dir=tmp_path / "runs/one", services=services).run()

    assert outcome.ok, outcome.failed
    assert seen[0]["tools"][0]["parameters"]["required"] == ["part"]
    [reply] = [m for m in seen[1]["messages"] if m["role"] == "tool"]
    assert reply["content"] == "body is 2 m" and len(reply["images"]) == 1
    assert reply["images"][0].kind == "image/png"
