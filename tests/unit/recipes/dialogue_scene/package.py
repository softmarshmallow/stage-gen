"""One authored scene package, built on disk, for tests that resolve or plan.

A scene is a directory whose members are bound by exact digest, so tests cannot
hand the resolver a dict any more - the bytes have to exist. This writes the
smallest package that resolves, and returns the document so a test can mutate one
field and assert the refusal.
"""

from __future__ import annotations

import hashlib
import tomllib
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

SECOND_CHARACTER_TOML = """\
schema_version = 1
kind = "character-profile-v1"
profile_id = "ren-hoshino"
revision = 1
display_name = "Ren"
age_years = 41
description = "An original caretaker who locks the seminar building every evening."
visual_identity = "Person of average height with close-cropped grey hair and deep-set brown eyes."
wardrobe = "Olive work jacket over a plain shirt, dark trousers, and a ring of keys."
invariants = [
  "Close-cropped grey hair",
  "Olive work jacket and a ring of keys",
]

# The four drawn faces, authored per actor. The FIRST is the base plate; the rest
# are face-only edits of it, so the resting face leads.

[[expressions]]
expression_id = "gruff"
label = "Gruff"
description = "Composed and attentive, waiting for the other to speak"
direction = "Level unhurried gaze, mouth closed and even, jaw loose."

[[expressions]]
expression_id = "amused"
label = "Amused"
description = "Open delight with bright eyes and an unguarded smile"
direction = "Eyes creased deeply at the corners, a wide slow smile, brows lifted."

[[expressions]]
expression_id = "apologetic"
label = "Apologetic"
description = "Caught out, with the sentence unfinished"
direction = "Eyes moving away, mouth pulled to one side, brows raised unevenly."

[[expressions]]
expression_id = "firm"
label = "Firm"
description = "Focused concern with the brows drawn and the mouth firm"
direction = "Brows drawn low and together, eyes narrowed and steady, mouth pressed closed."

[rights]
status = "unreviewed"
basis = ["Original repository-authored text with no external character reference."]
"""

CHARACTER_TOML = """\
schema_version = 1
kind = "character-profile-v1"
profile_id = "mio-researcher"
revision = 1
display_name = "Mio"
age_years = 23
description = "An original final-year student who keeps the seminar notes."
visual_identity = "Young woman of average height with dark eyes and short black hair."
wardrobe = "Navy cardigan over a white collared shirt and a knee-length grey skirt."
invariants = [
  "Short black hair with a single silver pin",
  "Navy cardigan over a white collared shirt",
]

# The four drawn faces, authored per actor. The FIRST is the base plate; the rest
# are face-only edits of it, so the resting face leads.

[[expressions]]
expression_id = "steady"
label = "Steady"
description = "Composed and attentive, waiting for the other to speak"
direction = "Level gaze toward the listener, lips closed and relaxed, brows even."

[[expressions]]
expression_id = "glad"
label = "Glad"
description = "Open delight with bright eyes and an unguarded smile"
direction = "Eyes bright and creased at the corners, an open unguarded smile, brows lifted."

[[expressions]]
expression_id = "caught"
label = "Caught"
description = "Caught out, with the sentence unfinished"
direction = "Gaze cast aside, mouth caught between a smile and a word, inner brows raised."

[[expressions]]
expression_id = "worried"
label = "Worried"
description = "Focused concern with the brows drawn and the mouth firm"
direction = "Brows drawn together, eyes fixed on the listener, mouth closed and firm."

[rights]
status = "unreviewed"
basis = ["Original repository-authored text with no external character reference."]
"""

SCENARIO_SCRIPT = """\
label opening:
    stage lounge
    "The lamps are still on over the empty seminar table."
    show mio steady at center
    show ren gruff at left
    mio "I hoped you would stay after the seminar."

    menu:
        "Stay a while.":
            jump staying
        "Say you have to go.":
            jump leaving


label staying:
    set stayed
    mio glad "Then sit. The notes will keep."
    ren firm "I will be locking up at seven regardless."
    jump closing


label leaving:
    mio caught "Of course. I did not mean to keep you."
    ren apologetic "The east door is already bolted, for what it is worth."
    jump closing


label closing:
    if stayed:
        jump ending_stayed

    jump ending_left


label ending_stayed:
    mio worried "Next week, then. Same table."
    ren amused "Next week."
    hide mio
    hide ren
    end stayed_late


label ending_left:
    hide mio
    hide ren
    end went_home
"""


SECOND_SCENARIO_SCRIPT = """\
label night:
    stage corridor
    "The corridor lights click off one bank at a time."
    show mio steady at center
    mio "You are still here."
    show ren firm at left
    ren "So are you."
    jump lounge_again


label lounge_again:
    stage lounge
    mio glad "The table is warmer than the corridor."
    hide mio
    hide ren
    end locked_up
"""


def second_scenario_toml(*, script_sha256: str) -> str:
    """A second beat of the same episode: same cast, one shared stage, one new one.

    The shared `lounge` declaration is byte-identical to the first scenario's on
    purpose - that is the case the union has to collapse to one backdrop node.
    """

    return f'''\
schema_version = 2
kind = "scenario-v2"
game_id = "seminar_hall"
scenario_id = "late_shift"
display_name = "The Late Shift"
revision = 1
script = "scenarios/late_shift.scenario"
script_sha256 = "{script_sha256}"
entry = "night"

[[cast]]
actor_id = "mio"
display_name = "Mio"
expressions = ["steady", "glad", "caught", "worried"]

[[cast]]
actor_id = "ren"
display_name = "Ren"
expressions = ["gruff", "amused", "apologetic", "firm"]

[[stages]]
stage_id = "lounge"
brief = "An original empty evening study lounge, warm lamps, no people"

[[stages]]
stage_id = "corridor"
brief = "An original empty tiled corridor at night, half the lights already off"

[[endings]]
outcome_id = "locked_up"
label = "You were locked in together"
'''


def scenario_toml(*, script_sha256: str) -> str:
    return f'''\
schema_version = 2
kind = "scenario-v2"
game_id = "seminar_hall"
scenario_id = "after_seminar"
display_name = "After the Seminar"
revision = 1
script = "scenarios/after_seminar.scenario"
script_sha256 = "{script_sha256}"
entry = "opening"

[[cast]]
actor_id = "mio"
display_name = "Mio"
expressions = ["steady", "glad", "caught", "worried"]

[[cast]]
actor_id = "ren"
display_name = "Ren"
expressions = ["gruff", "amused", "apologetic", "firm"]

[[stages]]
stage_id = "lounge"
brief = "An original empty evening study lounge, warm lamps, no people"

[[flags]]
flag_id = "stayed"

[[endings]]
outcome_id = "stayed_late"
label = "You stayed"

[[endings]]
outcome_id = "went_home"
label = "You left"
'''


def cover_png(*, landscape: bool = False) -> bytes:
    """A deterministic stand-in for the authored style plate.

    ``landscape`` gives a 16:9 establishing shot instead of a portrait canvas. A
    style plate is a reference for medium, palette and light, not a canvas
    anything is composited onto, so both shapes are legitimate art direction and
    the pipeline has to carry either.
    """

    size = (2048, 1152) if landscape else (1024, 1536)
    output = BytesIO()
    Image.new("RGB", size, (40, 60, 110)).save(output, format="PNG")
    return output.getvalue()


def write_scene_package(
    root: Path,
    *,
    second_scenario: bool = False,
    landscape_plate: bool = False,
    **overrides: object,
) -> Path:
    """Write a resolvable package under ``root`` and return that directory.

    ``second_scenario`` binds a second beat of the same episode, which shares both
    actors and one of its two stages with the first. It is what the de-duplication
    tests plan: the union must add one backdrop, not a second copy of everything.
    """

    root.mkdir(parents=True, exist_ok=True)
    (root / "references").mkdir(exist_ok=True)
    (root / "scenarios").mkdir(exist_ok=True)
    (root / "characters").mkdir(exist_ok=True)
    character_bytes = CHARACTER_TOML.encode("utf-8")
    (root / "characters/mio.toml").write_bytes(character_bytes)
    second_bytes = SECOND_CHARACTER_TOML.encode("utf-8")
    (root / "characters/ren.toml").write_bytes(second_bytes)
    cover = cover_png(landscape=landscape_plate)
    (root / "references/cover.png").write_bytes(cover)
    script_bytes = SCENARIO_SCRIPT.encode("utf-8")
    (root / "scenarios/after_seminar.scenario").write_bytes(script_bytes)
    scenario_bytes = scenario_toml(script_sha256=hashlib.sha256(script_bytes).hexdigest()).encode(
        "utf-8"
    )
    (root / "scenarios/after_seminar.toml").write_bytes(scenario_bytes)
    catalog = (
        'schema_version = 1\nkind = "scenario-catalog-v1"\ngame_id = "seminar_hall"\n'
        'revision = 1\n\n[[scenarios]]\nscenario_id = "after_seminar"\n'
    )
    second_scenario_sha256: str | None = None
    if second_scenario:
        second_script = SECOND_SCENARIO_SCRIPT.encode("utf-8")
        (root / "scenarios/late_shift.scenario").write_bytes(second_script)
        second_scenario_bytes = second_scenario_toml(
            script_sha256=hashlib.sha256(second_script).hexdigest()
        ).encode("utf-8")
        (root / "scenarios/late_shift.toml").write_bytes(second_scenario_bytes)
        second_scenario_sha256 = hashlib.sha256(second_scenario_bytes).hexdigest()
        catalog += '\n[[scenarios]]\nscenario_id = "late_shift"\n'
    (root / "scenarios/index.toml").write_text(catalog, encoding="utf-8")
    document = scene_value(
        character_sha256=hashlib.sha256(character_bytes).hexdigest(),
        second_sha256=hashlib.sha256(second_bytes).hexdigest(),
        cover_sha256=hashlib.sha256(cover).hexdigest(),
        scenario_sha256=hashlib.sha256(scenario_bytes).hexdigest(),
        second_scenario_sha256=second_scenario_sha256,
        **overrides,
    )
    (root / "scene.toml").write_text(_to_toml(document), encoding="utf-8")
    (root / "ui.toml").write_text(
        ui_toml(cover_sha256=hashlib.sha256(cover).hexdigest()), encoding="utf-8"
    )
    return root


def ui_toml(*, cover_sha256: str) -> str:
    """The scene's screen-fixed interface contract, drawn against the same plate."""

    return f"""\
schema_version = 4
kind = "game-ui-v4"
game_id = "seminar_hall"
revision = 1

[[references]]
reference_id = "cover"
source = "references/cover.png"
source_sha256 = "{cover_sha256}"
rights_status = "unreviewed"
rights_basis = ["Original brand-neutral test fixture."]

[panel_frame]
layout = "nine_slice_panel_1024_v1"
alpha_policy = "transparent_exterior_opaque_body_v1"
reference_ids = ["cover"]
prompt = "A calm dialogue-box frame in the plate's palette with a slim even border."

[button_rect]
layout = "nine_slice_button_sheet_4x1024_v1"
alpha_policy = "transparent_exterior_opaque_body_v1"
reference_ids = ["cover"]
prompt = "A calm rounded choice button in the plate's palette with a slim even border."

[preview_icons]
layout = "icon_grid_4x4_1024_preview_v1"
alpha_policy = "transparent_exterior_opaque_glyph_v1"
reference_ids = ["cover"]
prompt = "Soft flat glyphs in the plate's palette with a gentle painted edge."
"""


def scene_value(
    *,
    character_sha256: str,
    second_sha256: str,
    cover_sha256: str,
    scenario_sha256: str,
    second_scenario_sha256: str | None = None,
    **overrides: object,
) -> dict[str, Any]:
    """The authored document, as a plain value a test can mutate before parsing."""

    value: dict[str, Any] = {
        "schema_version": 5,
        "kind": "dialogue-scene-v5",
        "game_id": "seminar_hall",
        "display_name": "Seminar Hall",
        "revision": 1,
        "scene_brief": "A student stays behind in the study lounge after a seminar",
        "style_reference_id": "cover",
        "cast": [
            {
                "actor_id": "mio",
                "reference_id": "cover",
                "character_profile": {
                    "schema_version": 1,
                    "kind": "character-profile-binding-v1",
                    "ref": "characters/mio.toml",
                    "source_sha256": character_sha256,
                },
            },
            {
                "actor_id": "ren",
                "character_profile": {
                    "schema_version": 1,
                    "kind": "character-profile-binding-v1",
                    "ref": "characters/ren.toml",
                    "source_sha256": second_sha256,
                },
            },
        ],
        "references": [
            {
                "reference_id": "cover",
                "source": "references/cover.png",
                "source_sha256": cover_sha256,
                "rights_status": "unreviewed",
                "rights_basis": ["Original brand-neutral test fixture."],
            }
        ],
        "scenarios": [
            {
                "schema_version": 1,
                "kind": "scenario-binding-v1",
                "ref": "scenarios/after_seminar.toml",
                "source_sha256": scenario_sha256,
            }
        ],
        "presentation": {"framing_zoom": 70, "source_framing_zoom": 70},
        "transparency_mode": "chroma",
    }
    if second_scenario_sha256 is not None:
        value["scenarios"].append(
            {
                "schema_version": 1,
                "kind": "scenario-binding-v1",
                "ref": "scenarios/late_shift.toml",
                "source_sha256": second_scenario_sha256,
            }
        )
    value.update(overrides)
    return value


def read_scene_value(root: Path) -> dict[str, Any]:
    return tomllib.loads((root / "scene.toml").read_text(encoding="utf-8"))


def _to_toml(value: Any, prefix: str = "") -> str:
    """Just enough TOML for this document shape; tests own no serializer library."""

    scalars: list[str] = []
    tables: list[str] = []
    for key, item in value.items():
        path = f"{prefix}{key}"
        if isinstance(item, dict):
            tables.append(f"\n[{path}]\n{_to_toml(item, f'{path}.')}")
        elif isinstance(item, list) and item and isinstance(item[0], dict):
            tables.extend(f"\n[[{path}]]\n{_to_toml(entry, f'{path}.')}" for entry in item)
        else:
            scalars.append(f"{key} = {_scalar(item)}\n")
    return "".join(scalars) + "".join(tables)


def _scalar(item: Any) -> str:
    if isinstance(item, bool):
        return "true" if item else "false"
    if isinstance(item, int):
        return str(item)
    if isinstance(item, list):
        return "[" + ", ".join(_scalar(entry) for entry in item) + "]"
    escaped = str(item).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
