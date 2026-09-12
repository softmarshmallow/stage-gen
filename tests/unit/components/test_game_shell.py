"""The `game-shell-v3` authored contract, and the refusals that are its point.

Most of these are not shape tests. Each names a decision the contract makes — text is
composited rather than drawn, a typeface is an input, a backdrop is ordered far to near —
and proves the document refuses the authoring that would break it, offline and before any
provider is called.
"""

from __future__ import annotations

from typing import cast

import pytest

from ember_hollow_pipeline.shell import (
    LOADING_SCREEN,
    OPENING_SHOT,
    REDISTRIBUTABLE_FONT_LICENSES,
    SHELL_CANVAS,
    TITLE_SCREEN,
    GameShell,
    LoadingBackdropBinding,
    Rect,
    ShellLayout,
    ShellPlate,
    load_game_shell_bytes,
)
from stage_gen.components._game_input import AuthoredContractLoadError

DIGEST = "a" * 64
FONT_DIGEST = "b" * 64

HEADER = f"""
schema_version = 3
kind = "game-shell-v3"
game_id = "ember-hollow"
revision = 1

[[references]]
reference_id = "cover_style"
source = "references/style-plate.png"
source_sha256 = "{DIGEST}"
rights_status = "redistribution-approved"
rights_basis = ["Digest-bound reviewed package evidence."]

[typeface]
family = "Fredoka"
source = "fonts/fredoka-variable.ttf"
source_sha256 = "{FONT_DIGEST}"
license = "OFL-1.1"
license_source = "fonts/OFL.txt"
copyright = "Copyright 2016 The Fredoka Project Authors"
upstream_source = "google/fonts, ofl/fredoka/Fredoka[wdth,wght].ttf"
retrieved = "2026-08-24"
"""

TITLE = """
[title]
layout = "title_screen_16x9_v1"

[[title.backdrop]]
depth = "far"

[title.backdrop.plate]
mode = "still"
alpha_policy = "fully_opaque_v1"
reference_ids = ["cover_style"]
prompt = "The hollow at dusk, the fire a small warm point among cold blue firs."
"""

OPENING = """
[opening]
layout = "opening_16x9_v1"
skippable = true
music_track = "main_theme"

[[opening.shots]]
shot_id = "the_hollow"
move = "push_in"
seconds = 4.0
card = "Some fires are older than the people who tend them."
out_transition = "dissolve"

[opening.shots.plate]
mode = "still"
alpha_policy = "fully_opaque_v1"
reference_ids = ["cover_style"]
prompt = "A wide cold valley under low cloud, one thread of smoke rising from the trees."
"""


def _load(*sections: str) -> GameShell:
    return load_game_shell_bytes("".join((HEADER, *sections)).encode("utf-8"))


def _refusal(*sections: str) -> str:
    with pytest.raises(AuthoredContractLoadError) as error:
        _load(*sections)
    return str(error.value)


# --- the document parses and says what it holds -------------------------------


def test_a_shell_reports_the_screens_in_the_order_a_player_meets_them() -> None:
    shell = _load(OPENING, TITLE)

    assert shell.screen_names() == ("opening", "title")
    assert shell.opening is not None and shell.opening.seconds == pytest.approx(4.0)
    assert shell.title is not None and shell.title.backdrop[0].depth == "far"


def test_every_declared_plate_is_enumerated_with_the_label_a_refusal_uses() -> None:
    shell = _load(OPENING, TITLE)

    assert [label for label, _ in shell.plates()] == [
        "opening.shots.the_hollow",
        "title.backdrop.far",
    ]


def test_a_title_screen_composites_the_games_own_name() -> None:
    """The name is not in this document: the host takes it from the package."""

    shell = _load(TITLE)

    assert "<display_name>" in shell.composited_text()


def test_a_shell_with_no_screen_is_refused() -> None:
    assert "declares at least one screen" in _refusal()


# --- text is composited, never drawn ------------------------------------------


@pytest.mark.parametrize(
    "phrase",
    [
        "the game's title across the sky",
        "a carved wooden logo above the trees",
        "bold lettering cut into the stone",
        "a banner reading the name of the settlement",
    ],
)
def test_a_prompt_asking_for_lettering_is_refused_offline(phrase: str) -> None:
    section = TITLE.replace(
        "The hollow at dusk, the fire a small warm point among cold blue firs.", phrase
    )

    message = _refusal(section)
    assert "composited by the host" in message


def test_a_prompt_describing_the_frames_layout_is_refused_offline() -> None:
    section = TITLE.replace(
        "The hollow at dusk, the fire a small warm point among cold blue firs.",
        "The valley on the left half and the sky on the right half.",
    )

    assert "the layout owns the geometry" in _refusal(section)


def test_an_ordinary_picture_prompt_is_not_caught_by_the_lettering_rule() -> None:
    section = TITLE.replace(
        "The hollow at dusk, the fire a small warm point among cold blue firs.",
        "A stone lintel above the door, worn smooth, no marks on it.",
    )

    assert _load(section).title is not None


# --- a typeface is an input ---------------------------------------------------


def test_a_shell_that_composites_text_without_a_typeface_is_refused() -> None:
    without = HEADER.split("[typeface]")[0]
    document = (without + TITLE).encode("utf-8")

    with pytest.raises(AuthoredContractLoadError) as error:
        load_game_shell_bytes(document)
    assert "declares no typeface" in str(error.value)


def test_a_typeface_licence_that_does_not_permit_redistribution_is_refused() -> None:
    section = HEADER.replace('license = "OFL-1.1"', 'license = "UFL-1.0"')
    document = (section + TITLE).encode("utf-8")

    with pytest.raises(AuthoredContractLoadError) as error:
        load_game_shell_bytes(document)
    assert "permit redistributing the font file" in str(error.value)


def test_every_licence_this_contract_accepts_is_one_that_permits_redistribution() -> None:
    """A guard on the list itself: widening it is a rights decision, not a convenience."""

    assert REDISTRIBUTABLE_FONT_LICENSES == ("OFL-1.1", "Apache-2.0", "CC0-1.0")


def test_a_typeface_outside_the_fonts_directory_is_refused() -> None:
    section = HEADER.replace(
        'source = "fonts/fredoka-variable.ttf"', 'source = "references/fredoka-variable.ttf"'
    )
    document = (section + TITLE).encode("utf-8")

    with pytest.raises(AuthoredContractLoadError) as error:
        load_game_shell_bytes(document)
    assert "must live under fonts/" in str(error.value)


def test_a_typefaces_licence_text_must_sit_beside_the_face() -> None:
    section = HEADER.replace('license_source = "fonts/OFL.txt"', 'license_source = "OFL.txt"')
    document = (section + TITLE).encode("utf-8")

    with pytest.raises(AuthoredContractLoadError) as error:
        load_game_shell_bytes(document)
    assert "beside the face" in str(error.value)


# --- references and plates ----------------------------------------------------


def test_a_plate_naming_an_undeclared_reference_is_refused() -> None:
    section = TITLE.replace('reference_ids = ["cover_style"]', 'reference_ids = ["nothing_here"]')

    assert "undeclared references" in _refusal(section)


def test_a_backdrop_is_declared_far_to_near() -> None:
    near_first = TITLE.replace('depth = "far"', 'depth = "near"').replace(
        'alpha_policy = "fully_opaque_v1"', 'alpha_policy = "transparent_exterior_v1"'
    )

    assert "starts at its far layer" in _refusal(near_first)


def test_the_far_layer_is_the_picture_and_must_be_opaque() -> None:
    section = TITLE.replace(
        'alpha_policy = "fully_opaque_v1"', 'alpha_policy = "transparent_exterior_v1"'
    )

    assert "must declare fully_opaque_v1" in _refusal(section)


def test_an_emblem_is_a_shape_on_air() -> None:
    section = (
        TITLE
        + """
[title.emblem]
mode = "still"
alpha_policy = "fully_opaque_v1"
reference_ids = ["cover_style"]
prompt = "A pressed-iron ember badge, three sparks over a banked hearth."
"""
    )

    assert "transparent exterior" in _refusal(section)


def test_an_opening_shot_fills_the_screen() -> None:
    section = OPENING.replace(
        'alpha_policy = "fully_opaque_v1"', 'alpha_policy = "transparent_exterior_v1"'
    )

    assert "fully opaque" in _refusal(section)


def test_two_shots_may_not_share_an_id() -> None:
    twice = (
        OPENING
        + """
[[opening.shots]]
shot_id = "the_hollow"
seconds = 2.0

[opening.shots.plate]
mode = "still"
alpha_policy = "fully_opaque_v1"
reference_ids = ["cover_style"]
prompt = "The same valley, closer, the smoke gone."
"""
    )

    assert "shot_id" in _refusal(twice)


# --- the loading screen may cost nothing --------------------------------------


def test_a_loading_backdrop_may_be_bound_to_art_the_run_already_publishes() -> None:
    shell = _load(
        TITLE,
        """
[loading]
layout = "loading_screen_16x9_v1"
tips = ["A banked fire keeps until morning."]

[loading.backdrop]
source = "run_artifact"
artifact_role = "season_look_winter"
""",
    )

    assert shell.loading is not None
    assert isinstance(shell.loading.backdrop, LoadingBackdropBinding)
    # A bound backdrop declares no plate, so it adds nothing to the generated set.
    assert [label for label, _ in shell.plates()] == ["title.backdrop.far"]


def test_a_generated_loading_backdrop_joins_the_generated_set() -> None:
    shell = _load(
        TITLE,
        """
[loading]
layout = "loading_screen_16x9_v1"

[loading.backdrop]
mode = "still"
alpha_policy = "fully_opaque_v1"
reference_ids = ["cover_style"]
prompt = "The hearth close up, embers banked under grey ash."
""",
    )

    assert shell.loading is not None
    assert isinstance(shell.loading.backdrop, ShellPlate)
    assert [label for label, _ in shell.plates()] == [
        "title.backdrop.far",
        "loading.backdrop",
    ]


# --- layout geometry ----------------------------------------------------------


def test_every_shell_layout_reserves_its_regions_inside_one_16x9_canvas() -> None:
    for layout in (TITLE_SCREEN, LOADING_SCREEN, OPENING_SHOT):
        assert layout.canvas == SHELL_CANVAS == (2560, 1440)
        assert layout.region_names()


def test_a_drifting_region_is_measured_over_the_range_the_host_may_move_it() -> None:
    """The title parallaxes, so a region quiet only in the still frame is not quiet."""

    band = TITLE_SCREEN.region("mark_band")
    union = TITLE_SCREEN.drift_union("mark_band")

    assert TITLE_SCREEN.drift == 96
    assert union.width == band.width + 2 * TITLE_SCREEN.drift
    assert union.height == band.height + 2 * TITLE_SCREEN.drift


def test_a_still_screen_measures_the_region_itself() -> None:
    assert LOADING_SCREEN.drift == 0
    assert LOADING_SCREEN.drift_union("status_strip") == LOADING_SCREEN.region("status_strip")


def test_a_drift_union_is_clamped_to_the_canvas() -> None:
    layout = ShellLayout(
        layout="edge_v1",
        reserved=(("edge", Rect(x=0, y=0, width=100, height=100)),),
        drift=32,
    )

    union = layout.drift_union("edge")
    assert (union.x, union.y) == (0, 0)
    assert (union.width, union.height) == (132, 132)


def test_a_region_that_leaves_the_canvas_is_a_broken_layout() -> None:
    with pytest.raises(ValueError, match="leaves the canvas"):
        ShellLayout(
            layout="broken_v1",
            reserved=(("off", Rect(x=2500, y=0, width=400, height=100)),),
        )


def test_the_geometry_record_is_what_the_cache_key_hashes() -> None:
    record = TITLE_SCREEN.geometry_record()

    assert record["layout"] == "title_screen_16x9_v1"
    assert record["drift"] == 96
    reserved = record["reserved"]
    assert isinstance(reserved, list)
    assert [cast(dict[str, object], entry)["region"] for entry in reserved] == [
        "mark_band",
        "control_stack",
    ]


# --- a clip shot: the second thing an opening shot may be ---------------------


CLIP_OPENING = """
[opening]
layout = "opening_16x9_v1"
ending = "cut_to_black"

[[opening.shots]]
shot_id = "the_walk"
seconds = 8.0

[opening.shots.plate]
mode = "clip"
reference_ids = ["cover_style"]
prompt = "The small robot trudges away across an empty snowfield as its chest light dims."
"""


def test_a_clip_shot_is_a_second_kind_of_plate_not_a_flag_on_the_first() -> None:
    shell = _load(CLIP_OPENING)

    assert [label for label, _ in shell.clips()] == ["opening.shots.the_walk"]
    # And it is absent from plates(), which everything downstream joins to a PNG.
    assert shell.plates() == ()
    clip = shell.clips()[0][1]
    assert (clip.mode, clip.draw, clip.take) == ("clip", 1, None)
    # A clip carries no alpha policy: video has no alpha.
    assert not hasattr(clip, "alpha_policy")


def test_a_document_says_which_kind_of_plate_it_means() -> None:
    """``mode`` is required on both branches, so a v1 document is refused by name."""

    assert "mode" in _refusal(CLIP_OPENING.replace('mode = "clip"\n', ""))
    assert "mode" in _refusal(OPENING.replace('mode = "still"\n', ""))


def test_a_clip_shot_is_held_because_it_brings_its_own_camera() -> None:
    moved = CLIP_OPENING.replace("seconds = 8.0", 'move = "push_in"\nseconds = 8.0')
    assert "moves the camera over a clip" in _refusal(moved)
    # The same move over a still is exactly what the host is for.
    assert _load(OPENING).opening is not None


def test_a_clip_names_references_the_document_has_to_declare() -> None:
    """The check reads clips as well as stills, or a clip could name anything."""

    unknown = CLIP_OPENING.replace('["cover_style"]', '["no_such_plate"]')
    assert "names undeclared references ['no_such_plate']" in _refusal(unknown)
    assert dict(_load(CLIP_OPENING).reference_users()) == {
        "opening.shots.the_walk": ("cover_style",)
    }


def test_a_clip_prompt_may_not_ask_for_lettering_either() -> None:
    lettering = CLIP_OPENING.replace("as its chest light dims.", "under the title of the game.")
    assert "shell clip prompt" in _refusal(lettering)


def test_a_draw_is_the_reroll_because_a_video_route_takes_no_seed() -> None:
    assert (
        _load(CLIP_OPENING.replace('mode = "clip"', 'mode = "clip"\ndraw = 3')).clips()[0][1].draw
        == 3
    )
    assert "draw" in _refusal(CLIP_OPENING.replace('mode = "clip"', 'mode = "clip"\ndraw = 0'))


_TAKE = 'take = {{ path = "shell/{name}.take.mp4", sha256 = "{digest}" }}'
_DIGEST = "a" * 64


def test_a_clip_may_name_the_file_instead_of_asking_for_one() -> None:
    """The expensive route's manual gate: draw it outside a run, then link the winner."""

    adopted = _load(
        CLIP_OPENING.replace(
            'mode = "clip"', 'mode = "clip"\n' + _TAKE.format(name="walk", digest=_DIGEST)
        )
    )
    take = adopted.clips()[0][1].take
    assert take is not None
    assert (take.path, take.sha256) == ("shell/walk.take.mp4", _DIGEST)


def test_a_take_stays_inside_the_package_and_is_the_format_the_gate_expects() -> None:
    outside = CLIP_OPENING.replace(
        'mode = "clip"', 'mode = "clip"\n' + _TAKE.format(name="../walk", digest=_DIGEST)
    )
    assert "shell clip take path" in _refusal(outside)
    wrong_format = CLIP_OPENING.replace(
        'mode = "clip"',
        'mode = "clip"\n' + _TAKE.format(name="walk", digest=_DIGEST).replace(".mp4", ".ogv"),
    )
    assert ".mp4" in _refusal(wrong_format)


def test_adopting_a_take_and_asking_for_another_draw_are_contradictory() -> None:
    """A reroll counter asks the route for another clip; an adopted shot asks for none."""

    both = CLIP_OPENING.replace(
        'mode = "clip"',
        'mode = "clip"\ndraw = 2\n' + _TAKE.format(name="walk", digest=_DIGEST),
    )
    assert "cannot also raise draw" in _refusal(both)


# --- how the opening ends -----------------------------------------------------


def test_an_opening_ends_on_a_cut_unless_it_says_otherwise() -> None:
    shell = _load(OPENING)
    assert shell.opening is not None and shell.opening.ending == "cut_to_black"


def test_matching_the_title_needs_a_title_to_match() -> None:
    """The one ending that is a claim about the picture, refused offline without one."""

    matched = CLIP_OPENING.replace('ending = "cut_to_black"', 'ending = "match_title"')
    assert "nothing for its last frame to be measured against" in _refusal(matched)
    # With a title screen declared, the same document is fine.
    assert _load(matched, TITLE).opening is not None


def test_an_ending_outside_the_vocabulary_is_refused() -> None:
    assert "ending" in _refusal(CLIP_OPENING.replace("cut_to_black", "flare_out"))
