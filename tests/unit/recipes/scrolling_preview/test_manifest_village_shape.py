"""The manifest reads the declared roster under the exact authored schema.

Game binding chooses directed versus undirected roster semantics. Resident rendering independently
chooses still versus strip geometry, so a directed run may validly publish either representation.
Once a village is declared, an absent or invalid bible is a contract error rather than permission
to publish a silently village-less run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from stage_gen.recipes.scrolling_preview import manifest as manifest_module
from stage_gen.recipes.scrolling_preview.resident import DirectedVillageSpec
from stage_gen.recipes.scrolling_preview.village import VillageSpec

TAG = "test-tag"


def _npc(index: int, directed: bool) -> dict[str, Any]:
    npc: dict[str, Any] = {
        "role_label": f"role-{index}",
        "name": f"Name{index}",
        "body_plan": f"wiry and quick, trade {index}" if directed else f"humanoid worker {index}",
        "brief": f"brief {index}",
        "greeting": "Hello.",
        "remark": "Fine weather.",
        "farewell": "Safe travels.",
    }
    if directed:
        npc |= {
            "body_kind": "human",
            "stance": ("standing_at_ease", "arms_crossed", "hands_on_hips", "hands_clasped")[index],
            "holding": ("none", "broom", "ledger", "lantern")[index],
        }
    return npc


def _write_bible(run_dir: Path, *, directed: bool) -> None:
    payload = {
        "name": "Hollowbrook",
        "one_liner": "A quiet market square.",
        "narrative": "A crossing where the road widens into stalls.",
        "fixtures_theme": "market stalls",
        "npcs": [_npc(i, directed) for i in range(4)],
        "fixtures": [{"name": f"fixture-{i}", "brief": f"brief {i}"} for i in range(8)],
    }
    (run_dir / f"village_spec_{TAG}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_a_directed_bible_is_read_under_the_directed_game_contract(tmp_path: Path) -> None:
    _write_bible(tmp_path, directed=True)
    spec = manifest_module._read_village_spec(tmp_path, TAG, directed=True)
    assert isinstance(spec, DirectedVillageSpec)
    assert [npc.body_kind for npc in spec.npcs] == ["human"] * 4


def test_a_directed_bible_is_rejected_under_the_undirected_contract(tmp_path: Path) -> None:
    _write_bible(tmp_path, directed=True)
    with pytest.raises(ValueError, match="declared village specification is invalid"):
        manifest_module._read_village_spec(tmp_path, TAG, directed=False)


def test_a_directed_strip_run_uses_the_directed_contract(tmp_path: Path) -> None:
    """Raster geometry does not select the authored roster schema."""

    _write_bible(tmp_path, directed=True)
    assert isinstance(
        manifest_module._read_village_spec(tmp_path, TAG, directed=True), DirectedVillageSpec
    )


def test_an_undirected_bible_still_reads_exactly_as_before(tmp_path: Path) -> None:
    _write_bible(tmp_path, directed=False)
    spec = manifest_module._read_village_spec(tmp_path, TAG, directed=False)
    assert isinstance(spec, VillageSpec)
    assert not isinstance(spec, DirectedVillageSpec)


def test_the_default_stays_the_strip_profile(tmp_path: Path) -> None:
    # Every run that predates the resident render profile calls this with no third argument.
    _write_bible(tmp_path, directed=False)
    assert manifest_module._read_village_spec(tmp_path, TAG) is not None


def test_a_declared_missing_bible_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing or unreadable"):
        manifest_module._read_village_spec(tmp_path, TAG, directed=True)


def test_a_declared_corrupt_bible_is_rejected(tmp_path: Path) -> None:
    (tmp_path / f"village_spec_{TAG}.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="declared village specification is invalid"):
        manifest_module._read_village_spec(tmp_path, TAG, directed=True)


def test_the_shape_resolver_answers_both_kinds_of_run() -> None:
    """One resolver, so the model and the schema name can never disagree.

    They disagreed once: the request was sent under the directed schema name while the cache
    validator compared against the undirected one and parsed with the undirected model, so a
    directed roster was never resumable and regenerated on every run - taking all four
    turnarounds, the fixture sheet and all four stills with it, because every village prompt is
    derived from the roster.
    """

    from stage_gen.recipes.scrolling_preview.resident import (
        DIRECTED_VILLAGE_SPEC_SCHEMA_NAME,
        village_spec_shape,
    )
    from stage_gen.recipes.scrolling_preview.village import VILLAGE_SPEC_SCHEMA_NAME

    assert village_spec_shape(directed=True) == (
        DirectedVillageSpec,
        DIRECTED_VILLAGE_SPEC_SCHEMA_NAME,
    )
    assert village_spec_shape(directed=False) == (VillageSpec, VILLAGE_SPEC_SCHEMA_NAME)
    # The two names must differ, or a run of one kind would resume the other kind's roster.
    assert DIRECTED_VILLAGE_SPEC_SCHEMA_NAME != VILLAGE_SPEC_SCHEMA_NAME


def test_a_directed_roster_is_cache_valid_only_under_the_directed_shape(tmp_path: Path) -> None:
    _write_bible(tmp_path, directed=True)
    from stage_gen.recipes.scrolling_preview import executor as executor_module
    from stage_gen.recipes.scrolling_preview.resident import (
        DIRECTED_VILLAGE_SPEC_SCHEMA_NAME,
    )

    path = tmp_path / f"village_spec_{TAG}.json"
    spec = DirectedVillageSpec.model_validate_json(path.read_bytes())
    sidecar: dict[str, Any] = {
        "params": {
            "schema_name": DIRECTED_VILLAGE_SPEC_SCHEMA_NAME,
            "artifact_value": "caller-canonicalized",
            "validated": True,
        },
        "validation": executor_module._village_spec_roster_record(spec),
    }
    assert executor_module._valid_village_spec_cache(path, sidecar, None, directed=True) is True
    # Read as undirected it is unparsable, which is what made it regenerate every run.
    assert executor_module._valid_village_spec_cache(path, sidecar, None, directed=False) is False
