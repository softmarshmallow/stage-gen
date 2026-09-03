"""A synthetic two-genre package: the committed bellweather platformer plus a
runner member authored entirely in tmp, sharing the cover reference by digest.

Every runner member here is fixture-authored. Bellweather carried a committed
runner member while the genre was being built, and it was retired once Iron
Petal became the canonical runner game - so these tests no longer mirror a
committed closure, they construct the one they mean to test. That is the
better arrangement anyway: a refusal test that depends on a real package's
authoring choices fails for two reasons at once.

The default chunks are compliant with the full `reaction_fair_v1` placement
discipline - apron, separations, landing clearance, press windows, telegraph
arcs - so each refusal test violates exactly one rule on top of a passing
baseline. The arc pickup rows below were computed from the SDK's own
closed forms (launch surface 5, offsets 1..4 of the declared arc).
"""

from __future__ import annotations

import hashlib
import shutil
from io import BytesIO
from pathlib import Path

from PIL import Image


def painted_over_guide(guide: bytes) -> bytes:
    """Repaint every opaque guide cell, the way an admitted painting must.

    A structural-ground guide's colours are registration, never artwork, so a
    provider result still wearing them is refused as a painting that went
    around the guide rather than over it. Fixtures standing in for a provider
    have to paint, not echo. Banding is horizontal on purpose: a synthetic
    material should not assert a projection the test is not about.
    """

    with Image.open(BytesIO(guide)) as opened:
        painted = opened.convert("RGBA")
    alpha = painted.getchannel("A").tobytes()
    body = bytearray(painted.tobytes())
    for index in range(painted.width * painted.height):
        if alpha[index] < 128:
            continue
        band = 30 + (index // painted.width // 7 % 3) * 9
        base = index * 4
        body[base : base + 4] = bytes((18 + band, 96 + band, 120 + band, 255))
    painted = Image.frombytes("RGBA", painted.size, bytes(body))
    output = BytesIO()
    painted.save(output, format="PNG")
    return output.getvalue()


SOURCE_PACKAGE = Path(__file__).resolve().parents[2] / "library" / "games" / "bellweather"

COVER_SHA256 = "e8d27ab2d83210fe2bf8e4f072588614fbe293de75dae51677a96079f1e9f6a5"

RUNNER_GAMEPLAY = """schema_version = 4
kind = "runner-gameplay-v4"
game_id = "bellweather"
revision = 1
track_id = "meadow-dash"

[run]
speed_profile = "steady_runner_v1"
jump_profile = "double_arc_v1"
collision_box = "torso_v1"
duck_profile = "slide_v1"

[run.consequences]
hazard = "drain_v1"
pit = "drain_and_recover_v1"
crush = "end_run_v1"

[run.vitals]
profile = "three_point_v1"
hurt_representation = "blink_v1"

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


def runner_track_toml(chunks: str, *, rows: int = 8, walk_surface_row: int = 5) -> str:
    return f"""schema_version = 4
kind = "runner-track-v4"
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
rows = {rows}
walk_surface_row = {walk_surface_row}

{chunks}
"""


def chunk_toml(
    segment_id: str,
    rows: list[str],
    *,
    difficulty: int = 1,
    role: str | None = None,
    extra: str = "",
) -> str:
    # `role` is a simple key, so it is written before `occupancy` and well
    # before any `extra` sub-table: TOML binds a bare key to whichever table
    # header precedes it.
    role_line = f'role = "{role}"\n' if role is not None else ""
    return f"""[[segments.chunks]]
segment_id = "{segment_id}"
difficulty = {difficulty}
{role_line}occupancy = {occupancy_toml(rows)}
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

RUNNER_AUDIO = """schema_version = 4
kind = "runner-audio-v4"
game_id = "bellweather"
revision = 1

[music.death]
action = "pause"
fade_seconds = 0.6
curve = "exponential"

[music.restart]
action = "resume"
fade_seconds = 0.3
curve = "linear"

[music.hurt]
duck_gain = 0.5
fade_seconds = 0.04
hold_seconds = 0.15
recovery_seconds = 0.5
curve = "linear"

[bindings]
takeoff = "takeoff_whistle"
air_jump = "air_jump_whistle"
land = "soft_landing"
slide = "leaf_slide"
hazard_cleared = "clear_sparkle"
collect = "token_chime"
hurt = "soft_landing"
death = "run_ended"

[[effects]]
effect_id = "takeoff_whistle"
display_name = "Takeoff Whistle"

[effects.realization]
kind = "oscillator_sweep_v1"
waveform = "triangle"
start_frequency_hz = 330
end_frequency_hz = 660
duration_milliseconds = 120
gain = 0.16
strength_pitch_multiplier = 0.0

[[effects]]
effect_id = "air_jump_whistle"
display_name = "Air Jump Whistle"

[effects.realization]
kind = "oscillator_sweep_v1"
waveform = "triangle"
start_frequency_hz = 440
end_frequency_hz = 990
duration_milliseconds = 120
gain = 0.16
strength_pitch_multiplier = 0.0

[[effects]]
effect_id = "soft_landing"
display_name = "Soft Landing"

[effects.realization]
kind = "oscillator_sweep_v1"
waveform = "sine"
start_frequency_hz = 220
end_frequency_hz = 160
duration_milliseconds = 80
gain = 0.12
strength_pitch_multiplier = 0.0

[[effects]]
effect_id = "leaf_slide"
display_name = "Leaf Slide"

[effects.realization]
kind = "oscillator_sweep_v1"
waveform = "sawtooth"
start_frequency_hz = 200
end_frequency_hz = 120
duration_milliseconds = 160
gain = 0.07
strength_pitch_multiplier = 0.0

[[effects]]
effect_id = "clear_sparkle"
display_name = "Clear Sparkle"

[effects.realization]
kind = "oscillator_sweep_v1"
waveform = "sine"
start_frequency_hz = 520
end_frequency_hz = 780
duration_milliseconds = 100
gain = 0.10
strength_pitch_multiplier = 0.0

[[effects]]
effect_id = "token_chime"
display_name = "Token Chime"

[effects.realization]
kind = "oscillator_sweep_v1"
waveform = "sine"
start_frequency_hz = 660
end_frequency_hz = 880
duration_milliseconds = 90
gain = 0.12
strength_pitch_multiplier = 1.0

[[effects]]
effect_id = "run_ended"
display_name = "Run Ended"

[effects.realization]
kind = "generated_clip_v1"
prompt = "heavy wooden cart toppling onto gravel"
duration_seconds = 1.0
gain = 0.5
strength_pitch_multiplier = 0.0
"""

#: The same audio contract with the run-start announcement spoken. Opt-in per
#: test, so the default fixture keeps its provider census and the speech tests
#: pay for exactly one more operation.
RUNNER_AUDIO_SPOKEN = (
    RUNNER_AUDIO.replace("[bindings]\n", '[bindings]\nstage_start = "mira_go"\n', 1)
    + """
[[effects]]
effect_id = "mira_go"
display_name = "Mira: Here We Go"

[effects.realization]
kind = "spoken_line_v1"
text = "[excited][shouting] よーし、いくよーっ!"
voice_id = "mira"
stability = 0.5
max_seconds = 3.0
gain = 0.7
strength_pitch_multiplier = 0.0
"""
)

RUNNER_VOICES = """schema_version = 1
kind = "game-voices-v1"
game_id = "bellweather"
revision = 1

[[voices]]
voice_id = "mira"
display_name = "Mira"
language_code = "ja"
casting = "Eleven-year-old rescue pilot: bright, quick, never breathy."
rights_status = "unreviewed"

[voices.provider]
name = "elevenlabs"
voice = "voice-fixture-7"
verified_on = "2026-09-03"
"""

VOICES_MEMBER_SOURCE = """
[genres.voices]
source = "voices.toml"
"""

RUNNER_SOUNDTRACK = """schema_version = 1
kind = "game-soundtrack-v1"
game_id = "bellweather"
revision = 1

[playback]
selection = "shuffle"
no_immediate_repeat = true

[[tracks]]
track_id = "sunpetal_sprint"
display_name = "Sunpetal Sprint"
creative_brief = "An original bright fantasy runner instrumental, playful and quick."

[tracks.generation]
intent = "generate"
instrumental = true
seamless_loop = true
target_duration_seconds = 90

[[tracks]]
track_id = "orchard_rush"
display_name = "Orchard Rush"
creative_brief = "An original cheerful orchard-run instrumental, warm and lively."

[tracks.generation]
intent = "generate"
instrumental = true
seamless_loop = true
target_duration_seconds = 90
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


#: The runner member appended to the committed platformer container. A TOML
#: array-of-tables entry is position-independent, so appending it declares a
#: second genre without rewriting the container the platformer tests share.
RUNNER_MEMBER = """
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
"""


#: The encounter grid. The default eight-row fixture band cannot hold a salvo
#: AND the avatar: 5 - 3x1.0 leaves two rows where 2.40 + 0.5 are needed, so an
#: encounter authored on it is refused - which is the lane proof working.
#:
#: The band is not merely "taller": the dodge proof bounds it from ABOVE too,
#: because a taller band takes longer to cross and the shot's flight time is
#: fixed. Eleven rows over a walk surface at eight is the band Iron Petal
#: authors and the one `barrage_boss_v1` was tuned against; twelve over nine
#: refuses.
ENCOUNTER_ROWS = 11
ENCOUNTER_WALK_SURFACE_ROW = 8
ENCOUNTER_FLAT = ["0" * 24] * ENCOUNTER_WALK_SURFACE_ROW + ["1" * 24] * (
    ENCOUNTER_ROWS - ENCOUNTER_WALK_SURFACE_ROW
)

ENCOUNTER_BLOCK = """
[encounter]
boss_id = "bramble_harvester"
profile = "barrage_boss_v1"
locomotion = "thrust_v1"
interval_columns = 400
arena_segment_id = "harvest_arena"
boss_projectile_id = "thorn_burst"
player_projectile_id = "spark_pin"
"""

RUNNER_GAMEPLAY_ENCOUNTER = (
    RUNNER_GAMEPLAY.replace('crush = "end_run_v1"', 'crush = "end_run_v1"\nshot = "drain_v1"', 1)
    + ENCOUNTER_BLOCK
)

_FLY_MOTION = "\n".join(
    [
        "[[avatar.motions]]",
        'state = "fly"',
        'playback_mode = "loop"',
        "canonical_frame_indices = [0, 1, 2, 3]",
        "frames_per_second = 12",
        "",
        "[[avatar.motions]]",
        'state = "death"',
    ]
)

RUNNER_AVATAR_FLY = RUNNER_AVATAR.replace('[[avatar.motions]]\nstate = "death"', _FLY_MOTION, 1)

RUNNER_BOSSES = f"""schema_version = 1
kind = "boss-content-v1"
game_id = "bellweather"
revision = 1

[[references]]
reference_id = "cover_style"
source = "references/cover.png"
source_sha256 = "{COVER_SHA256}"
rights_status = "redistribution-approved"
rights_basis = ["AI-generated Bellweather concept cover approved by the authenticated task owner."]

[[bosses]]
boss_id = "bramble_harvester"
display_name = "Bramble Harvester"
body_kind = "overgrown_machine"
height_units = 1.8
reference_ids = ["cover_style"]
prompt = "A stalled harvesting rig wrapped in bramble, hanging in the air on tired lift fans."

[[bosses.motions]]
state = "hover"
playback_mode = "loop"
canonical_frame_indices = [0, 1, 2, 3]
frames_per_second = 10

[[bosses.motions]]
state = "attack"
playback_mode = "once"
canonical_frame_indices = [0, 1, 2, 3]
frames_per_second = 12

[[bosses.motions]]
state = "death"
playback_mode = "once"
canonical_frame_indices = [0, 1, 2, 3]
frames_per_second = 8
"""

RUNNER_PROJECTILES = f"""schema_version = 2
kind = "projectile-content-v2"
game_id = "bellweather"
revision = 1

[[references]]
reference_id = "cover_style"
source = "references/cover.png"
source_sha256 = "{COVER_SHA256}"
rights_status = "redistribution-approved"
rights_basis = ["AI-generated Bellweather concept cover approved by the authenticated task owner."]

[[projectiles]]
projectile_id = "thorn_burst"
display_name = "Thorn Burst"
silhouette = "irregular_v1"
flight = "flat_bolt_v1"
impact = "single_target_v1"
reference_ids = ["cover_style"]
length_units = 0.35
prompt = "A ragged knot of flung bramble seed."

[[projectiles]]
projectile_id = "spark_pin"
display_name = "Spark Pin"
silhouette = "axial_v1"
flight = "flat_bolt_v1"
impact = "single_target_v1"
reference_ids = ["cover_style"]
length_units = 0.30
prompt = "A slim repair pin trailing a bright filament."
"""

BOSS_MEMBER_SOURCE = """
[genres.content.bosses]
source = "runner/content/bosses.toml"
"""

PROJECTILE_MEMBER_SOURCE = """
[genres.content.projectiles]
source = "runner/content/projectiles.toml"
"""


#: A run chunk on the encounter grid, plus the arena the fight is fought over.
#: Deliberately plain: these tests are about the encounter's obligations, not
#: about the placement discipline, which the eight-row chunks already cover.
ENCOUNTER_CHUNKS = "\n".join(
    [
        chunk_toml("harvest_flat", ENCOUNTER_FLAT),
        chunk_toml("harvest_arena", ENCOUNTER_FLAT, role="arena"),
    ]
)


def two_genre_package(
    tmp_path: Path,
    *,
    chunks: str = DEFAULT_CHUNKS,
    gameplay: str = RUNNER_GAMEPLAY,
    avatar: str = RUNNER_AVATAR,
    props: str = RUNNER_PROPS,
    bosses: str | None = None,
    projectiles: str | None = None,
    rows: int = 8,
    walk_surface_row: int = 5,
    spoken: bool = False,
) -> Path:
    """Copy the committed platformer bellweather and author a runner member on
    top of it, so tests control every chunk under admission while the
    platformer-owned members stay the canonical ones. ``spoken`` speaks the
    run-start announcement and binds the voice catalog it resolves through."""

    package = tmp_path / "bellweather"
    shutil.copytree(SOURCE_PACKAGE, package)
    runner = package / "runner"
    (runner / "content").mkdir(parents=True)
    (runner / "audio.toml").write_text(
        RUNNER_AUDIO_SPOKEN if spoken else RUNNER_AUDIO, encoding="utf-8"
    )
    (runner / "soundtrack.toml").write_text(RUNNER_SOUNDTRACK, encoding="utf-8")
    if spoken:
        (package / "voices.toml").write_text(RUNNER_VOICES, encoding="utf-8")
    with (package / "game.toml").open("a", encoding="utf-8") as container:
        container.write(RUNNER_MEMBER)
        if bosses is not None:
            container.write(BOSS_MEMBER_SOURCE)
        if projectiles is not None:
            container.write(PROJECTILE_MEMBER_SOURCE)
        if spoken:
            container.write(VOICES_MEMBER_SOURCE)
    (runner / "gameplay.toml").write_text(gameplay, encoding="utf-8")
    (runner / "track.toml").write_text(
        runner_track_toml(chunks, rows=rows, walk_surface_row=walk_surface_row), encoding="utf-8"
    )
    (runner / "content" / "avatar.toml").write_text(avatar, encoding="utf-8")
    (runner / "content" / "props.toml").write_text(props, encoding="utf-8")
    (runner / "content" / "items.toml").write_text(RUNNER_ITEMS, encoding="utf-8")
    if bosses is not None:
        (runner / "content" / "bosses.toml").write_text(bosses, encoding="utf-8")
    if projectiles is not None:
        (runner / "content" / "projectiles.toml").write_text(projectiles, encoding="utf-8")
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
    "painted_over_guide",
    "runner_only_package",
    "runner_props_toml",
    "two_genre_package",
]
