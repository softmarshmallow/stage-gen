"""Shared game UI bundle; individual artwork lives in ui_art."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from demo_game_tools.media.ui.atlas import (
    ATLAS_ALPHA_POLICY,
)
from demo_game_tools.media.ui.cursors import CURSOR_ALPHA_POLICY, CURSOR_SET_LAYOUT
from demo_game_tools.media.ui.icons import ICON_ALPHA_POLICY, PREVIEW_ICONS_LAYOUT
from stage_gen.components._game_input import (
    PACKAGE_ID_PATTERN,
    parse_toml_contract,
    unique_values,
)
from stage_gen.components.ui_art.models import (
    ATLAS_ROLE_LAYOUTS as ATLAS_ROLE_LAYOUTS,
)
from stage_gen.components.ui_art.models import (
    INVENTORY_CANVAS_HEIGHT as INVENTORY_CANVAS_HEIGHT,
)
from stage_gen.components.ui_art.models import (
    INVENTORY_CANVAS_WIDTH as INVENTORY_CANVAS_WIDTH,
)
from stage_gen.components.ui_art.models import (
    INVENTORY_PANEL_ALPHA_POLICY as INVENTORY_PANEL_ALPHA_POLICY,
)
from stage_gen.components.ui_art.models import (
    INVENTORY_PANEL_HEIGHT as INVENTORY_PANEL_HEIGHT,
)
from stage_gen.components.ui_art.models import (
    INVENTORY_PANEL_LAYOUT as INVENTORY_PANEL_LAYOUT,
)
from stage_gen.components.ui_art.models import (
    INVENTORY_PANEL_LEFT as INVENTORY_PANEL_LEFT,
)
from stage_gen.components.ui_art.models import (
    INVENTORY_PANEL_TOP as INVENTORY_PANEL_TOP,
)
from stage_gen.components.ui_art.models import (
    INVENTORY_PANEL_WIDTH as INVENTORY_PANEL_WIDTH,
)
from stage_gen.components.ui_art.models import (
    INVENTORY_SLOT_COLUMNS as INVENTORY_SLOT_COLUMNS,
)
from stage_gen.components.ui_art.models import (
    INVENTORY_SLOT_GUTTER as INVENTORY_SLOT_GUTTER,
)
from stage_gen.components.ui_art.models import (
    INVENTORY_SLOT_LEFT as INVENTORY_SLOT_LEFT,
)
from stage_gen.components.ui_art.models import (
    INVENTORY_SLOT_ROWS as INVENTORY_SLOT_ROWS,
)
from stage_gen.components.ui_art.models import (
    INVENTORY_SLOT_SIZE as INVENTORY_SLOT_SIZE,
)
from stage_gen.components.ui_art.models import (
    INVENTORY_SLOT_TOP as INVENTORY_SLOT_TOP,
)
from stage_gen.components.ui_art.models import (
    OPTIONAL_SHEET_LAYOUTS as OPTIONAL_SHEET_LAYOUTS,
)
from stage_gen.components.ui_art.models import (
    UI_SHEET_LAYOUTS as UI_SHEET_LAYOUTS,
)
from stage_gen.components.ui_art.models import (
    AtlasRoleDirection as AtlasRoleDirection,
)
from stage_gen.components.ui_art.models import (
    CursorSetDirection as CursorSetDirection,
)
from stage_gen.components.ui_art.models import (
    IconSetDirection as IconSetDirection,
)
from stage_gen.components.ui_art.models import (
    InventoryPanelDirection as InventoryPanelDirection,
)
from stage_gen.components.ui_art.models import (
    UiArtwork as UiArtwork,
)
from stage_gen.components.ui_art.models import (
    UiReference as UiReference,
)
from stage_gen.components.ui_art.models import (
    inventory_panel_layout_contract as inventory_panel_layout_contract,
)

GAME_UI_SCHEMA_VERSION = 5


class GameUi(UiArtwork):
    """One root UI document, deliberately separate from gameplay rules.

    Every genre draws panels, buttons and a handful of system icons, so the two atlas
    roles and the preview icon set are required of any game that has a UI document at
    all. The inventory panel and the cursor set are not: the panel is one genre's fixed
    eight-slot furniture, and the cursors belong to a runtime that owns a mouse pointer;
    a visual novel or a puzzle room that declared either would be authoring a screen it
    never draws. A recipe whose runtime needs one refuses a document without it at
    resolve time, where the requirement belongs.
    """

    schema_version: Literal[5]
    kind: Literal["game-ui-v5"]
    game_id: str = Field(pattern=PACKAGE_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    references: list[UiReference] = Field(min_length=1, max_length=32)
    inventory_panel: InventoryPanelDirection | None = None
    panel_frame: AtlasRoleDirection
    button_rect: AtlasRoleDirection
    preview_icons: IconSetDirection
    cursor_set: CursorSetDirection | None = None

    def required_inventory_panel(self) -> InventoryPanelDirection:
        """The panel, for a recipe whose runtime draws it and cannot proceed without it."""

        if self.inventory_panel is None:
            raise ValueError("this UI document declares no inventory panel")
        return self.inventory_panel

    @model_validator(mode="after")
    def validate_sheet_layouts(self) -> GameUi:
        for role, expected in ATLAS_ROLE_LAYOUTS.items():
            direction: AtlasRoleDirection = getattr(self, role)
            if direction.layout != expected:
                raise ValueError(f"{role}.layout must be {expected!r}, got {direction.layout!r}")
            if direction.alpha_policy != ATLAS_ALPHA_POLICY:
                raise ValueError(f"{role}.alpha_policy must be {ATLAS_ALPHA_POLICY!r}")
        if self.preview_icons.layout != PREVIEW_ICONS_LAYOUT:
            raise ValueError(
                f"preview_icons.layout must be {PREVIEW_ICONS_LAYOUT!r}, "
                f"got {self.preview_icons.layout!r}"
            )
        if self.preview_icons.alpha_policy != ICON_ALPHA_POLICY:
            raise ValueError(f"preview_icons.alpha_policy must be {ICON_ALPHA_POLICY!r}")
        if self.cursor_set is not None:
            if self.cursor_set.layout != CURSOR_SET_LAYOUT:
                raise ValueError(
                    f"cursor_set.layout must be {CURSOR_SET_LAYOUT!r}, "
                    f"got {self.cursor_set.layout!r}"
                )
            if self.cursor_set.alpha_policy != CURSOR_ALPHA_POLICY:
                raise ValueError(f"cursor_set.alpha_policy must be {CURSOR_ALPHA_POLICY!r}")
        return self

    @model_validator(mode="after")
    def validate_reference_closure(self) -> GameUi:
        unique_values((entry.reference_id for entry in self.references), "UI reference_id")
        unique_values((entry.source for entry in self.references), "UI reference source")
        declared = {entry.reference_id for entry in self.references}
        selected: set[str] = set()
        for role in ("inventory_panel", *UI_SHEET_LAYOUTS, *OPTIONAL_SHEET_LAYOUTS):
            direction = getattr(self, role)
            if direction is None:
                continue
            unknown = sorted(set(direction.reference_ids) - declared)
            if unknown:
                raise ValueError(f"{role} references unknown IDs: " + ", ".join(unknown))
            selected.update(direction.reference_ids)
        unused = sorted(declared - selected)
        if unused:
            raise ValueError("UI declares unused reference IDs: " + ", ".join(unused))
        return self


def load_game_ui_bytes(data: bytes) -> GameUi:
    return parse_toml_contract(data, model=GameUi, label="game UI contract")
