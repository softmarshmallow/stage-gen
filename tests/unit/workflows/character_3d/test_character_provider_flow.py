"""Offline profile and graph contracts; no generated art or live success claims."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from gnode import BindingTable
from stage_gen.components.character_3d.io import digest
from stage_gen.components.character_3d.package_resources import resource
from stage_gen.orchestration.character_3d.runtime_services import create_services
from stage_gen.recipes.character_3d.experiment import validate_experiment
from stage_gen.recipes.character_3d.partitions import CORE_REGIONS, apply_partition, partition_plan
from stage_gen.recipes.character_3d.profiles import articulation, diagnostic_samples
from stage_gen.recipes.character_3d.provider_runner import ProviderBriefRun, validate_export_space
from stage_gen.recipes.character_3d.requirements import validate_requirements

JsonObject = dict[str, Any]


@pytest.fixture
def package(tmp_path: Path) -> Path:
    root = tmp_path / "package"
    root.mkdir()
    # Copy declared metadata across the test-fixture boundary. No installed-wheel
    # snapshot is needed: these graph tests never invoke the Blender worker.
    for name in (
        "profiles/sd_human_fixed.json",
        "profiles/sd_human.json",
        "models/openrouter-gpt-6-astra-2026-09-11.json",
    ):
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(resource(name).read_bytes())
    return root


def experiment(preset: str = "whole") -> JsonObject:
    value: JsonObject = {
        "schema_version": 1,
        "experiment_id": "provider_flow_offline_fixture",
        "claim": "Offline synthetic graph regression fixture",
        "scope": "original_brief_to_provider_rig_and_reviewed_motion_development",
        "pipeline_mode": "brief_to_rig",
        "profile": {
            "path": "profiles/sd_human_fixed.json",
            "sha256": "1d047009a270156fe55783aafe99fe8342b3d8a116e4a3e32c79f83f344b1e79",
        },
        "pricing": {
            "path": "models/openrouter-gpt-6-astra-2026-09-11.json",
            "sha256": "b8ba5085ee0bad0762f95d4441b18ed96306393954ecad3e2b0a367fbb778eda",
        },
        "agent_route": "openai/gpt-6-astra@openrouter",
        "parts": [],
        "partition_preset": "whole",
        "rigging": {
            "strategy": "provider",
            "route": "v1.0-20240301@tripo",
            "reservation_usd": "0.25",
            "poll_interval_seconds": 5,
            "preservation": "audit",
        },
        "brief": {
            "description": "Original compact short-haired SD adult human in a fitted plain "
            "jacket and trousers, fixed mitten hands and visible feet.",
            "rights_basis": "Original text-only test fixture.",
        },
        "limits": {
            "max_usd": "61",
            "agent_max_usd": "12.00",
            "max_dispatches": 64,
            "max_wall_seconds": 2700,
            "max_worker_calls": 220,
            "max_assembly_revisions": 4,
            "max_review_rounds": 2,
            "max_rig_revisions": 2,
            "agent_input_token_reserve": 131072,
            "agent_max_text_bytes": 262144,
            "agent_recent_image_limit": 24,
        },
        "upstream": {
            "max_reference_generations": 3,
            "max_crops": 32,
            "mesh_params": {"texture": True, "pbr": True, "quad": True, "face_limit": 10000},
            "poll_interval_seconds": 5,
        },
    }
    value["budget_account"] = {
        "root": "budget",
        "account_id": "fixture",
        "ceiling_usd": "100",
        "historical_liability_usd": "0",
    }
    value["partition_preset"] = preset
    for field in ("profile", "pricing"):
        value[field]["sha256"] = digest(resource(value[field]["path"]))
    return value


def profile(preset: str) -> JsonObject:
    return apply_partition(json.loads(resource("profiles/sd_human_fixed.json").read_text()), preset)


@pytest.mark.parametrize("preset", ["whole", "head_body_hair"])
def test_fixed_profile_covers_human_without_claiming_finger_control(preset: str) -> None:
    settings = profile(preset)
    validate_requirements(settings, experiment(preset))
    compiler = articulation(settings)
    assert len(compiler.PARENTS) == 22
    assert not any("finger" in name or "thumb" in name for name in compiler.PARENTS)
    poses = diagnostic_samples(settings, {"clips": compiler.motion_clips()})
    assert ("wrist_bend", 0.75) in poses
    assert not any(name == "hand_curl" for name, _ in poses)
    plan = partition_plan(preset)
    regions = [region for group in plan["generation_groups"].values() for region in group]
    assert set(regions) == {*CORE_REGIONS, "hair"}
    assert len(regions) == len(set(regions))
    assert plan["qualification_status"] == "development_only"


@pytest.mark.parametrize("preset,mesh_count", [("whole", 3), ("head_body_hair", 6)])
def test_real_graph_declares_provider_rig_and_separate_collection_checkpoint(
    tmp_path: Path, package: Path, preset: str, mesh_count: int
) -> None:
    root = tmp_path / "run"
    root.mkdir()
    run = ProviderBriefRun(
        package_root=package,
        input_root=tmp_path,
        run_root=root,
        experiment=experiment(preset),
        blender=Path("/usr/bin/true"),
        services=create_services(live=False),
    )
    nodes = {node.node_id: node for node in run.graph.nodes}
    assert nodes["rig_01"].depends_on == ("rig_submit_01",)
    assert nodes["rig_submit_01"].depends_on == ("assembly_admit",)
    assert nodes["rig_review_01"].depends_on == ("rig_01",)
    assert run.registry.node_type(nodes["rig_submit_01"].type_id).operation == "body_rig"
    assert run.registry.node_type(nodes["rig_01"].type_id).operation == "body_rig"
    assert (
        sum(
            run.registry.node_type(node.type_id).operation == "part_mesh" for node in nodes.values()
        )
        == mesh_count
    )
    assert all("rig_agent" not in node.type_id for node in nodes.values())
    assert (
        run.upstream_bindings().require("reference_image").model.model
        == "openai/gpt-image-2.5-sunburst"
    )
    assert run.additional_provider_reservation() == 0.5


@pytest.mark.parametrize(
    "field,value",
    [
        ("strategy", "agent"),
        ("route", "fake@fal"),
        ("reservation_usd", "NaN"),
        ("reservation_usd", True),
        ("poll_interval_seconds", float("inf")),
        ("preservation", "repaint"),
    ],
)
def test_bad_provider_configuration_refused_offline(field: str, value: object) -> None:
    request = experiment()
    request["rigging"][field] = value
    with pytest.raises(ValueError):
        validate_experiment(request)


def test_fixed_profile_does_not_modify_historical_hand_profile() -> None:
    old = json.loads(resource("profiles/sd_human.json").read_text())
    snapshot = copy.deepcopy(old)
    with pytest.raises(ValueError):
        apply_partition(old, "whole")
    assert old == snapshot
    assert any("fingers" in name for name in articulation(old).PARENTS)


def test_missing_provider_binding_refused_before_any_factory(tmp_path: Path, package: Path) -> None:
    from stage_gen.orchestration.character_3d.bindings import application_bindings

    root = tmp_path / "run"
    root.mkdir()
    # The application table without its provider-rig route: planning must refuse
    # before any executor factory or provider client exists.
    incomplete = BindingTable(
        [item for item in application_bindings().bindings if item.operation != "body_rig"]
    )
    services = SimpleNamespace(upstream_bindings=lambda: incomplete)
    with pytest.raises((KeyError, ValueError)):
        ProviderBriefRun(
            package_root=package,
            input_root=tmp_path,
            run_root=root,
            experiment=experiment(),
            blender=Path("/usr/bin/true"),
            services=services,
        )


def test_insufficient_rig_reservation_refused_before_upstream_spend(
    tmp_path: Path, package: Path
) -> None:
    root = tmp_path / "run"
    root.mkdir()
    request = experiment()
    request["rigging"]["reservation_usd"] = "0.01"
    with pytest.raises(ValueError, match="Rig reservation cannot cover"):
        ProviderBriefRun(
            package_root=package,
            input_root=tmp_path,
            run_root=root,
            experiment=request,
            blender=Path("/usr/bin/true"),
            services=create_services(live=False),
        )


def test_provider_strategy_rejects_historical_finger_profile_before_dispatch(
    tmp_path: Path, package: Path
) -> None:
    request = experiment()
    request.pop("partition_preset")
    request["profile"] = {
        "path": "profiles/sd_human.json",
        "sha256": digest(resource("profiles/sd_human.json")),
    }
    with pytest.raises(ValueError, match="only the fixed-hand SD human profile"):
        ProviderBriefRun(
            package_root=package,
            input_root=tmp_path,
            run_root=tmp_path / "run",
            experiment=request,
            blender=Path("/usr/bin/true"),
            services=create_services(live=False),
        )


@pytest.mark.parametrize("height", [None, True, "2", 0, -1, float("inf"), float("nan")])
def test_invalid_profile_height_refused_before_generation(height: Any) -> None:
    settings = profile("whole")
    settings["target_height"] = height
    with pytest.raises(ValueError, match="target_height must be finite and positive"):
        validate_requirements(settings, experiment())


@pytest.mark.parametrize(
    "height,ground", [(1.0000003, 0), (2, 0.2), (float("nan"), 0), (2, float("inf"))]
)
def test_actual_export_scale_or_placement_blocks_before_paid_review(
    height: float, ground: float
) -> None:
    with pytest.raises(ValueError, match="violates profile height or ground placement"):
        validate_export_space({"bounds": {"dimensions": [1, height, 1], "min": [0, ground, 0]}}, 2)


def test_export_space_tolerates_float32_import_roundoff() -> None:
    validate_export_space(
        {"bounds": {"dimensions": [1, 2.0000003, 1], "min": [0, -0.0000004, 0]}}, 2
    )
