"""A synthetic two-genre bellweather: the committed platformer package plus a
runner member authored in tmp, sharing the cover reference by digest."""

from __future__ import annotations

import shutil
from pathlib import Path

SOURCE_PACKAGE = Path(__file__).resolve().parents[2] / "library" / "games" / "bellweather"

COVER_SHA256 = "e8d27ab2d83210fe2bf8e4f072588614fbe293de75dae51677a96079f1e9f6a5"

RUNNER_GAMEPLAY = """schema_version = 1
kind = "runner-gameplay-v1"
game_id = "bellweather"
revision = 1
track_id = "meadow-dash"

[run]
speed_profile = "steady_runner_v1"
jump_profile = "single_arc_v1"
collision_policy = "end_run_v1"

[ramp]
profile = "gentle_ramp_v1"
"""

# 12 columns x 8 rows; walk surface at row 5 (three solid rows at the bottom).
FLAT_ROWS = [
    "000000000000",
    "000000000000",
    "000000000000",
    "000000000000",
    "000000000000",
    "111111111111",
    "111111111111",
    "111111111111",
]

GAP_ROWS = [
    "000000000000",
    "000000000000",
    "000000000000",
    "000000000000",
    "000000000000",
    "111100011111",
    "111100011111",
    "111100011111",
]


def occupancy_toml(rows: list[str]) -> str:
    quoted = ",\n  ".join(f'"{row}"' for row in rows)
    return f"[\n  {quoted},\n]"


def runner_track_toml(chunks: str) -> str:
    return f"""schema_version = 1
kind = "runner-track-v1"
game_id = "bellweather"
track_id = "meadow-dash"
revision = 1
display_name = "Meadow Dash"

[view]
profile = "side_view_2d"
gameplay_space = "side_plane"

[camera]
mode = "auto_run_x_v1"

[continuity]
seamless_axis = "x"
loop_construction = "mirror_repeat"

[[references]]
reference_id = "cover_style"
source = "references/cover.png"
source_sha256 = "{COVER_SHA256}"
rights_status = "redistribution-approved"
rights_basis = ["AI-generated Bellweather concept cover approved by the authenticated task owner."]

[[layers]]
layer_id = "meadow_sky"
reference_ids = ["cover_style"]
plane = "background"
order = 0
parallax = 0.1
alpha_mode = "opaque"
vertical_anchor = "canvas_cover"
prompt = "A bright morning sky band over rolling meadow silhouettes."

[layers.presentation]
contrast = 1.0
saturation = 1.0
atmosphere_color = "#9db8d9"
atmosphere_strength = 0.0
detail_blur_screen_pixels = 0.0

[ground]
mode = "terrain-atlas-3x3-minimal-v1"
reference_ids = ["cover_style"]
vertical_fit = "floor_to_screen_bottom"
prompt = "Warm meadow-path stone cap over a darker packed-earth fill."

[segments]
rows = 8
walk_surface_row = 5

{chunks}
"""


def chunk_toml(segment_id: str, rows: list[str], *, difficulty: int = 1, extra: str = "") -> str:
    return f"""[[segments.chunks]]
segment_id = "{segment_id}"
difficulty = {difficulty}
occupancy = {occupancy_toml(rows)}
{extra}"""


RUNNER_AVATAR = f"""schema_version = 1
kind = "runner-avatar-v1"
game_id = "bellweather"
revision = 1

[[references]]
reference_id = "cover_style"
source = "references/cover.png"
source_sha256 = "{COVER_SHA256}"
rights_status = "redistribution-approved"
rights_basis = ["AI-generated Bellweather concept cover approved by the authenticated task owner."]

[avatar]
avatar_id = "wayfarer_sprinter"
display_name = "The Wayfarer, Running"
body_kind = "human"
age = 19
reference_ids = ["cover_style"]
prompt = "The same compact adventurer, satchel strapped tight, sprinting with nothing trailing."

[[avatar.motions]]
state = "run"
playback_mode = "loop"
canonical_frame_indices = [0, 1, 2, 3]
frames_per_second = 10

[[avatar.motions]]
state = "jump"
playback_mode = "once"
canonical_frame_indices = [0, 1, 2, 3]
frames_per_second = 10

[[avatar.motions]]
state = "death"
playback_mode = "once"
canonical_frame_indices = [0, 1, 2, 3]
frames_per_second = 8
"""

RUNNER_PROPS = f"""schema_version = 2
kind = "prop-content-v2"
game_id = "bellweather"
revision = 1

[[references]]
reference_id = "cover_style"
source = "references/cover.png"
source_sha256 = "{COVER_SHA256}"
rights_status = "redistribution-approved"
rights_basis = ["AI-generated Bellweather concept cover approved by the authenticated task owner."]

[[props]]
prop_id = "toppled_cart"
height_units = 1.00
display_name = "Toppled Cart"
reference_ids = ["cover_style"]
prompt = "A small toppled wooden hand cart shedding round loaves; strict side view, isolated."
"""

RUNNER_ITEMS = f"""schema_version = 2
kind = "item-content-v2"
game_id = "bellweather"
revision = 1

[[references]]
reference_id = "cover_style"
source = "references/cover.png"
source_sha256 = "{COVER_SHA256}"
rights_status = "redistribution-approved"
rights_basis = ["AI-generated Bellweather concept cover approved by the authenticated task owner."]

[[items]]
item_id = "meadow_penny"
height_units = 0.25
display_name = "Meadow Penny"
item_kind = "currency"
reference_ids = ["cover_style"]
prompt = "A tiny warm-brass coin with one pressed petal and no text; clean collectible icon."
"""

DEFAULT_CHUNKS = "\n".join(
    [
        chunk_toml("warmup_flat", FLAT_ROWS),
        chunk_toml(
            "first_gap",
            GAP_ROWS,
            difficulty=2,
            extra=(
                '[[segments.chunks.hazards]]\nprop_id = "toppled_cart"\ncolumn = 2\n\n'
                '[[segments.chunks.pickups]]\nitem_id = "meadow_penny"\ncolumn = 5\nrow = 3\n'
            ),
        ),
    ]
)


def two_genre_package(tmp_path: Path, *, chunks: str = DEFAULT_CHUNKS) -> Path:
    """Copy the committed two-genre bellweather and swap in this fixture's
    authored runner gameplay and track, so tests control the chunks under
    admission while every other member stays the canonical one."""

    package = tmp_path / "bellweather"
    shutil.copytree(SOURCE_PACKAGE, package)
    runner = package / "runner"
    (runner / "gameplay.toml").write_text(RUNNER_GAMEPLAY, encoding="utf-8")
    (runner / "track.toml").write_text(runner_track_toml(chunks), encoding="utf-8")
    (runner / "content" / "avatar.toml").write_text(RUNNER_AVATAR, encoding="utf-8")
    (runner / "content" / "props.toml").write_text(RUNNER_PROPS, encoding="utf-8")
    (runner / "content" / "items.toml").write_text(RUNNER_ITEMS, encoding="utf-8")
    return package


__all__ = [
    "COVER_SHA256",
    "DEFAULT_CHUNKS",
    "FLAT_ROWS",
    "GAP_ROWS",
    "chunk_toml",
    "two_genre_package",
]
