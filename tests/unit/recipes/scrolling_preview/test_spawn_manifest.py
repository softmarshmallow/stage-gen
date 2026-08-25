"""Current manifest projection for authored hunting-ground mob populations."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

from stage_gen.components.game_contract import (
    GAME_LIBRARY_RESOLUTION_VERSION,
    GameContract,
    canonical_game_contract_json,
)
from stage_gen.config import TransparencyMode
from stage_gen.contracts import BinaryArtifact, InputProvenance, ProvenanceInput
from stage_gen.recipes.scrolling_preview import manifest as manifest_module
from stage_gen.recipes.scrolling_preview.game import (
    GAME_RESOLUTION_VERSION,
    game_art_direction_prompt,
)
from stage_gen.recipes.scrolling_preview.manifest import (
    write_scrolling_preview_manifest,
)
from stage_gen.recipes.scrolling_preview.map_book import (
    MAP_BOOK_MANIFEST_KIND,
    CollectedMapBook,
)
from stage_gen.recipes.scrolling_preview.soundtrack import CollectedSoundtrack
from stage_gen.reliability import write_artifact_with_provenance


def _mob_population(
    *,
    mob_tier: int = 1,
    map_id: str = "stage-1-approach",
    right_column_exclusive: int = 48,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "mob-population-v1",
        "update_interval_ms": 100,
        "max_spawn_batch_per_update": 2,
        "maps": [
            {
                "map_id": map_id,
                "seed_salt": 17,
                "zones": [
                    {
                        "zone_id": "lower-field",
                        "surface": "terrain",
                        "left_column": 8,
                        "right_column_exclusive": right_column_exclusive,
                        "initial_population": 1,
                        "target_population": 1,
                        "population_cap": 2,
                        "respawn_delay_ms": 5_000,
                        "respawn_variance_ms": 1_000,
                        "spawn_interval_ms": 500,
                        "spawn_batch_size": 1,
                        "retry_delay_ms": 250,
                        "spawn_visibility": "offscreen_preferred",
                        "camera_margin_px": 128,
                        "min_player_distance_px": 256,
                        "minimum_spawn_separation_px": 64,
                        "wander_radius_px": 128,
                        "pursuit_leash_px": 192,
                        "replacement_policy": "same_archetype",
                        "spawn_table": [
                            {
                                "mob_tier": mob_tier,
                                "weight": 1,
                                "min_alive": 1,
                                "max_alive": 2,
                            }
                        ],
                    }
                ],
            }
        ],
    }


def _projected_mob_population(
    *,
    mob_slot: int = 0,
    map_id: str = "stage-1-approach",
) -> dict[str, object]:
    projection: Any = _mob_population(mob_tier=mob_slot + 1, map_id=map_id)
    spawn_table = projection["maps"][0]["zones"][0]["spawn_table"]
    projection_entry = spawn_table[0]
    projection_entry["mob_slot"] = projection_entry.pop("mob_tier") - 1
    return cast(dict[str, object], projection)


def _game_contract(
    *,
    mob_tier: int = 1,
    map_id: str = "stage-1-approach",
    right_column_exclusive: int = 48,
) -> GameContract:
    return GameContract.model_validate(
        {
            "schema_version": 3,
            "kind": "game-contract-v3",
            "game_id": "test-game",
            "revision": 3,
            "display_name": "Test Game",
            "camera": {"projection": "side_view_2d"},
            "style": {
                "keywords": [
                    "hand-painted gouache",
                    "warm dusk palette",
                    "soft diffuse light",
                ]
            },
            "proportion": {"heads_tall": 2.0},
            "cast": {
                "player": {"body_kind": "human"},
                "resident": {"body_kind_default": "human"},
            },
            "gameplay": {
                "mob_population": _mob_population(
                    mob_tier=mob_tier,
                    map_id=map_id,
                    right_column_exclusive=right_column_exclusive,
                )
            },
            "rights": {"status": "unreviewed", "notice": "Test fixture."},
        }
    )


def _game_contract_v3(
    *, include_population: bool = False, map_id: str = "stage-1-approach"
) -> GameContract:
    payload = _game_contract(map_id=map_id).model_dump(mode="json", exclude_none=True)
    payload["schema_version"] = 3
    payload["kind"] = "game-contract-v3"
    payload["revision"] = 3
    if not include_population:
        payload.pop("gameplay")
    return GameContract.model_validate(payload)


def _level_profile(*, role: str, encounter_model: str, interaction_model: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "level-profile-v1",
        "role": role,
        "view": {"projection": "orthographic_2d", "viewpoint": "side_on"},
        "camera": {
            "tracking_mode": "player_follow",
            "framing_mode": "dead_zone",
            "scroll_axes": ["horizontal"],
        },
        "traversal": {
            "ground_model": "heightfield",
            "platform_model": "one_way",
            "affordances": ["ground_move", "jump", "air_jump", "drop_through"],
        },
        "mechanisms": {
            "encounter_model": encounter_model,
            "combat_model": "real_time_action" if role == "combat_field" else "none",
            "loot_model": "defeat_drops" if role == "combat_field" else "none",
            "transition_model": "bidirectional_portals",
            "interaction_model": interaction_model,
        },
    }


def _world_spec() -> dict[str, object]:
    kinds = [
        "sun-coin",
        "spore-vial",
        "rune-shard",
        "gate-key",
        "bone-charm",
        "signal-map",
        "flint-tool",
        "thorn-blade",
    ]
    return {
        "world": {"name": "Vale", "one_liner": "A quiet ruin.", "narrative": "Rain."},
        "mobs": [
            {
                "tier_label": "scout",
                "body_plan": "winged avian",
                "name": "Mote",
                "brief": "A pale bird.",
            },
            {
                "tier_label": "apex",
                "body_plan": "four-legged quadruped",
                "name": "Maw",
                "brief": "A stone beast.",
            },
        ],
        "obstacles": [
            {
                "sheet_theme": "mossy ruins",
                "props": [{"name": f"prop {index}", "brief": "weathered"} for index in range(8)],
            }
        ],
        "items": [
            {"kind": kind, "name": f"item {index}", "brief": "small"}
            for index, kind in enumerate(kinds)
        ],
        "layers": [
            {
                "id": "deep_sky",
                "title": "Deep sky",
                "z_index": 0,
                "parallax": 0.0,
                "opaque": True,
                "paint_region": "all canvas",
                "description": "Clouds",
            },
            {
                "id": "near_ruins",
                "title": "Near ruins",
                "z_index": 1,
                "parallax": 1.8,
                "opaque": False,
                "paint_region": "lower half",
                "description": "Arches",
            },
        ],
    }


def _write_resolved_game(run_dir: Path, tag: str, contract: GameContract) -> tuple[Path, Path]:
    artifact = run_dir / f"game_{tag}.json"
    artifact_bytes = canonical_game_contract_json(contract)
    canonical_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    source_sha256 = "a" * 64
    binding = {
        "schema_version": 1,
        "kind": "game-contract-binding-v1",
        "ref": "library/games/test-game/game.toml",
        "source_sha256": source_sha256,
    }
    identity = {
        "schema_version": 1,
        "kind": "resolved-game-contract-v1",
        "resolution_version": GAME_LIBRARY_RESOLUTION_VERSION,
        "binding": binding,
        "game_id": contract.game_id,
        "revision": contract.revision,
        "projection": contract.camera.projection,
        "source_sha256": source_sha256,
        "canonical_sha256": canonical_sha256,
        "canonical_bytes": len(artifact_bytes),
        "vocabulary_sha256": "b" * 64,
        "rights_status": contract.rights.status,
        "recipe_resolution_version": GAME_RESOLUTION_VERSION,
        "art_direction_sha256": hashlib.sha256(
            game_art_direction_prompt(contract).encode("utf-8")
        ).hexdigest(),
        "artifact_ref": f"sha256:{canonical_sha256}",
        "artifact_sha256": canonical_sha256,
        "artifact_bytes": len(artifact_bytes),
    }
    provenance = write_artifact_with_provenance(
        artifact,
        BinaryArtifact(data=artifact_bytes, media_type="application/json"),
        ProvenanceInput(
            provider="local",
            model=GAME_RESOLUTION_VERSION,
            prompt="resolve authored game contract",
            refs=[str(binding["ref"])],
            inputs=[
                InputProvenance(
                    ref=str(binding["ref"]),
                    sha256=source_sha256,
                    source="content",
                    bytes=1024,
                    media_type="application/toml",
                )
            ],
            params={"stage": "game-resolve", "game_contract": identity},
            attempts=1,
        ),
    )
    return artifact, Path(provenance)


def test_collects_verified_v3_game_lineage_and_rejects_identity_drift(
    tmp_path: Path,
) -> None:
    tag = "directed"
    artifact, provenance = _write_resolved_game(tmp_path, tag, _game_contract())
    collected = manifest_module._collect_game_contract(
        tmp_path, tag, {artifact.name, provenance.name}
    )
    assert collected.contract.schema_version == 3
    assert collected.manifest_binding["path"] == artifact.name

    sidecar = json.loads(provenance.read_text(encoding="utf-8"))
    sidecar["params"]["game_contract"]["canonical_sha256"] = "0" * 64
    provenance.write_text(json.dumps(sidecar), encoding="utf-8")
    with pytest.raises(ValueError, match="lineage mismatch"):
        manifest_module._collect_game_contract(tmp_path, tag, {artifact.name, provenance.name})


def test_collects_verified_v3_game_with_materialized_combat_text(tmp_path: Path) -> None:
    tag = "combat-text"
    artifact, provenance = _write_resolved_game(tmp_path, tag, _game_contract_v3())
    collected = manifest_module._collect_game_contract(
        tmp_path, tag, {artifact.name, provenance.name}
    )
    assert collected.contract.schema_version == 3
    assert collected.contract.combat_text_manifest() == {
        "schema_version": 1,
        "kind": "combat-text-v1",
        "enabled": True,
    }


@pytest.mark.asyncio
async def test_v3_writes_manifest_v7_with_default_combat_text_and_optional_population(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tag = "v7-combat-text"
    contract = _game_contract_v3()
    binding: dict[str, object] = {
        "source_sha256": "a" * 64,
        "canonical_sha256": "b" * 64,
        "path": f"game_{tag}.json",
        "provenance_path": f"game_{tag}.json.meta.json",
    }
    monkeypatch.setattr(
        manifest_module,
        "_ensure_run_music_pair",
        lambda *_args: {"source": "per-run", "rights_status": "unrecorded"},
    )
    monkeypatch.setattr(manifest_module, "_collect_image_repeat", lambda *_args: [])
    monkeypatch.setattr(manifest_module, "_collect_canonical_images", lambda *_args: [])
    monkeypatch.setattr(
        manifest_module,
        "_collect_runtime_assets",
        lambda *_args: (
            [],
            {"path": f"world_spec_{tag}.json", "provenancePath": "world.meta.json"},
        ),
    )
    monkeypatch.setattr(
        manifest_module,
        "_collect_game_contract",
        lambda *_args: manifest_module._CollectedGameContract(contract, binding),
    )

    result = await write_scrolling_preview_manifest(
        run_dir=tmp_path,
        tag=tag,
        transparency_mode=TransparencyMode.CHROMA,
        game_contract=True,
    )
    manifest = json.loads(await asyncio.to_thread(Path(result.manifest_path).read_text))
    sidecar = json.loads(await asyncio.to_thread(Path(result.manifest_provenance_path).read_text))
    assert manifest["schema_version"] == 7
    assert manifest["game_contract"] == {**binding, "contract_schema_version": 3}
    assert manifest["gameplay"] == {
        "combat_text": {
            "schema_version": 1,
            "kind": "combat-text-v1",
            "enabled": True,
        }
    }
    assert sidecar["params"]["mob_population_maps"] == 0
    assert sidecar["params"]["combat_text_enabled"] is True
    assert "mob_population_projection_verified" not in sidecar["validation"]
    assert sidecar["validation"]["combat_text_projection_verified"] is True


@pytest.mark.asyncio
async def test_v3_writes_manifest_v7_and_resolves_mob_slots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tag = "v7"
    contract = _game_contract()
    binding: dict[str, object] = {
        "source_sha256": "a" * 64,
        "canonical_sha256": "b" * 64,
        "path": f"game_{tag}.json",
        "provenance_path": f"game_{tag}.json.meta.json",
    }
    (tmp_path / f"world_spec_{tag}.json").write_text(json.dumps(_world_spec()), encoding="utf-8")
    monkeypatch.setattr(
        manifest_module,
        "_ensure_run_music_pair",
        lambda *_args: {"source": "per-run", "rights_status": "unrecorded"},
    )
    monkeypatch.setattr(manifest_module, "_collect_image_repeat", lambda *_args: [])
    monkeypatch.setattr(manifest_module, "_collect_canonical_images", lambda *_args: [])
    monkeypatch.setattr(
        manifest_module,
        "_collect_runtime_assets",
        lambda *_args: (
            [],
            {"path": f"world_spec_{tag}.json", "provenancePath": "world.meta.json"},
        ),
    )
    monkeypatch.setattr(
        manifest_module,
        "_collect_game_contract",
        lambda *_args: manifest_module._CollectedGameContract(contract, binding),
    )

    result = await write_scrolling_preview_manifest(
        run_dir=tmp_path,
        tag=tag,
        transparency_mode=TransparencyMode.CHROMA,
        game_contract=True,
    )
    manifest = json.loads(await asyncio.to_thread(Path(result.manifest_path).read_text))
    sidecar: dict[str, Any] = json.loads(
        await asyncio.to_thread(Path(result.manifest_provenance_path).read_text)
    )

    assert manifest["schema_version"] == 7
    assert manifest["game_contract"] == {**binding, "contract_schema_version": 3}
    assert manifest["gameplay"]["mob_population"] == _projected_mob_population()
    assert binding["path"] in sidecar["refs"]
    assert sidecar["params"]["mob_population_maps"] == 1
    assert sidecar["validation"]["mob_population_projection_verified"] is True

    invalid = _game_contract(mob_tier=3)
    monkeypatch.setattr(
        manifest_module,
        "_collect_game_contract",
        lambda *_args: manifest_module._CollectedGameContract(invalid, binding),
    )
    with pytest.raises(ValueError, match="mob_tier 3 exceeds mob_count 2"):
        await write_scrolling_preview_manifest(
            run_dir=tmp_path,
            tag=tag,
            transparency_mode=TransparencyMode.CHROMA,
            game_contract=True,
        )

    invalid_zone = _game_contract(right_column_exclusive=201)
    monkeypatch.setattr(
        manifest_module,
        "_collect_game_contract",
        lambda *_args: manifest_module._CollectedGameContract(invalid_zone, binding),
    )
    with pytest.raises(ValueError, match="exceeds stage_column_count 200"):
        await write_scrolling_preview_manifest(
            run_dir=tmp_path,
            tag=tag,
            transparency_mode=TransparencyMode.CHROMA,
            game_contract=True,
        )


@pytest.mark.asyncio
async def test_v7_composes_current_map_book_soundtrack_and_hunting_map_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tag = "map-aware"
    for name in (
        f"music_{tag}_field_theme.mp3",
        f"music_{tag}_field_theme.mp3.meta.json",
        f"soundtrack_{tag}.json",
        f"soundtrack_{tag}.json.meta.json",
        f"map_book_{tag}.json",
        f"map_book_{tag}.json.meta.json",
    ):
        (tmp_path / name).write_bytes(b"test")
    (tmp_path / f"world_spec_{tag}.json").write_text(
        json.dumps(_world_spec()),
        encoding="utf-8",
    )

    collected_soundtrack = CollectedSoundtrack(
        manifest={
            "schema_version": 2,
            "kind": "game-soundtrack-manifest-v2",
            "game_id": "test-game",
            "revision": 1,
            "source": {
                "path": f"soundtrack_{tag}.json",
                "provenance_path": f"soundtrack_{tag}.json.meta.json",
                "source_sha256": "a" * 64,
                "canonical_sha256": "b" * 64,
            },
            "playback": {"selection": "shuffle", "no_immediate_repeat": True},
            "tracks": [
                {"track_id": "field_theme"},
                {"track_id": "village_theme"},
            ],
        },
        artifact_paths=(
            f"soundtrack_{tag}.json",
            f"soundtrack_{tag}.json.meta.json",
            f"music_{tag}_field_theme.mp3",
            f"music_{tag}_field_theme.mp3.meta.json",
        ),
        default_music={
            "path": f"music_{tag}_field_theme.mp3",
            "provenance_path": f"music_{tag}_field_theme.mp3.meta.json",
            "source": "per-run",
            "rights_status": "unreviewed",
        },
    )
    collected_map_book = CollectedMapBook(
        manifest={
            "schema_version": 2,
            "kind": MAP_BOOK_MANIFEST_KIND,
            "game_id": "test-game",
            "revision": 1,
            "entry_map_id": "village-hub",
            "source": {
                "path": f"map_book_{tag}.json",
                "provenance_path": f"map_book_{tag}.json.meta.json",
                "source_sha256": "c" * 64,
                "canonical_sha256": "d" * 64,
            },
            "soundtrack": {
                "source_sha256": "a" * 64,
                "canonical_sha256": "b" * 64,
            },
            "maps": [
                {
                    "map_id": "village-hub",
                    "soundtrack_track_ids": ["field_theme", "village_theme"],
                    "level_profile": _level_profile(
                        role="social_hub",
                        encounter_model="none",
                        interaction_model="proximity_dialogue",
                    ),
                },
                {
                    "map_id": "stage-1-approach",
                    "soundtrack_track_ids": ["field_theme", "village_theme"],
                    "level_profile": _level_profile(
                        role="combat_field",
                        encounter_model="continuous_population",
                        interaction_model="none",
                    ),
                },
            ],
        },
        artifact_paths=(
            f"map_book_{tag}.json",
            f"map_book_{tag}.json.meta.json",
        ),
    )
    binding: dict[str, object] = {
        "source_sha256": "e" * 64,
        "canonical_sha256": "f" * 64,
        "path": f"game_{tag}.json",
        "provenance_path": f"game_{tag}.json.meta.json",
    }
    contract = _game_contract()

    monkeypatch.setattr(
        manifest_module,
        "collect_scrolling_soundtrack",
        lambda *_args: collected_soundtrack,
    )

    def collect_map_book(
        *_args: object,
        soundtrack_manifest: dict[str, object],
    ) -> CollectedMapBook:
        assert soundtrack_manifest["schema_version"] == 2
        assert soundtrack_manifest["kind"] == "game-soundtrack-manifest-v2"
        return collected_map_book

    monkeypatch.setattr(manifest_module, "collect_scrolling_map_book", collect_map_book)
    monkeypatch.setattr(
        manifest_module,
        "_read_village_spec",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(manifest_module, "village_manifest_block", lambda *_args: {})
    monkeypatch.setattr(manifest_module, "_collect_image_repeat", lambda *_args: [])
    monkeypatch.setattr(manifest_module, "_collect_canonical_images", lambda *_args: [])
    monkeypatch.setattr(
        manifest_module,
        "_collect_runtime_assets",
        lambda *_args: (
            [],
            {"path": f"world_spec_{tag}.json", "provenancePath": "world.meta.json"},
        ),
    )
    monkeypatch.setattr(
        manifest_module,
        "_collect_game_contract",
        lambda *_args: manifest_module._CollectedGameContract(contract, binding),
    )

    result = await write_scrolling_preview_manifest(
        run_dir=tmp_path,
        tag=tag,
        transparency_mode=TransparencyMode.CHROMA,
        village=True,
        soundtrack=True,
        map_book=True,
        game_contract=True,
    )
    manifest = json.loads(
        await asyncio.to_thread(Path(result.manifest_path).read_text, encoding="utf-8")
    )
    assert manifest["schema_version"] == 7
    assert manifest["soundtrack"]["schema_version"] == 2
    assert manifest["soundtrack"]["kind"] == "game-soundtrack-manifest-v2"
    assert manifest["map_book"]["kind"] == MAP_BOOK_MANIFEST_KIND
    assert manifest["gameplay"]["mob_population"] == _projected_mob_population()
    assert collected_soundtrack.manifest["schema_version"] == 2
    assert collected_soundtrack.manifest["kind"] == "game-soundtrack-manifest-v2"

    for invalid_map_id in ("village-hub", "unknown-hunting-ground"):
        invalid = _game_contract(map_id=invalid_map_id)
        monkeypatch.setattr(
            manifest_module,
            "_collect_game_contract",
            lambda *_args, value=invalid: manifest_module._CollectedGameContract(value, binding),
        )
        with pytest.raises(ValueError, match=r"must exactly cover.*unexpected"):
            await write_scrolling_preview_manifest(
                run_dir=tmp_path,
                tag=tag,
                transparency_mode=TransparencyMode.CHROMA,
                village=True,
                soundtrack=True,
                map_book=True,
                game_contract=True,
            )


def test_map_book_v2_population_targets_follow_explicit_encounter_mechanisms() -> None:
    map_book = CollectedMapBook(
        manifest={
            "schema_version": 2,
            "kind": MAP_BOOK_MANIFEST_KIND,
            "entry_map_id": "village-hub",
            "maps": [
                {
                    "map_id": "village-hub",
                    # Deliberately combat_field: role is descriptive and must not enable spawns.
                    "level_profile": _level_profile(
                        role="combat_field",
                        encounter_model="none",
                        interaction_model="proximity_dialogue",
                    ),
                },
                {
                    "map_id": "stage-1-approach",
                    # Deliberately social_hub: the explicit mechanism still enables population.
                    "level_profile": _level_profile(
                        role="social_hub",
                        encounter_model="continuous_population",
                        interaction_model="none",
                    ),
                },
            ],
        },
        artifact_paths=(),
    )
    allowed = manifest_module._mob_population_hunting_map_ids(map_book)
    assert allowed == frozenset({"stage-1-approach"})

    contract = _game_contract_v3(include_population=True)
    assert contract.gameplay is not None
    assert contract.gameplay.mob_population is not None
    assert manifest_module._validate_mob_population_coverage(
        map_book,
        contract.gameplay.mob_population,
    ) == frozenset({"stage-1-approach"})
    assert (
        contract.mob_population_manifest(
            mob_count=2,
            allowed_map_ids=allowed,
            stage_column_count=200,
        )
        == _projected_mob_population()
    )
    with pytest.raises(ValueError, match="not an allowed hunting map"):
        _game_contract_v3(include_population=True, map_id="village-hub").mob_population_manifest(
            mob_count=2,
            allowed_map_ids=allowed,
            stage_column_count=200,
        )

    with pytest.raises(ValueError, match=r"must exactly cover.*missing: stage-1-approach"):
        manifest_module._validate_mob_population_coverage(
            map_book,
            None,
        )
    unexpected = _game_contract_v3(include_population=True, map_id="village-hub")
    assert unexpected.gameplay is not None
    with pytest.raises(ValueError, match="unexpected: village-hub"):
        manifest_module._validate_mob_population_coverage(
            map_book,
            unexpected.gameplay.mob_population,
        )

    social_only = CollectedMapBook(
        manifest={
            "schema_version": 2,
            "kind": MAP_BOOK_MANIFEST_KIND,
            "entry_map_id": "village-hub",
            "maps": [
                {
                    "map_id": "village-hub",
                    "level_profile": _level_profile(
                        role="social_hub",
                        encounter_model="none",
                        interaction_model="proximity_dialogue",
                    ),
                }
            ],
        },
        artifact_paths=(),
    )
    assert (
        manifest_module._validate_mob_population_coverage(
            social_only,
            None,
        )
        == frozenset()
    )
