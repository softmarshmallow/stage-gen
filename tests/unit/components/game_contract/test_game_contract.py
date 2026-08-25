"""The authored game contract: what it accepts, what it refuses, and why."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from stage_gen.components.game_contract import (
    MAXIMUM_HEADS_TALL,
    MINIMUM_HEADS_TALL,
    GameContract,
    GameContractLoadError,
    ResidentDirection,
    canonical_game_contract_json,
    game_contract_sha256,
    load_game_contract,
    load_game_contract_bytes,
    load_game_vocabulary,
    resolve_game_contract_binding,
)
from stage_gen.recipes.scrolling_preview.proportion import (
    MAXIMUM_HEADS_TALL as RECIPE_MAXIMUM,
)
from stage_gen.recipes.scrolling_preview.proportion import (
    MINIMUM_HEADS_TALL as RECIPE_MINIMUM,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SHIPPED_REF = "library/games/whimsical-storybook-fantasy/game.toml"
SHIPPED_PATH = REPOSITORY_ROOT / SHIPPED_REF


def _contract_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 3,
        "kind": "game-contract-v3",
        "game_id": "test-game",
        "revision": 1,
        "display_name": "Test Game",
        "camera": {"projection": "side_view_2d"},
        "style": {
            "keywords": [
                "hand-painted gouache",
                "warm dusk palette",
                "soft diffuse light",
            ],
            "avoid": ["3D rendering"],
        },
        "proportion": {"heads_tall": 2.0, "by_body_kind": {"avian": 2.4}},
        "cast": {
            "player": {"body_kind": "human"},
            "resident": {"body_kind_default": "human"},
        },
        "rights": {"status": "unreviewed", "notice": "Test fixture."},
    }
    payload.update(overrides)
    return payload


def _load(payload: dict[str, Any]) -> GameContract:
    return load_game_contract_bytes(json.dumps(payload).encode("utf-8"), source_suffix=".json")


class TestVocabulary:
    def test_the_packaged_vocabulary_loads_and_offers_every_closed_list(self) -> None:
        loaded = load_game_vocabulary()
        vocabulary = loaded.vocabulary
        assert (
            loaded.sha256
            == hashlib.sha256(
                (
                    REPOSITORY_ROOT / "src/stage_gen/resources/prompting/game_vocabulary_v1.json"
                ).read_bytes()
            ).hexdigest()
        )
        assert vocabulary.people_body_kinds
        assert "none" in vocabulary.prop_names
        assert vocabulary.style_facet("hand-painted gouache") == "medium"

    def test_an_unapproved_word_is_named_rather_than_ignored(self) -> None:
        vocabulary = load_game_vocabulary().vocabulary
        for lookup, value in (
            (vocabulary.style_facet, "cinematic 8k masterpiece"),
            (vocabulary.body, "demigod"),
            (vocabulary.stance, "dabbing"),
            (vocabulary.prop, "plasma rifle"),
        ):
            with pytest.raises(ValueError, match="unapproved"):
                lookup(value)

    def test_a_body_kind_carries_the_sentence_an_image_model_can_draw(self) -> None:
        # The label is a word; the anatomy is a silhouette. This is why the vocabulary stores
        # both rather than letting the prompt builder interpolate the identifier.
        vocabulary = load_game_vocabulary().vocabulary
        elf = vocabulary.body("elf")
        assert elf.people is True
        assert "elf" not in elf.anatomy
        assert vocabulary.body("quadruped").people is False


class TestContract:
    def test_the_shipped_game_loads_and_is_digest_stable(self) -> None:
        contract = load_game_contract(SHIPPED_PATH)
        assert contract.game_id == "whimsical-storybook-fantasy"
        assert contract.camera.projection == "side_view_2d"
        assert game_contract_sha256(contract) == game_contract_sha256(
            load_game_contract(SHIPPED_PATH)
        )

    def test_current_contract_materializes_one_canonical_default_combat_text_policy(self) -> None:
        contract = _load(_contract_payload(revision=3))
        assert contract.gameplay is not None
        assert contract.gameplay.mob_population is None
        assert contract.combat_text_manifest() == {
            "schema_version": 1,
            "kind": "combat-text-v1",
            "enabled": True,
        }
        canonical = json.loads(canonical_game_contract_json(contract))
        assert canonical["gameplay"]["combat_text"] == contract.combat_text_manifest()

    @pytest.mark.parametrize(
        ("schema_version", "kind"),
        [(1, "game-contract-v1"), (2, "game-contract-v2")],
    )
    def test_previous_document_versions_are_rejected(self, schema_version: int, kind: str) -> None:
        with pytest.raises(GameContractLoadError):
            _load(_contract_payload(schema_version=schema_version, kind=kind))

    def test_one_table_answers_the_build_for_the_whole_cast(self) -> None:
        # The defect this contract exists for: `character_heads_tall` named the player's build
        # and a village generated beside it had nothing to consult.
        contract = _load(_contract_payload())
        assert contract.heads_for("human") == 2.0
        assert contract.heads_for(contract.cast.player.body_kind) == 2.0
        assert contract.heads_for(contract.cast.resident.body_kind_default) == 2.0
        assert contract.heads_for("avian") == 2.4
        assert contract.heads_for("dwarf") == 2.0

    def test_the_build_bounds_match_the_recipe_they_direct(self) -> None:
        # The component may not import the recipe, so the numbers are written twice. This is the
        # assertion that keeps the two copies from drifting.
        assert (MINIMUM_HEADS_TALL, MAXIMUM_HEADS_TALL) == (RECIPE_MINIMUM, RECIPE_MAXIMUM)

    def test_an_integer_build_is_widened_and_a_boolean_is_not(self) -> None:
        assert _load(_contract_payload(proportion={"heads_tall": 3})).heads_for("human") == 3.0
        with pytest.raises(GameContractLoadError):
            _load(_contract_payload(proportion={"heads_tall": True}))

    @pytest.mark.parametrize("heads", [1.9, 8.1, 0.0, -2.0])
    def test_a_build_outside_the_drawable_range_is_refused(self, heads: float) -> None:
        with pytest.raises(GameContractLoadError):
            _load(_contract_payload(proportion={"heads_tall": heads}))

    def test_keywords_must_name_the_medium(self) -> None:
        # A keyword list that never names a medium qualifies a style that was never stated.
        with pytest.raises(GameContractLoadError, match="must name the medium"):
            _load(
                _contract_payload(
                    style={
                        "keywords": [
                            "warm dusk palette",
                            "soft diffuse light",
                            "paper grain",
                        ]
                    }
                )
            )

    def test_an_invented_keyword_is_refused_rather_than_passed_through(self) -> None:
        with pytest.raises(GameContractLoadError, match="unapproved style keyword"):
            _load(
                _contract_payload(
                    style={
                        "keywords": [
                            "hand-painted gouache",
                            "trending on artstation",
                            "warm dusk palette",
                        ]
                    }
                )
            )

    def test_an_invented_avoidance_is_refused_too(self) -> None:
        with pytest.raises(GameContractLoadError, match="unapproved style avoidance"):
            _load(
                _contract_payload(
                    style={
                        "keywords": ["hand-painted gouache", "warm dusk palette", "paper grain"],
                        "avoid": ["ugly, blurry, bad hands"],
                    }
                )
            )

    def test_a_cast_member_must_have_a_body_a_person_has(self) -> None:
        for role, patch in (
            (
                "player",
                {"player": {"body_kind": "quadruped"}, "resident": {"body_kind_default": "human"}},
            ),
            (
                "resident",
                {"player": {"body_kind": "human"}, "resident": {"body_kind_default": "amorphous"}},
            ),
        ):
            with pytest.raises(GameContractLoadError, match="not a body a person has"):
                _load(_contract_payload(cast=patch))
            assert role

    def test_duplicate_keywords_are_refused(self) -> None:
        with pytest.raises(GameContractLoadError):
            _load(
                _contract_payload(
                    style={
                        "keywords": [
                            "hand-painted gouache",
                            "warm dusk palette",
                            "warm dusk palette",
                        ]
                    }
                )
            )

    def test_an_unknown_camera_still_parses_only_as_a_known_projection(self) -> None:
        with pytest.raises(GameContractLoadError):
            _load(_contract_payload(camera={"projection": "top_down_2d"}))

    def test_an_animated_resident_must_be_drawn_in_the_side_orientation(self) -> None:
        # A strip's frames are compared against a side-view symmetry ceiling and reviewed for
        # which edge the subject faces. Neither question has an answer for a front view.
        with pytest.raises(ValueError, match="side orientation"):
            ResidentDirection.model_validate(
                {
                    "body_kind_default": "human",
                    "orientation": "front",
                    "animation": "strip",
                }
            )
        assert (
            ResidentDirection.model_validate(
                {"body_kind_default": "human", "orientation": "side", "animation": "strip"}
            ).animation
            == "strip"
        )

    def test_residents_default_to_a_forward_facing_still(self) -> None:
        resident = _load(_contract_payload()).cast.resident
        assert (resident.orientation, resident.animation) == ("front", "still")
        assert resident.allow_pose is True
        assert resident.allow_held_prop is True

    def test_an_unknown_field_is_refused_rather_than_silently_dropped(self) -> None:
        with pytest.raises(GameContractLoadError):
            _load(_contract_payload(mood="cosy"))

    def test_a_toml_native_date_is_refused_by_name(self) -> None:
        document = b'schema_version = 3\nkind = "game-contract-v3"\nreleased = 2026-01-01\n'
        with pytest.raises(GameContractLoadError, match="date/time"):
            load_game_contract_bytes(document, source_suffix=".toml")

    def test_a_duplicate_json_key_is_refused(self) -> None:
        with pytest.raises(GameContractLoadError, match="duplicate JSON key"):
            load_game_contract_bytes(
                b'{"schema_version": 3, "schema_version": 3}', source_suffix=".json"
            )


class TestLibraryResolution:
    def _binding(self, **overrides: Any) -> dict[str, Any]:
        binding: dict[str, Any] = {
            "schema_version": 1,
            "kind": "game-contract-binding-v1",
            "ref": SHIPPED_REF,
            "source_sha256": hashlib.sha256(SHIPPED_PATH.read_bytes()).hexdigest(),
        }
        binding.update(overrides)
        return binding

    def test_the_shipped_game_resolves_and_publishes_both_digests(self) -> None:
        resolved = resolve_game_contract_binding(self._binding(), game_library_root=REPOSITORY_ROOT)
        identity = resolved.identity()
        # Both digests belong in the identity: the contract names the keywords, and the
        # vocabulary decides what those keywords become in a prompt.
        assert identity["source_sha256"] == resolved.source_sha256
        assert identity["vocabulary_sha256"] == load_game_vocabulary().sha256
        assert identity["projection"] == "side_view_2d"
        assert identity["rights_status"] == "unreviewed"
        assert resolved.source_provenance.media_type == "application/toml"

    def test_a_source_that_changed_since_the_request_is_a_mismatch(self) -> None:
        with pytest.raises(ValueError, match="source_sha256 mismatch"):
            resolve_game_contract_binding(
                self._binding(source_sha256="0" * 64),
                game_library_root=REPOSITORY_ROOT,
            )

    @pytest.mark.parametrize(
        "ref",
        [
            "library/games/whimsical-storybook-fantasy/other.toml",
            "library/characters/whimsical-storybook-fantasy/game.toml",
            "library/games/game.toml",
        ],
    )
    def test_only_one_path_shape_is_a_game(self, ref: str) -> None:
        with pytest.raises(ValueError, match="game ref must equal"):
            resolve_game_contract_binding(self._binding(ref=ref), game_library_root=REPOSITORY_ROOT)

    @pytest.mark.parametrize(
        "ref",
        [
            "../library/games/x/game.toml",
            "/library/games/x/game.toml",
            "library/games/./x/game.toml",
        ],
    )
    def test_a_ref_that_leaves_the_root_is_refused_before_any_read(self, ref: str) -> None:
        with pytest.raises(ValueError):
            resolve_game_contract_binding(self._binding(ref=ref), game_library_root=REPOSITORY_ROOT)

    def test_a_game_id_must_match_the_directory_it_is_filed_under(self, tmp_path: Path) -> None:
        # The cheapest available guard against a copied file that still claims to be the game
        # it was copied from.
        target = tmp_path / "library" / "games" / "renamed"
        target.mkdir(parents=True)
        (target / "game.toml").write_bytes(SHIPPED_PATH.read_bytes())
        with pytest.raises(ValueError, match="must match its library directory"):
            resolve_game_contract_binding(
                self._binding(ref="library/games/renamed/game.toml"),
                game_library_root=tmp_path,
            )

    def test_a_symlinked_game_is_refused(self, tmp_path: Path) -> None:
        target = tmp_path / "library" / "games" / "whimsical-storybook-fantasy"
        target.mkdir(parents=True)
        (target / "game.toml").symlink_to(SHIPPED_PATH)
        with pytest.raises(ValueError, match="non-symlink"):
            resolve_game_contract_binding(self._binding(), game_library_root=tmp_path)
