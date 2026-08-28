from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from stage_gen.orchestration.game_package import resolve_game_package
from stage_gen.recipes.scrolling_preview.prepared_manifest import (
    PREPARED_RUNTIME_MANIFEST_KIND,
    PreparedManifestError,
    assemble_prepared_runtime,
    runtime_artifact_paths,
    verify_prepared_runtime,
)

REPOSITORY_ROOT = Path(__file__).parents[4]
BELLWEATHER = REPOSITORY_ROOT / "library/games/bellweather"


def _layer_validation(anchor: str, offset: float) -> dict[str, object]:
    """A minimal stand-in for the producer's measured placement record."""

    return {
        "placement": {
            "schema_version": 1,
            "kind": "prepared-map-layer-placement-v1",
            "vertical_anchor": anchor,
            "vertical_offset": offset,
            "vertical_offset_source": "measured",
            "minimum_seal_offset": offset if offset else None,
            "source_height": 12,
            "trimmed_height": 12,
            "trimmed_top": 0,
            "trimmed_bottom": 11,
        }
    }


def _terrain_artifact(map_id: str, package: object) -> bytes:
    """Geometry is a generated artifact now, so the manifest fixture has to supply one."""

    game_map = next(entry for entry in package.maps if entry.map_id == map_id)  # type: ignore[attr-defined]
    rows, columns = game_map.terrain.rows, game_map.terrain.columns
    surface = rows - game_map.terrain.walk_surface_row
    grid = [["0"] * columns for _ in range(rows)]
    for row in range(rows - surface, rows):
        grid[row] = ["1"] * columns
    placements = []
    if game_map.climbable is not None:
        for index, variant in enumerate(game_map.climbable.variants):
            column = 10 + index * 20
            grid[game_map.terrain.walk_surface_row - 4][column] = "1"
            placements.append(
                {
                    "climbable_id": f"c{index + 1}",
                    "variant_id": variant.variant_id,
                    "normalized_x": round((column + 0.5) / columns, 6),
                    "bottom_surface": "terrain",
                    "rise_tiles": 4,
                }
            )
    return json.dumps(
        {
            "schema_version": 1,
            "kind": "map-terrain-v1",
            "map_id": map_id,
            "occupancy": ["".join(row) for row in grid],
            "walk_surface_row": game_map.terrain.walk_surface_row,
            "climbable_placements": placements,
        }
    ).encode()


def _write_artifact(root: Path, relative_path: str, *, color: int = 40) -> None:
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix == ".mp3":
        target.write_bytes(b"ID3" + bytes([color]) * 32)
        return
    if relative_path.endswith("climbable.validation.json"):
        cells = _CLIMBABLE_CELLS_BY_PATH.get(relative_path, 1)
        target.write_text(
            json.dumps(
                {
                    "index_order": "left_to_right",
                    "placements": [
                        {
                            "index": index,
                            "target_bbox": [index * 40, 0, index * 40 + 32, 96],
                        }
                        for index in range(cells)
                    ],
                }
            ),
            encoding="utf-8",
        )
        return
    if relative_path.endswith(".validation.json"):
        anchor = _ANCHORS_BY_PATH.get(relative_path, "screen_bottom")
        offset = 0.0 if anchor in {"canvas_cover", "screen_top"} else 0.25
        target.write_text(json.dumps(_layer_validation(anchor, offset)), encoding="utf-8")
        return
    Image.new("RGBA", (16, 12), (color, 90, 180, 255)).save(target)


_ANCHORS_BY_PATH: dict[str, str] = {}
_CLIMBABLE_CELLS_BY_PATH: dict[str, int] = {}


def test_runtime_manifest_is_stable_id_bound_and_portable(tmp_path: Path) -> None:
    package = resolve_game_package(BELLWEATHER)
    complete = tmp_path / "complete"
    correction = tmp_path / "correction"
    _ANCHORS_BY_PATH.clear()
    _CLIMBABLE_CELLS_BY_PATH.clear()
    for game_map in package.maps:
        if game_map.climbable is not None:
            _CLIMBABLE_CELLS_BY_PATH[f"maps/{game_map.map_id}/climbable.validation.json"] = len(
                game_map.climbable.variants
            )
        for layer in game_map.layers:
            _ANCHORS_BY_PATH[f"maps/{game_map.map_id}/layers/{layer.layer_id}.validation.json"] = (
                layer.vertical_anchor
            )
    for relative_path in runtime_artifact_paths(package):
        if relative_path.endswith("/terrain.json"):
            map_id = relative_path.split("/")[1]
            for root in (correction, complete):
                target = root / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(_terrain_artifact(map_id, package))
            continue
        _write_artifact(complete, relative_path)
    padded_prop_path = "content/props/sunwheel_bread_stall.png"
    padded_prop = Image.new("RGBA", (16, 12), (0, 0, 0, 0))
    padded_prop.paste((40, 90, 180, 255), (0, 0, 16, 9))
    padded_prop.save(complete / padded_prop_path)
    corrected_path = "content/players/wayfarer/states/idle.png"
    _write_artifact(correction, corrected_path, color=210)

    output = tmp_path / "runtime"
    result = assemble_prepared_runtime(
        package,
        artifact_roots=(correction, complete),
        output_dir=output,
    )

    assert result.manifest["kind"] == PREPARED_RUNTIME_MANIFEST_KIND
    assert result.artifact_count == len(runtime_artifact_paths(package))
    assert result.manifest["entry_map_id"] == "sunpetal-crossing"
    maps = result.manifest["maps"]
    assert isinstance(maps, list)
    assert [entry["map_id"] for entry in maps] == [
        "sunpetal-crossing",
        "crowncrag-road",
    ]
    assert len(maps[0]["ground"]["occupancy"]) == package.maps[0].terrain.rows
    assert maps[0]["ground"]["terrain_asset"]["sha256"]
    assert maps[0]["layers"][2]["presentation"] == {
        "contrast": 0.84,
        "saturation": 0.9,
        "atmosphere_color": "#b8e8f4",
        "atmosphere_strength": 0.06,
        "detail_blur_screen_pixels": 0.65,
    }
    presentation = result.manifest["presentation"]
    assert isinstance(presentation, dict)
    assert presentation["contact_shadows"] == {
        "enabled": True,
        "opacity": 0.18,
        "softness_screen_pixels": 6.0,
    }
    assert "climbable" not in maps[0]
    assert maps[0]["portal"]["mode"] == "portal-pair-1x2-v1"
    climbable = maps[1]["climbable"]
    assert climbable["mode"] == "climbable-atlas-v1"
    assert climbable["index_order"] == "left_to_right"
    # Roster order is atlas order: ladders left to right, then ropes.
    assert [entry["variant_id"] for entry in climbable["variants"]] == [
        "bellroot_ladder",
        "shrine_rope_ladder",
        "bellrope_climb",
    ]
    assert [entry["role"] for entry in climbable["variants"]] == ["ladder", "ladder", "rope"]
    assert [entry["cell_index"] for entry in climbable["variants"]] == [0, 1, 2]
    assert all(
        entry["cell"]["width"] > 0 and entry["cell"]["height"] > 0
        for entry in climbable["variants"]
    )
    assert climbable["placements"][0] == {
        "climbable_id": "c1",
        "variant_id": "bellroot_ladder",
        "normalized_x": 0.109375,
        "bottom_surface": "terrain",
        "rise_tiles": 4,
    }
    assert len(climbable["placements"]) == 3
    assert maps[1]["portal"]["endpoints"][0]["anchor"] == "west_gate"
    player = result.manifest["player"]
    assert isinstance(player, dict)
    assert player["states"]["idle"] == {
        "source_facing": "right",
        "runtime_mirror": True,
        "columns": 4,
        "rows": 1,
        "source_frame_count": 4,
        "anchor": "bottom",
        "playback": {"mode": "hold", "canonical_frame_indices": [0]},
        "asset": player["states"]["idle"]["asset"],
    }
    assert player["states"]["crouch"] == {
        "source_facing": "right",
        "runtime_mirror": True,
        "columns": 4,
        "rows": 1,
        "source_frame_count": 4,
        "anchor": "bottom",
        "playback": {
            "mode": "loop",
            "canonical_frame_indices": [0, 1, 2, 3],
            "frames_per_second": 6,
        },
        "asset": player["states"]["crouch"]["asset"],
    }
    assert (player["dialogue"]["columns"], player["dialogue"]["rows"]) == (3, 2)
    npcs = result.manifest["npcs"]
    assert isinstance(npcs, list)
    assert all(
        npc["world"]
        == {
            "source_facing": "front",
            "runtime_mirror": False,
            "columns": 4,
            "rows": 1,
            "source_frame_count": 4,
            "anchor": "bottom",
            "playback": {"mode": "hold", "canonical_frame_indices": [0]},
            "asset": npc["world"]["asset"],
        }
        for npc in npcs
    )
    assert all((npc["dialogue"]["columns"], npc["dialogue"]["rows"]) == (2, 2) for npc in npcs)
    props = result.manifest["props"]
    assert isinstance(props, list)
    assert props[0]["prop_id"] == "sunwheel_bread_stall"
    assert props[0]["ground_contact_y_normalized"] == 0.75
    assert all(0 < prop["ground_contact_y_normalized"] <= 1 for prop in props)
    ui = result.manifest["ui"]
    assert isinstance(ui, dict)
    assert ui["inventory_panel"]["layout"] == "inventory_grid_4x2_v1"
    assert ui["inventory_panel"]["alpha_policy"] == ("transparent_exterior_opaque_panel_v1")
    assert len(ui["inventory_panel"]["slots"]) == 8
    corrected = output / corrected_path
    assert (
        hashlib.sha256(corrected.read_bytes()).hexdigest()
        == hashlib.sha256((correction / corrected_path).read_bytes()).hexdigest()
    )
    assert not any(str(output) in str(value) for value in result.manifest.values())
    closure = result.manifest["closure"]
    assert isinstance(closure, dict)
    assert verify_prepared_runtime(output) == {
        "schema_version": 1,
        "kind": "prepared-runtime-verification-v1",
        "valid": True,
        "game_id": "bellweather",
        "package_sha256": package.package_sha256,
        "artifact_count": len(runtime_artifact_paths(package)),
        "artifacts_sha256": closure["artifacts_sha256"],
    }


def test_runtime_manifest_missing_artifact_leaves_no_partial_output(tmp_path: Path) -> None:
    package = resolve_game_package(BELLWEATHER)
    incomplete = tmp_path / "incomplete"
    paths = runtime_artifact_paths(package)
    for relative_path in paths[:-1]:
        if relative_path.endswith("/terrain.json"):
            target = incomplete / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_terrain_artifact(relative_path.split("/")[1], package))
            continue
        _write_artifact(incomplete, relative_path)
    output = tmp_path / "runtime"

    with pytest.raises(PreparedManifestError, match="missing accepted runtime artifact"):
        assemble_prepared_runtime(
            package,
            artifact_roots=(incomplete,),
            output_dir=output,
        )

    assert not output.exists()
    assert list(tmp_path.glob(".runtime.assembling-*")) == []
