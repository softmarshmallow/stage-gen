from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

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

    scenario = package / "scenario.toml"
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

    with pytest.raises(ValueError, match="invalid dialogue-scene-v2"):
        _parsed({**document, "kind": "dialogue-theme-request-v3"})
    camel = dict(document)
    camel["sceneBrief"] = camel.pop("scene_brief")
    with pytest.raises(ValueError, match="invalid dialogue-scene-v2"):
        _parsed(camel)
    with pytest.raises(ValueError, match="invalid dialogue-scene-v2"):
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
    assert binding["ref"] == "scenario.toml"
    with pytest.raises(ValueError, match="invalid dialogue-scene-v2"):
        _parsed({**document, "scenario": {**binding, "ref": "../elsewhere.toml"}})
    with pytest.raises(ValueError, match="invalid dialogue-scene-v2"):
        _parsed({**document, "dialogue": [{"id": "a", "speaker": "Mio", "text": "Hi."}]})


def test_a_profile_that_is_not_a_package_member_is_refused(tmp_path: Path) -> None:
    """The binding names a member by relative path; anything else leaves the package."""

    document = _document(write_scene_package(tmp_path / "pkg"))
    binding = document["character_profile"]
    assert isinstance(binding, dict)
    with pytest.raises(ValueError, match="invalid dialogue-scene-v2"):
        _parsed({**document, "character_profile": {"ref": "character.toml"}})
    # The binding refuses escape itself; the document refuses a member that is
    # not a profile at all, so neither check depends on the other holding.
    with pytest.raises(ValueError, match="parent segments"):
        _parsed({**document, "character_profile": {**binding, "ref": "../elsewhere.toml"}})
    with pytest.raises(ValueError, match="package-relative TOML member"):
        _parsed({**document, "character_profile": {**binding, "ref": "character.json"}})
    camel = dict(binding)
    camel["sourceSha256"] = camel.pop("source_sha256")
    with pytest.raises(ValueError, match="invalid dialogue-scene-v2"):
        _parsed({**document, "character_profile": camel})


def test_an_underage_character_profile_is_refused(tmp_path: Path) -> None:
    """The age floor is the legal adult line, and it is enforced offline."""

    root = write_scene_package(tmp_path / "pkg")
    source = (root / "character.toml").read_text(encoding="utf-8")
    (root / "character.toml").write_bytes(
        source.replace("age_years = 23", "age_years = 16").encode()
    )
    document = _document(root)
    binding = document["character_profile"]
    assert isinstance(binding, dict)
    binding["source_sha256"] = hashlib.sha256((root / "character.toml").read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="adult age from 18"):
        resolve_dialogue_scene(document, root=root)


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
        _parsed({**document, "identity_reference_id": "missing"})


def test_recipe_declares_locked_dependency_dag(tmp_path: Path) -> None:
    graph = _graph(write_scene_package(tmp_path / "pkg"))
    assert [node.node_id for node in graph.nodes] == [
        "scene-request",
        "scene-scenario",
        "scene-profile-resolve",
        "scene-style-select",
        "scene-concept",
        "scene-plan",
        "scene-background",
        "scene-expression-neutral",
        "scene-expression-delighted",
        "scene-expression-flustered",
        "scene-expression-concerned",
        "scene-canonicalize-neutral",
        "scene-canonicalize-delighted",
        "scene-canonicalize-flustered",
        "scene-canonicalize-concerned",
        "scene-bundle",
    ]
    assert graph.terminal_node_id == "scene-bundle"
    assert graph.node("scene-bundle").depends_on == (
        "scene-scenario",
        "scene-background",
        "scene-canonicalize-neutral",
        "scene-canonicalize-delighted",
        "scene-canonicalize-flustered",
        "scene-canonicalize-concerned",
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
    concept = graph.node("scene-concept")
    assert concept.operation == "local"
    assert concept.card is not None
    authored = {entry.label: entry for entry in concept.card.authored_inputs}
    assert authored["cover"].ref == "references/cover.png"
    assert authored["cover"].sha256 == resolved.identity_reference.sha256

    image_nodes = [node for node in graph.nodes if node.operation == "image_generation"]
    assert len(image_nodes) == 5
    for node in image_nodes:
        assert resolved.identity_reference.sha256 in node.input_sha256, node.node_id

    # The backdrop is drawn against the same plate the character stands in.
    background = graph.node("scene-background")
    assert background.card is not None
    assert any(
        reference.node_id == "scene-concept" for reference in background.card.reference_inputs
    )


def test_each_derived_expression_is_its_own_node_off_the_neutral_source(tmp_path: Path) -> None:
    # The stage pipeline this replaces derived three expressions inside one stage and
    # canonicalized four inside another, so a single bad state failed the whole batch.
    graph = _graph(write_scene_package(tmp_path / "pkg"))
    for state in ("delighted", "flustered", "concerned"):
        assert graph.node(f"scene-expression-{state}").depends_on == ("scene-expression-neutral",)
        assert graph.node(f"scene-canonicalize-{state}").depends_on == (
            f"scene-expression-{state}",
        )


def test_bundle_paths_rights_and_review_are_strict() -> None:
    raw: dict[str, object] = {
        "schema_version": 5,
        "kind": "dialogue-scene-bundle-v5",
        "recipe": "dialogue-scene",
        "recipe_version": "dialogue-scene-v6",
        "tag": "demo",
        "game_id": "seminar_hall",
        "run_identity_sha256": "a" * 64,
        "request": {
            "path": "request.json",
            "sha256": "b" * 64,
            "provenance_path": "request.json.meta.json",
            "provenance_sha256": "1" * 64,
        },
        "plan": {
            "path": "plan.json",
            "sha256": "c" * 64,
            "provenance_path": "plan.json.meta.json",
            "provenance_sha256": "2" * 64,
        },
        "character_profile": {
            "path": "character-profile.json",
            "sha256": "5" * 64,
            "provenance_path": "character-profile.json.meta.json",
            "provenance_sha256": "6" * 64,
        },
        "character_profile_binding": {
            "schema_version": 1,
            "kind": "character-profile-binding-v1",
            "ref": "character.toml",
            "source_sha256": "7" * 64,
        },
        "character_profile_sha256": "5" * 64,
        "identity_reference": {
            "path": "assets/concept.png",
            "sha256": "d" * 64,
            "provenance_path": "assets/concept.png.meta.json",
            "provenance_sha256": "e" * 64,
        },
        "identity_reference_source": "references/cover.png",
        "assets": [
            {
                "id": "concept",
                "role": "concept",
                "state": None,
                "path": "assets/concept.png",
                "sha256": "d" * 64,
                "bytes": 1,
                "media": {
                    "mime_type": "image/png",
                    "width": 1024,
                    "height": 1536,
                    "alpha": False,
                },
                "provenance_path": "assets/concept.png.meta.json",
                "provenance_sha256": "e" * 64,
                "selected_attempt": 0,
            },
            {
                "id": "background",
                "role": "background",
                "state": None,
                "path": "assets/background.png",
                "sha256": "3" * 64,
                "bytes": 1,
                "media": {
                    "mime_type": "image/png",
                    "width": 1672,
                    "height": 941,
                    "alpha": False,
                },
                "provenance_path": "assets/background.png.meta.json",
                "provenance_sha256": "4" * 64,
                "selected_attempt": 1,
            },
            *[
                {
                    "id": f"mio-{state}",
                    "role": "expression",
                    "state": state,
                    "path": f"assets/expression-{state}.png",
                    "sha256": "d" * 64,
                    "bytes": 1,
                    "media": {
                        "mime_type": "image/png",
                        "width": 1024,
                        "height": 1536,
                        "alpha": True,
                    },
                    "provenance_path": f"assets/expression-{state}.png.meta.json",
                    "provenance_sha256": "e" * 64,
                    "selected_attempt": 1,
                }
                for state in ("neutral", "delighted", "flustered", "concerned")
            ],
        ],
        "attempt_ledger": {"path": "attempts.json", "sha256": "f" * 64},
        "scenario": {
            "path": "scenario.json",
            "sha256": "1" * 64,
            "provenance_path": "scenario.json.meta.json",
            "provenance_sha256": "2" * 64,
        },
        "scenario_validation": {
            "path": "scenario.validation.json",
            "sha256": "3" * 64,
            "provenance_path": "scenario.validation.json.meta.json",
            "provenance_sha256": "4" * 64,
        },
        "scenario_binding": {
            "schema_version": 1,
            "kind": "scenario-binding-v1",
            "ref": "scenario.toml",
            "source_sha256": "5" * 64,
        },
        "scenario_sha256": "1" * 64,
        "scene_data": {
            "scene_id": "mio-scene",
            "title": "Study lounge",
            "scene_label": "Study lounge",
            "concept_asset_id": "concept",
            "background": {"asset_id": "background", "alt": "Study lounge"},
            "appearance": {
                "id": "mio",
                "label": "Mio",
                "age": 23,
                "role": "Final-year student",
                "tagline": "Final-year student",
                "description": "Young woman in a navy cardigan",
                "visual_identity": "Young woman in a navy cardigan",
                "art_direction": "Original visual novel art",
            },
            "placement": {"slot": "right", "framing_zoom": 70, "source_framing_zoom": 70},
            "available_states": ["neutral", "delighted", "flustered", "concerned"],
            "expression_variants": [
                {
                    "id": f"mio-{state}",
                    "asset_id": f"mio-{state}",
                    "appearance_id": "mio",
                    "state": state,
                    "label": state,
                    "description": f"A {state} expression",
                    "alt": f"Mio with a {state} expression",
                    "slot": "right",
                }
                for state in ("neutral", "delighted", "flustered", "concerned")
            ],
        },
        "review": {"status": "pending", "path": None, "sha256": None},
        "rights": {"aggregate": "unreviewed", "publication_authorized": False},
    }
    assert DialogueBundle.model_validate(raw).rights.publication_authorized is False
    legacy = {**raw, "schema_version": 4, "kind": "dialogue-scene-bundle-v4"}
    with pytest.raises(ValidationError):
        DialogueBundle.model_validate(legacy)
    camel = {**raw, "runIdentitySha256": raw["run_identity_sha256"]}
    del camel["run_identity_sha256"]
    with pytest.raises(ValidationError):
        DialogueBundle.model_validate(camel)
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
    scenario = package / "scenario.toml"
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
        node.node_id
        for node in original.nodes
        if node.node_id.startswith(("scene-background", "scene-expression", "scene-canonicalize"))
    ]
    assert art_nodes, "the fixture must contain generated art"
    for node_id in art_nodes:
        assert original.node(node_id).cache_key == edited.node(node_id).cache_key, node_id
    # The narrative did change, and the nodes that carry it say so.
    assert original.node("scene-scenario").cache_key != edited.node("scene-scenario").cache_key
    assert original.node("scene-bundle").cache_key != edited.node("scene-bundle").cache_key
