#!/usr/bin/env python3
"""Render the asset-scale documentation figures from a prepared game package.

Both figures are deterministic composites of published package bytes: no
provider call, no retouching, and no pixel the pipeline did not already
produce.

``asset-unit-calibration.webp`` draws one map twice under two sizing rules.
Above, the per-class pixel constant the runtime shipped, applied to each
untrimmed canvas. Below, each subject's judged height in tiles projected
through the asset unit. Both panels carry a ruler marking one, two and three
player heights.

``motion-rebase-ab.webp`` draws every frame of one actor at one uniform source
scale: the shipped per-state scale beside the same frames rebased onto the idle
baseline, with each panel's baseline crown drawn across every state.

This proves the sizing arithmetic and the composition. It does not approve
generated appearance, and it authors no contract.

Glyph rasterization depends on the fonts installed on the rendering machine, so
committed figure bytes are the author's render rather than a cross-machine
reproducible artifact. The build a figure was composited from is recorded in
the prose that carries it.

    uv run python scripts/render_asset_scale_figures.py \
        --package out/bellweather-prepared-v11-bound --output docs/media
    uv run python scripts/render_asset_scale_figures.py \
        --package out/bellweather-prepared-v11-bound --output build/figures \
        --figure motion-rebase
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from PIL import Image, ImageDraw, ImageFont

_Font = ImageFont.FreeTypeFont | ImageFont.ImageFont

GAME_ID: Final = "bellweather"
MAP_ID: Final = "sunpetal-crossing"

VIEW_WIDTH: Final = 1280
VIEW_HEIGHT: Final = 720
TILE_PX: Final = 64
CAMERA_X: Final = 560
ATLAS_CELL_PX: Final = 120
ATLAS_INSET_PX: Final = 10

# Mirrors the runtime's painted-alpha threshold, so a subject measured here has
# the extent the consumer would measure.
ALPHA_THRESHOLD: Final = 64

PLAYER_PX: Final = 154
IDLE_CELL_PX: Final = 822
PLAYER_NORMALIZED_X: Final = 0.135

# The shipped rule: one pixel constant per class, applied to the untrimmed
# canvas. These are the constants the runtime carried, reproduced so the figure
# shows what actually shipped rather than a reconstruction of it.
SHIPPED_STALL_PX: Final = 170
SHIPPED_PROP_PX: Final = 110
SHIPPED_NPC_PX: Final = 150

STATE_ORDER: Final = (
    "idle",
    "walk",
    "run",
    "jump",
    "crouch",
    "climb",
    "basic_attack",
    "skill_cast",
    "hurt",
    "death",
)

# States the shipped runtime rescaled from their own cell height. Everything
# else inherited the idle cell, which is why those states collapse.
SYNTH_STATES: Final = frozenset(
    {"idle", "walk", "run", "jump", "crouch", "climb", "basic_attack", "skill_cast"}
)

# Per-state multipliers against the idle baseline, judged once for the study
# against this package's motion atlases. These are figure inputs, not authored
# declarations: the contract authority for a rebase record is
# docs/spec/motion-rebase.md, and a real multiplier is derived from the
# artwork rather than written by hand.
REBASE: Final[Mapping[str, float]] = {
    "idle": 1.00,
    "walk": 1.00,
    "run": 1.25,
    "jump": 1.20,
    "crouch": 1.09,
    "climb": 1.05,
    "basic_attack": 1.18,
    "skill_cast": 1.22,
    "hurt": 1.08,
    "death": 1.22,
}

# Intended world size in tiles, read off the artwork by eye, anchored on the
# player at 2.40 tiles. This is the free-estimate starting catalogue the study
# began from: the comparison plate later revised the well from 2.60 to 2.40,
# and the figure deliberately shows the 2.60 estimate. Correcting a value here
# silently changes committed pixels, so leave the table as judged.
JUDGED: Final[Mapping[str, float]] = {
    # props
    "bridge_lantern_stand": 3.20,  # iron rack, lanterns hang above head height
    "flowered_village_bench": 1.10,  # seat and low backrest, about waist high
    "herb_drying_rack": 2.60,  # timber frame, top bar just over head
    "homeward_signpost": 3.00,  # trail post, arrows well above head
    "menders_handcart": 1.50,  # wheel to waist, handles rise a little
    "millers_grain_stall": 3.20,  # market stall, awning clears a standing adult
    "petalstone_well": 2.60,  # stone rim is knee high, but the A-frame is tall
    "sunwheel_bread_stall": 3.00,  # market stall with awning
    # npcs
    "brom_copperkeg": 2.15,  # dwarf smith, stocky and short
    "elowen_thistledew": 2.50,  # elf herbalist, slender and slightly tall
    "mara_crumbwell": 2.40,  # baker, same build as the player
    "pip_pennant": 2.25,  # young messenger, a touch shorter
    # mobs
    "bellbelly_toad": 1.10,  # squat and wide
    "bramblehart": 1.80,  # deer-thing, chest high to the player
    "crowncrag_page_eater": 3.20,  # boss dragon, must loom
    "jewelwing_beetle": 0.70,  # big beetle
    "petal_puff": 0.70,  # small puffball
    "thimblejay": 1.00,  # bird, knee high
    # items
    "castle_moonkey": 0.35,
    "rosehip_tart": 0.30,
    "runaway_story_page": 0.45,
    "spindlehook": 0.50,
    "sunleaf_coin": 0.25,
    # player
    "wayfarer": 2.40,  # the anchor
}

CALLOUT_SUBJECT: Final = "petalstone_well"

PAGE: Final = (250, 248, 245)
PANEL: Final = (240, 236, 229)
INK: Final = (26, 24, 22)
MUTED: Final = (124, 117, 108)
HEADER_INK: Final = (24, 22, 20)
HEADER_TEXT: Final = (248, 246, 243)
HEADER_MUTED: Final = (168, 162, 153)
HEADER_ACCENT: Final = (233, 146, 105)
BAND_INK: Final = (38, 35, 32)
BAND_MUTED: Final = (163, 157, 148)
GROUND_RULE: Final = (158, 149, 136)

SHIPPED_COLOR: Final = (216, 96, 52)
JUDGED_COLOR: Final = (36, 168, 124)
SHIPPED_FRAME_COLOR: Final = (176, 67, 31)
REBASED_FRAME_COLOR: Final = (11, 125, 92)

FONT_DIRECTORIES: Final = (
    Path("/System/Library/Fonts/Supplemental"),
    Path("/Library/Fonts"),
    Path("/usr/share/fonts/truetype/liberation"),
    Path("/usr/share/fonts/truetype/dejavu"),
)
REGULAR_FONT_NAMES: Final = ("Arial.ttf", "LiberationSans-Regular.ttf", "DejaVuSans.ttf")
BOLD_FONT_NAMES: Final = ("Arial Bold.ttf", "LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf")

WEBP_QUALITY: Final = 82
WEBP_METHOD: Final = 6

FIGURE_NAMES: Final = ("asset-unit", "motion-rebase")
FIGURE_FILENAMES: Final = {
    "asset-unit": "asset-unit-calibration.webp",
    "motion-rebase": "motion-rebase-ab.webp",
}


def _load_font(size: int, *, bold: bool = False) -> _Font:
    """Return a font at ``size``, falling back to Pillow's bundled default."""
    names = BOLD_FONT_NAMES if bold else REGULAR_FONT_NAMES
    for directory in FONT_DIRECTORIES:
        for name in names:
            candidate = directory / name
            if candidate.is_file():
                return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default(size)


def _alpha_trimmed(image: Image.Image) -> Image.Image:
    """Crop ``image`` to the pixels the runtime would treat as painted."""
    mask = image.getchannel("A").point(lambda value: 255 if value > ALPHA_THRESHOLD else 0)
    box = mask.getbbox()
    if box is None:
        raise ValueError("subject has no painted pixels above the alpha threshold")
    return image.crop(box)


def _load_manifest(package: Path) -> tuple[dict[str, Any], str]:
    """Return the package manifest and the digest of its exact bytes."""
    manifest_path = package / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"no manifest at {manifest_path}")
    raw = manifest_path.read_bytes()
    manifest: dict[str, Any] = json.loads(raw.decode("utf-8"))
    game_id = str(manifest.get("game_id", ""))
    if game_id != GAME_ID:
        raise SystemExit(
            f"package declares game_id {game_id!r}; the judged tables in this script were "
            f"read off {GAME_ID!r} and do not describe another game"
        )
    return manifest, hashlib.sha256(raw).hexdigest()


def _map_record(manifest: Mapping[str, Any]) -> dict[str, Any]:
    for record in manifest["maps"]:
        if record["map_id"] == MAP_ID:
            return dict(record)
    raise SystemExit(f"package has no map {MAP_ID!r}")


def _judged_tiles(subject: str) -> float:
    if subject not in JUDGED:
        raise SystemExit(f"no judged height for {subject!r}; the figure would misreport it")
    return JUDGED[subject]


def _open_rgba(package: Path, relative: str) -> Image.Image:
    path = package / relative
    if not path.is_file():
        raise SystemExit(f"package is missing {relative}")
    with Image.open(path) as opened:
        return opened.convert("RGBA")


def _first_column(image: Image.Image, columns: int) -> Image.Image:
    if columns <= 1:
        return image
    return image.crop((0, 0, image.width // columns, image.height))


def _layer_top(placement: Mapping[str, Any], walk_y: int, rendered_height: float) -> float:
    anchor = str(placement["vertical_anchor"])
    offset = float(placement["vertical_offset"])
    if anchor == "canvas_cover":
        return 0.0
    if anchor == "screen_top":
        return offset * rendered_height
    if anchor == "screen_center":
        return VIEW_HEIGHT / 2 - rendered_height / 2 + offset * rendered_height
    datum = VIEW_HEIGHT if anchor == "screen_bottom" else walk_y
    return datum - (1 - offset) * rendered_height


def _render_scene(
    package: Path,
    manifest: Mapping[str, Any],
    map_record: Mapping[str, Any],
    *,
    judged: bool,
) -> Image.Image:
    """Composite one viewport of the map under one sizing rule."""
    ground = map_record["ground"]
    occupancy = ground["occupancy"]
    rows = len(occupancy)
    world_width = len(occupancy[0]) * TILE_PX
    walk_surface_row = int(ground["walk_surface_row"])
    walk_y = VIEW_HEIGHT - (rows - walk_surface_row) * TILE_PX
    canvas = Image.new("RGBA", (VIEW_WIDTH, VIEW_HEIGHT), (0, 0, 0, 255))

    ordered_layers = sorted(
        map_record["layers"],
        key=lambda layer: (layer["plane"] != "background", layer["order"]),
    )
    for layer in ordered_layers:
        placement = layer["placement"]
        source = _open_rgba(package, layer["asset"]["path"])
        scale = VIEW_HEIGHT / float(placement["source_height"])
        width = max(1, int(source.width * scale))
        height = max(1, int(source.height * scale))
        resized = source.resize((width, height), Image.Resampling.LANCZOS)
        top = _layer_top(placement, walk_y, float(placement["trimmed_height"]) * scale)
        offset = int(-CAMERA_X * float(layer["parallax"])) % width
        for repeat in (-1, 0, 1, 2):
            canvas.alpha_composite(resized, (offset + repeat * width, int(top)))

    atlas = _open_rgba(package, ground["asset"]["path"])

    def atlas_cell(row: int, column: int) -> Image.Image:
        box = (
            column * ATLAS_CELL_PX,
            row * ATLAS_CELL_PX,
            (column + 1) * ATLAS_CELL_PX,
            (row + 1) * ATLAS_CELL_PX,
        )
        return atlas.crop(box).resize((TILE_PX, TILE_PX), Image.Resampling.LANCZOS)

    cap_cell = atlas_cell(0, 6)
    fill_cell = atlas_cell(1, 6)
    inset = round(ATLAS_INSET_PX / ATLAS_CELL_PX * TILE_PX)
    for row in range(walk_surface_row, rows):
        y = VIEW_HEIGHT - (rows - row) * TILE_PX - inset
        tile = cap_cell if row == walk_surface_row else fill_cell
        for column in range(-1, VIEW_WIDTH // TILE_PX + 2):
            canvas.alpha_composite(tile, (column * TILE_PX - int(CAMERA_X) % TILE_PX, y))

    def place(
        subject: str,
        relative: str,
        columns: int,
        shipped_height: int,
        normalized_x: float,
        contact: float,
    ) -> None:
        source = _first_column(_open_rgba(package, relative), columns)
        if judged:
            trimmed = _alpha_trimmed(source)
            scale = (_judged_tiles(subject) * TILE_PX) / trimmed.height
            drawn, ground_contact = trimmed, 1.0
        else:
            scale = shipped_height / source.height
            drawn, ground_contact = source, contact
        width = max(1, int(drawn.width * scale))
        height = max(1, int(drawn.height * scale))
        resized = drawn.resize((width, height), Image.Resampling.LANCZOS)
        x = normalized_x * world_width - CAMERA_X
        canvas.alpha_composite(resized, (int(x - width / 2), int(walk_y - height * ground_contact)))

    props = {record["prop_id"]: record for record in manifest["props"]}
    npcs = {record["npc_id"]: record for record in manifest["npcs"]}
    gameplay = manifest["gameplay"]
    for placement in gameplay["prop_placements"]:
        if placement["map_id"] != MAP_ID:
            continue
        prop_id = placement["prop_id"]
        record = props[prop_id]
        shipped = SHIPPED_STALL_PX if "stall" in prop_id else SHIPPED_PROP_PX
        place(
            prop_id,
            record["asset"]["path"],
            1,
            shipped,
            float(placement["normalized_x"]),
            float(record.get("ground_contact_y_normalized", 1.0)),
        )
    for placement in gameplay["npc_placements"]:
        if placement["map_id"] != MAP_ID:
            continue
        npc_id = placement["npc_id"]
        world = npcs[npc_id]["world"]
        place(
            npc_id,
            world["asset"]["path"],
            int(world["columns"]),
            SHIPPED_NPC_PX,
            float(placement["normalized_x"]),
            1.0,
        )
    idle = manifest["player"]["states"]["idle"]
    place(
        "wayfarer",
        idle["asset"]["path"],
        int(idle["columns"]),
        PLAYER_PX,
        PLAYER_NORMALIZED_X,
        1.0,
    )
    return canvas.convert("RGB")


def _unit_ruler_ys(walk_y: int, player_px: int) -> list[int]:
    """Return the y of one, two and three player heights above the walk surface."""
    return [walk_y - step * player_px for step in (1, 2, 3)]


def _callout_x(map_record: Mapping[str, Any], manifest: Mapping[str, Any]) -> int:
    occupancy = map_record["ground"]["occupancy"]
    world_width = len(occupancy[0]) * TILE_PX
    for placement in manifest["gameplay"]["prop_placements"]:
        if placement["map_id"] == MAP_ID and placement["prop_id"] == CALLOUT_SUBJECT:
            return int(float(placement["normalized_x"]) * world_width - CAMERA_X)
    raise SystemExit(f"map {MAP_ID!r} does not place {CALLOUT_SUBJECT!r}")


def _compose_unit_figure(
    shipped_scene: Image.Image,
    judged_scene: Image.Image,
    walk_y: int,
    callout_x: int,
) -> Image.Image:
    title_font = _load_font(31, bold=True)
    subtitle_font = _load_font(18)
    band_font = _load_font(20, bold=True)
    band_subtitle_font = _load_font(15)
    tick_font = _load_font(14, bold=True)

    band_height = 46
    header_height = 158
    footer_height = 40
    canvas = Image.new(
        "RGB",
        (VIEW_WIDTH, header_height + 2 * (band_height + VIEW_HEIGHT) + footer_height),
        PAGE,
    )
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, VIEW_WIDTH, 100), fill=HEADER_INK)
    draw.text((22, 14), "One asset unit is one player height", fill=HEADER_TEXT, font=title_font)
    draw.text(
        (22, 49),
        "Nothing an image model returns carries a size. A generated subject fills its own "
        "canvas, so its pixels encode aspect ratio and nothing else.",
        fill=HEADER_MUTED,
        font=subtitle_font,
    )
    draw.text(
        (22, 72),
        "Magnitude is therefore authored, as a multiple of the player, and projected to the "
        "screen exactly once.",
        fill=HEADER_ACCENT,
        font=subtitle_font,
    )
    draw.text(
        (22, 116),
        "Same map, same camera, same artwork. Only the rule that turns a subject into "
        "pixels differs.",
        fill=MUTED,
        font=subtitle_font,
    )

    def band(
        y: int,
        color: tuple[int, int, int],
        heading: str,
        subtitle: str,
        scene: Image.Image,
        callout: str,
    ) -> None:
        draw.rectangle((0, y, VIEW_WIDTH, y + band_height), fill=BAND_INK)
        draw.rectangle((0, y, 8, y + band_height), fill=color)
        draw.text((24, y + 7), heading, fill=PAGE, font=band_font)
        draw.text(
            (24 + draw.textlength(heading, font=band_font) + 18, y + 11),
            subtitle,
            fill=BAND_MUTED,
            font=band_subtitle_font,
        )
        top = y + band_height
        canvas.paste(scene, (0, top))
        for step, ruler_y in enumerate(_unit_ruler_ys(walk_y, PLAYER_PX), start=1):
            tick_y = top + ruler_y
            for x in range(18, 168, 12):
                draw.line(((x, tick_y), (x + 6, tick_y)), fill=color, width=2)
            label = f"{step} player height" + ("s" if step > 1 else "")
            label_width = draw.textlength(label, font=tick_font)
            draw.rectangle(
                (18, tick_y - 19, 20 + label_width + 8, tick_y - 2),
                fill=HEADER_INK,
            )
            draw.text((22, tick_y - 18), label, fill=PAGE, font=tick_font)
        draw.line(((18, top + walk_y), (168, top + walk_y)), fill=color, width=2)
        leader_top = top + walk_y - 250
        for tick_y in range(leader_top, top + walk_y, 11):
            draw.line(
                ((callout_x, tick_y), (callout_x, min(tick_y + 5, top + walk_y))),
                fill=color,
                width=2,
            )
        callout_width = draw.textlength(callout, font=tick_font)
        draw.rectangle(
            (
                callout_x - callout_width / 2 - 9,
                leader_top - 25,
                callout_x + callout_width / 2 + 9,
                leader_top - 3,
            ),
            fill=HEADER_INK,
        )
        draw.text(
            (callout_x - callout_width / 2, leader_top - 22),
            callout,
            fill=PAGE,
            font=tick_font,
        )

    band(
        header_height,
        SHIPPED_COLOR,
        "AS SHIPPED",
        "one pixel constant per class, applied to the untrimmed canvas: props "
        f"{SHIPPED_PROP_PX} px, stalls {SHIPPED_STALL_PX} px, cast {SHIPPED_NPC_PX} px, "
        f"player {PLAYER_PX} px",
        shipped_scene,
        f"petalstone_well  -  {SHIPPED_PROP_PX} px canvas constant",
    )
    band(
        header_height + band_height + VIEW_HEIGHT,
        JUDGED_COLOR,
        "CALIBRATED",
        "each subject's declared height_units, projected through player_height_tiles x 64 px",
        judged_scene,
        f"petalstone_well  -  {JUDGED[CALLOUT_SUBJECT]:.2f} units",
    )
    draw.text(
        (22, header_height + 2 * (band_height + VIEW_HEIGHT) + 12),
        "A constant cannot express that the well is 2.60 units and the bread stall 3.00, "
        "because the constant is not about the subject. It is about the class.",
        fill=MUTED,
        font=band_subtitle_font,
    )
    return canvas


def _state_frames(package: Path, relative: str, columns: int) -> tuple[list[Image.Image], int]:
    """Return every alpha-trimmed frame of one motion atlas and its cell height."""
    atlas = _open_rgba(package, relative)
    cell_width = atlas.width // columns
    frames = [
        _alpha_trimmed(atlas.crop((index * cell_width, 0, (index + 1) * cell_width, atlas.height)))
        for index in range(columns)
    ]
    return frames, atlas.height


def _shipped_scale(state: str, cell_height: int) -> float:
    """Return the scale the runtime applied to ``state``."""
    if state in SYNTH_STATES:
        return PLAYER_PX / cell_height
    return PLAYER_PX / IDLE_CELL_PX


def _rebased_scale(state: str, idle_trimmed_height: int) -> float:
    """Return the asset-unit scale composed with the state's rebase multiplier."""
    return (PLAYER_PX / idle_trimmed_height) * REBASE[state]


def _row_heights(
    drawn_heights: Mapping[str, Sequence[float]],
    idle_shipped_height: float,
    idle_rebased_height: float,
    margin: int = 10,
) -> dict[str, int]:
    """Size every row so the baseline crown rule stays inside its own panel."""
    return {
        state: int(max(max(heights), idle_shipped_height, idle_rebased_height) + margin)
        for state, heights in drawn_heights.items()
    }


def _compose_motion_figure(package: Path, manifest: Mapping[str, Any]) -> Image.Image:
    title_font = _load_font(31, bold=True)
    subtitle_font = _load_font(18)
    heading_font = _load_font(21, bold=True)
    state_font = _load_font(17, bold=True)
    multiplier_font = _load_font(15)
    small_font = _load_font(13)

    states = manifest["player"]["states"]
    frames: dict[str, list[Image.Image]] = {}
    shipped: dict[str, float] = {}
    rebased: dict[str, float] = {}
    for state in STATE_ORDER:
        if state not in states:
            raise SystemExit(f"player has no {state!r} atlas; the figure would be incomplete")
        record = states[state]
        state_frames, cell_height = _state_frames(
            package, record["asset"]["path"], int(record["columns"])
        )
        frames[state] = state_frames
        shipped[state] = _shipped_scale(state, cell_height)
    idle_trimmed_height = frames["idle"][0].height
    for state in STATE_ORDER:
        rebased[state] = _rebased_scale(state, idle_trimmed_height)

    drawn_heights = {
        state: [
            frame.height * scale
            for frame in frames[state]
            for scale in (shipped[state], rebased[state])
        ]
        for state in STATE_ORDER
    }
    idle_shipped_height = frames["idle"][0].height * shipped["idle"]
    idle_rebased_height = frames["idle"][0].height * rebased["idle"]
    row_heights = _row_heights(drawn_heights, idle_shipped_height, idle_rebased_height)

    cell_width = (
        max(
            int(frame.width * scale)
            for state in STATE_ORDER
            for frame in frames[state]
            for scale in (shipped[state], rebased[state])
        )
        + 16
    )
    gutter, padding, middle, label_height, row_gap = 132, 22, 34, 30, 20
    header_height = 158
    panel_width = 4 * cell_width
    width = padding + gutter + panel_width + middle + panel_width + padding
    height = (
        header_height
        + sum(row_heights[state] + label_height + row_gap for state in STATE_ORDER)
        + padding
    )

    canvas = Image.new("RGB", (width, height), PAGE)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, width, 100), fill=HEADER_INK)
    draw.text(
        (padding, 14), "One actor, ten states, forty frames", fill=HEADER_TEXT, font=title_font
    )
    draw.text(
        (padding, 49),
        "Separate generation calls do not share a scale, and an alpha box cannot tell a short "
        "pose from a small drawing.",
        fill=HEADER_MUTED,
        font=subtitle_font,
    )
    draw.text(
        (padding, 72),
        "As shipped, this character reaches the screen across a 1.5x range of scales, decided "
        "only by which state is playing.",
        fill=HEADER_ACCENT,
        font=subtitle_font,
    )

    shipped_x = padding + gutter
    rebased_x = padding + gutter + panel_width + middle
    heading_y = 116
    columns = (
        (
            shipped_x,
            SHIPPED_FRAME_COLOR,
            "A  -  as shipped",
            "one scale per state, taken from cell height",
        ),
        (
            rebased_x,
            REBASED_FRAME_COLOR,
            "B  -  rebased",
            "one multiplier per state, judged against the idle baseline",
        ),
    )
    for x, color, heading, subtitle in columns:
        draw.rectangle((x, heading_y, x + 7, heading_y + 28), fill=color)
        draw.text((x + 16, heading_y - 2), heading, fill=INK, font=heading_font)
        draw.text((x + 16, heading_y + 22), subtitle, fill=MUTED, font=small_font)

    y = header_height
    for state in STATE_ORDER:
        row_height = row_heights[state]
        ground_y = y + row_height
        panels = (
            (shipped_x, shipped[state], SHIPPED_FRAME_COLOR, idle_shipped_height),
            (rebased_x, rebased[state], REBASED_FRAME_COLOR, idle_rebased_height),
        )
        for x, scale, color, idle_height in panels:
            draw.rectangle((x, y, x + panel_width, ground_y), fill=PANEL)
            crown_y = ground_y - idle_height
            for dash_x in range(x, x + panel_width, 13):
                draw.line(((dash_x, crown_y), (dash_x + 7, crown_y)), fill=color, width=2)
            if state == "idle":
                draw.text((x + 6, crown_y - 19), "idle crown", fill=color, font=small_font)
            draw.line(((x, ground_y), (x + panel_width, ground_y)), fill=GROUND_RULE, width=1)
            for index, frame in enumerate(frames[state]):
                frame_width = max(1, int(frame.width * scale))
                frame_height = max(1, int(frame.height * scale))
                resized = frame.resize((frame_width, frame_height), Image.Resampling.LANCZOS)
                frame_x = x + index * cell_width + (cell_width - frame_width) // 2
                canvas.paste(resized, (frame_x, ground_y - frame_height), resized)
                draw.text(
                    (x + index * cell_width + 6, ground_y + 6),
                    f"{frame_height} px",
                    fill=MUTED,
                    font=small_font,
                )
        draw.text((padding, ground_y - 34), state, fill=INK, font=state_font)
        multiplier = REBASE[state]
        label = "baseline" if state == "idle" else f"x{multiplier:.2f}"
        draw.text((padding, ground_y - 15), label, fill=REBASED_FRAME_COLOR, font=multiplier_font)
        y = ground_y + label_height + row_gap

    draw.text(
        (padding, height - 30),
        "Drawn subject height under each frame. The multiplier is per state, never per frame: "
        "four frames share one generation canvas, so they share one scale.  Height still varies "
        "inside a state after rebasing, and that variation is pose.",
        fill=MUTED,
        font=small_font,
    )
    return canvas


def _save_webp(image: Image.Image, path: Path) -> dict[str, int]:
    """Encode ``image`` as WebP with every knob explicit and report its size."""
    # The composites are built with Image.new, so they carry no ICC profile or
    # EXIF block for the encoder to copy through.
    image.save(
        path,
        format="WEBP",
        lossless=False,
        quality=WEBP_QUALITY,
        method=WEBP_METHOD,
        exact=False,
    )
    return {"width": image.width, "height": image.height, "bytes": path.stat().st_size}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--figure", choices=(*FIGURE_NAMES, "all"), default="all")
    arguments = parser.parse_args()

    package: Path = arguments.package
    output: Path = arguments.output
    manifest, manifest_sha256 = _load_manifest(package)
    map_record = _map_record(manifest)
    output.mkdir(parents=True, exist_ok=True)

    selected = FIGURE_NAMES if arguments.figure == "all" else (arguments.figure,)
    figures: dict[str, dict[str, int | str]] = {}

    if "asset-unit" in selected:
        ground = map_record["ground"]
        rows = len(ground["occupancy"])
        walk_y = VIEW_HEIGHT - (rows - int(ground["walk_surface_row"])) * TILE_PX
        shipped_scene = _render_scene(package, manifest, map_record, judged=False)
        judged_scene = _render_scene(package, manifest, map_record, judged=True)
        figure = _compose_unit_figure(
            shipped_scene,
            judged_scene,
            walk_y,
            _callout_x(map_record, manifest),
        )
        path = output / FIGURE_FILENAMES["asset-unit"]
        figures["asset-unit-calibration"] = {"path": str(path), **_save_webp(figure, path)}

    if "motion-rebase" in selected:
        figure = _compose_motion_figure(package, manifest)
        path = output / FIGURE_FILENAMES["motion-rebase"]
        figures["motion-rebase-ab"] = {"path": str(path), **_save_webp(figure, path)}

    report = {
        "kind": "asset-scale-figure-render-v1",
        "package": str(package),
        "manifest_sha256": manifest_sha256,
        "figures": figures,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
