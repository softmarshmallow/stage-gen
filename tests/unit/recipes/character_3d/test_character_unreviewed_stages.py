"""Unreviewed selection preserves candidates and integrity without invoking judges."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from PIL import Image

from gnode import Node, NodeExecutionError
from stage_gen.components.character_3d.io import canonical_digest, digest, read_json, write_json
from stage_gen.components.character_3d.package_resources import resource
from stage_gen.orchestration.character_3d.runtime_services import create_services
from stage_gen.recipes.character_3d.brief_runner import BriefRun
from stage_gen.recipes.character_3d.full_runner import FullRun
from stage_gen.recipes.character_3d.provider_runner import ProviderBriefRun
from stage_gen.recipes.character_3d.runner import CharacterRun
from tests.unit.recipes.character_3d.test_character_provider_flow import experiment
from tests.unit.recipes.character_3d.test_character_whole_recovery import fixture_package


def make_run(root: Path, *, lane: str = "brief_to_rig", provider: bool = False) -> CharacterRun:
    package = fixture_package(root)
    settings = experiment()
    settings["review_mode"] = "none"
    settings["pipeline_mode"] = lane
    if not provider:
        settings.pop("rigging")
        settings.pop("partition_preset")
        cat = "profiles/sd_cat.json"
        (package / cat).write_bytes(resource(cat).read_bytes())
        settings["profile"] = {"path": cat, "sha256": digest(package / cat)}
    if lane != "brief_to_rig":
        settings.pop("brief")
        settings.pop("upstream")
        settings["parts"] = [
            {"part_id": role, "role": role, "source": {"path": role + ".glb", "sha256": "a" * 64}}
            for role in ("head", "body", "tail")
        ]
    cls = (
        ProviderBriefRun
        if provider
        else {"assembly": CharacterRun, "parts_to_rig": FullRun, "brief_to_rig": BriefRun}[lane]
    )
    (root / "run").mkdir()
    return cls(
        package_root=package,
        input_root=root,
        run_root=root / "run",
        experiment=settings,
        blender=Path("/usr/bin/true"),
        services=create_services(live=False),
    )


def node(run: CharacterRun, name: str) -> Node:
    return next(item for item in run.graph.nodes if item.node_id == name)


def seed(run: CharacterRun, name: str, record: dict[str, Any]) -> None:
    run.records[name] = record
    write_json(run.run_root / f"nodes/{name}.json", record)


def source(run: CharacterRun, path: Path) -> dict[str, str]:
    return {"path": path.relative_to(run.input_root).as_posix(), "sha256": digest(path)}


@pytest.mark.parametrize("lane,count", [("assembly", 6), ("parts_to_rig", 8), ("brief_to_rig", 15)])
def test_cat_graph_omits_all_review_rounds(tmp_path: Path, lane: str, count: int) -> None:
    run = make_run(tmp_path, lane=lane)
    assert len(run.graph.nodes) == count
    assert all("review" not in item.node_id for item in run.graph.nodes)
    assert node(run, "assembly_admit").depends_on == ("assemble_01",)
    assert node(run, "assembly_admit").ports[0].kind == "unreviewed-assembly-v1"
    assert not any(item.node_id.endswith("_02") for item in run.graph.nodes)
    if lane == "brief_to_rig":
        assert node(run, "references_admit").depends_on == ("references_01",)
        assert node(run, "part_admit_body").depends_on == ("generate_body_01",)


def test_reference_selection_verifies_manifest_and_images(tmp_path: Path) -> None:
    run = cast(BriefRun, make_run(tmp_path))
    path = run.run_root / "reference.png"
    Image.new("RGB", (64, 64), "gray").save(path)
    image = {"source": source(run, path)}
    payload = {"canonical": image, "parts": {"body": {"views": [image]}}}
    manifest = run.run_root / "bundle.json"
    write_json(manifest, payload)
    bundle = {
        **payload,
        "bundle_sha256": canonical_digest(payload),
        "manifest": source(run, manifest),
    }
    seed(run, "references_01", {"bundle": bundle})
    asyncio.run(run.select_references(node(run, "references_admit"), cast(Any, None)))
    selected = run.records["references_admit"]
    assert selected["review_status"] == "skipped" and "accepted" not in selected
    assert run.reference_source == image["source"]
    assert run.reference_bundle == bundle
    path.write_bytes(b"changed image")
    with pytest.raises(ValueError, match=r"hash|SHA|changed|digest"):
        asyncio.run(run.select_references(node(run, "references_admit"), cast(Any, None)))


def test_part_and_assembly_selection_keep_defective_candidates(tmp_path: Path) -> None:
    run = cast(BriefRun, make_run(tmp_path))
    path = run.run_root / "candidate.glb"
    path.write_bytes(b"synthetic producer-validated candidate")
    asset = {"source": source(run, path), "metrics": {"blocking_findings": ["visible defect"]}}
    run.studio.assets["part_body_01"] = asset
    seed(run, "generate_body_01", {"asset_id": "part_body_01", "open_issues": ["visible defect"]})
    asyncio.run(run.select_part(node(run, "part_admit_body"), cast(Any, None)))
    assert run.parts["body"] == asset
    assert run.records["part_admit_body"]["review_status"] == "skipped"
    run.studio.assets["assembly_01"] = asset
    seed(run, "assemble_01", {"asset_id": "assembly_01", "open_issues": ["visible defect"]})
    asyncio.run(run.select_assembly(node(run, "assembly_admit"), cast(Any, None)))
    record = read_json(run.run_root / "nodes/assembly_admit.json")
    assert record["status"] == "completed_unreviewed" and "accepted" not in record
    assert record["source"] == asset["source"]
    assert run.studio.admitted_assembly == "assembly_01"
    assert path.read_bytes() == b"synthetic producer-validated candidate"
    path.write_bytes(b"modified after selection")
    with pytest.raises(ValueError, match="changed"):
        asyncio.run(run.select_assembly(node(run, "assembly_admit"), cast(Any, None)))


def test_failed_normalization_keeps_raw_output_but_blocks_selection(tmp_path: Path) -> None:
    run = cast(BriefRun, make_run(tmp_path))
    path = run.run_root / "raw.glb"
    path.write_bytes(b"synthetic malformed provider response")
    seed(
        run,
        "generate_body_01",
        {
            "asset_id": "part_body_01",
            "raw_part": {"source": source(run, path)},
            "structural_failure": {"error_type": "ValueError"},
        },
    )
    with pytest.raises(NodeExecutionError, match="import or texture"):
        asyncio.run(run.select_part(node(run, "part_admit_body"), cast(Any, None)))
    assert path.exists() and "body" not in run.parts


@pytest.mark.parametrize(
    "mode,status,holdback", [("required", "accepted", "2"), ("none", "completed_unreviewed", None)]
)
def test_outcome_and_producer_budget_follow_review_policy(
    tmp_path: Path, mode: str, status: str, holdback: str | None
) -> None:
    run = make_run(tmp_path)
    run.experiment["review_mode"] = mode
    run.experiment.pop("budget_account")
    run.experiment["limits"]["agent_review_holdback_usd"] = "2"
    run.live = True
    run.api_key = "offline-fixture"
    captured: dict[str, Any] = {}

    def factory(*args: Any, **kwargs: Any) -> Any:
        captured.update(kwargs)
        return SimpleNamespace()

    run.services = SimpleNamespace(episode_backend_factory=factory)
    run.backend("assemble_01")
    assert captured["limits"].review_holdback_usd == holdback
    assert run.successful_outcome_status() == status
    run.live = False
    assert run.successful_outcome_status() == "offline_fixture_complete"
