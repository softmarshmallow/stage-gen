from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

from stage_gen.components.game_map import PreparedGameMap, load_prepared_game_map_bytes
from stage_gen.components.game_map.prepared import (
    load_prepared_map_terrain_bytes,
    validate_generated_terrain,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
LIBRARY_ROOT = REPOSITORY_ROOT / "library" / "games"


def _load_script() -> ModuleType:
    path = REPOSITORY_ROOT / "scripts/design_map.py"
    spec = importlib.util.spec_from_file_location("design_map", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()


def _map(map_id: str) -> PreparedGameMap:
    return load_prepared_game_map_bytes(
        (LIBRARY_ROOT / "bellweather" / "maps" / f"{map_id}.toml").read_bytes()
    )


def test_the_profile_is_derived_from_the_authored_map_rather_than_restated() -> None:
    # The point of the terrain contract: the rules a design is judged against come from the map
    # itself, so a second copy cannot drift away from the document it claims to describe.
    assert not hasattr(SCRIPT, "BELLWEATHER_SIDE_VIEW")
    for map_id in ("crowncrag-road", "sunpetal-crossing"):
        game_map = _map(map_id)
        profile = SCRIPT.terrain_profile(game_map)
        assert profile.geometry.columns == game_map.terrain.columns
        assert profile.geometry.rows == game_map.terrain.rows


def test_a_map_without_a_climbable_atlas_gets_no_climbable_words() -> None:
    # The village declares no atlas, so the grammar it is offered cannot name a ladder at all.
    village = SCRIPT.terrain_profile(_map("sunpetal-crossing"))
    words = SCRIPT.vocabulary(village)
    assert "perch" not in words and "tower" not in words
    assert village.climbable_variants == ()

    road = SCRIPT.terrain_profile(_map("crowncrag-road"))
    assert "perch" in SCRIPT.vocabulary(road)
    assert road.climbable_variants


def test_the_profile_restates_the_consumers_own_traversal_constants() -> None:
    # This is what stops the designer's idea of the game drifting from the runtime's.
    from stage_gen.components.game_map.prepared import MAX_UNASSISTED_TERRAIN_RISE_TILES
    from stage_gen.recipes.scrolling_preview import terrain_design

    profile = SCRIPT.terrain_profile(_map("crowncrag-road"))
    movement = profile.movement
    assert movement.max_step_up_tiles == MAX_UNASSISTED_TERRAIN_RISE_TILES
    assert movement.jump_reach == terrain_design.TERRAIN_JUMP_REACH
    assert movement.level_gap_tiles == terrain_design.TERRAIN_LEVEL_GAP_TILES
    assert movement.climbable_rise_tiles == terrain_design.TERRAIN_CLIMBABLE_RISE_TILES
    # Boundary behaviour, not just the table: a retune of web/lib/runtime/player.ts should fail
    # here rather than in a browser.
    assert movement.reachable(1, 8) and not movement.reachable(1, 9)
    assert movement.reachable(2, 6) and not movement.reachable(2, 7)
    assert not movement.reachable(3, 0)


def test_expand_refuses_a_design_that_would_resize_the_grid() -> None:
    game_map = _map("crowncrag-road")
    profile = SCRIPT.terrain_profile(game_map)
    design = SCRIPT.example_design(game_map).model_copy(update={"columns": 200})
    with pytest.raises(SCRIPT.MapDesignError, match="may not resize the grid"):
        SCRIPT.expand(design, profile)


def test_check_accepts_the_example_and_rejects_an_unreachable_design(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert SCRIPT.main(["check", "--map", "crowncrag-road", "--example"]) == 0

    game_map = _map("crowncrag-road")
    stranded = SCRIPT.example_design(game_map).model_copy(
        update={
            "chunks": [
                {"kind": "run", "len": 40},
                {
                    "kind": "hop_chain",
                    "count": 2,
                    "jump_rise": 2,
                    "gap": 6,
                    "platform_width": 4,
                    "dir": "up",
                },
                {"kind": "run", "len": 20},
            ]
        }
    )
    path = tmp_path / "stranded.json"
    path.write_text(stranded.model_dump_json())
    assert SCRIPT.main(["check", "--map", "crowncrag-road", "--design", str(path)]) == 1
    assert "REJECTED" in capsys.readouterr().out


def test_render_writes_a_png_and_refuses_to_write_into_docs(tmp_path: Path) -> None:
    out = tmp_path / "road.png"
    assert SCRIPT.main(["render", "--map", "crowncrag-road", "--example", "--out", str(out)]) == 0
    assert out.is_file() and out.stat().st_size > 0

    with pytest.raises(SCRIPT.MapDesignError, match="refusing to write"):
        game_map = _map("crowncrag-road")
        profile = SCRIPT.terrain_profile(game_map)
        designed, _ = SCRIPT.expand(SCRIPT.example_design(game_map), profile)
        SCRIPT.render(designed, profile, REPOSITORY_ROOT / "docs/media/nope.png", "no")


def test_compile_writes_a_terrain_artifact_the_map_accepts(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    assert (
        SCRIPT.main(["compile", "--map", "crowncrag-road", "--example", "--run-dir", str(run_dir)])
        == 0
    )
    artifact = run_dir / "maps/crowncrag-road/terrain.json"
    assert artifact.is_file()
    terrain = load_prepared_map_terrain_bytes(artifact.read_bytes())
    game_map = _map("crowncrag-road")
    # The artifact must satisfy the map it was compiled for, not merely parse.
    validate_generated_terrain(game_map, terrain)
    assert terrain.map_id == "crowncrag-road"
    assert len(terrain.occupancy) == game_map.terrain.rows
    assert terrain.walk_surface_row == game_map.terrain.walk_surface_row


def test_compile_never_writes_into_the_authored_library(tmp_path: Path) -> None:
    # Terrain is a run artifact. Nothing this script does may edit a map document.
    library = tmp_path / "games"
    shutil.copytree(LIBRARY_ROOT, library)
    before = {path: path.read_bytes() for path in sorted(library.rglob("*")) if path.is_file()}
    assert (
        SCRIPT.main(
            [
                "compile",
                "--map",
                "crowncrag-road",
                "--example",
                "--run-dir",
                str(tmp_path / "run"),
                "--library-root",
                str(library),
            ]
        )
        == 0
    )
    after = {path: path.read_bytes() for path in sorted(library.rglob("*")) if path.is_file()}
    assert after == before


def test_design_without_the_live_opt_in_makes_no_provider_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("STAGE_GEN_RUN_LIVE", raising=False)
    assert (
        SCRIPT.main(["design", "--map", "crowncrag-road", "--out", str(tmp_path / "design.json")])
        == 1
    )
    assert "provider" in capsys.readouterr().out
    assert not (tmp_path / "design.json").exists()


def test_the_example_sentence_stays_valid_for_the_shipped_road() -> None:
    # A canned example that silently stopped satisfying the map would make every other test here
    # vacuous, so it is asserted rather than assumed.
    game_map = _map("crowncrag-road")
    profile = SCRIPT.terrain_profile(game_map)
    _, problems = SCRIPT.expand(SCRIPT.example_design(game_map), profile)
    assert problems == []


def test_the_shipped_maps_carry_a_terrain_request_and_no_geometry() -> None:
    for map_id in ("crowncrag-road", "sunpetal-crossing"):
        text = (LIBRARY_ROOT / "bellweather" / "maps" / f"{map_id}.toml").read_text()
        assert "occupancy = [" not in text
        assert "[[climbable.placements]]" not in text
        assert '[terrain]\nmode = "platformer-chunk-map-v1"' in text
        game_map = _map(map_id)
        assert game_map.kind == "game-map-v8"
        assert json.loads(game_map.terrain.model_dump_json())["brief"].strip()
