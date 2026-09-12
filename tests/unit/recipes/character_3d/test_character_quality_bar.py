"""Offline quality-bar and labeled-atlas contracts; no provider or Blender calls."""

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

from stage_gen.components.character_3d.atlas import AtlasCell, build_atlas
from stage_gen.components.character_3d.io import digest, read_json
from stage_gen.components.character_3d.package_resources import resource
from stage_gen.components.character_3d.review_reuse import review_context
from stage_gen.recipes.character_3d import quality_bar as qb
from stage_gen.recipes.character_3d.experiment import validate_experiment
from stage_gen.recipes.character_3d.runner import REVIEW_SCHEMA, CharacterRun
from tests.unit.recipes.character_3d.test_character_provider_flow import experiment

JsonObject = dict[str, Any]
PROFILE: JsonObject = json.loads(resource("profiles/sd_human_fixed.json").read_text())


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


def test_experiment_validation_refuses_unknown_and_unimplemented_bars() -> None:
    base = experiment()
    validate_experiment({**base, "review_quality_bar": "low"})
    validate_experiment({**base, "review_quality_bar": "medium"})
    with pytest.raises(ValueError, match="review_quality_bar"):
        validate_experiment({**base, "review_quality_bar": "strict"})
    with pytest.raises(ValueError, match="not implemented"):
        validate_experiment({**base, "review_quality_bar": "high"})


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


def test_review_context_and_numeric_tools_follow_the_bar() -> None:
    def context(level: str) -> str:
        return review_context(
            "rig",
            PROFILE,
            ["rest_shape"],
            "policy",
            route="openai/gpt-6-astra@openrouter",
            schema=REVIEW_SCHEMA,
            quality_bar=qb.quality_bar({"review_quality_bar": level}, PROFILE),
        )

    assert context("medium") != context("low")
    assert context("low") == context("low")
    tools = [SimpleNamespace(name="inspect_asset"), SimpleNamespace(name="render_asset")]
    assert [tool.name for tool in qb.numeric_tools(tools)] == ["inspect_asset"]
    with pytest.raises(ValueError, match="inspect_asset"):
        qb.numeric_tools(tools[1:])


def test_pre_export_reviews_preview_the_declared_matte_finish() -> None:
    matte = SimpleNamespace(profile=PROFILE)
    assert CharacterRun.review_material_mode(matte) == "matte_policy"  # type: ignore[arg-type]
    preserve = SimpleNamespace(profile={"surface_policy": {"default": "preserve"}})
    assert CharacterRun.review_material_mode(preserve) == "native"  # type: ignore[arg-type]


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


def test_atlas_review_evidence_renders_each_pose_once_at_the_bar_height(tmp_path: Path) -> None:
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

    run = SimpleNamespace(
        profile={
            "review": {
                "required_views": ["front", "left"],
                "target_character_height_pixels": [120, 180],
                "inspection_height_pixels": 600,
            }
        },
        run_root=run_root,
        studio=SimpleNamespace(
            render=render, next_dir=next_dir, worker=SimpleNamespace(run_root=run_root)
        ),
    )
    bar = qb.quality_bar({}, run.profile)
    evidence, refs = asyncio.run(
        CharacterRun.atlas_review_evidence(
            run,  # type: ignore[arg-type]
            "rig_01",
            [(None, 0), ("cheer", 1.5), ("cheer", 1.5)],
            bar,
        )
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
        manifest = read_json(row_path.with_name(f"row-{index:02d}-manifest.json"))
        assert manifest["cells"] == row["cells"] and manifest["rows"] == [row["label"]]
    face = run_root / evidence["face_strip"]["path"]
    assert digest(face) == evidence["face_strip"]["sha256"]
    assert evidence["face_strip"]["source_character_height_pixels"] == 600
    assert evidence["face_strip"]["columns"] == ["front"]
    assert [ref.provenance_ref for ref in refs] == [
        *("run://" + row["path"] for row in evidence["rows"]),
        "run://" + evidence["face_strip"]["path"],
    ]
