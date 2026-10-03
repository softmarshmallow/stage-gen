from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import cast

import pytest
from PIL import Image

from demo_game_tools.kits.character_profile import canonical_character_profile_json
from demo_game_tools.kits.ui_art.nodes import UI_SHEET_ROLES, sheet_family
from stage_gen.image_prompting import load_image_style_resources, materialize_style_anchor
from stage_gen.image_style import StyleModeSelection
from tests.unit._ui_atlas_fixture import ui_sheet
from the_grain_pipeline.dialogue_scene.identity import (
    canonical_json_bytes,
    canonical_sha256,
    content_sha256,
)
from the_grain_pipeline.dialogue_scene.manifest import _fit, dialogue_bundle
from the_grain_pipeline.dialogue_scene.prompts import TEMPLATE_DIGEST
from the_grain_pipeline.dialogue_scene.scene_request import (
    ResolvedDialogueScene,
    read_scene_document,
    resolve_dialogue_scene,
)

from .package import write_scene_package


def _png(width: int, height: int, *, alpha: bool) -> bytes:
    output = BytesIO()
    mode = "RGBA" if alpha else "RGB"
    color = (20, 30, 80, 128) if alpha else (20, 30, 80)
    Image.new(mode, (width, height), color).save(output, format="PNG")
    return output.getvalue()


def _plan(scene: ResolvedDialogueScene, index: int) -> dict[str, object]:
    profile = scene.actors[index].profile
    return {
        "schema_version": 8,
        "kind": "dialogue-scene-plan-v8",
        "recipe_version": "dialogue-scene-v8",
        "policy_version": "coming-of-age-nonexplicit-v3",
        "expression_profile": "expression-core-v3",
        "art_request_sha256": scene.art_request_sha256,
        "appearance_id": profile.profile.profile_id,
        "character_profile_ref": profile.ref,
        "character_profile_source_sha256": profile.source_sha256,
        "character_profile_sha256": profile.canonical_sha256,
        "identity_reference_sha256": scene.style_reference.sha256,
        "shared_locks": {
            "identity": "Mio identity",
            "wardrobe": "navy cardigan",
            "pose": "fixed conversational pose",
            "lighting": "soft evening light",
            "style": "polished 2D visual novel",
        },
        "geometry": {
            "canvas": {"width": 1024, "height": 1536},
            "crop": "top-hair-through-waist",
            "slot": "right",
            "safe_bounds": [0.0, 0.0, 1.0, 1.0],
        },
        "states": [
            {
                "id": expression.expression_id,
                "label": expression.label,
                "description": expression.description,
                "direction": expression.direction,
            }
            for expression in scene.actors[index].expressions
        ],
        "prompt_templates": [
            {"id": "profile-neutral-v1", "sha256": TEMPLATE_DIGEST},
            {"id": "profile-expression-edit-v1", "sha256": TEMPLATE_DIGEST},
        ],
    }


def _write_inputs(root: Path) -> str:
    """A completed run directory, including the republished authored plate.

    The bundle refuses a concept whose bytes are not the ones the package
    declared, so the fixture publishes the package's own cover rather than a
    lookalike PNG of the right size.
    """

    package = write_scene_package(root / "package")
    scene = resolve_dialogue_scene(read_scene_document(package), root=package)
    _write_json_pair(root / "request.json", scene.request_bytes)
    (root / "characters").mkdir(exist_ok=True)
    (root / "plans").mkdir(exist_ok=True)
    for index, actor in enumerate(scene.actors):
        _write_json_pair(
            root / f"characters/{actor.asset_prefix}.json",
            canonical_character_profile_json(actor.profile.profile),
        )
        _write_json_pair(
            root / f"plans/{actor.asset_prefix}.json",
            json.dumps(_plan(scene, index)).encode(),
        )
    (root / "scenarios").mkdir(exist_ok=True)
    for scenario in scene.scenarios:
        slug = scenario.declarations.scenario_id.replace("_", "-")
        _write_json_pair(root / f"scenarios/{slug}.json", scenario.program_bytes)
        _write_json_pair(
            root / f"scenarios/{slug}.validation.json",
            json.dumps(scenario.admission.model_dump(mode="json"), sort_keys=True).encode(),
        )
    anchor = materialize_style_anchor(
        StyleModeSelection(
            schema_version=1,
            kind="image_style_selection_v1",
            style_mode="cel_shaded_anime_2d",
        ),
        load_image_style_resources(),
    )
    _write_json_pair(
        root / "style-anchor.json",
        json.dumps(anchor.model_dump(mode="json"), sort_keys=True).encode(),
    )
    # The interface sheets and the records the gate wrote beside them, exactly as a real run
    # leaves them: the bundle reads the measured geometry rather than the declared template.
    ui = root / "ui"
    ui.mkdir()
    for role_name, role in UI_SHEET_ROLES.items():
        family = sheet_family(role)
        canonical, facts = family.canonicalize(ui_sheet(role_name), role)
        _write_image(ui / f"{role_name}.png", canonical)
        (ui / f"{role_name}.validation.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "prepared-ui-atlas-validation-v2",
                    **family.contract(cast(dict[str, object], facts["canonical"])),
                }
            ),
            encoding="utf-8",
        )
    assets = root / "assets"
    assets.mkdir()
    files = {
        "style-plate.png": scene.style_reference.data,
        **{
            f"stage-{stage.stage_id.replace('_', '-')}.png": _png(1672, 941, alpha=False)
            for stage in scene.stages
        },
        **{
            f"{actor.asset_prefix}-{expression.expression_id}.png": _png(1024, 1536, alpha=True)
            for actor in scene.actors
            for expression in actor.expressions
        },
    }
    for name, data in files.items():
        _write_image(assets / name, data)
    return "manifest-test-chroma"


def _write_image(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def _write_json_pair(path: Path, data: bytes) -> None:
    path.write_bytes(data)


@pytest.mark.asyncio
async def test_the_bundle_binds_every_member_by_digest_and_the_anchor_into_its_identity(
    tmp_path: Path,
) -> None:
    tag = _write_inputs(tmp_path)
    first = await dialogue_bundle(tmp_path, tag=tag)
    raw = json.loads(canonical_json_bytes(first))
    assert (raw["schema_version"], raw["kind"]) == (9, "dialogue-scene-bundle-v9")
    assert "sceneData" not in raw and "attempt_ledger" not in raw
    assert raw["scene_data"]["placement"]["framing_zoom"] == 70
    # v9 binds files by path and digest alone; which call made each is the run's record.
    assert set(raw["request"]) == {"path", "sha256"}
    assert first.request.sha256 == content_sha256((tmp_path / "request.json").read_bytes())
    mio = next(actor for actor in first.actors if actor.actor_id == "mio")
    assert mio.plan.sha256 == content_sha256((tmp_path / "plans/mio.json").read_bytes())
    for asset in first.assets:
        assert asset.sha256 == content_sha256((tmp_path / asset.path).read_bytes())
    assert first.recipe_version == "dialogue-scene-v8"
    assert first.scene_data.actors[0].appearance.art_direction == (
        "clean 2D Japanese anime illustration"
    )

    anchor_raw = json.loads((tmp_path / "style-anchor.json").read_text(encoding="utf-8"))
    anchor_raw["resource_sha256"] = "9" * 64
    _write_json_pair(
        tmp_path / "style-anchor.json", json.dumps(anchor_raw, sort_keys=True).encode()
    )
    style_changed = await dialogue_bundle(tmp_path, tag=tag)
    assert style_changed.run_identity_sha256 != first.run_identity_sha256

    plan = json.loads((tmp_path / "plans/mio.json").read_text(encoding="utf-8"))
    plan["shared_locks"]["pose"] = "a different fixed conversational pose"
    _write_json_pair(tmp_path / "plans/mio.json", json.dumps(plan).encode())
    replanned = await dialogue_bundle(tmp_path, tag=tag)
    assert canonical_sha256(replanned) != canonical_sha256(style_changed)


def test_projection_copy_is_cut_on_a_word_boundary_and_never_left_untrimmed() -> None:
    """A hard slice on authored prose is a refusal waiting for the wrong sentence.

    Every persisted string in this contract must be trimmed, so a brief whose
    character limit happened to land on a space produced a value the bundle then
    refused - at the terminal node, after every image in the scene had been drawn
    and paid for. The length of an author's sentence is not something they should
    have to think about, and certainly not something they should discover after a
    run.
    """

    # The exact failure: the cut lands on a space, so the naive slice ends in one.
    brief = "a" * 159 + " tail"
    assert brief[:160].endswith(" ")
    fitted = _fit(brief, 160)
    assert fitted == fitted.strip()
    assert len(fitted) <= 160

    # Alt text may be heard, so it does not end mid-word.
    sentence = "The inside of a service lift with a painted name reversed on it, two client " * 4
    fitted = _fit(sentence, 160)
    assert len(fitted) <= 160
    assert fitted == fitted.strip()
    assert sentence.startswith(fitted)
    assert sentence[len(fitted)] in " ,"

    # A single word longer than the budget still yields something, rather than
    # collapsing a min_length=1 field to the empty string.
    assert _fit("x" * 400, 96) == "x" * 96
    # Short enough to keep whole, and trimmed on the way through.
    assert _fit("  already short  ", 96) == "already short"
