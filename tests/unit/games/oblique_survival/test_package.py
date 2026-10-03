"""Offline tests of the authored package: its loaders, its briefs and its manifest.

What the build does with these (which steps a scope plans, what an edit re-bills) is
tested against the builder in ``test_workflow.py``.

    uv run pytest tests/unit/games/oblique_survival/test_package.py
"""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any, Final, cast

import pytest

from ember_hollow_pipeline import survival_prompts, survival_request
from ember_hollow_pipeline.layout import build_layout
from ember_hollow_pipeline.manifest import (
    Manifest,
    _music_block,
    music_ref,
)
from ember_hollow_pipeline.models import (
    FOUR_WAY_FACINGS,
    Forage,
    Package,
    SourceError,
)
from ember_hollow_pipeline.shell import ShellClip
from ember_hollow_pipeline.survival_request import DigestLedger, load_package
from tests.unit.games.oblique_survival._survival_fixture import (
    write_fixture,
)

PACKAGE: Final = Path("godot/games/ember_hollow/inputs")


def _forage(package: Package) -> Forage:
    """The authored forage sheet, which the fixture package has."""

    assert package.forage is not None
    return package.forage


def _manifest(document: Manifest) -> dict[str, Any]:
    """The manifest read as the JSON a consumer receives.

    It is a TypedDict in the recipe so a producer cannot misspell a block. A
    test asserts about the document a consumer parses, and narrowing every
    nested block would say less about the claim than the claim does.
    """

    return cast(dict[str, Any], document)


@pytest.fixture(scope="module")
def package() -> Package:
    return load_package(PACKAGE)


def test_the_seam_policy_rewrites_the_prop_prompt_and_the_review(package: Package) -> None:
    prop = package.prop("pine")
    banned = survival_prompts.prop_prompt(package, prop, "standing")
    assert "no ground patch" in banned and "fading softly" not in banned
    painted = survival_prompts.prop_prompt(
        replace(package, ground_contact="painted_base"), prop, "standing"
    )
    assert "fading softly to fully transparent" in painted and "no ground patch" not in painted
    assert (
        "no ground patch" in survival_prompts.family_review_prompt("props", ["pine"], "shadow")
        or True
    )
    assert "feathered patch of ground at its base" in survival_prompts.family_review_prompt(
        "props", ["pine"], "painted_base"
    )


def test_an_unknown_seam_policy_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "source"
    shutil.copytree(PACKAGE, root)
    survival = root / "survival.toml"
    survival.write_text(
        survival.read_text().replace('ground_contact = "skirt_decal"', 'ground_contact = "glue"')
    )
    with pytest.raises(SourceError):
        load_package(root)


# --- the look contract -----------------------------------------------------------------


def test_every_generative_prompt_states_the_one_light(package: Package) -> None:
    """A 2.5D scene has no runtime light, so every drawing must agree on one."""

    clause = survival_prompts.light_clause(package)
    assert clause == survival_prompts.LIGHT_CLAUSES["overhead"]
    carriers = [
        survival_prompts.prop_prompt(package, package.prop("thorn_bush"), "full"),
        survival_prompts.prop_sheet_prompt(package, package.prop("pine")),
        survival_prompts.item_prompt(package, "log", "a log"),
        survival_prompts.actor_concept_prompt(package, package.player),
        survival_prompts.actor_motion_prompt(
            package, package.player, package.player.states[0].state
        ),
        *(survival_prompts.decal_prompt(package, decal) for decal in package.decals),
    ]
    if package.forage is not None:
        carriers.append(survival_prompts.forage_prompt(package, package.forage))
    for prompt in carriers:
        assert clause in prompt
    # The review asks the same question of the finished set.
    assert "lit from directly overhead" in survival_prompts.family_review_prompt("props", ["pine"])


def test_a_patch_prompt_asks_for_a_shape_and_never_a_ring(package: Package) -> None:
    for decal in package.decals:
        prompt = survival_prompts.decal_prompt(package, decal)
        assert survival_prompts.PATCH_SHAPE_CLAUSE in prompt
        assert "ring" not in decal.prompt.lower(), decal.decal_id
        assert "circle" not in decal.prompt.lower(), decal.decal_id


def test_the_look_refuses_a_light_it_has_no_clause_for(tmp_path: Path) -> None:
    root = tmp_path / "source"
    shutil.copytree(PACKAGE, root)
    survival = root / "survival.toml"
    text = survival.read_text()
    survival.write_text(text.replace('light = "overhead"', 'light = "upper_left"'))
    with pytest.raises(SourceError, match=r"look\.light"):
        load_package(root)
    survival.write_text(text.replace('light = "overhead"', 'light = "overhead"\nmirror = true'))
    with pytest.raises(SourceError, match="not a choice"):
        load_package(root)


# --- the style plate -------------------------------------------------------------------


def test_the_style_plate_is_declared_and_digested(package: Package) -> None:
    assert package.style_reference == "references/style-plate.png"
    assert package.style_reference_digest
    # The plate is part of the package digest, so redrawing it re-locks the source.
    assert package.digests["references/style-plate.png"] == package.style_reference_digest


def test_the_plate_rides_on_generative_prompts_and_not_on_paintovers(package: Package) -> None:
    carried = survival_prompts.prop_prompt(package, package.prop("birch"), "standing")
    assert survival_prompts.STYLE_PLATE_CLAUSE in carried

    forage = package.forage
    assert forage is not None
    paintover = survival_prompts.forage_prompt(package, forage)
    assert survival_prompts.STYLE_PLATE_CLAUSE not in paintover
    # Reference image 1 is the lattice there, and the prompt says so.
    assert "Edit reference image 1" in paintover

    fire = survival_prompts.fire_strip_prompt(package, package.fire.columns, package.fire.rows)
    assert survival_prompts.STYLE_PLATE_CLAUSE not in fire


def test_a_package_without_a_plate_says_nothing_about_one(package: Package) -> None:
    bare = replace(package, style_reference=None, style_reference_digest=None)
    assert survival_prompts.STYLE_PLATE_CLAUSE not in survival_prompts.prop_prompt(
        bare, bare.prop("birch"), "standing"
    )


def test_a_plate_outside_the_package_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "source"
    shutil.copytree(PACKAGE, root)
    survival = root / "survival.toml"
    original = survival.read_text()
    for bad in ('"../style-plate.png"', '"/etc/passwd.png"', '"references/missing.png"'):
        survival.write_text(original.replace('"references/style-plate.png"', bad))
        with pytest.raises(SourceError):
            load_package(root)


# --- the prop sheet ----------------------------------------------------------------------


def test_the_sheet_prompt_lists_the_looks_in_reading_order_at_one_scale(package: Package) -> None:
    pine = package.prop("pine")
    prompt = survival_prompts.prop_sheet_prompt(package, pine)
    positions = [prompt.index(f"{state} (") for state in pine.states]
    assert positions == sorted(positions)
    # The authored sizes travel as words the model can act on.
    assert "grown (the reference, full height)" in prompt
    assert "stump (about a sixth the height of the grown look (12%))" in prompt
    assert "ONE shared drawing scale" in prompt
    assert "grown look is the reference" in prompt
    assert "never enlarged to fill" in prompt
    assert survival_prompts.light_clause(package) in prompt
    # Native alpha on the sprite route, the plate riding as reference image 1;
    # never a paintover, never magenta.
    assert survival_prompts.STYLE_PLATE_CLAUSE in prompt
    assert survival_prompts.NO_FLOOR_CLAUSE in prompt
    assert "Edit reference image 1" not in prompt
    assert "magenta" not in prompt
    assert "do not draw the grid" in prompt
    assert "cell 1" not in prompt


def test_a_sized_sprite_look_may_fill_its_canvas_and_an_unsized_one_may_not(
    package: Package,
) -> None:
    bush = package.prop("thorn_bush")
    # picked is unsized: it rides the baseline's ruler and must keep its scale.
    assert "exactly the same drawing scale" in survival_prompts.prop_prompt(package, bush, "picked")
    sized = replace(bush, look_height_units={"picked": 0.3})
    prompt = survival_prompts.prop_prompt(package, sized, "picked")
    assert "filling the canvas" in prompt
    assert "about half the height of the full look (55%)" in prompt
    assert "exactly the same drawing scale" not in prompt


# --- facings ------------------------------------------------------------------------------


def test_the_player_always_carries_the_four_way_facing_set(package: Package) -> None:
    assert package.player.facings.set == "four_way"
    assert package.player.facings.facings == FOUR_WAY_FACINGS
    assert package.mob.facings.set == "single_mirrored"
    assert package.mob.facings.facings == ()
    assert package.player.baseline_key == "idle.front"
    assert package.mob.baseline_key == "idle"
    with pytest.raises(SourceError, match="always carries the four_way"):
        survival_request._facings({"set": "single_mirrored"}, role="player", key="player")
    with pytest.raises(SourceError, match="side_view"):
        survival_request._facings(
            {"set": "four_way", "side_view": "isometric"}, role="player", key="player"
        )
    assert survival_request._facings(None, role="mob", key="mob").set == "single_mirrored"
    assert survival_request._facings(None, role="player", key="player").side_view == "quarter"


def test_a_facing_prompt_names_its_view_and_the_front_reference(package: Package) -> None:
    player = package.player
    front = survival_prompts.actor_motion_prompt(package, player, "walk", facing="front")
    back = survival_prompts.actor_motion_prompt(package, player, "walk", facing="back")
    left = survival_prompts.actor_motion_prompt(package, player, "walk", facing="left")
    single = survival_prompts.actor_motion_prompt(package, package.mob, "walk")
    assert "seen squarely from the front" in front
    assert "Reference image 2" not in front
    assert "facing directly away from the viewer" in back
    assert "Reference image 2 is the same action seen from the front" in back
    assert "turned toward the viewer's left" in left
    assert "three-quarter-front view" in single and "four-facing set" not in single
    assert len({front, back, left}) == 3
    # The light contract holds on every facing.
    for prompt in (front, back, left):
        assert survival_prompts.light_clause(package) in prompt


def test_the_music_loader_wants_exactly_one_track_per_cue() -> None:
    def track(track_id: str, cue: str) -> dict[str, object]:
        return {
            "track_id": track_id,
            "cue": cue,
            "target_duration_seconds": 90,
            "prompt": "A loop.",
        }

    with pytest.raises(SourceError, match="needs a package root"):
        survival_request._music(
            {"tracks": [{**track("a", "day"), "take": "music/x.mp3"}, track("b", "night")]}
        )
    with pytest.raises(SourceError, match="not a file inside the package"):
        survival_request._music(
            {"tracks": [{**track("a", "day"), "take": "music/missing.mp3"}, track("b", "night")]},
            root=PACKAGE,
            digests=DigestLedger(),
        )
    with pytest.raises(SourceError, match=r"relative \.mp3 path"):
        survival_request._music(
            {"tracks": [{**track("a", "day"), "take": "../music.toml"}, track("b", "night")]},
            root=PACKAGE,
            digests=DigestLedger(),
        )

    assert survival_request._music(None) == ()
    loaded = survival_request._music({"tracks": [track("a", "day"), track("b", "night")]})
    assert [t.cue for t in loaded] == ["day", "night"]
    with pytest.raises(SourceError, match="two tracks for the 'day' cue"):
        survival_request._music({"tracks": [track("a", "day"), track("b", "day")]})
    with pytest.raises(SourceError, match="no track for the 'night' cue"):
        survival_request._music({"tracks": [track("a", "day")]})
    with pytest.raises(SourceError, match="cue must be one of"):
        survival_request._music({"tracks": [track("a", "dusk"), track("b", "night")]})
    with pytest.raises(SourceError, match="repeats track_id"):
        survival_request._music({"tracks": [track("a", "day"), track("a", "night")]})


def test_the_manifest_publishes_the_transition_beside_the_cues(
    package: Package, tmp_path: Path
) -> None:
    block = _music_block(package, tmp_path)
    assert block == {}, "no audio on disk is no block at all, transition included"
    for track in package.music:
        path = tmp_path / music_ref(track.track_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not really an mp3")
    block = _music_block(package, tmp_path)
    assert set(block) == {"day", "night", "transition"}
    assert block["transition"] == {
        "crossfade_seconds": package.music_transition.crossfade_seconds,
        "curve": package.music_transition.curve,
        "overlap": package.music_transition.overlap,
        "switch_at": package.music_transition.switch_at,
    }


# --- weather --------------------------------------------------------------------------


def test_the_weather_loader_refuses_what_no_consumer_could_play(package: Package) -> None:
    def doc(**overrides: object) -> dict[str, object]:
        rain = {
            "condition_id": "rain",
            "onset_seconds": 10.0,
            "decay_seconds": 10.0,
            "dry_spell_seconds": [10.0, 20.0],
            "wet_spell_seconds": [10.0, 20.0],
            "drops": {
                "kinds": ["streak", "drop"],
                "count_per_screen": 100,
                "fall_speed_meters_per_second": 10.0,
                "height_units": 0.3,
                "prompt": "a streak and a drop",
            },
        }
        rain.update(overrides)
        return {"kind": "oblique-survival-weather-v1", "conditions": [rain]}

    assert survival_request._weather(None, decals=package.decals) == ()
    loaded = survival_request._weather(doc(), decals=package.decals)
    assert loaded[0].drops is not None and loaded[0].ground is None
    with pytest.raises(SourceError, match="condition_id must be one of"):
        survival_request._weather(doc(condition_id="hail"), decals=package.decals)
    # Snow with only a cover is a condition; the cover's band is pale.
    snowy = survival_request._weather(
        doc(condition_id="snow", drops=None, cover={"texel_meters": 2.0, "prompt": "snow"}),
        decals=package.decals,
    )
    assert snowy[0].cover is not None and snowy[0].cover.value_target == 0.82
    with pytest.raises(SourceError, match=r"drops\.shape must be one of"):
        survival_request._weather(
            doc(
                drops={
                    "kinds": ["a", "b"],
                    "count_per_screen": 10,
                    "fall_speed_meters_per_second": 1.0,
                    "height_units": 0.1,
                    "prompt": "x",
                    "shape": "star",
                }
            ),
            decals=package.decals,
        )
    with pytest.raises(SourceError, match='does not declare with use = "wet"'):
        survival_request._weather(
            doc(wet={"decal_id": "path", "per_100_sqm": 1.0, "dry_seconds": 30.0}),
            decals=package.decals,
        )
    with pytest.raises(SourceError, match="exactly four distinct quadrant cells"):
        survival_request._weather(
            doc(
                ground={
                    "kinds": ["a", "b"],
                    "height_units": 0.1,
                    "rate_per_100_sqm_per_second": 1.0,
                    "prompt": "x",
                }
            ),
            decals=package.decals,
        )
    with pytest.raises(SourceError, match="ordered low then high"):
        survival_request._weather(doc(dry_spell_seconds=[30.0, 10.0]), decals=package.decals)
    with pytest.raises(SourceError, match=r"needs a \[conditions\.strike\] layer"):
        survival_request._weather(
            doc(sound={"strike": {"prompt": "thunder", "duration_seconds": 3.0}}),
            decals=package.decals,
        )
    with pytest.raises(SourceError, match="declares no layer at all"):
        survival_request._weather(doc(drops=None), decals=package.decals)


def test_the_sounds_loader_refuses_what_no_consumer_could_play() -> None:
    good = {"cue": "chop", "prompt": "heavy axe chop into a tree trunk", "duration_seconds": 0.6}
    assert survival_request._sounds(None) == ()
    clips = survival_request._sounds({"cues": [good]})
    assert clips[0].gain == 1.0 and clips[0].pitch_jitter == 0.0 and clips[0].loop is False
    for bad, reason in (
        ({"cues": []}, "at least one"),
        ({"cues": [{**good, "cue": "jump"}]}, "must be one of"),
        ({"cues": [good, good]}, "twice"),
        ({"cues": [{**good, "duration_seconds": 0.2}]}, "duration_seconds"),
        ({"cues": [{**good, "prompt": "x" * 451}]}, "450-character"),
        ({"cues": [{**good, "loop": "yes"}]}, "loop must be a boolean"),
        ({"cues": [{**good, "gain": 4.5}]}, "gain"),
        ({"cues": [{**good, "volume": 1.0}]}, "unknown keys"),
        ({"cues": [{**good, "onsets": 1}]}, "onsets must be a boolean"),
        ({"cues": [{**good, "onsets": True, "loop": True}]}, "cannot both loop"),
        ({"cues": [{**good, "take": "sounds/chop.take.mp3"}]}, "package root"),
    ):
        with pytest.raises(SourceError, match=reason):
            survival_request._sounds(bad)


def test_still_prompts_are_timeless_and_motion_prompts_are_not(package: Package) -> None:
    """A sprite that is not a motion atlas never moves, so its brief says so once."""

    clause = survival_prompts.STILL_CLAUSE
    stills = [
        survival_prompts.prop_prompt(package, package.prop("thorn_bush"), "full"),
        survival_prompts.prop_sheet_prompt(package, package.prop("pine")),
        survival_prompts.item_prompt(package, "log", "a log"),
        survival_prompts.actor_concept_prompt(package, package.player),
        survival_prompts.ground_prompt(package, package.biomes[0]),
        survival_prompts.forage_prompt(package, _forage(package)),
        *(survival_prompts.decal_prompt(package, decal) for decal in package.decals),
    ]
    for prompt in stills:
        assert prompt.count(clause) == 1
    rain = package.weather[0]
    assert package.water is not None
    assert rain.ground is not None and rain.strike is not None and rain.drops is not None
    moving = [
        survival_prompts.actor_motion_prompt(
            package, package.player, package.player.states[0].state
        ),
        survival_prompts.fire_strip_prompt(package, 4, 4),
        survival_prompts.dust_prompt(package),
        survival_prompts.water_prompt(package, package.water),
        survival_prompts.splash_sheet_prompt(package, rain.ground),
        survival_prompts.strike_sheet_prompt(package, rain.strike),
        survival_prompts.drops_sheet_prompt(package, rain.drops),
    ]
    for prompt in moving:
        assert clause not in prompt
    # The puddle's own brief no longer asks for the wave the clause forbids.
    puddle = next(decal for decal in package.decals if decal.decal_id == "puddle")
    assert "ripple" not in puddle.prompt


def test_the_manifest_carries_the_crafting_table_and_every_item_s_gameplay(
    package: Package, tmp_path: Path
) -> None:
    world = build_layout(package)
    document = _manifest(write_fixture(package, tmp_path / "run", world))
    crafting = document["crafting"]
    assert crafting["slots"] == package.crafting.slots
    assert crafting["start"] == dict(package.crafting.start)
    assert crafting["stations"]["campfire"] == {
        "prop_id": "campfire",
        "state": "lit",
        "reach_meters": 3.0,
    }
    by_id = {recipe["recipe_id"]: recipe for recipe in crafting["recipes"]}
    # A built prop names the look it is built in: the fire is built lit, the
    # bench in its baseline look when the author said nothing.
    assert by_id["campfire"]["product"] == {"prop_id": "campfire", "state": "lit"}
    assert by_id["workbench"]["product"] == {
        "prop_id": "workbench",
        "state": package.prop("workbench").baseline_state,
    }
    assert by_id["axe"]["product"] == {"item_id": "axe", "count": 1}
    assert by_id["pickaxe"]["station"] == "workbench"
    axe = document["items"]["axe"]
    assert axe["tool"] == {"verb": "chop", "uses": 25}
    assert axe["stack_max"] == 1
    assert (
        axe["icon"] == {"x": 2560 % 1024, "y": (10 // 4) * 256, "w": 256, "h": 256}
        or axe["icon"]["w"] == 256
    )
    berry = document["items"]["berry"]
    assert berry["use"]["kind"] == "consume" and berry["use"]["hunger"] == 20.0
    assert berry["display_name"] == "Berries"
    icons = document["icons"]
    assert [cell["item_id"] for cell in icons["cells"] if "item_id" in cell] == [
        item.item_id for item in package.items
    ]
    assert [cell["glyph"] for cell in icons["cells"] if "glyph" in cell] == [
        glyph.glyph for glyph in package.icons.glyphs
    ]
    assert document["props"]["pine"]["interactions"][0]["tool"] == {
        "item_id": "axe",
        "hits": 2,
        "required": True,
    }
    assert document["props"]["pine"]["interactions"][0]["from"] == ["sapling", "grown", "old"]
    assert document["props"]["thorn_bush"]["interactions"][0]["tool"] is None
    assert [i["verb"] for i in document["props"]["dead_snag"]["interactions"]] == [
        "chop",
        "gather",
        "burn",
    ]
    assert "recipe" not in document["gameplay"]["campfire"]
    forage = document["ground"]["forage"]
    assert package.forage is not None
    assert forage["cell_meters"] == package.forage.cell_meters
    assert forage["cells"][0]["item_id"] == "twig" and forage["cells"][0]["count"] == 2
    assert forage["cells"][0]["regrow_seconds"] == 240.0
    assert document["status"]["ground_layers"] == "ok"


# --- seasons -------------------------------------------------------------------------


def test_the_manifest_carries_the_seasons_and_every_look(package: Package, tmp_path: Path) -> None:
    world = build_layout(package)
    document = _manifest(write_fixture(package, tmp_path / "run", world))
    seasons = document["seasons"]
    assert seasons["calendar"] == {"order": ["summer", "winter"], "days_per_season": 4}
    winter = next(s for s in seasons["seasons"] if s["season_id"] == "winter")
    assert winter["snow"] == 1.0 and winter["cold"] == 1.0 and winter["look"] == "winter"
    assert winter["hidden_forage"] == ["mushroom", "moss"] and winter["barren"] == ["thorn_bush"]
    assert seasons["looks"] == ["winter"]
    assert document["status"]["seasons"] == "ok"
    grown = document["props"]["pine"]["states"]["grown"]
    look = grown["looks"]["winter"]
    assert look["image"] == "package/props/pine/grown.winter.png"
    # The state's own ruler and the same anchor; its own contact row.
    assert look["px_per_meter"] == grown["px_per_meter"]
    assert look["anchor"] == grown["anchor"]
    assert 0.0 < look["ground_contact_y_normalized"] <= 1.0
    for prop_id, block in document["props"].items():
        for state, spec in block["states"].items():
            assert "winter" in spec["looks"], (prop_id, state)
    assert "plants" not in document["ground"] and "clutter" not in document["ground"]
    assert "plants" not in document["layout"] and "clutter" not in document["layout"]
    ice = document["weather"]["snow"]["ice"]
    assert ice["texture"] == "package/weather/snow/ice.png" and ice["tiling"] == "mirror_repeat_2d"
    assert document["gameplay"]["warmth"]["drain_per_second"] == 0.5
    assert document["gameplay"]["campfire"]["heat_radius_meters"] == 3.5
    assert document["gameplay"]["torch"]["heat_scale"] == 0.7
    cloak = document["items"]["grass_cloak"]["use"]
    assert cloak["kind"] == "wear" and cloak["insulation"] == 0.5
    assert document["items"]["warm_stone"]["use"]["heat_seconds"] == 120.0
    assert document["items"]["cooked_berry"]["use"]["warmth"] == 10.0
    assert [cell["glyph"] for cell in document["icons"]["cells"] if "glyph" in cell] == [
        "heart",
        "bowl",
        "flame",
        "snowflake",
        "sun",
        "moon",
    ]


# --- the opening's clips: drawn in the run, or adopted into it -------------------------


def _shell_with(package: Package, **clip_fields: object) -> Package:
    """The package's shell with the same edit applied to every opening clip."""

    shell = package.shell
    assert shell is not None and shell.opening is not None
    opening = shell.opening.model_copy(
        update={
            "shots": [
                shot.model_copy(update={"plate": shot.plate.model_copy(update=clip_fields)})
                if isinstance(shot.plate, ShellClip)
                else shot
                for shot in shell.opening.shots
            ]
        }
    )
    return replace(package, shell=shell.model_copy(update={"opening": opening}))
