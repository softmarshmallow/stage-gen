from __future__ import annotations

import json
import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]
LOOKUP_PATH = (
    REPOSITORY_ROOT
    / "src/stage_gen/resources/terrain/godot_3x3_minimal_lookup_v1.json"
)
REFERENCE_PATH = (
    REPOSITORY_ROOT
    / "fixtures/image_gen_templates/terrain_atlas_godot_topology_reference.md"
)
ROW = re.compile(
    r"^\| `\((\d+), (\d+)\)` \| (?:`([01]{9})`|—) \|",
    re.MULTILINE,
)
TERRAIN_ROW = re.compile(
    r"^\| `\((\d+), (\d+)\)` \| `([01]{9})` \| `([^`]+)` \| `([^`]+)` \|",
    re.MULTILINE,
)


def test_terrain_atlas_cell_reference_matches_authoritative_lookup() -> None:
    contract = json.loads(LOOKUP_PATH.read_text(encoding="utf-8"))
    reference = REFERENCE_PATH.read_text(encoding="utf-8")
    observed = {
        (int(column), int(row)): mask
        for column, row, mask in ROW.findall(reference)
    }
    expected = {
        tuple(coordinate): mask for mask, coordinate in contract["lookup"].items()
    }
    placeholder = tuple(contract["placeholder_cell"])

    assert len(observed) == 48
    assert observed.pop(placeholder) == ""
    assert observed == expected


def test_terrain_atlas_cell_reference_neighbor_columns_match_each_mask() -> None:
    reference = REFERENCE_PATH.read_text(encoding="utf-8")
    rows = TERRAIN_ROW.findall(reference)
    assert len(rows) == 47

    for _, _, mask, connected_sides, filled_corners in rows:
        expected_sides = "+".join(
            direction
            for direction, index in (("N", 1), ("E", 5), ("S", 7), ("W", 3))
            if mask[index] == "1"
        )
        expected_corners = "+".join(
            direction
            for direction, index in (("NW", 0), ("NE", 2), ("SW", 6), ("SE", 8))
            if mask[index] == "1"
        )
        assert connected_sides == (expected_sides or "—")
        assert filled_corners == (expected_corners or "—")


def test_terrain_atlas_cell_reference_states_locked_selection_rules() -> None:
    reference = " ".join(REFERENCE_PATH.read_text(encoding="utf-8").split())

    for required in (
        "47 reachable masks",
        "nw, n, ne, w, center, e, sw, s, se",
        "both cardinal cells adjacent to that corner",
        "one-cell-high floating platforms",
        "not a 9-slice",
        "Smooth visual slopes",
        "cap is not necessarily grass",
        "fill is not necessarily dirt",
    ):
        assert required in reference
