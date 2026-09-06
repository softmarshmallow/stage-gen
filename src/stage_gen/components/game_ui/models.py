"""Exact-current authored presentation contract for game user-interface art."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field, field_validator, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    PACKAGE_ID_PATTERN,
    SHA256_PATTERN,
    SNAKE_ID_PATTERN,
    normalized_text,
    parse_toml_contract,
    portable_relative_path,
    unique_values,
)
from stage_gen.components.game_ui.atlas import (
    ATLAS_ALPHA_POLICY,
    BUTTON_RECT_LAYOUT,
    PANEL_FRAME_LAYOUT,
)
from stage_gen.components.game_ui.cursors import CURSOR_ALPHA_POLICY, CURSOR_SET_LAYOUT
from stage_gen.components.game_ui.icons import ICON_ALPHA_POLICY, PREVIEW_ICONS_LAYOUT

GAME_UI_SCHEMA_VERSION = 5

INVENTORY_PANEL_LAYOUT = "inventory_grid_4x2_v1"
INVENTORY_PANEL_ALPHA_POLICY = "transparent_exterior_opaque_panel_v1"
INVENTORY_CANVAS_WIDTH = 1536
INVENTORY_CANVAS_HEIGHT = 1024
INVENTORY_PANEL_LEFT = 128
INVENTORY_PANEL_TOP = 160
INVENTORY_PANEL_WIDTH = 1280
INVENTORY_PANEL_HEIGHT = 704
INVENTORY_SLOT_LEFT = 208
INVENTORY_SLOT_TOP = 240
INVENTORY_SLOT_SIZE = 256
INVENTORY_SLOT_GUTTER = 32
INVENTORY_SLOT_COLUMNS = 4
INVENTORY_SLOT_ROWS = 2


class UiReference(PersistedContractModel):
    """One digest-bound visual reference selected by a UI role."""

    reference_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    source: str
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    rights_status: Literal["unreviewed", "restricted", "redistribution-approved"]
    rights_basis: list[str] = Field(min_length=1, max_length=16)

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        source = portable_relative_path(value, "UI reference source")
        if not source.startswith("references/"):
            raise ValueError("UI references must live under references/")
        if PurePosixPath(source).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("UI references must use PNG, JPEG, or WebP")
        return source

    @field_validator("rights_basis")
    @classmethod
    def validate_rights_basis(cls, value: list[str]) -> list[str]:
        normalized = [normalized_text(entry, "UI reference rights basis") for entry in value]
        unique_values(normalized, "UI reference rights basis")
        return normalized


class InventoryPanelDirection(PersistedContractModel):
    """Presentation inputs for the current fixed eight-slot inventory panel."""

    layout: Literal["inventory_grid_4x2_v1"]
    alpha_policy: Literal["transparent_exterior_opaque_panel_v1"]
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    prompt: str

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "inventory_panel.reference_ids")
        return value

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "inventory_panel.prompt", multiline=True)


class AtlasRoleDirection(PersistedContractModel):
    """Presentation inputs for one nine-slice atlas role.

    The layout id is the whole geometry contract: a role never authors cell rectangles or
    insets, because the producer renders its template from the declared geometry and the
    validate node publishes the *detected* geometry beside the artifact.
    """

    layout: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    alpha_policy: Literal["transparent_exterior_opaque_body_v1"]
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    prompt: str

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "atlas role reference_ids")
        return value

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "atlas role prompt", multiline=True)


class IconSetDirection(PersistedContractModel):
    """Presentation inputs for the fixed preview icon set.

    The glyphs, their order and the grid are the layout's, not the author's: an image model
    draws named, well-known symbols dependably and bespoke ones not, so a game may say how
    the set should look and nothing about what is in it. The prompt is style direction only.
    """

    layout: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    alpha_policy: Literal["transparent_exterior_opaque_glyph_v1"]
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    prompt: str

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "preview_icons.reference_ids")
        return value

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "preview_icons.prompt", multiline=True)


class CursorSetDirection(PersistedContractModel):
    """Presentation inputs for the fixed cursor set.

    Like the icon set, the pointers, their order, the grid and the hotspot rule per pointer
    are the layout's; the prompt is style direction only. Declared by a game whose runtime
    owns a mouse pointer, and by no other: a touch game or one that leaves the pointer to
    the browser would be authoring a picture it never draws.
    """

    layout: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    alpha_policy: Literal["transparent_exterior_opaque_glyph_v1"]
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    prompt: str

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "cursor_set.reference_ids")
        return value

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "cursor_set.prompt", multiline=True)


ATLAS_ROLE_LAYOUTS: dict[str, str] = {
    "panel_frame": PANEL_FRAME_LAYOUT,
    "button_rect": BUTTON_RECT_LAYOUT,
}

#: Every sheet role a document must declare, with the layout each is pinned to.
UI_SHEET_LAYOUTS: dict[str, str] = {**ATLAS_ROLE_LAYOUTS, "preview_icons": PREVIEW_ICONS_LAYOUT}

#: The sheet roles a document may declare, with the layout each is pinned to.
OPTIONAL_SHEET_LAYOUTS: dict[str, str] = {"cursor_set": CURSOR_SET_LAYOUT}


class GameUi(PersistedContractModel):
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


def inventory_panel_layout_contract() -> dict[str, object]:
    """Project the fixed V1 layout without making the web consumer infer geometry."""

    slots = []
    for row in range(INVENTORY_SLOT_ROWS):
        for column in range(INVENTORY_SLOT_COLUMNS):
            slots.append(
                {
                    "slot_id": f"slot_{row * INVENTORY_SLOT_COLUMNS + column}",
                    "x": INVENTORY_SLOT_LEFT
                    + column * (INVENTORY_SLOT_SIZE + INVENTORY_SLOT_GUTTER),
                    "y": INVENTORY_SLOT_TOP + row * (INVENTORY_SLOT_SIZE + INVENTORY_SLOT_GUTTER),
                    "width": INVENTORY_SLOT_SIZE,
                    "height": INVENTORY_SLOT_SIZE,
                }
            )
    return {
        "layout": INVENTORY_PANEL_LAYOUT,
        "alpha_policy": INVENTORY_PANEL_ALPHA_POLICY,
        "canvas": {"width": INVENTORY_CANVAS_WIDTH, "height": INVENTORY_CANVAS_HEIGHT},
        "panel_bounds": {
            "x": INVENTORY_PANEL_LEFT,
            "y": INVENTORY_PANEL_TOP,
            "width": INVENTORY_PANEL_WIDTH,
            "height": INVENTORY_PANEL_HEIGHT,
        },
        "slots": slots,
    }


def load_game_ui_bytes(data: bytes) -> GameUi:
    return parse_toml_contract(data, model=GameUi, label="game UI contract")


__all__ = [
    "ATLAS_ROLE_LAYOUTS",
    "GAME_UI_SCHEMA_VERSION",
    "INVENTORY_CANVAS_HEIGHT",
    "INVENTORY_CANVAS_WIDTH",
    "INVENTORY_PANEL_ALPHA_POLICY",
    "INVENTORY_PANEL_HEIGHT",
    "INVENTORY_PANEL_LAYOUT",
    "INVENTORY_PANEL_LEFT",
    "INVENTORY_PANEL_TOP",
    "INVENTORY_PANEL_WIDTH",
    "INVENTORY_SLOT_COLUMNS",
    "INVENTORY_SLOT_GUTTER",
    "INVENTORY_SLOT_LEFT",
    "INVENTORY_SLOT_ROWS",
    "INVENTORY_SLOT_SIZE",
    "INVENTORY_SLOT_TOP",
    "OPTIONAL_SHEET_LAYOUTS",
    "UI_SHEET_LAYOUTS",
    "AtlasRoleDirection",
    "CursorSetDirection",
    "GameUi",
    "IconSetDirection",
    "InventoryPanelDirection",
    "UiReference",
    "inventory_panel_layout_contract",
    "load_game_ui_bytes",
]
