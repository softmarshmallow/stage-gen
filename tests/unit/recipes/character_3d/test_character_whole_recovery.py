"""Real graph/scheduler/admission logic with explicitly synthetic provider geometry."""

from __future__ import annotations

import asyncio
import base64
import copy
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

import pytest

from gnode import Node, NodeExecutionContext, NodeExecutionResult, RunSummary, Scheduler
from stage_gen.components.character_3d.io import canonical_digest, digest, write_bytes, write_json
from stage_gen.components.character_3d.package_resources import resource
from stage_gen.components.character_3d.worker import contract as worker_contract
from stage_gen.components.character_3d.worker_client import (
    WorkerClient,
    WorkerRefusal,
    worker_refusal,
)
from stage_gen.orchestration.character_3d.runtime_services import create_services
from stage_gen.recipes.character_3d.profiles import articulation
from stage_gen.recipes.character_3d.provider_runner import ProviderBriefRun
from stage_gen.recipes.character_3d.quality_bar import quality_bar
from stage_gen.recipes.character_3d.recovery import default_recovery_state
from tests.unit.recipes.character_3d.test_character_provider_flow import (
    experiment as experiment_fixture,
)

Record = dict[str, Any]
experiment = cast(Callable[[str], Record], experiment_fixture)

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII="
)


def fixture_package(root: Path) -> Path:
    """Copy declared metadata across the isolated synthetic test boundary."""
    package = root / "package"
    for name in (
        "profiles/sd_human_fixed.json",
        "profiles/sd_human.json",
        "models/openrouter-gpt-6-astra-2026-09-11.json",
    ):
        destination = package / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(resource(name).read_bytes())
    return package


class Worker:
    """No Blender or model calls: preserve source identities in synthetic bytes."""

    def __init__(self, run: Flow) -> None:
        self.run = run
        self.input_root, self.run_root = run.input_root, run.run_root
        self.calls, self.max_calls = 0, 1000

    async def execute(self, request: Record, *, script: str = "main.py") -> tuple[Record, str]:
        self.calls += 1
        folder = self.run_root / request["output_dir"]
        operation = request["operation"]
        report: Record
        if operation == "normalize":
            if self.run.structural_failure and request["source"]["path"].endswith("mesh_1.glb"):
                raise RuntimeError("Synthetic first mesh failed normalization")
            source = self.input_root / request["source"]["path"]
            write_bytes(folder / "model.glb", source.read_bytes())
            report = {"result": {"after_reimport": {"meshes": []}}}
        elif operation == "assemble":
            write_bytes(folder / "model.glb", json.dumps(request["parts"]).encode())
            report = {
                "export": {"after_reimport": {"meshes": []}},
                "part_roles": {},
                "seams": {},
            }
        elif operation == "render":
            images = []
            for index, view in enumerate(request["options"]["views"]):
                name = view if isinstance(view, str) else view["name"]
                image = f"{index}.png"
                write_bytes(folder / image, PNG)
                entry: Record = {"name": name, "image": image}
                height = request["options"].get("character_height_pixels")
                if height is not None:
                    entry["requested_character_height_pixels"] = height
                    entry["projected_geometry"] = {"height_pixels": height, "fully_in_frame": True}
                images.append(entry)
            report = {"pose": None, "result": {"images": images, "framing_bounds": {}}}
        else:
            raise AssertionError("Unexpected fixture worker operation")
        write_json(folder / "report.json", report)
        return report, request["output_dir"]


class Executor:
    def __init__(self, run: Flow) -> None:
        self.run = run
        self.calls: list[Record] = []

    async def submit(self, source: Record, attempt: int) -> Record:
        asset = self.run.studio.asset(self.run.studio.admitted_assembly)
        assert source == asset["source"]
        gate = "assembly_admit" if attempt == 1 else "recovery_assembly_admit"
        assert self.run.records[gate]["source"] == source
        self.calls.append(copy.deepcopy(source))
        return {"status": "submitted", "source": source, "attempt": attempt}


class Flow(ProviderBriefRun):
    def __init__(
        self,
        root: Path,
        *,
        decisions: dict[str, bool] | None = None,
        unchanged_mesh: bool = False,
        unchanged_rig: bool = False,
        old_assembly: bool = False,
        structural_failure: bool = False,
        rig_refusals: Sequence[str] = (),
        preset: str = "whole",
    ) -> None:
        self.decisions = decisions or {}
        self.rig_refusals = tuple(rig_refusals)
        self.unchanged_mesh, self.unchanged_rig = unchanged_mesh, unchanged_rig
        self.old_assembly = old_assembly
        self.mesh_calls: list[int] = []
        self.episodes: list[str] = []
        self.structural_failure = structural_failure
        (root / "run").mkdir(parents=True)
        super().__init__(
            package_root=fixture_package(root),
            input_root=root,
            run_root=root / "run",
            experiment=experiment(preset),
            blender=Path("/usr/bin/true"),
            services=create_services(live=False),
        )
        self.worker = cast(WorkerClient, Worker(self))
        self.studio.worker = self.worker
        self.fake_rig = Executor(self)
        self._rig_executor = self.fake_rig
        cast(Any, self.upstream_executor).generate_part = self.fake_mesh

    def provider_key(self, name: str) -> str:
        raise AssertionError("Provider credentials must never be requested")

    def source(self, path: Path) -> Record:
        return {"path": path.relative_to(self.input_root).as_posix(), "sha256": digest(path)}

    async def fake_mesh(self, role: str, views: Sequence[Record], attempt: int) -> Record:
        assert self.records["references_admit"]["status"] == "references_admitted"
        assert attempt not in self.mesh_calls
        self.mesh_calls.append(attempt)
        path = self.run_root / "provider" / f"mesh_{attempt}.glb"
        write_bytes(path, f"SYNTHETIC mesh {1 if self.unchanged_mesh else attempt}".encode())
        return {"source": self.source(path), "operation_id": f"mesh_character_{attempt:02d}"}

    async def stub(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        return self.result(node, {"fixture_only": True})

    check_runtime = preflight = produce_references = review_references = stub

    async def admit_references(
        self, node: Node, context: NodeExecutionContext
    ) -> NodeExecutionResult:
        self.reference_bundle = {"parts": {"character": {"views": []}}}
        return self.result(node, {"status": "references_admitted", "fixture_only": True})

    async def mandatory_review_evidence(
        self, asset_id: str, poses: Any
    ) -> tuple[list[Any], list[Any]]:
        # This proves orchestration and review binding, never visual quality.
        return [], []

    async def episode(
        self, node: Node, *, instructions: str, parse: Callable[[Record], Record], **kwargs: Any
    ) -> NodeExecutionResult:
        self.episodes.append(node.node_id)
        data = json.loads(instructions)
        value: Record
        if node.node_id.startswith("assemble_"):
            if self.old_assembly and node.node_id == "assemble_recovery_02":
                asset_id = self.studio.revisions[0]
            else:
                result = await self.studio.build_assembly(
                    {
                        "parts": [
                            {
                                "part_id": "character",
                                "uniform_scale": 1,
                                "rotation_degrees_xyz": [0, 0, 0],
                                "translation": [0, 0, 0],
                            }
                        ]
                    }
                )
                asset_id = json.loads(result.text)["asset_id"]
            value = {"asset_id": asset_id, "rationale": "Synthetic fixture.", "open_issues": []}
        else:
            passed = self.decisions.get(node.node_id, True)
            value = {
                "asset_id": data["asset_id"],
                "source_sha256": data["source_sha256"],
                "accepted": passed,
                "criteria": [
                    {"criterion": name, "passed": passed, "evidence": "Fixture."}
                    for name in data["required_criteria"]
                ],
                "issues": []
                if passed
                else [
                    {
                        "severity": "blocking",
                        "region": "fixture",
                        "description": "Scripted rejection.",
                        "repair": "Scripted.",
                        "smallest_visible_character_height_pixels": quality_bar(
                            self.experiment, self.profile
                        )["verdict_character_height_pixels"],
                    }
                ],
                "notes": "Scripted semantic decision, not VLM evidence.",
            }
        return self.result(node, parse(value))

    async def produce_rig(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        submission = self.records[node.depends_on[0]]
        if submission["status"] == "reuse_admitted":
            return self.result(node, {"asset_id": submission["asset_id"]})
        source = self.studio.asset(self.studio.admitted_assembly)["source"]
        if node.node_id in self.rig_refusals:
            # The worker's declared refusal, exactly as the client raises it.
            receipt = {"status": "raw_rig_collected", "source": source, "known_cost_usd": "0.25"}
            refusal = WorkerRefusal(
                "ValueError", worker_contract.PRESERVATION_REFUSALS["connectivity"], "log"
            )
            return self.rig_structural_failure(node, node.node_id, receipt, refusal)
        path = self.run_root / "rig" / f"{node.node_id}.glb"
        payload = b"SYNTHETIC SAME RIG" if self.unchanged_rig else source["sha256"].encode()
        write_bytes(path, payload)
        self.studio.assets[node.node_id] = {
            "source": self.source(path),
            "role": "rig",
            "inventory": {},
            "required_but_missing_weights": [],
            "metrics": {"blocking_findings": []},
            "rig_plan": {"clips": articulation(self.profile).motion_clips()},
            "rig_report": {},
            "metrics_report": "fixture_only",
            "rig_ready": True,
            "assembly_asset_id": self.studio.admitted_assembly,
        }
        self.studio.rig_revisions.append(node.node_id)
        self.studio.rig_frozen = True
        return self.result(node, {"asset_id": node.node_id})


def execute(run: Flow) -> RunSummary:
    result = asyncio.run(
        Scheduler(run.graph.resources).run(
            run.graph, run.registry, invocation_id="whole_recovery_fixture"
        )
    )
    return result


def test_rejected_rig_regenerates_from_refs_and_rebinds_both_admissions(tmp_path: Path) -> None:
    run = Flow(tmp_path, decisions={"rig_review_01": False})
    result = execute(run)
    assert result.ok, [(n.node_id, n.error) for n in result.nodes if n.error]
    assert run.mesh_calls == [1, 2]
    assert len(run.fake_rig.calls) == 2
    assert run.fake_rig.calls[0] != run.fake_rig.calls[1]
    assert run.records["generate_character_02"]["reused_admitted_revision"]
    for name in (
        "recovery_part_review_02",
        "assemble_recovery_02",
        "assembly_review_03",
        "rig_review_02",
    ):
        assert name in run.episodes
    assert run.studio.revisions == ["assembly_01", "assembly_02"]
    assert run.studio.asset("rig_01")["assembly_asset_id"] == "assembly_01"
    assert run.studio.asset("rig_02")["assembly_asset_id"] == "assembly_02"
    assert run.studio.asset("assembly_01")["source"] == run.fake_rig.calls[0]
    assert run.studio.asset("assembly_02")["source"] == run.fake_rig.calls[1]
    assert run.records["recovery_part_admit"]["asset"] == run.parts["character"]
    assert run.records["rig_admit"]["source"] == run.studio.asset("rig_02")["source"]
    for name, record in run.records.items():
        assert record == json.loads((run.run_root / "nodes" / f"{name}.json").read_text())
    checkpoint = default_recovery_state(run)
    assert checkpoint["records"]["parts_admit"]["parts"] != checkpoint["parts"]
    assert checkpoint["records"] == run.records


def test_rig_preservation_refusal_routes_into_whole_recovery(tmp_path: Path) -> None:
    run = Flow(tmp_path, rig_refusals=("rig_01",))
    result = execute(run)
    assert result.ok, [(n.node_id, n.error) for n in result.nodes if n.error]
    verdict = run.records["rig_review_01"]
    assert verdict["accepted"] is False
    assert verdict["structural_failure"]["check"] == "connectivity"
    assert verdict["source_sha256"] == run.studio.asset("assembly_01")["source"]["sha256"]
    assert verdict["issues"][0]["smallest_visible_character_height_pixels"] == 120
    assert "rig_review_01" not in run.episodes
    assert "rig_review_02" in run.episodes
    assert run.mesh_calls == [1, 2]
    assert len(run.fake_rig.calls) == 2
    assert "rig_01" not in run.studio.assets and "rig_01" not in run.studio.rig_revisions
    assert run.records["rig_admit"]["source"] == run.studio.asset("rig_02")["source"]
    assert run.records["rig_01"]["open_issues"] == [
        worker_contract.PRESERVATION_REFUSALS["connectivity"]
    ]


def test_second_rig_preservation_refusal_is_terminal(tmp_path: Path) -> None:
    run = Flow(tmp_path, rig_refusals=("rig_01", "rig_02"))
    result = execute(run)
    assert not result.ok
    errors = {n.node_id: n.error for n in result.nodes if n.error}
    assert "preservation audit after bounded attempts" in errors["rig_admit"]
    assert run.mesh_calls == [1, 2] and len(run.fake_rig.calls) == 2
    assert run.episodes.count("rig_review_01") == run.episodes.count("rig_review_02") == 0


def test_unclassified_worker_errors_stay_terminal() -> None:
    from stage_gen.recipes.character_3d.provider_runner import preservation_refusal

    crash = WorkerRefusal("RuntimeError", "Blender lost its GPU context", "log")
    assert preservation_refusal(crash) is None
    for name, message in worker_contract.PRESERVATION_REFUSALS.items():
        found = preservation_refusal(WorkerRefusal("ValueError", message, "log"))
        assert found == {
            "stage": "preservation_audit",
            "check": name,
            "error_type": "ValueError",
            "message": message,
        }


def test_worker_refusal_is_parsed_from_the_declared_log_line() -> None:
    log = (
        "Blender 5.2.0 LTS\nWORKER_ERROR "
        + json.dumps(
            {"error_type": "ValueError", "message": "Provider correspondence p95 exceeds 0.01mm"}
        )
        + "\nBlender quit\n"
    )
    refusal = worker_refusal(log)
    assert isinstance(refusal, WorkerRefusal)
    assert (refusal.error_type, refusal.message) == (
        "ValueError",
        "Provider correspondence p95 exceeds 0.01mm",
    )
    assert worker_refusal("Segmentation fault\n") is None
    assert worker_refusal("WORKER_ERROR not json\n") is None
    assert worker_refusal("WORKER_ERROR " + json.dumps({"message": 1}) + "\n") is None


def test_success_skips_every_recovery_episode_and_second_provider_task(tmp_path: Path) -> None:
    run = Flow(tmp_path)
    assert execute(run).ok
    assert run.mesh_calls == [1] and len(run.fake_rig.calls) == 1
    assert run.studio.revisions == ["assembly_01"]
    assert "recovery_part_review_02" not in run.episodes
    assert "assemble_recovery_02" not in run.episodes
    assert run.records["rig_submit_02"]["status"] == "reuse_admitted"


def test_initial_part_retry_exhausts_global_generation_budget(tmp_path: Path) -> None:
    run = Flow(tmp_path, decisions={"part_review_character_01": False, "rig_review_01": False})
    result = execute(run)
    assert not result.ok
    assert run.mesh_calls == [1, 2] and len(run.fake_rig.calls) == 1
    assert any(
        n.node_id == "regenerate_character_02" and "budget exhausted" in (n.error or "")
        for n in result.nodes
    )


def test_normalization_failure_also_consumes_one_generation(tmp_path: Path) -> None:
    run = Flow(tmp_path, decisions={"rig_review_01": False}, structural_failure=True)
    assert not execute(run).ok
    assert run.mesh_calls == [1, 2] and len(run.fake_rig.calls) == 1
    assert run.records["generate_character_01"]["structural_failure"]
    assert "part_review_character_01" not in run.episodes


def test_whole_refuses_more_than_two_generations_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = experiment("whole")
    original["limits"]["max_review_rounds"] = 3
    monkeypatch.setattr(f"{__name__}.experiment", lambda preset: original)
    with pytest.raises(ValueError, match="at most two"):
        Flow(tmp_path)


def test_full_allocation_remains_two_meshes_and_two_rigs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = experiment("whole")
    original["limits"].update(agent_max_usd="12.00", max_usd="26.50")
    original["upstream"]["max_reference_generations"] = 3
    monkeypatch.setattr(f"{__name__}.experiment", lambda preset: original)
    assert len(Flow(tmp_path).graph.nodes) == 31
    original["limits"]["max_usd"] = "26.49"
    with pytest.raises(ValueError, match="budget must cover"):
        Flow(tmp_path / "insufficient")


@pytest.mark.parametrize("gate", ["recovery_part_review_02", "assembly_review_03"])
def test_rejected_replacement_never_reaches_second_rig_submission(
    tmp_path: Path, gate: str
) -> None:
    run = Flow(tmp_path, decisions={"rig_review_01": False, gate: False})
    assert not execute(run).ok
    assert run.mesh_calls == [1, 2] and len(run.fake_rig.calls) == 1


def test_identical_replacement_mesh_is_refused_without_new_review_or_rig(tmp_path: Path) -> None:
    run = Flow(tmp_path, decisions={"rig_review_01": False}, unchanged_mesh=True)
    assert not execute(run).ok
    assert run.mesh_calls == [1, 2] and len(run.fake_rig.calls) == 1
    assert "recovery_part_review_02" not in run.episodes


def test_new_mesh_cannot_submit_an_old_assembly_revision(tmp_path: Path) -> None:
    run = Flow(tmp_path, decisions={"rig_review_01": False}, old_assembly=True)
    assert not execute(run).ok
    assert len(run.fake_rig.calls) == 1


def test_byte_identical_second_rig_keeps_negative_review(tmp_path: Path) -> None:
    run = Flow(tmp_path, decisions={"rig_review_01": False}, unchanged_rig=True)
    assert not execute(run).ok
    assert len(run.fake_rig.calls) == 2
    assert "rig_review_02" not in run.episodes
    assert run.records["rig_review_02"]["review_reused_from_node"] == "rig_review_01"
    assert run.records["rig_review_02"]["accepted"] is False


def test_whole_declared_routes_and_global_bounds_are_explicit(tmp_path: Path) -> None:
    run = Flow(tmp_path)
    nodes = {n.node_id: n for n in run.graph.nodes}
    assert len(nodes) == 31
    assert nodes["regenerate_character_02"].depends_on == ("rig_review_01",)
    assert nodes["rig_submit_02"].depends_on == ("recovery_assembly_admit",)
    assert (
        sum(run.registry.node_type(n.type_id).operation == "part_mesh" for n in nodes.values()) == 3
    )
    assert run.additional_provider_reservation() == 0.5
    segmented = Flow(tmp_path / "segmented", preset="head_body_hair")
    other = {n.node_id: n for n in segmented.graph.nodes}
    assert "regenerate_character_02" not in other
    assert other["rig_submit_02"].depends_on == ("rig_review_01",)
    assert canonical_digest(segmented.experiment["limits"]) == canonical_digest(
        run.experiment["limits"]
    )
