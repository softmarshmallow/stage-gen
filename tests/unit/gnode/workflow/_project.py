"""A small synthetic gnode project for workflow tests: files on disk, fake paid calls."""

from __future__ import annotations

import hashlib
import json
import textwrap
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from gnode import (
    CallRecord,
    HostServices,
    Plan,
    Planner,
    Route,
    RoutePrice,
    RouteTable,
    Store,
    make_plan,
    make_planner,
)
from gnode_std import file_facts, standard_types

ROUTES = RouteTable(
    [
        Route("image.generate", "img-a", "acme", RoutePrice(0.01, 0.04), frozenset({"alpha"})),
        Route("image.edit", "img-a", "acme", RoutePrice(0.02, 0.05), frozenset({"mask"})),
        Route("structured.generate", "llm-a", "acme", RoutePrice(0.001, 0.002)),
        Route("structured.generate", "llm-b", "other", RoutePrice(0.001, 0.003)),
        Route("vision.review", "llm-a", "other", RoutePrice(0.002, 0.004)),
        Route("vision.review", "vlm-c", "other", RoutePrice(0.002, 0.004)),
        Route("agent.turn", "llm-a", "acme", RoutePrice(0.001, 0.003)),
    ]
)

NODES = """
from gnode import Ctx, node, tool


@node("words", inputs={"text": "text"}, outputs={"report": "json"})
def words(ctx: Ctx) -> dict:
    text = ctx.read.text("text")
    return {"report": ctx.out.json({"words": text.split(), "count": len(text.split())})}


@node("split", inputs={"text": "text"}, outputs={"items": "json"})
def split(ctx: Ctx) -> dict:
    lines = [line for line in ctx.read.text("text").splitlines() if line.strip()]
    items = [{"id": f"l{i}", "text": t} for i, t in enumerate(lines)]
    return {"items": ctx.out.json({"lines": items})}


@node("shout", params={"text": str}, outputs={"text": "text"})
def shout(ctx: Ctx) -> dict:
    return {"text": ctx.out.text(ctx.params["text"].upper())}


@node("join", inputs={"parts": "text{}"}, outputs={"text": "text"})
def join(ctx: Ctx) -> dict:
    parts = ctx.inputs["parts"].items()
    return {"text": ctx.out.text("|".join(f"{k}={v.read_bytes().decode()}" for k, v in parts))}


@node("verdict", inputs={"subject": "file"}, params={"accept_take": int}, outputs={}, judge=True)
def verdict(ctx: Ctx) -> dict:
    ctx.fact("take", ctx.instance.take)
    ctx.fact("verdict", "accept" if ctx.instance.take >= ctx.params["accept_take"] else "reject")
    return {}


@tool
def remember(ctx: Ctx, word: str) -> str:
    '''Write one word down.'''
    ctx.state.setdefault("words", []).append(word)
    return f"noted {word}"


@node("note_taker", params={"topic": str}, outputs={"notes": "json"}, calls={"agent.turn": 4})
async def note_taker(ctx: Ctx) -> dict:
    agent = ctx.agent(system="Write down the words you are given.", tools=[remember])
    answer = await agent.run(f"Note the words of {ctx.params['topic']}", max_steps=4)
    return {"notes": ctx.out.json({"words": ctx.state.get("words", []), "answer": answer})}


@node("paint", inputs={"image": "image"}, params={"prompt": str}, outputs={"image": "image/png"},
      calls={"image.edit": 1})
async def paint(ctx: Ctx) -> dict:
    result = await ctx.image_edit(image=ctx.inputs["image"], prompt=ctx.params["prompt"])
    return {"image": result.image}
"""


def write(root: Path, files: Mapping[str, str | bytes]) -> Path:
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
    return root


def project(root: Path, workflow: str, **extra: str | bytes) -> Path:
    """A project with ``gnode.yaml``, the test nodes and one workflow file."""

    write(
        root,
        {
            "gnode.yaml": """
                gnode: project/v1
                routes:
                  image.generate: img-a@acme
                  image.edit: img-a@acme
                  structured.generate: llm-a@acme
                  vision.review: vlm-c@other
                  agent.turn: llm-a@acme
            """,
            "nodes/test_nodes.py": NODES,
            "workflows/flow.yaml": workflow,
            **extra,
        },
    )
    return root / "workflows/flow.yaml"


def planner(path: Path, **inputs: Any) -> Planner:
    return make_planner(
        path,
        inputs=inputs,
        cwd=path.parent.parent,
        builtins=standard_types(),
        routes=ROUTES,
        facts_reader=file_facts,
    )


async def plan(path: Path, *, max_usd: float | None = None, **inputs: Any) -> Plan:
    return await make_plan(planner(path, **inputs), max_usd=max_usd)


PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360f8cf000000020101a6f3f2660000000049454e44ae426082"
)


class FakeProvider:
    """Answers every paid call offline, counts them, and charges a fixed cost."""

    def __init__(self, store: Store, cost_usd: float = 0.01) -> None:
        self.store = store
        self.cost_usd = cost_usd
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    def services(self, *, live: bool = True) -> HostServices:
        capabilities = {
            name: self._handler(name)
            for name in (
                "image.generate",
                "image.edit",
                "structured.generate",
                "vision.review",
                "agent.turn",
            )
        }
        return HostServices(store=self.store, capabilities=capabilities, live=live)

    def _handler(self, name: str):  # type: ignore[no-untyped-def]
        async def handle(route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
            self.calls.append((name, dict(request)))
            if name.startswith("image."):
                seed = hashlib.sha256(json.dumps([name, take, str(request.get("prompt"))]).encode())
                data = PNG + seed.digest()[:4]
                file = self.store.put_bytes(data, kind="image/png", name="image")
                return CallRecord({"image": file}, None, self.cost_usd)
            if name == "vision.review":
                return CallRecord({}, {"verdict": "accept"}, self.cost_usd)
            if name == "agent.turn":
                answered = any(m["role"] == "tool" for m in request["messages"])
                calls = [] if answered else [{"name": "remember", "arguments": {"word": "tide"}}]
                return CallRecord(
                    {}, {"text": "done" if answered else "", "tool_calls": calls}, self.cost_usd
                )
            return CallRecord({}, {"answer": take}, self.cost_usd)

        return handle
