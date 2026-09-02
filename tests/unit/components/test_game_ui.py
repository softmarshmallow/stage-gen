from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from stage_gen.components._game_input import AuthoredContractLoadError
from stage_gen.components.game_ui import (
    ATLAS_ALPHA_POLICY,
    BUTTON_RECT_LAYOUT,
    INVENTORY_PANEL_ALPHA_POLICY,
    INVENTORY_PANEL_LAYOUT,
    PANEL_FRAME_LAYOUT,
    inventory_panel_layout_contract,
    load_game_ui_bytes,
)
from stage_gen.resources import inventory_template_path

PACKAGE = Path(__file__).resolve().parents[3] / "library" / "games" / "bellweather"


def test_canonical_ui_contract_separates_presentation_from_gameplay() -> None:
    contract = load_game_ui_bytes((PACKAGE / "ui.toml").read_bytes())

    assert contract.game_id == "bellweather"
    assert contract.inventory_panel.layout == INVENTORY_PANEL_LAYOUT
    assert contract.inventory_panel.alpha_policy == INVENTORY_PANEL_ALPHA_POLICY
    assert "capacity" not in contract.model_dump(mode="json")
    layout = inventory_panel_layout_contract()
    assert layout["canvas"] == {"width": 1536, "height": 1024}
    slots = layout["slots"]
    assert isinstance(slots, list)
    assert len(slots) == 8


def test_ui_contract_carries_both_atlas_roles_and_pins_their_layouts() -> None:
    source = (PACKAGE / "ui.toml").read_bytes()
    contract = load_game_ui_bytes(source)

    assert contract.kind == "game-ui-v3"
    assert contract.panel_frame.layout == PANEL_FRAME_LAYOUT
    assert contract.button_rect.layout == BUTTON_RECT_LAYOUT
    assert contract.panel_frame.alpha_policy == ATLAS_ALPHA_POLICY
    assert contract.button_rect.reference_ids == ["cover_style"]

    swapped = source.replace(BUTTON_RECT_LAYOUT.encode(), PANEL_FRAME_LAYOUT.encode())
    with pytest.raises(AuthoredContractLoadError, match=r"button_rect\.layout must be"):
        load_game_ui_bytes(swapped)
    with pytest.raises(AuthoredContractLoadError, match="game-ui-v3"):
        load_game_ui_bytes(source.replace(b'kind = "game-ui-v3"', b'kind = "game-ui-v1"'))


def test_ui_contract_rejects_unknown_and_unused_references() -> None:
    source = (PACKAGE / "ui.toml").read_bytes()
    with pytest.raises(AuthoredContractLoadError, match="unknown IDs"):
        load_game_ui_bytes(source.replace(b'["cover_style"]', b'["missing_style"]'))

    unused = source.replace(
        b"[inventory_panel]",
        b"""[[references]]
reference_id = "unused_style"
source = "references/unused.png"
source_sha256 = "e8d27ab2d83210fe2bf8e4f072588614fbe293de75dae51677a96079f1e9f6a5"
rights_status = "redistribution-approved"
rights_basis = ["Reviewed package evidence."]

[inventory_panel]""",
    )
    with pytest.raises(AuthoredContractLoadError, match="unused reference IDs"):
        load_game_ui_bytes(unused)


def test_ui_contract_rejects_a_policy_that_allows_transparent_slots() -> None:
    source = (
        (PACKAGE / "ui.toml")
        .read_bytes()
        .replace(
            b"transparent_exterior_opaque_panel_v1",
            b"transparent_slots",
        )
    )

    with pytest.raises(AuthoredContractLoadError, match="literal_error"):
        load_game_ui_bytes(source)


def test_inventory_template_encodes_the_same_alpha_policy_as_the_output() -> None:
    with Image.open(inventory_template_path()) as image:
        assert image.mode == "RGBA"
        alpha = image.getchannel("A")

    assert alpha.getextrema() == (0, 255)
    assert alpha.crop((128, 160, 1408, 864)).getextrema() == (255, 255)
    assert alpha.crop((0, 0, 1536, 160)).getextrema() == (0, 0)
    assert alpha.crop((0, 864, 1536, 1024)).getextrema() == (0, 0)
    assert alpha.crop((0, 160, 128, 864)).getextrema() == (0, 0)
    assert alpha.crop((1408, 160, 1536, 864)).getextrema() == (0, 0)
