"""The motion-rebase node family: declared once, hosted under each recipe's own identity."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

import pytest
from PIL import Image

from gnode import (
    Binding,
    BindingTable,
    GraphBuilder,
    ModelRef,
    Node,
    SoftwareIdentity,
    StructuredGenerationRequest,
)
from stage_gen.components._node_kit import text_digest
from stage_gen.components.sideview_actor.motion_geometry import MotionAtlasGeometry
from stage_gen.components.sideview_actor.motion_rebase import (
    MOTION_REBASE_CORRECTION_SCHEMA_NAME,
    MOTION_REBASE_SCHEMA_NAME,
    MotionRebaseReading,
    StateRebaseReading,
)
from stage_gen.components.sideview_actor.motion_rebase_nodes import (
    MOTION_REBASE_JUDGE,
    MOTION_REBASE_VERIFY,
    REBASE_READING_KIND,
    REBASE_VERIFICATION_KIND,
    MotionRebaseHandlers,
    MotionRebaseHost,
    RebaseLayout,
    RebaseSubject,
    add_motion_rebase_nodes,
    motion_rebase_node_types,
)
from stage_gen.recipes.graph_document import RecipeGraph

STATES = ("idle", "run", "hurt")
GEOMETRY = MotionAtlasGeometry(columns=4, rows=1, required_cells=4, width=208, height=112)


class _Ops(StrEnum):
    LOCAL = "local"
    STRUCTURED_GENERATION = "structured_generation"


class _Graph(RecipeGraph):
    OPERATIONS = _Ops

    schema_version: Literal[1]
    kind: Literal["rebase-family-test-graph-v1"]
    recipe: Literal["rebase-family-test"]


PROFILE = BindingTable(
    [
        Binding(
            operation="structured_generation",
            model=ModelRef(model="test-judge", provider="openrouter"),
            features=frozenset(("structured_output", "image_input")),
            resource_id="openrouter-structured",
            estimated_duration_seconds=1.0,
            estimated_cost_low_usd=0.0,
            estimated_cost_high_usd=0.0,
            verified_on="2026-09-04",
        )
    ]
)


def test_a_recipe_keeps_its_shipped_identity_and_contracts() -> None:
    types = motion_rebase_node_types(
        identity_prefix="2d/sideview/runner",
        judge_version="runner-motion-rebase-v3",
        verify_version="runner-motion-rebase-verify-v3",
    )
    assert (
        types.judge.type_id
        == MOTION_REBASE_JUDGE.type_id
        == "2d/sideview/actor/motion_rebase.judge"
    )
    assert types.judge.cache_identity == "2d/sideview/runner/motion_rebase.judge"
    assert types.judge.contract_version == "runner-motion-rebase-v3"
    assert types.verify.cache_identity == "2d/sideview/runner/motion_rebase.verify"
    assert types.verify.contract_version == "runner-motion-rebase-verify-v3"
    plain = motion_rebase_node_types()
    assert plain.judge is MOTION_REBASE_JUDGE and plain.verify is MOTION_REBASE_VERIFY


def _atlas(height: int) -> bytes:
    image = Image.new("RGBA", (52 * 4, 112), (0, 0, 0, 0))
    for column in range(4):
        for y in range(6, 6 + height):
            for x in range(6, 46):
                image.putpixel((column * 52 + x, y), (30, 90, 200, 255))
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def _graph() -> _Graph:
    builder = GraphBuilder(profile=PROFILE)
    judge_id, verify_id = add_motion_rebase_nodes(
        builder,
        types=motion_rebase_node_types(),
        judge_id="hero-rebase-judge",
        verify_id="hero-rebase-verify",
        domain="hero",
        display_name="The Hero",
        states=STATES,
        depends_on=(),
        input_digests=(text_digest("hero"), text_digest(MOTION_REBASE_SCHEMA_NAME)),
        layout=RebaseLayout(
            plate="hero/rebase-plate.png",
            reading="hero/rebase-reading.json",
            verification_plate="hero/rebase-verify-plate.png",
            verification="hero/rebase-verification.json",
        ),
        params={"actor": "hero"},
    )
    assert (judge_id, verify_id) == ("hero-rebase-judge", "hero-rebase-verify")
    return _Graph.seal(
        resources=builder.resources(), nodes=builder.nodes, terminal_node_id=verify_id
    )


def test_the_graph_helper_declares_the_pair() -> None:
    graph = _graph()
    judge = graph.node("hero-rebase-judge")
    verify = graph.node("hero-rebase-verify")
    assert judge.card is not None and "The Hero" in (judge.card.prompt or "")
    assert [port.port_id for port in judge.ports] == ["plate", "reading"]
    assert judge.port("reading").kind == REBASE_READING_KIND
    assert verify.depends_on == (judge.node_id,)
    assert [port.port_id for port in verify.ports] == ["plate", "verification"]
    assert verify.port("verification").kind == REBASE_VERIFICATION_KIND
    assert verify.card is not None and verify.card.reference_inputs[0].node_id == judge.node_id
    assert judge.cache_key != verify.cache_key


@dataclass
class _Result:
    attempts: int


class _FakeJudge:
    """Answers like the structured service: parses, admits, and writes the record."""

    def __init__(self, multipliers: dict[str, float]) -> None:
        self._multipliers = multipliers
        self.requests: list[StructuredGenerationRequest[Any]] = []

    async def generate(self, request: StructuredGenerationRequest[Any]) -> _Result:
        self.requests.append(request)
        reading = MotionRebaseReading(
            baseline_state="idle",
            states=[
                StateRebaseReading(state=state, multiplier=value, evidence="head mass compared")
                for state, value in self._multipliers.items()
            ],
        )
        assert request.artifact_value is not None
        _publish(Path(request.artifact_path), request.artifact_value(reading))
        return _Result(attempts=1)


def _publish(path: Path, record: object) -> None:
    path.write_text(json.dumps(record), encoding="utf-8")


@pytest.mark.asyncio
async def test_the_handlers_judge_then_verify_over_the_subject(tmp_path: Path) -> None:
    graph = _graph()
    (tmp_path / "hero").mkdir()
    atlases = {"idle": 100, "run": 80, "hurt": 90}
    for state, height in atlases.items():
        (tmp_path / f"hero/{state}.png").write_bytes(_atlas(height))
    subject = RebaseSubject(
        label="hero",
        entity_id="hero",
        display_name="The Hero",
        states=STATES,
        baseline_state="idle",
        atlas_refs={state: f"hero/{state}.png" for state in STATES},
        geometry=lambda _state: GEOMETRY,
    )
    judge = _FakeJudge({"idle": 1.0, "run": 1.25, "hurt": 1.1})
    calls: list[str] = []

    async def provider_call(node: Node, role: str, prompt: str, thunk: Any) -> Any:
        calls.append(f"{node.node_id}:{role}")
        return await thunk()

    handlers = MotionRebaseHandlers(
        MotionRebaseHost(
            run_dir=tmp_path,
            subject=lambda _node: subject,
            component=SoftwareIdentity(name="@stage-gen/test", version="test-v1"),
            handler_version="test-v1",
            plate_model="test-rebase-plate-v1",
            metadata={"checkpoint": "content"},
        ),
        graph=graph,
        structured_service=judge,  # type: ignore[arg-type]
        provider_call=provider_call,
    )
    judged = await handlers.judge(graph.node("hero-rebase-judge"))
    assert judged.provider_operations == 1
    # The fake judge writes the record alone; the real service writes its sidecar too.
    assert [a.artifact_ref for a in judged.artifacts] == [
        "hero/rebase-plate.png",
        "hero/rebase-plate.png.meta.json",
        "hero/rebase-reading.json",
    ]
    first = judge.requests[0]
    assert first.schema.name == MOTION_REBASE_SCHEMA_NAME
    assert first.metadata["kind"] == "hero-motion-rebase"
    assert first.metadata["checkpoint"] == "content"
    assert first.prompt == graph.node("hero-rebase-judge").card.prompt  # type: ignore[union-attr]

    verified = await handlers.verify(graph.node("hero-rebase-verify"))
    assert [a.artifact_ref for a in verified.artifacts][2] == "hero/rebase-verification.json"
    second = judge.requests[1]
    assert second.schema.name == MOTION_REBASE_CORRECTION_SCHEMA_NAME
    assert second.metadata["kind"] == "hero-motion-rebase-verify"
    record = json.loads((tmp_path / "hero/rebase-verification.json").read_text())
    # The published multipliers are the first pass times the residual the judge read.
    assert set(record["states"]) == set(STATES)
    assert calls == ["hero-rebase-judge:motion_rebase", "hero-rebase-verify:motion_rebase"]
    plate_meta = (tmp_path / "hero/rebase-verify-plate.png.meta.json").read_text()
    # The verification plate's provenance carries the first pass it was composed with.
    assert '"first_pass"' in plate_meta and '"run": 1.25' in plate_meta
