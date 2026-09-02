"""A synthetic two-genre bellweather: the committed platformer package plus a
runner member authored in tmp, sharing the cover reference by digest.

The default chunks are compliant with the full `reaction_fair_v1` placement
discipline - apron, separations, landing clearance, press windows, telegraph
arcs - so each refusal test violates exactly one rule on top of a passing
baseline. The arc pickup rows below were computed from the SDK's own
closed forms (launch surface 5, offsets 1..4 of the declared arc).
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

SOURCE_PACKAGE = Path(__file__).resolve().parents[2] / "library" / "games" / "bellweather"

COVER_SHA256 = "e8d27ab2d83210fe2bf8e4f072588614fbe293de75dae51677a96079f1e9f6a5"

RUNNER_GAMEPLAY = """schema_version = 2
kind = "runner-gameplay-v2"
game_id = "bellweather"
revision = 1
track_id = "meadow-dash"

[run]
speed_profile = "steady_runner_v1"
jump_profile = "double_arc_v1"
collision_policy = "end_run_v1"
duck_profile = "slide_v1"

[ramp]
profile = "gentle_ramp_v1"
"""

#: A gameplay member with no duck verb, for the overhead-without-duck refusal.
RUNNER_GAMEPLAY_NO_DUCK = RUNNER_GAMEPLAY.replace('duck_profile = "slide_v1"\n', "")

# 12 columns x 8 rows; walk surface at row 5 (three solid rows at the bottom).
# Narrow on purpose: refusals that fire before the apron (seam, gap width,
# model-level placement) still read best on the smallest grid that shows them.
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

# 24 columns, all supported at the walk surface: room for a 5-column apron at
# each end with placements in between.
WIDE_FLAT_ROWS = ["0" * 24] * 5 + ["1" * 24] * 3

# 28 columns with a 3-column pit at columns 16-18, clear of the 7-column apron.
GAP28_ROWS = ["0" * 28] * 5 + ["1" * 16 + "000" + "1" * 9] * 3

#: Four pickups on the declared arc over the GAP28 pit (launch column 15).
ARC_PICKUPS = (
    '[[segments.chunks.pickups]]\nitem_id = "meadow_penny"\ncolumn = 16\nrow = 3\n\n'
    '[[segments.chunks.pickups]]\nitem_id = "meadow_penny"\ncolumn = 17\nrow = 2\n\n'
    '[[segments.chunks.pickups]]\nitem_id = "meadow_penny"\ncolumn = 18\nrow = 2\n\n'
    '[[segments.chunks.pickups]]\nitem_id = "meadow_penny"\ncolumn = 19\nrow = 3\n'
)

#: Four pickups on the declared arc over the default cart at column 7 (launch 5).
CART_ARC_PICKUPS = (
    '[[segments.chunks.pickups]]\nitem_id = "meadow_penny"\ncolumn = 6\nrow = 3\n\n'
    '[[segments.chunks.pickups]]\nitem_id = "meadow_penny"\ncolumn = 7\nrow = 2\n\n'
    '[[segments.chunks.pickups]]\nitem_id = "meadow_penny"\ncolumn = 8\nrow = 2\n\n'
    '[[segments.chunks.pickups]]\nitem_id = "meadow_penny"\ncolumn = 9\nrow = 3\n'
)


def occupancy_toml(rows: list[str]) -> str:
    quoted = ",\n  ".join(f'"{row}"' for row in rows)
    return f"[\n  {quoted},\n]"


def runner_track_toml(chunks: str) -> str:
    return f"""schema_version = 3
kind = "runner-track-v3"
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


RUNNER_AVATAR = f"""schema_version = 3
kind = "runner-avatar-v3"
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
silhouette_mode = "single_character_v1"
proportion_basis = "character_head_v1"
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
state = "slide"
playback_mode = "once"
canonical_frame_indices = [0, 1, 2, 3]
frames_per_second = 12

[[avatar.motions]]
state = "death"
playback_mode = "once"
canonical_frame_indices = [0, 1, 2, 3]
frames_per_second = 8
"""

#: An avatar with no slide strip, for the duck-without-slide refusal.
RUNNER_AVATAR_NO_SLIDE = RUNNER_AVATAR.replace(
    """[[avatar.motions]]
state = "slide"
playback_mode = "once"
canonical_frame_indices = [0, 1, 2, 3]
frames_per_second = 12

""",
    "",
)


def runner_props_toml(cart_height_units: float = 0.85) -> str:
    return f"""schema_version = 2
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
height_units = {cart_height_units}
display_name = "Toppled Cart"
reference_ids = ["cover_style"]
prompt = "A small toppled wooden hand cart shedding round loaves; strict side view, isolated."
"""


RUNNER_PROPS = runner_props_toml()

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
        chunk_toml("warmup_flat", WIDE_FLAT_ROWS),
        chunk_toml(
            "first_gap",
            GAP28_ROWS,
            difficulty=2,
            extra=(
                '[[segments.chunks.hazards]]\nprop_id = "toppled_cart"\ncolumn = 7\n'
                'anchor = "surface"\n\n' + CART_ARC_PICKUPS + "\n" + ARC_PICKUPS
            ),
        ),
    ]
)


def two_genre_package(
    tmp_path: Path,
    *,
    chunks: str = DEFAULT_CHUNKS,
    gameplay: str = RUNNER_GAMEPLAY,
    avatar: str = RUNNER_AVATAR,
    props: str = RUNNER_PROPS,
) -> Path:
    """Copy the committed two-genre bellweather and swap in this fixture's
    authored runner gameplay and track, so tests control the chunks under
    admission while every other member stays the canonical one."""

    package = tmp_path / "bellweather"
    shutil.copytree(SOURCE_PACKAGE, package)
    runner = package / "runner"
    (runner / "gameplay.toml").write_text(gameplay, encoding="utf-8")
    (runner / "track.toml").write_text(runner_track_toml(chunks), encoding="utf-8")
    (runner / "content" / "avatar.toml").write_text(avatar, encoding="utf-8")
    (runner / "content" / "props.toml").write_text(props, encoding="utf-8")
    (runner / "content" / "items.toml").write_text(RUNNER_ITEMS, encoding="utf-8")
    return package


def runner_only_package(
    tmp_path: Path,
    *,
    avatar: str = RUNNER_AVATAR,
    piloted_heads_tall: float | None = None,
) -> Path:
    """Build the same passing runner closure without any platformer-owned members."""

    source = two_genre_package(tmp_path / "staged", avatar=avatar)
    package = tmp_path / "runner-only"
    package.mkdir()
    shutil.copy2(source / "universe.md", package / "universe.md")
    shutil.copytree(source / "runner", package / "runner")
    references = package / "references"
    references.mkdir()
    for name in ("cover.png", "cover.provenance.json", "cover.visual-review.md"):
        shutil.copy2(source / "references" / name, references / name)

    provenance_sha256 = hashlib.sha256(
        (references / "cover.provenance.json").read_bytes()
    ).hexdigest()
    review_sha256 = hashlib.sha256((references / "cover.visual-review.md").read_bytes()).hexdigest()
    piloted_override = (
        "" if piloted_heads_tall is None else f"piloted_machine = {piloted_heads_tall}\n"
    )
    (package / "game.toml").write_text(
        f'''schema_version = 9
kind = "game-contract-v9"
game_id = "bellweather"
revision = 1
display_name = "Bellweather Runner"

[universe]
source = "universe.md"

[style]
label = "clean chibi storybook fantasy"
keywords = ["high-resolution 2D digital game art", "clean saturated color fields"]
avoid = ["text logos signatures or watermarks"]

[proportion]
heads_tall = 2.25

[proportion.by_body_kind]
human = 2.25
{piloted_override}
[scale]
unit = "player_height"
player_height_tiles = 2.40
minimum = 0.25
steps = [0.25, 0.5, 1.0]

[[genres]]
genre = "runner"

[genres.presentation]
view_profile = "side_view_2d"
gameplay_space = "side_plane"

[genres.presentation.contact_shadows]
enabled = true
opacity = 0.18
softness_screen_pixels = 6.0

[genres.cast]
avatar_id = "wayfarer_sprinter"

[genres.gameplay]
source = "runner/gameplay.toml"

[genres.track]
source = "runner/track.toml"

[genres.content.avatar]
source = "runner/content/avatar.toml"

[genres.content.props]
source = "runner/content/props.toml"

[genres.content.items]
source = "runner/content/items.toml"

[genres.audio]
source = "runner/audio.toml"

[genres.soundtrack]
source = "runner/soundtrack.toml"

[evidence.cover]
artifact_source = "references/cover.png"
artifact_sha256 = "{COVER_SHA256}"
provenance_source = "references/cover.provenance.json"
provenance_sha256 = "{provenance_sha256}"
review_source = "references/cover.visual-review.md"
review_sha256 = "{review_sha256}"

[rights]
status = "redistribution-approved"
basis = ["Original package text and approved AI-generated reference evidence."]
''',
        encoding="utf-8",
    )
    return package


__all__ = [
    "ARC_PICKUPS",
    "CART_ARC_PICKUPS",
    "COVER_SHA256",
    "DEFAULT_CHUNKS",
    "FLAT_ROWS",
    "GAP28_ROWS",
    "GAP_ROWS",
    "RUNNER_AVATAR",
    "RUNNER_AVATAR_NO_SLIDE",
    "RUNNER_GAMEPLAY",
    "RUNNER_GAMEPLAY_NO_DUCK",
    "WIDE_FLAT_ROWS",
    "chunk_toml",
    "runner_only_package",
    "runner_props_toml",
    "two_genre_package",
]
