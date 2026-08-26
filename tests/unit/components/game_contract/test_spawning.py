"""Strict authoring and projection tests for hunting-ground mob populations."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import ValidationError

from stage_gen.components.game_contract import GameContract, MobPopulationDirection


def _entry(tier: int = 1, **overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "mob_tier": tier,
        "weight": 1,
        "min_alive": 0,
        "max_alive": 4,
    }
    value.update(overrides)
    return value


def _zone(zone_id: str = "west-trail", **overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "zone_id": zone_id,
        "surface": "terrain",
        "left_column": 8,
        "right_column_exclusive": 60,
        "initial_population": 3,
        "target_population": 4,
        "population_cap": 5,
        "respawn_delay_ms": 7_000,
        "respawn_variance_ms": 1_000,
        "spawn_interval_ms": 400,
        "spawn_batch_size": 1,
        "retry_delay_ms": 750,
        "spawn_visibility": "offscreen_required",
        "camera_margin_px": 128,
        "min_player_distance_px": 320,
        "minimum_spawn_separation_px": 96,
        "wander_radius_px": 100,
        "pursuit_leash_px": 256,
        "replacement_policy": "reroll_spawn_table",
        "spawn_table": [_entry(1), _entry(2)],
    }
    value.update(overrides)
    return value


def _direction(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": 1,
        "kind": "mob-population-v1",
        "update_interval_ms": 100,
        "max_spawn_batch_per_update": 2,
        "maps": [
            {
                "map_id": "stage-1-approach",
                "seed_salt": 0,
                "zones": [_zone()],
            }
        ],
    }
    value.update(overrides)
    return value


def _game(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": 3,
        "kind": "game-contract-v3",
        "game_id": "test-game",
        "revision": 2,
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
        "gameplay": {"mob_population": _direction()},
        "rights": {"status": "unreviewed"},
    }
    value.update(overrides)
    return value


def test_game_contract_accepts_only_the_current_document_shape() -> None:
    current = GameContract.model_validate(_game())
    assert current.gameplay is not None
    assert current.gameplay.mob_population is not None
    assert current.combat_text_manifest() == {
        "schema_version": 1,
        "kind": "combat-text-v1",
        "enabled": True,
    }
    for schema_version, kind in ((1, "game-contract-v1"), (2, "game-contract-v2")):
        with pytest.raises(ValidationError):
            GameContract.model_validate(_game(schema_version=schema_version, kind=kind))
    with pytest.raises(ValidationError):
        GameContract.model_validate(_game(kind="game-contract-v2"))
    with pytest.raises(ValidationError, match=r"requires gameplay\.combat_text"):
        GameContract.model_validate(
            {**_game(), "gameplay": {"mob_population": _direction(), "combat_text": None}}
        )


@pytest.mark.parametrize("identifier", ["StageOne", "stage_one", "stage--one", "stage-"])
def test_map_and_zone_ids_are_portable_kebab_case_slugs(identifier: str) -> None:
    with pytest.raises(ValidationError, match="kebab-case"):
        MobPopulationDirection.model_validate(
            _direction(maps=[{"map_id": identifier, "seed_salt": 0, "zones": [_zone()]}])
        )
    with pytest.raises(ValidationError, match="kebab-case"):
        MobPopulationDirection.model_validate(
            _direction(
                maps=[
                    {
                        "map_id": "stage-1-approach",
                        "seed_salt": 0,
                        "zones": [_zone(zone_id=identifier)],
                    }
                ]
            )
        )


def test_map_and_zone_ids_are_unique_and_zones_do_not_overlap() -> None:
    first = {"map_id": "first-map", "seed_salt": 1, "zones": [_zone()]}
    with pytest.raises(ValidationError, match="unique map_id"):
        MobPopulationDirection.model_validate(_direction(maps=[first, copy.deepcopy(first)]))

    with pytest.raises(ValidationError, match="unique zone_id"):
        MobPopulationDirection.model_validate(
            _direction(
                maps=[
                    {
                        "map_id": "first-map",
                        "seed_salt": 1,
                        "zones": [_zone(), _zone()],
                    }
                ]
            )
        )

    with pytest.raises(ValidationError, match="overlap"):
        MobPopulationDirection.model_validate(
            _direction(
                maps=[
                    {
                        "map_id": "first-map",
                        "seed_salt": 1,
                        "zones": [
                            _zone("west", left_column=8, right_column_exclusive=60),
                            _zone("east", left_column=59, right_column_exclusive=90),
                        ],
                    }
                ]
            )
        )


def test_population_timing_and_spawn_table_feasibility_fail_closed() -> None:
    invalid_zones = (
        _zone(initial_population=5, target_population=4, population_cap=6),
        _zone(target_population=7, population_cap=6),
        _zone(left_column=8, right_column_exclusive=8),
        _zone(respawn_delay_ms=500, respawn_variance_ms=501),
        _zone(spawn_interval_ms=0),
        _zone(wander_radius_px=257, pursuit_leash_px=256),
        _zone(spawn_table=[_entry(1), _entry(1)]),
        _zone(spawn_table=[_entry(1, min_alive=3), _entry(2, min_alive=2)]),
        _zone(spawn_table=[_entry(1, max_alive=1), _entry(2, max_alive=2)]),
    )
    for zone in invalid_zones:
        with pytest.raises(ValidationError):
            MobPopulationDirection.model_validate(
                _direction(maps=[{"map_id": "first-map", "seed_salt": 0, "zones": [zone]}])
            )


def test_unknown_fields_and_coerced_values_are_rejected() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        MobPopulationDirection.model_validate(_direction(mood="cosy"))
    with pytest.raises(ValidationError):
        MobPopulationDirection.model_validate(_direction(update_interval_ms="100"))
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        MobPopulationDirection.model_validate(
            _direction(
                maps=[
                    {
                        "map_id": "first-map",
                        "seed_salt": 0,
                        "zones": [_zone(spawn_table=[_entry(0)])],
                    }
                ]
            )
        )


def test_manifest_projection_is_deterministic_and_resolves_every_mob_slot() -> None:
    contract = GameContract.model_validate(_game())
    assert contract.gameplay is not None
    first = contract.mob_population_manifest(mob_count=2)
    second = contract.mob_population_manifest(mob_count=2)
    assert first == second
    assert first is not second
    assert first is not None
    first_payload: Any = first
    population = contract.gameplay.mob_population
    assert population is not None
    authored = population.model_dump(mode="json")
    authored_entries = authored["maps"][0]["zones"][0]["spawn_table"]
    runtime_entries = first_payload["maps"][0]["zones"][0]["spawn_table"]
    assert [entry["mob_tier"] for entry in authored_entries] == [1, 2]
    assert [entry["mob_slot"] for entry in runtime_entries] == [0, 1]
    assert all("mob_tier" not in entry for entry in runtime_entries)

    with pytest.raises(ValueError, match=r"spawn_table\[1\].*mob_tier 2 exceeds mob_count 1"):
        contract.mob_population_manifest(mob_count=1)
    with pytest.raises(ValueError, match="positive integer"):
        contract.mob_population_manifest(mob_count=True)


def test_manifest_projection_validates_adapter_map_and_column_boundaries() -> None:
    direction = MobPopulationDirection.model_validate(_direction())
    projection: Any = direction.manifest_projection(
        mob_count=2,
        allowed_map_ids={"stage-1-approach"},
        stage_column_count=200,
    )
    assert projection["maps"][0]["map_id"] == "stage-1-approach"

    with pytest.raises(ValueError, match="not an allowed hunting map"):
        direction.manifest_projection(
            mob_count=2,
            allowed_map_ids={"stage-2-gauntlet"},
            stage_column_count=200,
        )
    with pytest.raises(ValueError, match="right_column_exclusive 60 exceeds"):
        direction.manifest_projection(
            mob_count=2,
            allowed_map_ids={"stage-1-approach"},
            stage_column_count=59,
        )
    with pytest.raises(ValueError, match="allowed_map_ids must contain"):
        direction.manifest_projection(mob_count=2, allowed_map_ids=set())
    with pytest.raises(ValueError, match="stage_column_count must be a positive integer"):
        direction.manifest_projection(mob_count=2, stage_column_count=True)
