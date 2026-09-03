from __future__ import annotations

from pathlib import Path


def test_map_contract_documents_the_exact_v10_terrain_camera_climbable_and_portal_ownership() -> (
    None
):
    repository = Path(__file__).parents[2]
    document = (repository / "docs/spec/game/map-generation-contract.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "`game-map-v10`",
        "`map-terrain-v1`",
        "### `[terrain]`",
        "### Camera",
        "`camera.follow_axes`",
        "Generated occupancy is gameplay geometry",
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
    # The retired identity, and the geometry that used to live in this document, must both be
    # gone rather than merely deprecated.
    assert "`game-map-v8`" not in document
    assert "`game-map-v7`" not in document
    assert "`ladder-4-tile-v1`" not in document
    # The camera moved out of the block that directs image generation. Both retired field names
    # must be gone from the authoring surface rather than documented as accepted aliases.
    assert "`view.camera_behavior` |" not in document
    assert "`view.scroll_axis` |" not in document
