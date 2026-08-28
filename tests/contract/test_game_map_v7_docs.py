from __future__ import annotations

from pathlib import Path


def test_map_contract_documents_exact_v7_placement_terrain_climbable_and_portal_ownership() -> None:
    repository = Path(__file__).parents[2]
    document = (repository / "docs/spec/game/map-generation-contract.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "`game-map-v7`",
        "`occupancy` is authored gameplay geometry",
        "`climbable-atlas-v1`",
        '`mode = "portal-pair-1x2-v1"`',
        "The map owns each endpoint's anchor, placement, and visual role.",
        "player may climb remains `gameplay.toml` navigation policy.",
        "## Vertical placement contract",
        "`vertical_anchor`",
        "`floor_to_screen_bottom`",
        "`walk_surface_row`",
        "full-coverage line",
    ):
        assert required in document
    assert "`game-map-v6`" not in document
    assert "`ladder-4-tile-v1`" not in document
