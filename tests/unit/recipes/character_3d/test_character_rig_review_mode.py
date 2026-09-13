"""Unreviewed character exports retain integrity without invoking paid reviewers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
from PIL import Image

from gnode import Graph, Node, NodeExecutionContext, NodeExecutionResult
from stage_gen.components.character_3d.io import (
    canonical_digest,
    read_json,
    verified_input,
    write_bytes,
    write_json,
)
from stage_gen.recipes.character_3d.recovery import StageRecovery
from stage_gen.recipes.character_3d.rig_runner import RigRun
from tests.unit.recipes.character_3d.test_character_whole_recovery import (
    Flow,
    execute,
)

Record = dict[str, Any]


class UnreviewedFlow(Flow):
    """Use synthetic producers and the real graph, scheduler and selection nodes."""

    damage: str | None = None

    def build_graph(self) -> Graph:
        self.experiment["review_mode"] = "none"
        return super().build_graph()

    async def produce_references(
        self, node: Node, context: NodeExecutionContext
    ) -> NodeExecutionResult:
        image = self.run_root / "references" / "canonical.png"
        manifest = self.run_root / "references" / "manifest.json"
        image.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 64), "white").save(image)
        payload = {
            "canonical": {"source": self.source(image)},
            "parts": {role: {"views": []} for role in self.profile["required_parts"]},
        }
        write_json(manifest, payload)
        return self.result(
            node,
            {
                "bundle": {
                    **payload,
                    "manifest": self.source(manifest),
                    "bundle_sha256": canonical_digest(payload),
                }
            },
        )

    async def fake_mesh(self, role: str, views: Sequence[Record], attempt: int) -> Record:
        assert self.records["references_admit"]["review_status"] == "skipped"
        assert attempt == 1
        self.mesh_calls.append(attempt)
        path = self.run_root / "provider" / f"{role}.glb"
        write_bytes(path, b"SYNTHETIC unreviewed mesh")
        return {"source": self.source(path), "operation_id": f"mesh_{role}_01"}

    async def episode(
        self, node: Node, *, instructions: str, parse: Callable[[Record], Record], **kwargs: Any
    ) -> NodeExecutionResult:
        assert node.node_id.startswith("assemble_"), "Review episode must not run"
        return await super().episode(node, instructions=instructions, parse=parse, **kwargs)

    async def produce_rig(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        result = await super().produce_rig(node, context)
        if node.node_id in self.studio.assets:
            asset = self.studio.assets[node.node_id]
            asset["required_but_missing_weights"] = ["left_paw_2"]
            asset["metrics"]["blocking_findings"] = [
                {
                    "code": "curl_does_not_demonstrate_declared_palmward_motion",
                    "message": "Synthetic wrong-way paw deformation",
                }
            ]
            if self.damage == "changed_export":
                (self.input_root / asset["source"]["path"]).write_bytes(b"CHANGED")
            elif self.damage == "appearance":
                asset["metrics"]["blocking_findings"].append(
                    "source_texture_appearance_or_binding_not_preserved"
                )
            elif self.damage == "incomplete":
                asset["rig_ready"] = False
            elif self.damage == "invalid_skin_weights":
                asset["metrics"]["blocking_findings"].append(
                    {"code": "invalid_skin_weights", "message": "Synthetic nonunit weights"}
                )
        return result


class UnreviewedLocalFlow(UnreviewedFlow):
    add_rig_nodes = RigRun.add_rig_nodes


@pytest.mark.parametrize("run_type", [UnreviewedFlow, UnreviewedLocalFlow])
def test_unreviewed_flow_delivers_defective_rig_without_review_or_regeneration(
    tmp_path: Path, run_type: type[UnreviewedFlow]
) -> None:
    run = run_type(tmp_path)
    result = execute(run)
    assert result.ok, [(node.node_id, node.error) for node in result.nodes if node.error]
    names = {node.node_id for node in run.graph.nodes}
    assert not any("review" in name or "recovery" in name for name in names)
    assert "rig_02" not in names
    assert run.mesh_calls == [1]
    assert len(run.fake_rig.calls) == (0 if run_type is UnreviewedLocalFlow else 1)
    assert run.additional_provider_reservation() == Decimal("0.25")
    selected = run.records["rig_admit"]
    assert selected["status"] == "completed_unreviewed"
    assert selected["review_status"] == "skipped"
    assert selected["source"] == run.studio.asset("rig_01")["source"]
    assert selected["quality_findings"]["required_but_missing_weights"] == ["left_paw_2"]
    assert selected["quality_findings"]["numeric_findings"][0]["code"] == (
        "curl_does_not_demonstrate_declared_palmward_motion"
    )
    assert "accepted" not in selected and "review_node" not in selected
    assert all(record.get("accepted") is not True for record in run.records.values())
    gate = next(node for node in run.graph.nodes if node.node_id == "rig_admit")
    assert gate.depends_on == ("rig_01",)
    assert gate.ports[0].kind == "unreviewed-rig-v1"


@pytest.mark.parametrize(
    "damage,message",
    [
        ("changed_export", "Registered artifact changed"),
        ("appearance", "source appearance preservation"),
        ("incomplete", "completed rig of the current assembly"),
        ("invalid_skin_weights", "Rig export integrity checks failed: invalid_skin_weights"),
    ],
)
def test_unreviewed_rig_still_refuses_integrity_failures(
    tmp_path: Path, damage: str, message: str
) -> None:
    run = UnreviewedFlow(tmp_path)
    run.damage = damage
    result = execute(run)
    assert not result.ok
    error = next(node.error for node in result.nodes if node.node_id == "rig_admit")
    assert error is not None and message in error
    assert "rig_admit" not in run.records
    assert len(run.fake_rig.calls) == 1


def test_unreviewed_provider_geometry_refusal_stays_terminal(tmp_path: Path) -> None:
    run = UnreviewedFlow(tmp_path, rig_refusals=("rig_01",))
    result = execute(run)
    assert not result.ok
    error = next(node.error for node in result.nodes if node.node_id == "rig_admit")
    assert error is not None and "geometry preservation audit" in error
    assert len(run.fake_rig.calls) == 1 and run.mesh_calls == [1]
    assert "rig_admit" not in run.records


def test_run_persists_unreviewed_outcome_and_retains_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = UnreviewedFlow(tmp_path)
    # Exercise live outcome classification with synthetic producers. Package freezing
    # is covered separately; recovery checkpoints and selection handlers remain real.
    run.live = True
    write_json(run.run_root / "runtime.json", {"fixture_only": True})
    monkeypatch.setattr(
        StageRecovery,
        "_identity_record",
        lambda recovery: {
            "fixture_only": True,
            "graph_sha256": recovery.run.graph.graph_sha256,
        },
    )
    requested_keys: list[str] = []

    def fixture_key(name: str) -> str:
        requested_keys.append(name)
        return "synthetic-unused-credential"

    monkeypatch.setattr(run, "provider_key", fixture_key)
    assert asyncio.run(run.run(admission_mode="development")) is True
    outcome = read_json(run.run_root / "outcome.json")
    selected = read_json(run.run_root / "nodes/rig_admit.json")
    assert outcome["status"] == "completed_unreviewed"
    assert outcome["review_mode"] == "none" and outcome["review_status"] == "skipped"
    assert outcome["qualification_eligible"] is False
    assert outcome["source"] == selected["source"] == run.studio.assets["rig_01"]["source"]
    assert "accepted" not in outcome and "accepted" not in selected
    assert verified_input(run.input_root, outcome["source"]).is_file()
    assert (run.run_root / "nodes/rig_01.json").is_file()
    checkpoint = read_json(run.run_root / "recovery/rig_admit.completed.json")
    assert checkpoint["state"]["records"]["rig_admit"] == selected
    assert set(requested_keys) == {"OPENROUTER_API_KEY", "TRIPO_API_KEY"}
    assert run.mesh_calls == [1] and len(run.fake_rig.calls) == 1
    assert not any("review" in name for name in run.episodes)


@pytest.mark.parametrize(
    "mode,matching_hash,allowed",
    [("none", True, True), ("required", True, False), ("none", False, False)],
)
def test_unreviewed_assembly_checkpoint_can_only_be_adopted_in_none_mode(
    tmp_path: Path, mode: str, matching_hash: bool, allowed: bool
) -> None:
    run = UnreviewedFlow(tmp_path)
    source_path = tmp_path / "assembly.glb"
    receipt_path = tmp_path / "assembly-selection.json"
    write_bytes(source_path, b"SYNTHETIC assembly checkpoint")
    source = run.source(source_path)
    checkpoint_source = source if matching_hash else {**source, "sha256": "0" * 64}
    write_json(receipt_path, {"review_status": "skipped", "source": checkpoint_source})
    run.experiment["assembly_input"] = {
        "source": source,
        "review": run.source(receipt_path),
        "part_roles": {"body": "character"},
    }
    run.experiment["review_mode"] = mode

    async def inspect(request: Record) -> tuple[Record, str]:
        return {"result": {"meshes": [{"name": "body"}]}}, "input_inspection"

    cast(Any, run.worker).execute = inspect
    node = run.graph.nodes[0]
    context = cast(NodeExecutionContext, None)
    if not allowed:
        with pytest.raises(ValueError, match="admitted review bound to its exact hash"):
            asyncio.run(run.adopt_assembly(node, context))
    else:
        asyncio.run(run.adopt_assembly(node, context))
        assert run.studio.admitted_assembly == "assembly_input"
        assert run.records[node.node_id]["review_status"] == "skipped"
