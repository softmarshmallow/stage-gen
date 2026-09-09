#!/usr/bin/env python3
"""Write the small survival run the suite reads when there is none.

    python3 tools/make_fixture_run.py <directory>

Nearly every Godot test opens a run — through `TestFixtures.world()` if not
directly — and `out/` is gitignored, so a fresh clone has nothing to point them
at. That is the whole reason the suite could not enter `scripts/check.py`: a gate
that needs an artifact the repository does not carry only ever runs on the
machine that made the artifact.

So the run is *authored*, not pruned from a real one. A fixture cut down from a
pipeline run inherits its producer's bugs and still needs that producer to have
run; this is a hand-written document at the contract's floor with the media
written beside it at exactly the sizes it declares. What it is worth beyond
running the suite is that it says, in one file, what the smallest package this
host will play actually is.

It shares the *vocabulary* of a real package — biome, prop, item and verb names,
and the authored constants a test names as the contract's own — and it does not
share the numbers a producer decides: it is thirty-two metres where a run is five
hundred and twelve, and it places twenty-four things where a run places 2,271.
Those counts are what `TestHarness.pinned()` guards; they are read only when the
suite is pointed at a real run.

What it cannot carry is sound and video: neither an mp3 nor an mp4 can be
synthesised from the standard library, so the document declares no `sounds`,
`music` or `shell` block, and the two tests that read those say so and pass.

No dependencies: the PNG writer below is fifteen lines of zlib.
"""

from __future__ import annotations

import json
import math
import struct
import sys
import zlib
from pathlib import Path

#: The document's identity. The kind's own version and the schema's are separate
#: numbers and always have been: `SurvivalDocument` refuses anything else.
KIND = "oblique-survival-manifest-v3"
SCHEMA_VERSION = 1

#: The world's side, in metres. Small enough that a test walking across it does
#: so in a few steps, large enough that the camera has somewhere to look.
SIZE_METERS = 32.0
#: The splat and biome plates, in cells, at two cells to the metre.
MASK_CELLS = 64
CELL_METERS = SIZE_METERS / MASK_CELLS
#: One tiled ground texture.
TILE_PX = 256
#: One drawn thing: a prop state, a decal, an item, one cell of the forage sheet.
PLATE_PX = 256
#: The player is the ruler; every `px_per_meter` below follows from a plate's
#: height in pixels over the thing's height in metres.
PLAYER_HEIGHT_METERS = 1.7


# ---------------------------------------------------------------- media


def png(path: Path, width: int, height: int, pixel) -> None:
    """Write one RGBA8 PNG.

    `pixel` is either `(x, y) -> (r, g, b, a)`, or a `bytearray` of
    `width * height * 4` already painted — the sheets do the second, because a
    thousand-square canvas asked pixel by pixel is a million calls a sheet.
    """
    raw = bytearray()
    if isinstance(pixel, (bytes, bytearray)):
        for y in range(height):
            raw.append(0)  # filter: none
            raw.extend(pixel[y * width * 4 : (y + 1) * width * 4])
    else:
        for y in range(height):
            raw.append(0)
            for x in range(width):
                raw.extend(bytes(pixel(x, y)))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + chunk(b"IEND", b"")
    )


def flat(colour):
    return lambda _x, _y: colour


def checker(one, two, size=8):
    return lambda x, y: one if ((x // size) + (y // size)) % 2 == 0 else two


def blob(colour, feet=0.92, waist=0.34):
    """A drawn thing: a filled ellipse standing on its own bottom edge.

    Every plate the host measures is measured for its lowest opaque row — the
    foot — so a plate whose alpha runs to the border would put the contact at
    the border whatever the record said. This one ends where the record says it
    does.
    """

    def pixel(x, y):
        cx, cy = PLATE_PX * 0.5, PLATE_PX * feet
        rx, ry = PLATE_PX * waist, PLATE_PX * feet
        inside = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0
        if not inside or y > PLATE_PX * feet:
            return (0, 0, 0, 0)
        shade = 1.0 - 0.3 * (y / PLATE_PX)
        return (int(colour[0] * shade), int(colour[1] * shade), int(colour[2] * shade), 255)

    return pixel


def strip(colour, columns, rows, cell_w, cell_h):
    """A sheet of `columns * rows` cells, each a blob a little unlike the last."""

    def pixel(x, y):
        column, row = x // cell_w, y // cell_h
        u, v = (x % cell_w) / cell_w, (y % cell_h) / cell_h
        lean = 0.04 * math.sin((column + row * columns) * 1.3)
        inside = ((u - 0.5 - lean) / 0.3) ** 2 + ((v - 0.92) / 0.9) ** 2 <= 1.0
        if not inside or v > 0.92:
            return (0, 0, 0, 0)
        shade = 1.0 - 0.25 * v
        return (int(colour[0] * shade), int(colour[1] * shade), int(colour[2] * shade), 255)

    return pixel


def land(x, y):
    """The land channel: land everywhere but a pond in one corner.

    `a` is land, `r` is the road and `g` is the darkening pass, which is what
    the splat's channel table below says.
    """
    pond = (x - 12) ** 2 + (y - 12) ** 2 < 30
    road = abs(x - MASK_CELLS * 0.5) < 2 and y > MASK_CELLS * 0.4
    return (255 if road else 0, 0, 40, 0 if pond else 255)


def biomes(x, y):
    """Three weight channels over the base: meadow, bog and scree."""
    if y < MASK_CELLS // 3:
        return (255, 0, 0, 255)
    if x > MASK_CELLS * 0.7:
        return (0, 0, 255, 255)
    if x < MASK_CELLS * 0.2 and y > MASK_CELLS * 0.6:
        return (0, 255, 0, 255)
    return (0, 0, 0, 255)


# ---------------------------------------------------------------- document


def actor_state(name, columns, fps, mode, cell_w, cell_h, height_meters, facings):
    """One actor state, and the same state once per facing where it has them.

    Each facing is drawn separately, so each comes back its own size: the four
    cells below differ by a few pixels the way four drawings do, and a reader
    that took one facing's cell for all four would be caught by that.
    """

    def spec_for(cell_w, cell_h, atlas):
        return {
            "atlas": atlas,
            "bottom_gutter_px": 12,
            "canonical_frame_indices": list(range(columns)),
            "cell_height": cell_h,
            "cell_width": cell_w,
            "columns": columns,
            "fps": fps,
            "frames": columns,
            "mode": mode,
            "px_per_meter": round(cell_h / height_meters, 4),
            "rebase_multiplier": 1.0,
            "rows": 1,
        }

    spec = spec_for(cell_w, cell_h, f"package/actors/{name}")
    if facings:
        spec["facings"] = {}
        for index, facing in enumerate(facings):
            spec["facings"][facing] = spec_for(
                cell_w + index * 3, cell_h + index * 5, f"package/actors/{name}"
            )
    return spec


def prop_state(prop, state, height_meters, contact, winter=True):
    spec = {
        "anchor": [0.5, contact],
        "drawn_height_meters": height_meters,
        "floor_plate_suspected": False,
        "ground_contact_y_normalized": contact,
        "height_meters": height_meters,
        "height_px": PLATE_PX,
        "height_units_source": "authored",
        "image": f"package/props/{prop}/{state}.png",
        "px_per_meter": round(PLATE_PX / height_meters, 4),
        "width_px": PLATE_PX,
    }
    if winter:
        # The winter card is a second drawing, so its foot is its own: a reader
        # that took the summer contact for both would never be caught.
        spec["looks"] = {
            "winter": {
                "anchor": [0.5, contact],
                "ground_contact_y_normalized": round(contact - 0.002, 5),
                "height_px": PLATE_PX,
                "image": f"package/props/{prop}/{state}.winter.png",
                "px_per_meter": round(PLATE_PX / height_meters, 4),
                "width_px": PLATE_PX,
            }
        }
    return spec


def item(item_id, display_name, index, height_meters, stack_max, tool=None, use=None):
    return {
        "display_name": display_name,
        "height_meters": height_meters,
        "height_px": PLATE_PX,
        "icon": {"h": 256, "w": 256, "x": (index % 6) * 256, "y": (index // 6) * 256},
        "image": f"package/items/{item_id}.png",
        "px_per_meter": round(PLATE_PX / height_meters, 4),
        "stack_max": stack_max,
        "tool": tool,
        "use": use,
        "width_px": PLATE_PX,
    }


def use(
    kind,
    *,
    burn_seconds=0.0,
    health=0.0,
    heat_seconds=0.0,
    hunger=0.0,
    insulation=0.0,
    radius_meters=0.0,
    slots=0,
    warmth=0.0,
):
    """One item's `use` block. Every field is published, whatever the kind."""
    return {
        "burn_seconds": burn_seconds,
        "health": health,
        "heat_seconds": heat_seconds,
        "hunger": hunger,
        "insulation": insulation,
        "kind": kind,
        "radius_meters": radius_meters,
        "slots": slots,
        "warmth": warmth,
    }


#: The pack's contents, in the order they sit in the icon sheet: id, name,
#: drawn height, stack, the tool it is, and what using it does. `use.kind` is
#: the published vocabulary — consume, wear, carry, light, warm — and the HUD
#: turns it into the word on the button, so a fixture that invented its own
#: names would leave every one of those buttons blank.
ITEMS = [
    ("log", "Log", 0.62, 10, None, None),
    ("berry", "Berries", 0.30, 10, None, use("consume", hunger=20.0)),
    ("cooked_berry", "Stewed berries", 0.30, 10, None, use("consume", hunger=45.0, warmth=10.0)),
    ("stone", "Stone", 0.28, 10, None, None),
    ("grass_tuft", "Grass", 0.36, 10, None, None),
    ("twig", "Twig", 0.44, 10, None, None),
    ("flint", "Flint", 0.26, 10, None, None),
    ("reed", "Reed", 0.70, 10, None, None),
    ("rope", "Reed rope", 0.5, 5, None, None),
    ("mushroom", "Mushroom", 0.22, 10, None, use("consume", hunger=12.0)),
    ("moss", "Moss", 0.24, 10, None, None),
    ("poultice", "Moss poultice", 0.30, 5, None, use("consume", health=30.0)),
    ("axe", "Flint axe", 0.58, 1, {"uses": 25, "verb": "chop"}, None),
    ("pickaxe", "Flint pick", 0.60, 1, {"uses": 20, "verb": "mine"}, None),
    (
        "torch",
        "Torch",
        0.72,
        1,
        {"uses": 1, "verb": "burn"},
        use("light", burn_seconds=60.0, radius_meters=3.5),
    ),
    ("grass_cloak", "Grass cloak", 0.71, 1, None, use("wear", insulation=0.5)),
    ("backpack", "Reed pack", 0.68, 1, None, use("carry", slots=4)),
    ("warm_stone", "Warm stone", 0.3, 1, None, use("warm", heat_seconds=120.0)),
]

#: Every biome, its friction and the channel that weights it.
BIOMES = [
    ("forest_floor", 0.7, "base", None, 0.2668, 0.36),
    ("dry_meadow", 0.55, "r", 0.24, 0.8078, 0.55),
    ("mossy_bog", 1.1, "g", 0.16, 0.5966, 0.46),
    ("grey_scree", 0.45, "b", 0.14, 0.528, 0.48),
]

#: The forage sheet: four cells at 256 px on a 512 px atlas.
#: Four cells at 256 px on a 512 px sheet. Every one is sized above the scale
#: block's own floor — 0.425 m, a quarter of the player — because a piece drawn
#: smaller than that is refused rather than drawn tiny (decision 0060).
FORAGE = [
    ("twig", ["forest_floor", "dry_meadow"], 0.544, 240.0, 2, "fallen"),
    ("grass_tuft", ["dry_meadow"], 0.48, 180.0, 1, "rooted"),
    ("flint", ["grey_scree"], 0.44, 300.0, 1, "fallen"),
    ("moss", ["mossy_bog"], 0.46, 210.0, 1, "rooted"),
]


def ground() -> dict:
    biome_specs = {}
    for name, friction, channel, share, luma, value in BIOMES:
        biome_specs[name] = {
            "friction": friction,
            "luma_mean": luma,
            "share": share,
            "texel_meters": 4.0,
            "texture": f"package/ground/{name}.png",
            "tiled_px": TILE_PX,
            "tiled_px_height": TILE_PX,
            "tiling": "mirror_repeat_2d",
            "value_target": value,
            "weight_channel": channel,
        }
    cells = []
    for index, (item_id, in_biomes, size, regrow, count, contact) in enumerate(FORAGE):
        cells.append(
            {
                "biomes": in_biomes,
                "box": {"x": 26, "y": 64, "w": 206, "h": 152},
                "contact": contact,
                "count": count,
                "drawn_size_meters": round(size * 0.87, 4),
                "h": 256,
                "index": index,
                "item_id": item_id,
                "px_per_meter": round(206 / size, 4),
                "regrow_seconds": regrow,
                "size_meters": size,
                "size_units": round(size / PLAYER_HEIGHT_METERS, 4),
                "w": 256,
                "x": (index % 2) * 256,
                "y": (index // 2) * 256,
            }
        )
    return {
        "base_biome": "forest_floor",
        "biome_splat": {
            "cell_meters": CELL_METERS,
            "channels": {"r": "dry_meadow", "g": "mossy_bog", "b": "grey_scree"},
            "image": "package/world/biomes.png",
            "resolution": MASK_CELLS,
        },
        "biomes": biome_specs,
        "decals": {
            "path": {
                "families": [],
                "height_meters": 2.4,
                "height_px": PLATE_PX,
                "image": "package/ground/decals/path.png",
                "use": "pad",
                "width_meters": 2.4,
                "width_px": PLATE_PX,
            },
            "puddle": {
                "families": [],
                "height_meters": 1.2,
                "height_px": PLATE_PX,
                "image": "package/ground/decals/puddle.png",
                "use": "wet",
                "width_meters": 1.6,
                "width_px": PLATE_PX,
            },
            "tree_skirt": {
                "families": ["tree"],
                "height_meters": 2.0,
                "height_px": PLATE_PX,
                "image": "package/ground/decals/tree_skirt.png",
                "use": "skirt",
                "width_meters": 2.0,
                "width_px": PLATE_PX,
            },
            "rock_skirt": {
                "families": ["rock"],
                "height_meters": 1.6,
                "height_px": PLATE_PX,
                "image": "package/ground/decals/rock_skirt.png",
                "use": "skirt",
                "width_meters": 1.6,
                "width_px": PLATE_PX,
            },
        },
        "forage": {
            "atlas": "package/ground/forage.png",
            "cell_meters": 0.6,
            "cells": cells,
            "columns": 2,
            "height_px": 512,
            "rows": 2,
            "width_px": 512,
        },
        "macro": {
            "luma_mean": 0.5822,
            "period_meters": 14.0,
            "strength": 0.55,
            "texel_meters": 48.0,
            "texture": "package/ground/macro.png",
            "tiling": "mirror_repeat_2d",
        },
        "road": {
            "edge_meters": 0.7,
            "luma_mean": 0.3611,
            "road_id": "dirt_track",
            "splat_channel": "r",
            "texel_meters": 4.0,
            "texture": "package/ground/road-dirt_track.png",
            "tiling": "mirror_repeat_2d",
            "value_target": 0.46,
            "width_meters": 2.2,
        },
        "size_meters": SIZE_METERS,
        "splat": {
            "blend": {
                "bomb_meters": 3.0,
                "bomb_rotate": 0.0,
                "decal_gain": 0.62,
                "edge_bleed": 0.2,
                "edge_bleed_width": 1.0,
                "edge_fine_meters": 6.0,
                "edge_fine_strength": 0.15,
                "edge_ink": 0.45,
                "edge_ink_width": 0.25,
                "edge_noise_strength": 0.35,
                "edge_rim": 0.12,
                "edge_shadow": 0.35,
                "edge_shadow_width": 0.4,
                "edge_softness": 0.03,
                "edge_streak": 0.6,
                "exposure": 1.0,
                "flow_meters": 200.0,
                "grade_desaturate": 0.0,
                "grade_lift": 0.03,
                "grade_warmth": 0.5,
                "level": {name: 1.0 for name, *_ in BIOMES},
                "macro_tint_strength": 0.15,
                "paper": 0.05,
                "paper_px": 4.0,
                "pool_gain": 0.12,
                "pool_radius_meters": 9.0,
                "road_edge_softness": 0.1,
                "road_noise_strength": 0.45,
                "road_noise_tile_meters": 3.0,
                "shadow_scale": 1.4,
            },
            "cell_meters": CELL_METERS,
            "channels": {"a": "land", "b": None, "g": "darken", "r": "dirt_track"},
            "image": "package/world/splat.png",
            "resolution": MASK_CELLS,
        },
        "water": {
            "cliff_colour": [0.17, 0.13, 0.1],
            "colour": [0.13, 0.2, 0.22],
            "depth_meters": 2.2,
            "luma_mean": 0.2345,
            "texel_meters": 12.0,
            "texture": "package/ground/water.png",
            "tiling": "mirror_repeat_2d",
            "value_target": 0.26,
        },
    }


def actors() -> dict:
    facings = ["front", "back", "left", "right"]
    wren_states = {}
    for state, columns, fps, mode in [
        ("idle", 4, 6.0, "loop"),
        ("walk", 4, 8.0, "loop"),
        ("gather", 4, 9.0, "once"),
        ("chop", 4, 12.0, "once"),
        ("hurt", 4, 10.0, "once"),
        ("death", 4, 8.0, "once"),
    ]:
        wren_states[state] = actor_state(
            f"wren/states/{state}.front.png",
            columns,
            fps,
            mode,
            96,
            128,
            PLAYER_HEIGHT_METERS,
            facings,
        )
        for facing in facings:
            wren_states[state]["facings"][facing]["atlas"] = (
                f"package/actors/wren/states/{state}.{facing}.png"
            )
    hound_states = {}
    for state, columns, fps, mode in [
        ("idle", 4, 5.0, "loop"),
        ("walk", 4, 9.0, "loop"),
        ("attack", 4, 12.0, "once"),
        ("hurt", 4, 10.0, "once"),
    ]:
        hound_states[state] = actor_state(
            f"grub_hound/states/{state}.png", columns, fps, mode, 96, 64, 0.85, []
        )
        hound_states[state]["atlas"] = f"package/actors/grub_hound/states/{state}.png"
    return {
        "grub_hound": {
            "baseline_state": "idle",
            "display_name": "Grub Hound",
            "facing_authored": "right",
            "facings": {"names": ["right"], "set": "single_mirrored", "side_view": "profile"},
            "footprint_radius_meters": 0.476,
            "ground_contact": "shadow",
            "height_meters": 0.85,
            "hostile": True,
            "mirror_for_left": True,
            "rebase": None,
            "role": "mob",
            "shadow_width_meters": 0.6,
            "states": hound_states,
            "still": "package/actors/grub_hound/states/idle.png",
        },
        "wren": {
            "baseline_state": "idle",
            "display_name": "Wren",
            "facing_authored": None,
            "facings": {"names": facings, "set": "four_way", "side_view": "quarter"},
            "footprint_radius_meters": 0.34,
            "ground_contact": "shadow",
            "height_meters": PLAYER_HEIGHT_METERS,
            "mirror_for_left": False,
            "rebase": None,
            "role": "player",
            "shadow_width_meters": 0.884,
            "states": wren_states,
            "still": "package/actors/wren/states/idle.front.png",
        },
    }


def props() -> dict:
    def chop(hits, yields, next_state, from_states):
        return {
            "from": from_states,
            "fx": "chips",
            "hits": hits,
            "next_state": next_state,
            "progress": [],
            "regrow_seconds": None,
            "tool": {"hits": 2, "item_id": "axe", "required": True},
            "verb": "chop",
            "yield_to": "ground",
            "yields": yields,
        }

    pine = {
        "anchor_record": None,
        "baseline_state": "grown",
        "drawn": {"columns": 2, "kind": "sheet", "rows": 2},
        "edge": "hard",
        "family": "tree",
        "footprint_radius_meters": 0.374,
        "height_meters": 5.44,
        "hit_reaction": "shake",
        "interactions": [
            chop(3, [{"count": 2, "item_id": "log"}], "stump", ["sapling", "grown", "old"]),
            {
                "from": ["sapling", "grown", "old"],
                "fx": "sparkle",
                "hits": 1,
                "next_state": "stump",
                "progress": [],
                "regrow_seconds": None,
                "tool": {"hits": 1, "item_id": "torch", "required": True},
                "verb": "burn",
                "yield_to": "ground",
                "yields": [],
            },
        ],
        "motion_hint": "sway_top",
        "shadow_width_meters": 1.615,
        "states": {
            "sapling": prop_state("pine", "sapling", 2.21, 0.896),
            "grown": prop_state("pine", "grown", 5.44, 0.914),
            "old": prop_state("pine", "old", 5.1, 0.889),
            "stump": prop_state("pine", "stump", 0.68, 0.883),
        },
        "variants": {"states": {}},
    }
    boulder = {
        "anchor_record": None,
        "baseline_state": "whole",
        "drawn": {"columns": 2, "kind": "sheet", "rows": 2},
        "edge": "hard",
        "family": "rock",
        "footprint_radius_meters": 0.34,
        "height_meters": 1.275,
        "hit_reaction": "none",
        # Three blows, and the two looks in `progress` are worn on the way: a
        # struck thing shows its damage before it gives way.
        "interactions": [
            {
                "from": ["whole", "cracked", "split"],
                "fx": "chips",
                "hits": 3,
                "next_state": "rubble",
                "progress": ["cracked", "split"],
                "regrow_seconds": 120.0,
                "tool": {"hits": 3, "item_id": "pickaxe", "required": True},
                "verb": "mine",
                "yield_to": "ground",
                "yields": [{"count": 2, "item_id": "stone"}],
            }
        ],
        "motion_hint": "none",
        "shadow_width_meters": 1.4,
        "states": {
            "whole": prop_state("moss_boulder", "whole", 1.275, 0.81),
            "cracked": prop_state("moss_boulder", "cracked", 1.267, 0.807),
            "split": prop_state("moss_boulder", "split", 1.263, 0.742),
            "rubble": prop_state("moss_boulder", "rubble", 0.51, 0.744),
        },
        "variants": {"states": {}},
    }
    thorn = {
        "anchor_record": None,
        "baseline_state": "full",
        "drawn": {"columns": 1, "kind": "sprite", "rows": 1},
        "edge": "soft",
        "family": "bush",
        "footprint_radius_meters": 0.45,
        "height_meters": 1.05,
        "hit_reaction": "shake",
        "interactions": [
            {
                "from": ["full"],
                "fx": "leaves",
                "hits": 1,
                "next_state": "picked",
                "progress": [],
                "regrow_seconds": 180.0,
                "tool": None,
                "verb": "gather",
                "yield_to": "pack",
                "yields": [{"count": 2, "item_id": "berry"}],
            }
        ],
        "motion_hint": "sway_top",
        "shadow_width_meters": 1.0,
        "states": {
            "full": prop_state("thorn_bush", "full", 1.05, 0.93),
            "picked": prop_state("thorn_bush", "picked", 0.9, 0.93),
        },
        "variants": {"states": {}},
    }
    campfire = {
        "anchor_record": None,
        "baseline_state": "unlit",
        "drawn": {"columns": 1, "kind": "sprite", "rows": 1},
        "edge": "hard",
        "family": "camp",
        "footprint_radius_meters": 0.374,
        "height_meters": 0.62,
        "hit_reaction": "none",
        "interactions": [
            {
                "from": ["unlit"],
                "fx": "sparkle",
                "hits": 1,
                "next_state": "lit",
                "progress": [],
                "regrow_seconds": None,
                "tool": {"hits": 1, "item_id": "torch", "required": False},
                "verb": "light",
                "yield_to": "ground",
                "yields": [],
            }
        ],
        "motion_hint": "flicker",
        "shadow_width_meters": 0.9,
        "states": {
            "unlit": prop_state("campfire", "unlit", 0.62, 0.94),
            "lit": prop_state("campfire", "lit", 0.62, 0.94),
        },
        "variants": {"states": {}},
    }
    workbench = {
        "anchor_record": None,
        "baseline_state": "whole",
        "drawn": {"columns": 1, "kind": "sprite", "rows": 1},
        "edge": "hard",
        "family": "camp",
        "footprint_radius_meters": 0.7,
        "height_meters": 0.95,
        "hit_reaction": "none",
        "interactions": [],
        "motion_hint": "none",
        "shadow_width_meters": 1.3,
        "states": {"whole": prop_state("workbench", "whole", 0.95, 0.95)},
        "variants": {"states": {}},
    }
    tuft = {
        "anchor_record": None,
        "baseline_state": "full",
        "drawn": {"columns": 1, "kind": "sprite", "rows": 1},
        "edge": "soft",
        "family": "bush",
        "footprint_radius_meters": 0.22,
        "height_meters": 0.45,
        "hit_reaction": "shake",
        "interactions": [
            {
                "from": ["full"],
                "fx": "leaves",
                "hits": 1,
                "next_state": "picked",
                "progress": [],
                "regrow_seconds": 120.0,
                "tool": None,
                "verb": "gather",
                "yield_to": "pack",
                "yields": [{"count": 1, "item_id": "grass_tuft"}],
            }
        ],
        "motion_hint": "sway_top",
        "shadow_width_meters": 0.5,
        "states": {
            "full": prop_state("grass_tuft", "full", 0.45, 0.95),
            "picked": prop_state("grass_tuft", "picked", 0.3, 0.95),
        },
        "variants": {"states": {}},
    }
    tent = {
        "anchor_record": None,
        "baseline_state": "pitched",
        "drawn": {"columns": 1, "kind": "sprite", "rows": 1},
        "edge": "hard",
        "family": "camp",
        "footprint_radius_meters": 1.054,
        "height_meters": 2.21,
        "hit_reaction": "none",
        "interactions": [],
        "motion_hint": "none",
        "shadow_width_meters": 2.4,
        "states": {"pitched": prop_state("canvas_tent", "pitched", 2.21, 0.9)},
        "variants": {"states": {}},
    }
    return {
        "campfire": campfire,
        "canvas_tent": tent,
        "grass_tuft": tuft,
        "moss_boulder": boulder,
        "pine": pine,
        "thorn_bush": thorn,
        "workbench": workbench,
    }


#: The six glyphs the HUD heads its lines with, on the item sheet beside them.
HUD_GLYPHS = ["heart", "bowl", "flame", "snowflake", "sun", "moon"]

#: The sixteen glyphs a preview sheet publishes, and the nine a cursor set does.
PREVIEW_GLYPHS = [
    "play",
    "pause",
    "close",
    "menu",
    "gear",
    "home",
    "retry",
    "check",
    "search",
    "hand",
    "heart",
    "star",
    "arrow_left",
    "arrow_right",
    "sound_on",
    "sound_off",
]
CURSOR_GLYPHS = [
    ("arrow", "tip_top_left"),
    ("hand", "tip_top"),
    ("grab", "centre"),
    ("crosshair", "centre"),
    ("inspect", "centre"),
    ("busy", "centre"),
    ("forbidden", "centre"),
    ("move", "centre"),
    ("text", "centre"),
]


def ui() -> dict:
    """The four UI sheets, laid out on a regular grid.

    A real sheet's cells are wherever the drawing put them and its insets were
    measured off the art; these are square and even. What the fixture is for is
    the *shape* — a nine-slice whose interior is its cell less its insets, and a
    glyph grid whose every cell names one word of the vocabulary.
    """

    def slice_sheet(role, states, band_fill, cell_w, cell_h, inset):
        cells = []
        for index, state in enumerate(states):
            x, y = 40, 40 + index * (cell_h + 40)
            cells.append(
                {
                    "cell": {"height": cell_h, "width": cell_w, "x": x, "y": y},
                    "content_rect": {
                        "height": cell_h - inset * 2,
                        "width": cell_w - inset * 2,
                        "x": x + inset,
                        "y": y + inset,
                    },
                    "safe_rect": {
                        "height": cell_h - inset * 2,
                        "width": cell_w - inset * 2,
                        "x": x + inset,
                        "y": y + inset,
                    },
                    "state": state,
                }
            )
        return {
            "alpha_policy": "transparent_exterior_opaque_body_v1",
            "asset": f"ui/{role}.png",
            "band_fill": band_fill,
            "canvas": {"height": 1024, "width": 1024},
            "cells": cells,
            "draw_scale": 2,
            "insets": {"bottom": inset, "left": inset, "right": inset, "top": inset},
            "layout": (
                "nine_slice_button_sheet_4x1024_v1"
                if role == "button_rect"
                else "nine_slice_panel_1024_v1"
            ),
            "role": role,
            "scale_mode": "nine_slice",
        }

    def glyph_sheet(role, glyphs, columns, cell_size, layout, cursors):
        cells = []
        for index, glyph in enumerate(glyphs):
            name = glyph[0] if cursors else glyph
            x = 24 + (index % columns) * (cell_size + 16)
            y = 24 + (index // columns) * (cell_size + 16)
            inset = cell_size // 5
            cell = {
                "cell": {"height": cell_size, "width": cell_size, "x": x, "y": y},
                "glyph": name,
                "glyph_rect": {
                    "height": cell_size - inset * 2,
                    "width": cell_size - inset * 2,
                    "x": x + inset,
                    "y": y + inset,
                },
            }
            if cursors:
                # The hotspot is where the rule says it is, in cell-local
                # pixels: an arrow points from its own upper left, a pointing
                # hand from the top of its finger, everything else from
                # the middle.
                rule = glyph[1]
                if rule == "tip_top_left":
                    spot = {"x": inset, "y": inset}
                elif rule == "tip_top":
                    spot = {"x": cell_size // 2, "y": inset}
                else:
                    spot = {"x": cell_size // 2, "y": cell_size // 2}
                cell["hotspot"] = spot
                cell["hotspot_rule"] = rule
            cells.append(cell)
        return {
            "alpha_policy": "transparent_exterior_opaque_glyph_v1",
            "asset": f"ui/{role}.png",
            "canvas": {"height": 1024, "width": 1024},
            "cell_size": cell_size,
            "cells": cells,
            "draw_scale": 2,
            "layout": layout,
            "role": role,
            "scale_mode": "fixed",
        }

    return {
        "button_rect": slice_sheet(
            "button_rect", ["normal", "hover", "pressed", "disabled"], "stretch", 664, 176, 40
        ),
        "cursor_set": glyph_sheet(
            "cursor_set", CURSOR_GLYPHS, 3, 320, "cursor_grid_3x3_1024_v1", True
        ),
        "panel_frame": slice_sheet("panel_frame", ["default"], "tile", 904, 506, 96),
        "preview_icons": glyph_sheet(
            "preview_icons", PREVIEW_GLYPHS, 4, 232, "icon_grid_4x4_1024_preview_v1", False
        ),
    }


def manifest() -> dict:
    return {
        "actors": actors(),
        "camera": {
            "asset_pitch_degrees": 30.0,
            "distance_meters": 18.0,
            "follow_lerp": 0.08,
            "fov_degrees": 35.0,
            "pitch_degrees": 55.0,
            "reference_height_px": 900,
            "rotation_allowed": True,
            "yaw_degrees": 45.0,
            "yaw_step_degrees": 45.0,
        },
        "crafting": {
            # Eleven recipes: the two stations are themselves built by hand,
            # and a recipe whose product is a `prop_id` puts a thing on the
            # ground rather than in the pack.
            "recipes": [
                {
                    "ingredients": {"flint": 1, "twig": 1},
                    "product": {"count": 1, "item_id": "axe"},
                    "recipe_id": "axe",
                    "station": "hand",
                },
                {
                    "ingredients": {"grass_tuft": 2, "twig": 1},
                    "product": {"count": 1, "item_id": "torch"},
                    "recipe_id": "torch",
                    "station": "hand",
                },
                {
                    "ingredients": {"reed": 3},
                    "product": {"count": 1, "item_id": "rope"},
                    "recipe_id": "rope",
                    "station": "hand",
                },
                {
                    "ingredients": {"grass_tuft": 1, "moss": 2},
                    "product": {"count": 1, "item_id": "poultice"},
                    "recipe_id": "poultice",
                    "station": "hand",
                },
                {
                    "ingredients": {"grass_tuft": 3, "log": 2},
                    "product": {"prop_id": "campfire", "state": "lit"},
                    "recipe_id": "campfire",
                    "station": "hand",
                },
                {
                    "ingredients": {"log": 4, "rope": 1, "stone": 2},
                    "product": {"prop_id": "workbench", "state": "whole"},
                    "recipe_id": "workbench",
                    "station": "hand",
                },
                {
                    "ingredients": {"flint": 2, "twig": 2},
                    "product": {"count": 1, "item_id": "pickaxe"},
                    "recipe_id": "pickaxe",
                    "station": "workbench",
                },
                {
                    "ingredients": {"grass_tuft": 4, "rope": 4},
                    "product": {"count": 1, "item_id": "backpack"},
                    "recipe_id": "backpack",
                    "station": "workbench",
                },
                {
                    "ingredients": {"grass_tuft": 6, "rope": 2},
                    "product": {"count": 1, "item_id": "grass_cloak"},
                    "recipe_id": "grass_cloak",
                    "station": "workbench",
                },
                {
                    "ingredients": {"berry": 2},
                    "product": {"count": 1, "item_id": "cooked_berry"},
                    "recipe_id": "cooked_berry",
                    "station": "campfire",
                },
                {
                    "ingredients": {"stone": 1},
                    "product": {"count": 1, "item_id": "warm_stone"},
                    "recipe_id": "warm_stone",
                    "station": "campfire",
                },
            ],
            "slots": 12,
            "start": {},
            "stations": {
                "campfire": {"prop_id": "campfire", "reach_meters": 3.0, "state": "lit"},
                "workbench": {"prop_id": "workbench", "reach_meters": 3.0, "state": None},
            },
        },
        "fx": {
            "dust": {
                "atlas": "package/fx/dust.png",
                "cells": [
                    {"h": 256, "kind": "dust", "w": 256, "x": 0, "y": 0},
                    {"h": 256, "kind": "leaves", "w": 256, "x": 256, "y": 0},
                    {"h": 256, "kind": "chips", "w": 256, "x": 0, "y": 256},
                    {"h": 256, "kind": "sparkle", "w": 256, "x": 256, "y": 256},
                ],
                "height_px": 512,
                "px_per_meter": 512.0,
                "width_px": 512,
            },
            "fire": {
                "base_origin": [0.5, 0.95],
                "blend": "additive",
                "cell_px": 64,
                "columns": 4,
                "fps": 12.0,
                "frames": 16,
                "height_meters": 0.935,
                "mode": "loop",
                "px_per_meter": 68.4492,
                "rows": 4,
                "strip": "package/fx/fire.png",
            },
        },
        "gameplay": {
            "approach_meters": 4.5,
            "campfire": {
                "burn_seconds": 90.0,
                "heat_per_second": 8.0,
                "heat_radius_meters": 3.5,
                "light_color": [1.0, 0.72, 0.4],
                "light_radius_meters": 6.0,
            },
            "day_length_seconds": 480.0,
            "health": {"max": 100.0, "starve_damage_per_second": 2.0},
            "hunger": {"drain_per_second": 0.25, "max": 100.0},
            "interact_reach_meters": 0.6,
            "mob": {
                "aggro_radius_meters": 6.0,
                "attack_cooldown_seconds": 1.5,
                "attack_damage": 10.0,
                "attack_range_meters": 1.0,
                "speed_meters_per_second": 2.6,
                "wander_radius_meters": 4.0,
            },
            "night": {"tint": [0.35, 0.42, 0.7]},
            "pickup": "manual",
            "player_speed_meters_per_second": 3.2,
            "torch": {"heat_scale": 0.7},
            "warmth": {
                "dark_drain_per_second": 0.4,
                "drain_per_second": 0.5,
                "freeze_damage_per_second": 2.0,
                "max": 100.0,
                "night_scale": 0.6,
            },
        },
        "ground": ground(),
        "ground_contact": "skirt_decal",
        # One sheet carries both the pack's item icons and the six glyphs the
        # HUD heads its vital lines with; a run whose sheet lost the glyphs
        # falls back to a word, which is a thing worth being able to see fail.
        "icons": {
            "atlas": "package/items/icons.png",
            "cell_px": 256,
            "cells": [
                {
                    "h": 256,
                    "index": index,
                    "item_id": entry[0],
                    "w": 256,
                    "x": (index % 6) * 256,
                    "y": (index // 6) * 256,
                }
                for index, entry in enumerate(ITEMS)
            ]
            + [
                {
                    "glyph": glyph,
                    "h": 256,
                    "index": len(ITEMS) + offset,
                    "w": 256,
                    "x": ((len(ITEMS) + offset) % 6) * 256,
                    "y": ((len(ITEMS) + offset) // 6) * 256,
                }
                for offset, glyph in enumerate(HUD_GLYPHS)
            ],
            "columns": 6,
            "height_px": 1024,
            "rows": 4,
            "width_px": 1536,
        },
        "items": {
            entry[0]: item(entry[0], entry[1], index, entry[2], entry[3], entry[4], entry[5])
            for index, entry in enumerate(ITEMS)
        },
        "kind": KIND,
        # The manifest embeds the same world document the package carries, and
        # a test checks the two do not disagree — so this is the layout itself.
        "layout": layout(),
        "look": {
            "ground_pieces": {"jitter_degrees": 15.0, "orientation": "camera_facing"},
            "light": "overhead",
            "mirror": "facing_only",
        },
        "package_id": "suite-fixture",
        "presentation_profile": "elevated_oblique_perspective_ground_plane_v1",
        "props": props(),
        "publication_authorized": False,
        "scale": {
            "minimum_height_meters": 0.425,
            "minimum_height_units": 0.25,
            "minimum_screen_px": 33.7,
            "player_height_meters": PLAYER_HEIGHT_METERS,
            "screen_px_per_meter": 79.29,
        },
        "schema_version": SCHEMA_VERSION,
        "seasons": {
            "calendar": {"days_per_season": 4, "order": ["summer", "winter"]},
            "looks": ["winter"],
            "seasons": [
                {
                    "barren": [],
                    "cold": 0.0,
                    "display_name": "Summer",
                    "hidden_forage": [],
                    "look": "",
                    "night_share": 0.38,
                    "regrow_scale": 1.0,
                    "season_id": "summer",
                    "snow": 0.0,
                },
                {
                    "barren": ["thorn_bush"],
                    "cold": 1.0,
                    "display_name": "Winter",
                    "hidden_forage": ["mushroom", "moss"],
                    "look": "winter",
                    "night_share": 0.55,
                    "regrow_scale": 0.0,
                    "season_id": "winter",
                    "snow": 1.0,
                },
            ],
        },
        "status": "fixture",
        "style": {"label": "flat inked cutout survival", "reference_sha256": None},
        "title": "The suite's own world",
        "ui": ui(),
        "weather": weather(),
        "world": {"seed": 7, "set_pieces": []},
    }


def weather() -> dict:
    """Rain and snow, in the published shape and at the published numbers.

    The onsets are the two the sim's own arithmetic is checked against — rain
    reaches full in fourteen seconds, snow in sixty — and the strike interval
    is the band a bolt must be armed inside. Neither block carries its sound:
    an mp3 cannot be written from the standard library, and a weather block
    with no `sound` key is what a run without one publishes.
    """
    rain = {
        "cover": None,
        "decay_seconds": 26.0,
        "desaturate": 0.3,
        "drops": {
            "atlas": "package/weather/rain/drops.png",
            "cells": [
                {"h": 256, "kind": "streak", "w": 128, "x": 0, "y": 0},
                {"h": 256, "kind": "drop", "w": 128, "x": 128, "y": 0},
            ],
            "count_per_screen": 180,
            "fall_speed_meters_per_second": 12.0,
            "height_meters": 0.255,
            "height_px": 256,
            "layers": 3,
            "width_px": 256,
        },
        "dry_spell_seconds": [120.0, 360.0],
        "ground": {
            "atlas": "package/weather/rain/ground.png",
            "cells": [
                {"h": 256, "kind": "ring", "w": 256, "x": 0, "y": 0},
                {"h": 256, "kind": "ring", "w": 256, "x": 256, "y": 0},
            ],
            "height_meters": 0.272,
            "height_px": 256,
            "px_per_meter": 941.1765,
            "rate_per_100_sqm_per_second": 10.0,
            "width_px": 512,
        },
        "ice": None,
        "onset_seconds": 14.0,
        "sound": None,
        "strike": {
            "above": 0.72,
            "atlas": "package/weather/rain/strike.png",
            "cells": [
                {"h": 256, "kind": "bolt_0", "w": 128, "x": 0, "y": 0},
                {"h": 256, "kind": "bolt_1", "w": 128, "x": 128, "y": 0},
            ],
            "flash_seconds": 0.5,
            "height_meters": 13.6,
            "height_px": 256,
            "interval_seconds": [7.0, 24.0],
            "width_px": 256,
        },
        "tint": [0.8, 0.88, 0.94],
        "wet": {"decal_id": "puddle", "dry_seconds": 90.0},
        "wet_spell_seconds": [70.0, 200.0],
    }
    snow = {
        "cover": {
            "luma_mean": 0.9447,
            "texel_meters": 4.0,
            "texture": "package/weather/snow/cover.png",
            "tiling": "mirror_repeat_2d",
            "value_target": 0.84,
        },
        "decay_seconds": 120.0,
        "desaturate": 0.35,
        "drops": {
            "atlas": "package/weather/snow/drops.png",
            "cells": [
                {"h": 256, "kind": "flake", "w": 128, "x": 0, "y": 0},
                {"h": 256, "kind": "speck", "w": 128, "x": 128, "y": 0},
            ],
            "count_per_screen": 160,
            "fall_speed_meters_per_second": 1.2,
            "height_meters": 0.0595,
            "height_px": 256,
            "layers": 3,
            "width_px": 256,
        },
        "dry_spell_seconds": [600.0, 1800.0],
        "ground": None,
        "ice": {
            "luma_mean": 0.8896,
            "texel_meters": 12.0,
            "texture": "package/weather/snow/ice.png",
            "tiling": "mirror_repeat_2d",
            "value_target": 0.72,
        },
        "onset_seconds": 60.0,
        "sound": None,
        "strike": None,
        "tint": [0.88, 0.92, 1.0],
        "wet": None,
        "wet_spell_seconds": [300.0, 900.0],
    }
    return {"rain": rain, "snow": snow}


# ---------------------------------------------------------------- layout


#: What stands in the fixture world, hand-placed. Twenty-two things, each one
#: something the player can act on — decision 0060's rule holds here too.
#: The footprint the *layout* gives an instance, which must win over the
#: prop's own. Deliberately a little wider than the prop's authored radius.
FOOTPRINTS = {
    "canvas_tent": 1.275,
    "pine": 0.42,
    "moss_boulder": 0.7,
    "thorn_bush": 0.5,
    "grass_tuft": 0.26,
    "campfire": 0.55,
    "workbench": 0.78,
}

PLACED = [
    # The tent stands first, so it is `p0000`: the one entity whose footprint
    # the *layout* overrides, which is the rule a reader has to obey.
    ("canvas_tent", "pitched", [(-2.2, -1.4)]),
    ("pine", "grown", [(-9.0, -7.0), (-5.5, -8.5), (-2.0, -7.5), (2.5, -8.0), (6.0, -6.5)]),
    ("pine", "sapling", [(-7.5, -4.0), (4.0, -4.5)]),
    ("pine", "old", [(9.0, -5.0)]),
    ("moss_boulder", "whole", [(7.5, 1.5), (8.5, 4.5), (5.5, 6.0)]),
    ("thorn_bush", "full", [(-6.0, 3.0), (-4.5, 5.5), (-8.0, 6.5), (3.0, 7.0)]),
    ("grass_tuft", "full", [(-2.5, 4.0), (0.5, 6.5), (2.0, 3.5), (-10.0, 1.0)]),
    ("campfire", "unlit", [(1.4, 0.9)]),
    ("workbench", "whole", [(-3.6, 1.2)]),
]


def layout() -> dict:
    entities = []
    counts: dict[str, int] = {}
    index = 0
    for prop, state, spots in PLACED:
        for x, z in spots:
            # An optional field is *omitted* where it has no value, which is what
            # the producer publishes and what the readers assume: `String(null)`
            # is an invalid call that aborts its caller, so a layout writing an
            # explicit null builds no world at all.
            row = {
                "footprint_radius_meters": FOOTPRINTS[prop],
                "id": f"p{index:04d}",
                "kind": "prop",
                "prop": prop,
                "seed": 100 + index * 7,
                "state": state,
                "x": x,
                "z": z,
            }
            if prop in ("campfire", "workbench", "canvas_tent"):
                row["set_piece"] = "camp/0"
            else:
                row["cluster"] = f"{prop}/c0"
            entities.append(row)
            counts[prop] = counts.get(prop, 0) + 1
            index += 1
    for spot, (x, z) in enumerate([(-11.0, 9.0), (10.5, 9.5)]):
        entities.append(
            {
                "actor": "grub_hound",
                "cluster": "grub_hound/c0",
                "footprint_radius_meters": 0.476,
                "id": f"m{spot:04d}",
                "kind": "mob",
                "seed": 900 + spot,
                "x": x,
                "z": z,
            }
        )
        counts["grub_hound"] = counts.get("grub_hound", 0) + 1
    forage = []
    for spot in range(12):
        angle = spot * 2.399963
        radius = 4.0 + spot * 0.7
        forage.append(
            {
                "cell": spot % len(FORAGE),
                "rotation_degrees": round(-30.0 + spot * 5.0, 3),
                "scale": round(0.85 + (spot % 5) * 0.06, 3),
                "x": round(math.cos(angle) * radius, 3),
                "z": round(math.sin(angle) * radius, 3),
            }
        )
    decals = [
        {
            "decal": "path",
            "rotation_degrees": 0.0,
            "scale": 1.2,
            "under": "p0016",
            "x": 1.4,
            "z": 0.9,
        }
    ]
    # The shares are counted off the plates themselves rather than declared, so
    # the record and the picture cannot drift apart — which is exactly what one
    # of the ground checks compares.
    land_cells = sum(1 for y in range(MASK_CELLS) for x in range(MASK_CELLS) if land(x, y)[3] > 127)
    weights = {"dry_meadow": 0, "mossy_bog": 0, "grey_scree": 0, "forest_floor": 0}
    for y in range(MASK_CELLS):
        for x in range(MASK_CELLS):
            r, g, b, _a = biomes(x, y)
            if r > 127:
                weights["dry_meadow"] += 1
            elif g > 127:
                weights["mossy_bog"] += 1
            elif b > 127:
                weights["grey_scree"] += 1
            else:
                weights["forest_floor"] += 1
    total = float(MASK_CELLS * MASK_CELLS)
    return {
        "biome_shares": {name: round(count / total, 4) for name, count in weights.items()},
        "camp_position": {"x": 0.0, "z": 0.0},
        "cell_meters": CELL_METERS,
        "clear_radius_meters": 6.0,
        "counts": counts,
        "decals": decals,
        "entities": entities,
        "forage": forage,
        "land_share": round(land_cells / total, 4),
        "player_spawn": {"x": 0.0, "z": 2.4},
        "report": {},
        "road": {
            "points": [
                {"x": 0.0, "z": -2.0},
                {"x": 0.4, "z": 2.0},
                {"x": 0.2, "z": 6.0},
                {"x": -0.4, "z": 10.0},
            ],
            "road_id": "dirt_track",
            "width_meters": 2.2,
        },
        "seed": 7,
        "set_pieces": [
            {"clearing_radius_meters": 6.0, "id": "camp/0", "set_piece": "camp", "x": 0.0, "z": 0.0}
        ],
        "size_meters": SIZE_METERS,
    }


# ---------------------------------------------------------------- writing


GROUND_COLOURS = {
    "forest_floor": ((72, 88, 58), (64, 79, 52)),
    "dry_meadow": ((168, 158, 104), (156, 146, 96)),
    "mossy_bog": ((88, 110, 82), (78, 99, 74)),
    "grey_scree": ((138, 136, 130), (124, 122, 117)),
}

PROP_COLOURS = {
    "pine": (66, 96, 62),
    "moss_boulder": (128, 130, 122),
    "thorn_bush": (94, 82, 58),
    "campfire": (110, 84, 60),
    "workbench": (132, 106, 72),
    "canvas_tent": (176, 166, 140),
    "grass_tuft": (142, 152, 92),
}


def frame(sheet, side=1024):
    """A nine-slice sheet: each cell painted as a border, its interior clear."""
    canvas = bytearray(side * side * 4)
    inset = sheet["insets"]["left"]
    for entry in sheet["cells"]:
        box = entry["cell"]
        for y in range(box["y"], box["y"] + box["height"]):
            for x in range(box["x"], box["x"] + box["width"]):
                edge = min(
                    x - box["x"],
                    box["x"] + box["width"] - 1 - x,
                    y - box["y"],
                    box["y"] + box["height"] - 1 - y,
                )
                if edge >= inset:
                    continue
                shade = 190 - edge * 2
                at = (y * side + x) * 4
                canvas[at : at + 4] = bytes((shade, max(0, shade - 24), max(0, shade - 58), 255))
    return canvas


def grid(sheet, side=1024):
    """A glyph sheet: one filled disc a cell, inside the rect the record names."""
    canvas = bytearray(side * side * 4)
    for entry in sheet["cells"]:
        box = entry["glyph_rect"]
        cx, cy = box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5
        rx, ry = box["width"] * 0.5, box["height"] * 0.5
        for y in range(box["y"], box["y"] + box["height"]):
            for x in range(box["x"], box["x"] + box["width"]):
                if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 > 1.0:
                    continue
                at = (y * side + x) * 4
                canvas[at : at + 4] = b"\xec\xe8\xdc\xff"
    return canvas


def write(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    document = manifest()
    (root / "manifest.json").write_text(json.dumps(document, indent=1, sort_keys=True) + "\n")

    world = root / "package" / "world"
    (world).mkdir(parents=True, exist_ok=True)
    (world / "layout.json").write_text(json.dumps(layout(), indent=1, sort_keys=True) + "\n")
    png(world / "splat.png", MASK_CELLS, MASK_CELLS, land)
    png(world / "biomes.png", MASK_CELLS, MASK_CELLS, biomes)

    ground_dir = root / "package" / "ground"
    for name, (one, two) in GROUND_COLOURS.items():
        png(ground_dir / f"{name}.png", TILE_PX, TILE_PX, checker((*one, 255), (*two, 255), 16))
    png(
        ground_dir / "macro.png",
        TILE_PX,
        TILE_PX,
        checker((150, 150, 150, 255), (138, 138, 138, 255), 64),
    )
    png(ground_dir / "water.png", TILE_PX, TILE_PX, flat((40, 60, 68, 255)))
    png(
        ground_dir / "road-dirt_track.png",
        TILE_PX,
        TILE_PX,
        checker((122, 104, 82, 255), (112, 95, 74, 255), 16),
    )
    png(ground_dir / "forage.png", 512, 512, strip((148, 150, 96), 2, 2, 256, 256))
    for decal, colour in [
        ("path", (110, 96, 76)),
        ("puddle", (54, 70, 78)),
        ("tree_skirt", (52, 62, 44)),
        ("rock_skirt", (86, 88, 82)),
    ]:
        png(
            ground_dir / "decals" / f"{decal}.png",
            PLATE_PX,
            PLATE_PX,
            blob(colour, feet=0.5, waist=0.48),
        )

    # Each sheet is written at exactly the size its own record adds up to:
    # columns times the cell, by the cell's height.
    written: dict[Path, bool] = {}
    for actor_id, actor in document["actors"].items():
        colour = (176, 148, 112) if actor_id == "wren" else (122, 96, 74)
        for spec in actor["states"].values():
            for side in spec.get("facings", {"": spec}).values():
                path = root / side["atlas"]
                if path in written:
                    continue
                written[path] = True
                cell_w, cell_h = side["cell_width"], side["cell_height"]
                png(
                    path,
                    cell_w * side["columns"],
                    cell_h,
                    strip(colour, side["columns"], 1, cell_w, cell_h),
                )

    props_dir = root / "package" / "props"
    for prop_id, prop in document["props"].items():
        colour = PROP_COLOURS[prop_id]
        for state, spec in prop["states"].items():
            png(
                props_dir / prop_id / f"{state}.png",
                PLATE_PX,
                PLATE_PX,
                blob(colour, feet=spec["ground_contact_y_normalized"]),
            )
            for look in spec.get("looks", {}):
                png(
                    props_dir / prop_id / f"{state}.{look}.png",
                    PLATE_PX,
                    PLATE_PX,
                    blob((214, 220, 228), feet=spec["ground_contact_y_normalized"]),
                )

    items_dir = root / "package" / "items"
    for item_id, *_ in ITEMS:
        png(items_dir / f"{item_id}.png", PLATE_PX, PLATE_PX, blob((176, 156, 116), feet=0.9))
    png(items_dir / "icons.png", 1536, 1024, strip((176, 156, 116), 6, 4, 256, 256))

    fx_dir = root / "package" / "fx"
    png(fx_dir / "dust.png", 512, 512, strip((210, 200, 178), 2, 2, 256, 256))
    png(fx_dir / "fire.png", 256, 256, strip((236, 168, 72), 4, 4, 64, 64))

    weather_dir = root / "package" / "weather"
    png(weather_dir / "rain" / "drops.png", 256, 256, strip((196, 210, 226), 2, 1, 128, 256))
    png(weather_dir / "rain" / "ground.png", 512, 256, strip((150, 170, 186), 2, 1, 256, 256))
    png(weather_dir / "rain" / "strike.png", 256, 256, strip((238, 244, 255), 2, 1, 128, 256))
    png(weather_dir / "snow" / "drops.png", 256, 256, strip((236, 240, 248), 2, 1, 128, 256))
    png(
        weather_dir / "snow" / "cover.png",
        TILE_PX,
        TILE_PX,
        checker((236, 240, 246, 255), (226, 232, 240, 255), 16),
    )
    png(
        weather_dir / "snow" / "ice.png",
        TILE_PX,
        TILE_PX,
        checker((214, 226, 236, 255), (204, 218, 230, 255), 32),
    )

    # The UI sheets: a nine-slice is drawn as a frame so the interior its record
    # names is genuinely unpainted, and a glyph grid as one blob a cell.
    ui_dir = root / "ui"
    for role, sheet in document["ui"].items():
        if sheet["scale_mode"] == "nine_slice":
            png(ui_dir / f"{role}.png", 1024, 1024, frame(sheet))
        else:
            png(ui_dir / f"{role}.png", 1024, 1024, grid(sheet))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    root = Path(argv[1])
    write(root)
    print(f"   fixture run written to {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
