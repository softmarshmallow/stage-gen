from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from the_grain_pipeline.dialogue_scene.identity import canonical_json_bytes, canonical_sha256
from the_grain_pipeline.dialogue_scene.models import DialogueBundle, DialogueSceneDocument
from the_grain_pipeline.dialogue_scene.scene_request import (
    ResolvedDialogueScene,
    parse_dialogue_request,
    read_scene_document,
    resolve_dialogue_scene,
)

from .package import repoint_digests, write_scene_package


def _document(root: Path) -> dict[str, object]:
    return read_scene_document(root)


def _resolved(root: Path) -> ResolvedDialogueScene:
    return resolve_dialogue_scene(_document(root), root=root)


def _parsed(document: dict[str, object]) -> dict[str, object]:
    return parse_dialogue_request(document).model_dump(mode="json", exclude_none=True)


def test_scene_document_is_strict_canonical_and_rejects_camel_case(tmp_path: Path) -> None:
    root = write_scene_package(tmp_path / "pkg")
    document = _document(root)
    parsed = _parsed(document)
    reversed_value = dict(reversed(list(parsed.items())))
    assert canonical_json_bytes(parsed) == canonical_json_bytes(reversed_value)
    assert canonical_sha256(parsed) == canonical_sha256(reversed_value)

    with pytest.raises(ValueError, match="invalid dialogue-scene-v5"):
        _parsed({**document, "kind": "dialogue-theme-request-v3"})
    camel = dict(document)
    camel["sceneBrief"] = camel.pop("scene_brief")
    with pytest.raises(ValueError, match="invalid dialogue-scene-v5"):
        _parsed(camel)
    with pytest.raises(ValueError, match="invalid dialogue-scene-v5"):
        _parsed({**document, "unknown": True})
    with pytest.raises(ValueError, match="content policy"):
        _parsed({**document, "scene_brief": "A minor stays behind after the seminar"})


def test_scene_document_defaults_to_native_alpha(tmp_path: Path) -> None:
    document = _document(write_scene_package(tmp_path / "pkg"))
    explicit = DialogueSceneDocument.model_validate({**document, "transparency_mode": "native"})
    assert explicit.transparency_mode == "native"

    omitted = dict(document)
    del omitted["transparency_mode"]
    assert DialogueSceneDocument.model_validate(omitted).transparency_mode == "native"


def test_the_scene_binds_its_narrative_as_a_digest_bound_member(tmp_path: Path) -> None:
    """The scene carries no lines of its own; it names the scenario that does."""

    document = _document(write_scene_package(tmp_path / "pkg"))
    bindings = document["scenarios"]
    assert isinstance(bindings, list)
    binding = bindings[0]
    assert isinstance(binding, dict)
    assert binding["ref"] == "scenarios/after_seminar.toml"
    with pytest.raises(ValueError, match="invalid dialogue-scene-v5"):
        _parsed({**document, "scenarios": [{**binding, "ref": "../elsewhere.toml"}]})
    with pytest.raises(ValueError, match="invalid dialogue-scene-v5"):
        _parsed({**document, "scenarios": []})
    # The same scenario bound twice is an authoring slip, not a way to pay twice.
    with pytest.raises(ValueError, match="invalid dialogue-scene-v5"):
        _parsed({**document, "scenarios": [binding, dict(binding)]})
    with pytest.raises(ValueError, match="invalid dialogue-scene-v5"):
        _parsed({**document, "dialogue": [{"id": "a", "speaker": "Mio", "text": "Hi."}]})


def test_a_profile_that_is_not_a_package_member_is_refused(tmp_path: Path) -> None:
    """Each cast binding names a member by relative path; anything else escapes."""

    document = _document(write_scene_package(tmp_path / "pkg"))
    cast = document["cast"]
    assert isinstance(cast, list)
    first = cast[0]
    assert isinstance(first, dict)
    binding = first["character_profile"]
    assert isinstance(binding, dict)

    def with_first(profile: object) -> dict[str, object]:
        return {**document, "cast": [{**first, "character_profile": profile}, cast[1]]}

    with pytest.raises(ValueError, match="invalid dialogue-scene-v5"):
        _parsed(with_first({"ref": "characters/mio.toml"}))
    with pytest.raises(ValueError, match="invalid dialogue-scene-v5"):
        _parsed(with_first({**binding, "ref": "../elsewhere.toml"}))
    with pytest.raises(ValueError, match="invalid dialogue-scene-v5"):
        _parsed(with_first({**binding, "ref": "characters/mio.json"}))
    camel = dict(binding)
    camel["sourceSha256"] = camel.pop("source_sha256")
    with pytest.raises(ValueError, match="invalid dialogue-scene-v5"):
        _parsed(with_first(camel))


def test_an_underage_character_profile_is_refused(tmp_path: Path) -> None:
    root = write_scene_package(tmp_path / "pkg")
    profile = root / "characters/mio.toml"
    profile.write_text(
        profile.read_text(encoding="utf-8").replace("age_years = 23", "age_years = 17"),
        encoding="utf-8",
    )
    document = _document(root)
    cast = document["cast"]
    assert isinstance(cast, list)
    first = cast[0]
    assert isinstance(first, dict)
    binding = dict(first["character_profile"])
    binding["source_sha256"] = hashlib.sha256(profile.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="requires an adult age"):
        resolve_dialogue_scene(
            {**document, "cast": [{**first, "character_profile": binding}, cast[1]]}, root=root
        )


def test_a_reference_that_no_longer_matches_its_digest_is_refused(tmp_path: Path) -> None:
    root = write_scene_package(tmp_path / "pkg")
    (root / "references/cover.png").write_bytes(b"\x89PNG\r\n\x1a\nnot the authored bytes")
    with pytest.raises(ValueError, match="does not match its authored digest"):
        resolve_dialogue_scene(_document(root), root=root)


def test_a_reference_declared_but_never_used_is_refused(tmp_path: Path) -> None:
    """An unused declaration is a file the manifest would name for nothing."""

    root = write_scene_package(tmp_path / "pkg")
    document = _document(root)
    references = document["references"]
    assert isinstance(references, list)
    spare = {**references[0], "reference_id": "spare", "source": "references/spare.png"}
    with pytest.raises(ValueError, match="never used"):
        _parsed({**document, "references": [*references, spare]})
    with pytest.raises(ValueError, match="undeclared reference"):
        _parsed({**document, "style_reference_id": "missing"})


def test_two_scenarios_that_disagree_about_one_stage_are_refused(tmp_path: Path) -> None:
    """One stage_id is one backdrop, so two briefs for it is an authoring error.

    Refused offline rather than reconciled: which of the two briefs the single
    image should be drawn from is not a question the pipeline may answer, and
    silently taking the first-bound scenario's would make the art depend on the
    binding order.
    """

    package = write_scene_package(tmp_path / "pkg", second_scenario=True)
    scenario = package / "scenarios/late_shift.toml"
    scenario.write_text(
        scenario.read_text(encoding="utf-8").replace(
            "An original empty evening study lounge, warm lamps, no people",
            "An original empty evening study lounge with the lamps already out",
        ),
        encoding="utf-8",
    )
    _repoint_second_digest(package)
    with pytest.raises(ValueError) as refusal:
        _resolved(package)
    # The refusal has to name both sides. Keeping the first-bound brief and
    # discarding the other would make the drawn room a function of the order the
    # scene happens to list its scenarios in, and lose a writer's work silently.
    message = str(refusal.value)
    assert "stage lounge" in message
    assert "after_seminar: 'An original empty evening study lounge, warm lamps" in message
    assert "late_shift: 'An original empty evening study lounge with the lamps already out'" in (
        message
    )


def _repoint_second_digest(package: Path) -> None:
    """Re-pin the second scenario after a test edits it, and nothing else."""

    scenario = package / "scenarios/late_shift.toml"
    digest = hashlib.sha256(scenario.read_bytes()).hexdigest()
    scene = package / "scene.toml"
    scene.write_text(
        re.sub(
            r'(\[\[scenarios\]\]\n(?:.*\n)*?ref = "scenarios/late_shift\.toml"\n'
            r'source_sha256 = )"[0-9a-f]{64}"',
            lambda match: f'{match.group(1)}"{digest}"',
            scene.read_text(encoding="utf-8"),
            count=1,
        ),
        encoding="utf-8",
    )


def _ui_role_value(role: str, cell_count: int) -> dict[str, Any]:
    """One published atlas role, shaped exactly as the producer's gate emits it."""

    states = ["default"] if cell_count == 1 else ["normal", "hover", "pressed", "disabled"]
    layout = "nine_slice_panel_1024_v1" if cell_count == 1 else "nine_slice_button_sheet_4x1024_v1"
    return {
        "role": role,
        "layout": layout,
        "scale_mode": "nine_slice",
        "alpha_policy": "transparent_exterior_opaque_body_v1",
        "band_fill": "tile",
        "draw_scale": 2,
        "canvas": {"width": 1024, "height": 1024},
        "insets": {"left": 96, "top": 96, "right": 96, "bottom": 96},
        "cells": [
            {
                "state": state,
                "cell": {"x": 160, "y": 32 + index * 240, "width": 704, "height": 224},
                "content_rect": {"x": 256, "y": 128 + index * 240, "width": 512, "height": 32},
                "safe_rect": {"x": 256, "y": 128 + index * 240, "width": 512, "height": 32},
            }
            for index, state in enumerate(states)
        ],
        "asset_id": f"ui-{role.replace('_', '-')}",
    }


def _ui_icon_value() -> dict[str, Any]:
    """The published icon grid, shaped exactly as the producer's gate emits it."""

    cells = []
    for index in range(16):
        row, column = divmod(index, 4)
        x, y = 24 + column * 248, 24 + row * 248
        cells.append(
            {
                "glyph": _ICON_GLYPHS[index],
                "cell": {"x": x, "y": y, "width": 232, "height": 232},
                "glyph_rect": {"x": x + 46, "y": y + 46, "width": 140, "height": 140},
            }
        )
    return {
        "role": "preview_icons",
        "layout": "icon_grid_4x4_1024_preview_v1",
        "scale_mode": "fixed",
        "alpha_policy": "transparent_exterior_opaque_glyph_v1",
        "draw_scale": 2,
        "canvas": {"width": 1024, "height": 1024},
        "cell_size": 232,
        "cells": cells,
        "asset_id": "ui-preview-icons",
    }


_ICON_GLYPHS = (
    "play",
    "pause",
    "close",
    "menu",
    "gear",
    "home",
    "retry",
    "check",
    "search",
    "hand",
    "heart",
    "star",
    "arrow_left",
    "arrow_right",
    "sound_on",
    "sound_off",
)


def _bundle_value(root: Path) -> dict[str, Any]:
    """A structurally valid bundle for the fixture package, built from its own scene.

    Built rather than hand-written: a literal would have to be rewritten by hand
    every time the cast or the stage list changes, and a stale literal is exactly
    the thing a strictness test cannot afford.
    """

    resolved = _resolved(root)
    program = json.loads(resolved.scenarios[0].program_bytes)
    actors = list(resolved.actors)

    def bundle_file(path: str) -> dict[str, object]:
        return {"path": path, "sha256": "a" * 64}

    media = {
        "style": {"width": 1024, "height": 1536, "alpha": False},
        "background": {"width": 1672, "height": 941, "alpha": False},
        "expression": {"width": 1024, "height": 1536, "alpha": True},
        "ui": {"width": 1024, "height": 1024, "alpha": True},
    }

    def artifact(
        asset_id: str, role: str, path: str, state: str | None, actor: str | None
    ) -> dict[str, Any]:
        return {
            "id": asset_id,
            "role": role,
            "actor_id": actor,
            "state": state,
            "path": path,
            "sha256": "c" * 64,
            "bytes": 1,
            "media": {"mime_type": "image/png", **media[role]},
        }

    return {
        "schema_version": 9,
        "kind": "dialogue-scene-bundle-v9",
        "recipe": "dialogue-scene",
        "recipe_version": "dialogue-scene-v8",
        "tag": "seminar-hall",
        "game_id": "seminar_hall",
        "run_identity_sha256": "e" * 64,
        "request": bundle_file("request.json"),
        "actors": [
            {
                "actor_id": actor.actor_id,
                "character_profile": bundle_file(f"characters/{actor.asset_prefix}.json"),
                "character_profile_binding": {
                    "schema_version": 1,
                    "kind": "character-profile-binding-v1",
                    "ref": actor.profile.ref,
                    "source_sha256": actor.profile.source_sha256,
                },
                "character_profile_sha256": actor.profile.canonical_sha256,
                "plan": bundle_file(f"plans/{actor.asset_prefix}.json"),
            }
            for actor in actors
        ],
        "scenarios": [
            {
                "scenario_id": "after_seminar",
                "binding": {
                    "schema_version": 1,
                    "kind": "scenario-binding-v1",
                    "ref": "scenarios/after_seminar.toml",
                    "source_sha256": resolved.request.scenarios[0].source_sha256,
                },
                "program": bundle_file("scenarios/after-seminar.json"),
                "validation": bundle_file("scenarios/after-seminar.validation.json"),
                "program_sha256": "f" * 64,
            }
        ],
        "style_reference": bundle_file("assets/style-plate.png"),
        "style_reference_source": "references/cover.png",
        "assets": [
            artifact("style-plate", "style", "assets/style-plate.png", None, None),
            *[
                artifact(
                    stage["stage_id"].replace("_", "-"),
                    "background",
                    f"assets/stage-{stage['stage_id'].replace('_', '-')}.png",
                    None,
                    None,
                )
                for stage in program["stages"]
            ],
            *[
                artifact(
                    f"{actor.asset_prefix}-{state}",
                    "expression",
                    f"assets/{actor.asset_prefix}-{state}.png",
                    state,
                    actor.actor_id,
                )
                for actor in actors
                for expression in actor.expressions
                for state in (expression.expression_id,)
            ],
            *[
                artifact(f"ui-{role.replace('_', '-')}", "ui", f"ui/{role}.png", None, None)
                for role in ("panel_frame", "button_rect", "preview_icons")
            ],
        ],
        "scene_data": {
            "scene_id": "seminar-hall-scene",
            "title": "After the Seminar",
            "scene_label": "A student stays behind",
            "style_asset_id": "style-plate",
            "ui": {
                **{
                    role: _ui_role_value(role, states_count)
                    for role, states_count in (("panel_frame", 1), ("button_rect", 4))
                },
                "preview_icons": _ui_icon_value(),
            },
            "stages": [
                {
                    "stage_id": stage["stage_id"],
                    "asset_id": stage["stage_id"].replace("_", "-"),
                    "alt": stage["brief"][:160],
                }
                for stage in program["stages"]
            ],
            "actors": [
                {
                    "actor_id": actor.actor_id,
                    "appearance": {
                        "id": actor.profile.profile.profile_id,
                        "label": actor.profile.profile.display_name,
                        "age": actor.profile.profile.age_years,
                        "role": "A student",
                        "tagline": "A student",
                        "description": actor.profile.profile.description,
                        "visual_identity": actor.profile.profile.visual_identity,
                        "art_direction": "cel shaded anime",
                    },
                    "expression_variants": [
                        {
                            "id": f"{actor.asset_prefix}-{state}",
                            "asset_id": f"{actor.asset_prefix}-{state}",
                            "appearance_id": actor.profile.profile.profile_id,
                            "state": state,
                            "label": expression.label,
                            "description": expression.description,
                            "alt": f"{actor.display_name}, {expression.label.lower()}",
                        }
                        for expression in actor.expressions
                        for state in (expression.expression_id,)
                    ],
                }
                for actor in actors
            ],
            "placement": {"framing_zoom": 70, "source_framing_zoom": 70},
            "available_states": sorted(
                {expression.expression_id for actor in actors for expression in actor.expressions}
            ),
            "scenarios": [program],
        },
        "review": {"status": "pending", "path": None, "sha256": None},
        "rights": {"aggregate": "unreviewed", "publication_authorized": False},
    }


def test_bundle_paths_rights_and_review_are_strict(tmp_path: Path) -> None:
    raw = _bundle_value(write_scene_package(tmp_path / "pkg"))
    assert DialogueBundle.model_validate(raw).rights.publication_authorized is False

    for version in (5, 8):
        legacy = {**raw, "schema_version": version, "kind": f"dialogue-scene-bundle-v{version}"}
        with pytest.raises(ValidationError):
            DialogueBundle.model_validate(legacy)
    # v9 binds files by path and digest alone: a v8 provenance field is refused.
    with_provenance = {**raw, "request": {**raw["request"], "provenance_path": "x.meta.json"}}
    with pytest.raises(ValidationError):
        DialogueBundle.model_validate(with_provenance)

    camel = {**raw, "runIdentitySha256": raw["run_identity_sha256"]}
    del camel["run_identity_sha256"]
    with pytest.raises(ValidationError):
        DialogueBundle.model_validate(camel)

    # An actor in the inventory that scene_data does not stage, and vice versa,
    # is refused: the two halves name one cast or the bundle is inconsistent.
    mismatched = {**raw, "actors": raw["actors"][:1]}
    with pytest.raises(ValidationError, match="name the same cast"):
        DialogueBundle.model_validate(mismatched)

    assets = raw["assets"]
    assert isinstance(assets, list)
    assets[0]["path"] = "../escape.png"
    with pytest.raises(ValidationError, match="portable relative"):
        DialogueBundle.model_validate(raw)


def test_canonical_serialization_is_standards_compliant_json(tmp_path: Path) -> None:
    document = read_scene_document(write_scene_package(tmp_path / "pkg"))
    request = DialogueSceneDocument.model_validate(document)
    assert json.loads(canonical_json_bytes(request)) == request.model_dump(
        mode="json", exclude_none=True
    )


def test_a_scenario_that_drifted_from_its_digest_is_refused(tmp_path: Path) -> None:
    """The scene pins the scenario, which pins its script: one hash, whole narrative."""

    package = write_scene_package(tmp_path / "pkg")
    scenario = package / "scenarios/after_seminar.toml"
    scenario.write_text(
        scenario.read_text(encoding="utf-8").replace("revision = 1", "revision = 2"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="does not match its authored digest"):
        _resolved(package)


def test_the_narrative_is_admitted_before_any_art_is_planned(tmp_path: Path) -> None:
    """An unfinishable scenario must cost nothing, so it is refused during resolve."""

    package = write_scene_package(tmp_path / "pkg")
    script = package / "scenarios/after_seminar.scenario"
    script.write_text(
        script.read_text(encoding="utf-8") + "\n\nlabel orphan:\n    end went_home\n",
        encoding="utf-8",
    )
    repoint_digests(package)
    with pytest.raises(ValueError, match="labels no path reaches: orphan"):
        _resolved(package)
