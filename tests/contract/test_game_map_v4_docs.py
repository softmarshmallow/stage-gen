from __future__ import annotations

from pathlib import Path


def test_map_contract_documents_exact_v4_terrain_ladder_and_portal_ownership() -> None:
    repository = Path(__file__).parents[2]
    document = (repository / "docs/spec/game/map-generation-contract.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "`game-map-v4`",
        "`occupancy` is authored gameplay geometry",
        "`ladder-4-tile-v1`",
        '`mode = "portal-pair-1x2-v1"`',
        "The map owns each endpoint's anchor, placement, and visual role.",
        "player may climb remains `gameplay.toml` navigation policy.",
    ):
        assert required in document
    assert "`game-map-v3`" not in document
