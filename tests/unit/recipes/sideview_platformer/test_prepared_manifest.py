from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from stage_gen.components.game_ui import ATLAS_ROLES, atlas_role_contract, validate_atlas_image
from stage_gen.orchestration.game_package import ResolvedGamePackage, resolve_game_package
from stage_gen.recipes.sideview_platformer.prepared_manifest import (
    PREPARED_RUNTIME_MANIFEST_KIND,
    RUNTIME_ARTIFACT_ROLES,
    PreparedManifestError,
    _bound_artifact_paths,
    _validate_closure_roles,
    assemble_prepared_runtime,
    runtime_artifact_closure,
    runtime_artifact_paths,
    verify_prepared_runtime,
)
from tests.unit._ui_atlas_fixture import atlas_sheet

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
    if relative_path.endswith(("motion-rebase.json", "motion-rebase-first-pass.json")):
        target.write_text(
            json.dumps(
                {
                    "baseline_state": "idle",
                    "states": {
                        state: 1.0 for state in _MOTION_REBASE_STATES_BY_PATH[relative_path]
                    },
                    "plate_sha256": "0" * 64,
                    "verification_plate_sha256": "1" * 64,
                }
            ),
            encoding="utf-8",
        )
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
    if relative_path.startswith("ui/") and relative_path.endswith(".validation.json"):
        role = ATLAS_ROLES[relative_path[len("ui/") : -len(".validation.json")]]
        facts = validate_atlas_image(atlas_sheet(role), role)
        target.write_text(
            json.dumps({"schema_version": 1, "kind": "x", **atlas_role_contract(facts)}),
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
_MOTION_REBASE_STATES_BY_PATH: dict[str, list[str]] = {}


def _prepare_complete_root(root: Path, package: ResolvedGamePackage, *, color: int = 40) -> None:
    """Prime the placement stand-ins and write one complete accepted artifact set."""

    _ANCHORS_BY_PATH.clear()
    _CLIMBABLE_CELLS_BY_PATH.clear()
    _MOTION_REBASE_STATES_BY_PATH.clear()
    for player_content in package.player.players:
        _rebase_states = [motion.state for motion in player_content.motions]
        _MOTION_REBASE_STATES_BY_PATH[
            f"content/players/{player_content.player_id}/motion-rebase.json"
        ] = _rebase_states
        _MOTION_REBASE_STATES_BY_PATH[
            f"content/players/{player_content.player_id}/motion-rebase-first-pass.json"
        ] = _rebase_states
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
            target = root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_terrain_artifact(relative_path.split("/")[1], package))
            continue
        _write_artifact(root, relative_path, color=color)
    padded_prop = Image.new("RGBA", (16, 12), (0, 0, 0, 0))
    padded_prop.paste((color, 90, 180, 255), (0, 0, 16, 9))
    padded_prop.save(root / "content/props/sunwheel_bread_stall.png")


def test_runtime_manifest_is_stable_id_bound_and_portable(tmp_path: Path) -> None:
    package = resolve_game_package(BELLWEATHER)
    complete = tmp_path / "complete"
    correction = tmp_path / "correction"
    _ANCHORS_BY_PATH.clear()
    _CLIMBABLE_CELLS_BY_PATH.clear()
    _MOTION_REBASE_STATES_BY_PATH.clear()
    for player_content in package.player.players:
        _rebase_states = [motion.state for motion in player_content.motions]
        _MOTION_REBASE_STATES_BY_PATH[
            f"content/players/{player_content.player_id}/motion-rebase.json"
        ] = _rebase_states
        _MOTION_REBASE_STATES_BY_PATH[
            f"content/players/{player_content.player_id}/motion-rebase-first-pass.json"
        ] = _rebase_states
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
    for role, cells in (("panel_frame", 1), ("button_rect", 4)):
        atlas = ui[role]
        assert atlas["role"] == role
        assert atlas["scale_mode"] == "nine_slice"
        assert atlas["alpha_policy"] == "transparent_exterior_opaque_body_v1"
        assert atlas["band_fill"] == "stretch"
        assert len(atlas["cells"]) == cells
        assert set(atlas["insets"]) == {"left", "top", "right", "bottom"}
        assert atlas["asset"]["path"] == f"ui/{role}.png"
        assert "facts" not in atlas
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


def test_publishing_a_run_tag_is_immutable_until_replacement_is_explicit(tmp_path: Path) -> None:
    package = resolve_game_package(BELLWEATHER)
    complete = tmp_path / "complete"
    _prepare_complete_root(complete, package)
    output = tmp_path / "runtime"

    created = assemble_prepared_runtime(
        package,
        artifact_roots=(complete,),
        output_dir=output,
    )
    assert created.disposition == "created"
    assert created.replaced_manifest_sha256 is None
    published = (output / "manifest.json").read_bytes()

    # Integration is deterministic, so republishing the same closure is a no-op, not a conflict.
    unchanged = assemble_prepared_runtime(
        package,
        artifact_roots=(complete,),
        output_dir=output,
    )
    assert unchanged.disposition == "unchanged"
    assert unchanged.replaced_manifest_sha256 is None
    assert (output / "manifest.json").read_bytes() == published

    # Different bytes under one tag change what every citation of that tag means, so the default
    # refuses and leaves the published run exactly as it was.
    recolored = tmp_path / "recolored"
    _prepare_complete_root(recolored, package, color=90)
    with pytest.raises(PreparedManifestError, match="already exists with different content"):
        assemble_prepared_runtime(
            package,
            artifact_roots=(recolored,),
            output_dir=output,
        )
    assert (output / "manifest.json").read_bytes() == published

    replaced = assemble_prepared_runtime(
        package,
        artifact_roots=(recolored,),
        output_dir=output,
        replace_output=True,
    )
    assert replaced.disposition == "replaced"
    assert replaced.replaced_manifest_sha256 == hashlib.sha256(published).hexdigest()
    assert (output / "manifest.json").read_bytes() != published
    verify_prepared_runtime(output)
    assert list(tmp_path.glob(".runtime.assembling-*")) == []
    assert list(tmp_path.glob(".runtime.retired-*")) == []


def _artifact(path: str, role: str) -> dict[str, object]:
    return {
        "path": path,
        "sha256": "0" * 64,
        "bytes": 1,
        "media_type": "image/png",
        "role": role,
    }


def test_every_published_artifact_declares_the_role_the_closure_expects(tmp_path: Path) -> None:
    """The graph's declaration and the assembler's publication are one statement, not two."""

    package = resolve_game_package(BELLWEATHER)
    complete = tmp_path / "complete"
    _prepare_complete_root(complete, package)

    result = assemble_prepared_runtime(
        package,
        artifact_roots=(complete,),
        output_dir=tmp_path / "runtime",
    )

    closure = result.manifest["closure"]
    assert isinstance(closure, dict)
    artifacts = closure["artifacts"]
    assert isinstance(artifacts, list)
    published = tuple((record["path"], record["role"]) for record in artifacts)
    assert published == runtime_artifact_closure(package)
    # A role is a decision rather than a default, so both the vocabulary allows are in use.
    assert {role for _, role in published} == set(RUNTIME_ARTIFACT_ROLES)


def test_assets_are_exactly_what_the_manifest_binds(tmp_path: Path) -> None:
    """A consumer enumerating assets can trust the role instead of guessing from the path."""

    package = resolve_game_package(BELLWEATHER)
    complete = tmp_path / "complete"
    _prepare_complete_root(complete, package)

    result = assemble_prepared_runtime(
        package,
        artifact_roots=(complete,),
        output_dir=tmp_path / "runtime",
    )

    closure = result.manifest["closure"]
    assert isinstance(closure, dict)
    artifacts = closure["artifacts"]
    assert isinstance(artifacts, list)
    assets = {record["path"] for record in artifacts if record["role"] == "asset"}
    provenance = {record["path"] for record in artifacts if record["role"] == "provenance"}
    assert _bound_artifact_paths(result.manifest) == assets
    assert provenance and not provenance & assets
    player_id = package.player.players[0].player_id
    # The case no media type can classify: a judged plate is a PNG that nothing presents.
    assert f"content/players/{player_id}/motion-rebase-plate.png" in provenance
    assert f"content/players/{player_id}/states/idle.png" in assets


def test_assembly_rejects_an_asset_no_binding_claims() -> None:
    manifest: dict[str, object] = {"items": []}

    with pytest.raises(PreparedManifestError, match="without a manifest binding"):
        _validate_closure_roles(
            manifest, {"content/items/coin.png": _artifact("content/items/coin.png", "asset")}
        )


def test_assembly_rejects_a_binding_the_closure_does_not_publish_as_an_asset() -> None:
    record = _artifact("maps/meadow/terrain.json", "provenance")
    manifest: dict[str, object] = {"maps": [{"ground": {"terrain_asset": record}}]}

    with pytest.raises(PreparedManifestError, match="not published as assets"):
        _validate_closure_roles(manifest, {"maps/meadow/terrain.json": record})


def test_verification_rejects_a_closure_artifact_with_no_declared_role(tmp_path: Path) -> None:
    package = resolve_game_package(BELLWEATHER)
    complete = tmp_path / "complete"
    _prepare_complete_root(complete, package)
    output = tmp_path / "runtime"
    assemble_prepared_runtime(package, artifact_roots=(complete,), output_dir=output)

    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    del manifest["closure"]["artifacts"][0]["role"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(PreparedManifestError, match="declares no known role"):
        verify_prepared_runtime(output)
