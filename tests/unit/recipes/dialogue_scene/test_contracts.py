from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from stage_gen.config import StageGenConfig
from stage_gen.recipes.dialogue_scene.identity import canonical_json_bytes, canonical_sha256
from stage_gen.recipes.dialogue_scene.models import DialogueBundle, DialogueSceneDocument
from stage_gen.recipes.dialogue_scene.scene_graph import (
    DialogueSceneGraph,
    build_dialogue_scene_graph,
    dialogue_graph_profile,
)
from stage_gen.recipes.dialogue_scene.scene_request import (
    ResolvedDialogueScene,
    parse_dialogue_request,
    read_scene_document,
    resolve_dialogue_scene,
)

from .package import write_scene_package


def _document(root: Path) -> dict[str, object]:
    return read_scene_document(root)


def _resolved(root: Path) -> ResolvedDialogueScene:
    return resolve_dialogue_scene(_document(root), root=root)


def _graph(root: Path) -> DialogueSceneGraph:
    return build_dialogue_scene_graph(
        _resolved(root), profile=dialogue_graph_profile(StageGenConfig())
    )


def _parsed(document: dict[str, object]) -> dict[str, object]:
    return parse_dialogue_request(document).model_dump(mode="json", exclude_none=True)


def _repoint_digests(package: Path) -> None:
    """Re-pin an edited script, the way `stage-gen scenario check --write-digest` does.

    Editing prose invalidates two recorded hashes: the scenario's binding of its
    script, and the scene's binding of the scenario. A test that edits a line has
    to move both, or it proves a digest mismatch rather than what it meant to.
    """

    scenario = package / "scenarios/after_seminar.toml"
    script = package / "scenarios/after_seminar.scenario"
    scenario.write_text(
        re.sub(
            r'script_sha256 = "[0-9a-f]{64}"',
            f'script_sha256 = "{hashlib.sha256(script.read_bytes()).hexdigest()}"',
            scenario.read_text(encoding="utf-8"),
            count=1,
        ),
        encoding="utf-8",
    )
    scene = package / "scene.toml"
    scenario_digest = hashlib.sha256(scenario.read_bytes()).hexdigest()
    scene.write_text(
        re.sub(
            r'(\[scenario\][^\[]*?source_sha256 = )"[0-9a-f]{64}"',
            lambda match: f'{match.group(1)}"{scenario_digest}"',
            scene.read_text(encoding="utf-8"),
            count=1,
            flags=re.DOTALL,
        ),
        encoding="utf-8",
    )


def test_scene_document_is_strict_canonical_and_rejects_camel_case(tmp_path: Path) -> None:
    root = write_scene_package(tmp_path / "pkg")
    document = _document(root)
    parsed = _parsed(document)
    reversed_value = dict(reversed(list(parsed.items())))
    assert canonical_json_bytes(parsed) == canonical_json_bytes(reversed_value)
    assert canonical_sha256(parsed) == canonical_sha256(reversed_value)

    with pytest.raises(ValueError, match="invalid dialogue-scene-v3"):
        _parsed({**document, "kind": "dialogue-theme-request-v3"})
    camel = dict(document)
    camel["sceneBrief"] = camel.pop("scene_brief")
    with pytest.raises(ValueError, match="invalid dialogue-scene-v3"):
        _parsed(camel)
    with pytest.raises(ValueError, match="invalid dialogue-scene-v3"):
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
    binding = document["scenario"]
    assert isinstance(binding, dict)
    assert binding["ref"] == "scenarios/after_seminar.toml"
    with pytest.raises(ValueError, match="invalid dialogue-scene-v3"):
        _parsed({**document, "scenario": {**binding, "ref": "../elsewhere.toml"}})
    with pytest.raises(ValueError, match="invalid dialogue-scene-v3"):
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

    with pytest.raises(ValueError, match="invalid dialogue-scene-v3"):
        _parsed(with_first({"ref": "characters/mio.toml"}))
    with pytest.raises(ValueError, match="invalid dialogue-scene-v3"):
        _parsed(with_first({**binding, "ref": "../elsewhere.toml"}))
    with pytest.raises(ValueError, match="invalid dialogue-scene-v3"):
        _parsed(with_first({**binding, "ref": "characters/mio.json"}))
    camel = dict(binding)
    camel["sourceSha256"] = camel.pop("source_sha256")
    with pytest.raises(ValueError, match="invalid dialogue-scene-v3"):
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


def test_recipe_declares_locked_dependency_dag(tmp_path: Path) -> None:
    graph = _graph(write_scene_package(tmp_path / "pkg"))
    ids = [node.node_id for node in graph.nodes]
    assert ids[:5] == [
        "scene-request",
        "scene-scenario",
        "scene-style-select",
        "scene-style-plate",
        "stage-lounge",
    ]
    # One backdrop per declared stage, and a full expression fan-out per actor.
    assert [node_id for node_id in ids if node_id.startswith("stage-")] == ["stage-lounge"]
    for actor in ("mio", "ren"):
        assert f"actor-{actor}-profile" in ids
        assert f"actor-{actor}-plan" in ids
        assert f"actor-{actor}-neutral" in ids
        for state in ("delighted", "flustered", "concerned"):
            assert f"actor-{actor}-{state}" in ids
        for state in ("neutral", "delighted", "flustered", "concerned"):
            assert f"actor-{actor}-canonicalize-{state}" in ids
    assert graph.terminal_node_id == "scene-bundle"
    assert graph.node("scene-bundle").depends_on == (
        "scene-scenario",
        "stage-lounge",
        *(
            f"actor-{actor}-canonicalize-{state}"
            for actor in ("mio", "ren")
            for state in ("neutral", "delighted", "flustered", "concerned")
        ),
        # The shared nine-slice interface is a terminal like any other: the bundle cannot be
        # written until the panel and the button have been drawn, gated, and judged.
        "ui-panel_frame-review",
        "ui-button_rect-review",
    )


def test_the_authored_plate_is_published_not_generated(tmp_path: Path) -> None:
    """Nothing in the graph paints the art direction, and the plan says whose it is.

    The concept node became local when the plate stopped being generated, so the
    scene buys one fewer image than it used to; every image node still keys on
    the plate's bytes, so replacing the file re-bills the scene deliberately.
    """

    root = write_scene_package(tmp_path / "pkg")
    resolved = _resolved(root)
    graph = _graph(root)
    plate = graph.node("scene-style-plate")
    assert plate.operation == "local"
    assert plate.card is not None
    authored = {entry.label: entry for entry in plate.card.authored_inputs}
    assert authored["cover"].ref == "references/cover.png"
    assert authored["cover"].sha256 == resolved.style_reference.sha256

    # One backdrop, four expressions for each of two actors, and the two UI atlas sheets.
    image_nodes = [node for node in graph.nodes if node.operation == "image_generation"]
    assert len(image_nodes) == 11
    for node in image_nodes:
        assert resolved.style_reference.sha256 in node.input_sha256, node.node_id

    # Every backdrop is drawn against the same plate the cast stands in.
    background = graph.node("stage-lounge")
    assert background.card is not None
    assert any(
        reference.node_id == "scene-style-plate" for reference in background.card.reference_inputs
    )

    # Only the actor that binds the plate as its own is held to its identity.
    mio = graph.node("actor-mio-neutral")
    ren = graph.node("actor-ren-neutral")
    assert mio.card is not None and ren.card is not None
    assert len(mio.card.authored_inputs) == 2
    assert len(ren.card.authored_inputs) == 1


def test_each_derived_expression_is_its_own_node_off_the_neutral_source(tmp_path: Path) -> None:
    # The stage pipeline this replaces derived three expressions inside one stage and
    # canonicalized four inside another, so a single bad state failed the whole batch.
    graph = _graph(write_scene_package(tmp_path / "pkg"))
    for actor in ("mio", "ren"):
        for state in ("delighted", "flustered", "concerned"):
            assert graph.node(f"actor-{actor}-{state}").depends_on == (f"actor-{actor}-neutral",)
            assert graph.node(f"actor-{actor}-canonicalize-{state}").depends_on == (
                f"actor-{actor}-{state}",
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


def _bundle_value(root: Path) -> dict[str, Any]:
    """A structurally valid bundle for the fixture package, built from its own scene.

    Built rather than hand-written: a literal would have to be rewritten by hand
    every time the cast or the stage list changes, and a stale literal is exactly
    the thing a strictness test cannot afford.
    """

    resolved = _resolved(root)
    program = json.loads(resolved.scenario.program_bytes)
    states = ("neutral", "delighted", "flustered", "concerned")
    actors = list(resolved.actors)

    def bundle_file(path: str) -> dict[str, object]:
        return {
            "path": path,
            "sha256": "a" * 64,
            "provenance_path": f"{path}.meta.json",
            "provenance_sha256": "b" * 64,
        }

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
            "provenance_path": f"{path}.meta.json",
            "provenance_sha256": "d" * 64,
            "selected_attempt": 1,
        }

    return {
        "schema_version": 7,
        "kind": "dialogue-scene-bundle-v7",
        "recipe": "dialogue-scene",
        "recipe_version": "dialogue-scene-v7",
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
        "scenario": bundle_file("scenario.json"),
        "scenario_validation": bundle_file("scenario.validation.json"),
        "scenario_binding": {
            "schema_version": 1,
            "kind": "scenario-binding-v1",
            "ref": "scenarios/after_seminar.toml",
            "source_sha256": resolved.request.scenario.source_sha256,
        },
        "scenario_sha256": "f" * 64,
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
                for state in states
            ],
            *[
                artifact(f"ui-{role.replace('_', '-')}", "ui", f"ui/{role}.png", None, None)
                for role in ("panel_frame", "button_rect")
            ],
        ],
        "attempt_ledger": {"path": "attempts.json", "sha256": "1" * 64},
        "scene_data": {
            "scene_id": "seminar-hall-scene",
            "title": "After the Seminar",
            "scene_label": "A student stays behind",
            "style_asset_id": "style-plate",
            "ui": {
                role: _ui_role_value(role, states_count)
                for role, states_count in (("panel_frame", 1), ("button_rect", 4))
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
                            "label": state.title(),
                            "description": f"A {state} expression",
                            "alt": f"{actor.display_name} looking {state}",
                        }
                        for state in states
                    ],
                }
                for actor in actors
            ],
            "placement": {"framing_zoom": 70, "source_framing_zoom": 70},
            "available_states": list(states),
            "scenario": program,
        },
        "review": {"status": "pending", "path": None, "sha256": None},
        "rights": {"aggregate": "unreviewed", "publication_authorized": False},
    }


def test_bundle_paths_rights_and_review_are_strict(tmp_path: Path) -> None:
    raw = _bundle_value(write_scene_package(tmp_path / "pkg"))
    assert DialogueBundle.model_validate(raw).rights.publication_authorized is False

    legacy = {**raw, "schema_version": 5, "kind": "dialogue-scene-bundle-v5"}
    with pytest.raises(ValidationError):
        DialogueBundle.model_validate(legacy)

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
    _repoint_digests(package)
    with pytest.raises(ValueError, match="labels no path reaches: orphan"):
        _resolved(package)


def test_rewording_a_line_does_not_re_bill_a_single_image(tmp_path: Path) -> None:
    """The narrative is deliberately outside every image node's cache identity.

    A generated plate is a function of the look, the profile and the backdrop
    direction; it is not a function of what anybody says. If the whole document
    rode the image cache key, editing one line of dialogue would re-bill five
    provider images that would come back byte-identical.
    """

    original = _graph(write_scene_package(tmp_path / "before"))
    package = write_scene_package(tmp_path / "after")
    script = package / "scenarios/after_seminar.scenario"
    script.write_text(
        script.read_text(encoding="utf-8").replace(
            "I hoped you would stay after the seminar.",
            "I did hope you would stay after the seminar.",
        ),
        encoding="utf-8",
    )
    _repoint_digests(package)
    edited = _graph(package)

    art_nodes = [
        node.node_id for node in original.nodes if node.node_id.startswith(("stage-", "actor-"))
    ]
    assert art_nodes, "the fixture must contain generated art"
    for node_id in art_nodes:
        assert original.node(node_id).cache_key == edited.node(node_id).cache_key, node_id
    # The narrative did change, and the nodes that carry it say so.
    assert original.node("scene-scenario").cache_key != edited.node("scene-scenario").cache_key
    assert original.node("scene-bundle").cache_key != edited.node("scene-bundle").cache_key
