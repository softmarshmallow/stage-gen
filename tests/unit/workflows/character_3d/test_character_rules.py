"""The character rules the workflow's steps apply, offline: bars, atlases, profiles, exports."""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import jsonschema
import pytest
from PIL import Image

from stage_gen.components.character_3d import quality_bar as qb
from stage_gen.components.character_3d.atlas import AtlasCell, build_atlas
from stage_gen.components.character_3d.io import digest
from stage_gen.components.character_3d.partitions import (
    CORE_REGIONS,
    apply_partition,
    partition_plan,
)
from stage_gen.components.character_3d.profiles import articulation, diagnostic_samples
from stage_gen.components.character_3d.requirements import (
    validate_export_space,
    validate_requirements,
)
from stage_gen.components.character_3d.worker_client import WorkerRefusal, worker_refusal
from stage_gen.workflows.character_3d.harness import (
    REVIEW_SCHEMA,
    atlas_evidence,
    compile_profile,
    experiment,
    review_material_mode,
)

JsonObject = dict[str, Any]
PACKAGE = Path(__file__).resolve().parents[4] / "src/stage_gen/workflows/character_3d"
PROFILE: JsonObject = json.loads((PACKAGE / "profiles/sd_human_fixed.json").read_text())


def _settings(partition: str = "whole", **extra: Any) -> JsonObject:
    return {
        "pipeline_mode": "brief_to_rig",
        "review": "required",
        "quality_bar": "low",
        "partition": partition,
        "lane": "provider",
        "roles": [],
        **extra,
    }


def _verdict(*, failed: tuple[str, ...] = (), issues: list[JsonObject] | None = None) -> JsonObject:
    issues = issues or []
    return {
        "accepted": not failed and not any(i["severity"] == "blocking" for i in issues),
        "criteria": [
            {"criterion": name, "passed": name not in failed, "evidence": "fixture"}
            for name in ("rest_shape", "head_neck_attachment")
        ],
        "issues": issues,
    }


def _issue(severity: str, visible: int) -> JsonObject:
    return {
        "severity": severity,
        "region": "neck",
        "description": "fixture",
        "repair": "fixture",
        "smallest_visible_character_height_pixels": visible,
    }


def _cell_image(path: Path, *, box: tuple[int, int, int, int] = (70, 40, 130, 160)) -> Path:
    image = Image.new("RGB", (200, 200), (180, 180, 180))
    image.paste((90, 40, 120), box)
    image.save(path)
    return path


def test_levels_map_to_gameplay_heights_and_high_is_refused_offline() -> None:
    assert qb.verdict_height(PROFILE, "low") == 120
    assert qb.verdict_height(PROFILE, "medium") == 180
    low = qb.quality_bar({}, PROFILE)
    assert low["level"] == "low" and low["verdict_character_height_pixels"] == 120
    assert low["evidence_kind"] == "labeled_atlas_rows_v1"
    assert low["cell_character_height_pixels"] == 240
    assert "usable in a game" in low["policy"]
    medium = qb.quality_bar({"review_quality_bar": "medium"}, PROFILE)
    assert medium["verdict_character_height_pixels"] == 180
    assert "attachment boundary" in medium["policy"]
    assert "hair clip" in low["policy"] and "hair clip" not in medium["policy"]
    with pytest.raises(ValueError, match="not implemented"):
        qb.quality_bar({"review_quality_bar": "high"}, PROFILE)
    with pytest.raises(ValueError, match="review_quality_bar"):
        qb.quality_bar({"review_quality_bar": "closeup"}, PROFILE)
    profile = copy.deepcopy(PROFILE)
    del profile["review"]["target_character_height_pixels"]
    with pytest.raises(ValueError, match="target_character_height_pixels"):
        qb.quality_bar({}, profile)


def test_issue_heights_and_failed_criteria_respect_the_bar() -> None:
    medium = qb.quality_bar({"review_quality_bar": "medium"}, PROFILE)
    qb.check_issue_heights(
        _verdict(failed=("head_neck_attachment",), issues=[_issue("blocking", 180)]), medium
    )
    with pytest.raises(ValueError, match="declared review height"):
        qb.check_issue_heights(_verdict(issues=[_issue("minor", 600)]), medium)
    with pytest.raises(ValueError, match="blocking issue"):
        qb.check_issue_heights(
            _verdict(failed=("head_neck_attachment",), issues=[_issue("minor", 180)]), medium
        )
    issue = REVIEW_SCHEMA["properties"]["issues"]["items"]
    assert "smallest_visible_character_height_pixels" in issue["required"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {**_issue("minor", 120), "smallest_visible_character_height_pixels": "120"}, issue
        )


def test_upstream_policy_relaxes_brief_fidelity_at_low() -> None:
    low = qb.upstream_policy({}, PROFILE)
    assert low["level"] == "low" and low["verdict_character_height_pixels"] == 120
    assert "Proportion drift within the SD range" in low["policy"]
    assert "duplicated front posing as a back" in low["policy"]
    medium = qb.upstream_policy({"review_quality_bar": "medium"}, PROFILE)
    assert "half a head" in medium["policy"]


def test_rig_reviewers_get_numbers_only_and_pre_export_reviews_see_the_finish() -> None:
    tools = [SimpleNamespace(name="inspect_asset"), SimpleNamespace(name="render_asset")]
    assert [tool.name for tool in qb.numeric_tools(tools)] == ["inspect_asset"]
    with pytest.raises(ValueError, match="inspect_asset"):
        qb.numeric_tools(tools[1:])
    assert review_material_mode(PROFILE) == "matte_policy"
    assert review_material_mode({"surface_policy": {"default": "preserve"}}) == "native"


def test_atlas_cuts_native_pixels_and_labels_every_cell(tmp_path: Path) -> None:
    cells = []
    for row, pose in enumerate(("rest", "cheer 1.5s")):
        for column, view in enumerate(("front", "left")):
            path = _cell_image(tmp_path / f"{row}{column}.png", box=(70 + column * 5, 40, 130, 160))
            cells.append(AtlasCell(pose, view, path))
    atlas, manifest = build_atlas(cells)
    assert manifest["rows"] == ["rest", "cheer 1.5s"] and manifest["columns"] == ["front", "left"]
    assert manifest["resampled"] is False
    assert manifest["cell_side_pixels"] == 120 + 16
    assert (atlas.width, atlas.height) == (manifest["width"], manifest["height"])
    cell = manifest["cells"][0]
    assert cell["source_sha256"] == digest(cells[0].path)
    x0, y0, x1, y1 = cell["atlas_box"]
    crop = atlas.crop((x0, y0, x1, y1))
    source = Image.open(cells[0].path).crop(tuple(cell["source_crop"]))
    assert list(crop.getdata()) == list(source.getdata())
    with pytest.raises(ValueError, match="complete grid"):
        build_atlas(cells[:3])


def test_atlas_evidence_renders_each_pose_once_at_the_bar_height(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    (run_root / "observations").mkdir(parents=True)
    calls: list[tuple[JsonObject | None, int]] = []

    async def render(
        asset_id: str, *, views: list[str], pose: JsonObject | None, character_height_pixels: int
    ) -> tuple[JsonObject, tuple[str, ...]]:
        index = len(calls) + 1
        calls.append((pose, character_height_pixels))
        folder = run_root / f"observations/render-{index:04d}"
        folder.mkdir()
        images = []
        for view in views:
            path = _cell_image(folder / f"{view}.png")
            images.append(
                {
                    "path": f"observations/render-{index:04d}/{view}.png",
                    "sha256": digest(path),
                    "view": view,
                    "camera": {"private": "not projected"},
                }
            )
        return {"asset_id": asset_id, "pose": pose, "images": images}, ()

    counter = {"atlas": 0}

    def next_dir(prefix: str) -> str:
        counter["atlas"] += 1
        return f"observations/{prefix}-{counter['atlas']:04d}"

    profile = {
        "review": {
            "required_views": ["front", "left"],
            "target_character_height_pixels": [120, 180],
            "inspection_height_pixels": 600,
        }
    }
    studio = SimpleNamespace(
        render=render, next_dir=next_dir, worker=SimpleNamespace(run_root=run_root)
    )
    bar = qb.quality_bar({}, profile)
    evidence, files = asyncio.run(
        atlas_evidence(studio, profile, bar, "rig", [(None, 0), ("cheer", 1.5), ("cheer", 1.5)])
    )
    assert calls == [
        (None, 240),
        ({"clip": "cheer", "time_seconds": 1.5, "fps": 24}, 240),
        (None, 600),
    ]
    assert evidence["kind"] == "labeled_atlas_rows_v1"
    assert [row["label"] for row in evidence["rows"]] == ["rest", "cheer 1.5s"]
    assert evidence["columns"] == ["front", "left"]
    assert evidence["verdict_character_height_pixels"] == 120
    assert evidence["cell_character_height_pixels"] == 240
    assert "camera" not in json.dumps(evidence)
    for index, row in enumerate(evidence["rows"], start=1):
        row_path = run_root / row["path"]
        assert row_path.name == f"row-{index:02d}.png"
        assert digest(row_path) == row["sha256"]
    face = run_root / evidence["face_strip"]["path"]
    assert digest(face) == evidence["face_strip"]["sha256"]
    assert evidence["face_strip"]["source_character_height_pixels"] == 600
    assert files == [*(run_root / row["path"] for row in evidence["rows"]), face]


@pytest.mark.parametrize("preset", ["whole", "head_body_hair"])
def test_fixed_profile_covers_human_without_claiming_finger_control(preset: str) -> None:
    profile = compile_profile(PROFILE, _settings(preset))
    compiler = articulation(profile)
    assert len(compiler.PARENTS) == 22
    assert not any("finger" in name or "thumb" in name for name in compiler.PARENTS)
    poses = diagnostic_samples(profile, {"clips": compiler.motion_clips()})
    assert ("wrist_bend", 0.75) in poses
    assert not any(name == "hand_curl" for name, _ in poses)
    plan = partition_plan(preset)
    regions = [region for group in plan["generation_groups"].values() for region in group]
    assert set(regions) == {*CORE_REGIONS, "hair"}
    assert len(regions) == len(set(regions))


def test_the_grouped_hand_profile_takes_no_partition() -> None:
    old = json.loads((PACKAGE / "profiles/sd_human.json").read_text())
    snapshot = copy.deepcopy(old)
    with pytest.raises(ValueError):
        apply_partition(old, "whole")
    assert old == snapshot
    assert any("fingers" in name for name in articulation(old).PARENTS)


@pytest.mark.parametrize("height", [None, True, "2", 0, -1, float("inf"), float("nan")])
def test_an_invalid_profile_height_is_refused_while_planning(height: Any) -> None:
    profile = apply_partition(copy.deepcopy(PROFILE), "whole")
    profile["target_height"] = height
    with pytest.raises(ValueError, match="target_height must be finite and positive"):
        validate_requirements(profile, experiment(_settings()))


@pytest.mark.parametrize(
    "height,ground", [(1.0000003, 0), (2, 0.2), (float("nan"), 0), (2, float("inf"))]
)
def test_an_export_off_its_height_or_ground_is_refused(height: float, ground: float) -> None:
    with pytest.raises(ValueError, match="violates profile height or ground placement"):
        validate_export_space({"bounds": {"dimensions": [1, height, 1], "min": [0, ground, 0]}}, 2)


def test_export_space_tolerates_float32_import_roundoff() -> None:
    validate_export_space(
        {"bounds": {"dimensions": [1, 2.0000003, 1], "min": [0, -0.0000004, 0]}}, 2
    )


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
