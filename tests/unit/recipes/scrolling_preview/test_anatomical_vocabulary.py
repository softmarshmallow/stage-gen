"""The mob body-plan rule must accept anatomy written the way anatomy is written.

`ANATOMICAL_NOUNS` is named for nouns and was populated almost entirely with adjectives -
`legged`, `winged`, `limbed`, `armed`, `headed`, `tailed`, `horned`, `antlered`, `insectoid` -
with none of the plain forms beside them. There is no stemming in the check: `anatomical_tokens`
lowercases and strips punctuation and nothing else, so `legs` and `legged` are unrelated strings.

A live `world-spec` run failed all six provider attempts on the plan pinned below, which is an
unambiguous description of a drawable creature and matched nothing in the list. The rule was
right and its vocabulary was wrong - the same defect, in the same list, that the first live
village hit from the other direction when it had no word for a human.
"""

from __future__ import annotations

import pytest

from stage_gen.recipes.scrolling_preview.models import (
    ANATOMICAL_NOUNS,
    WorldSpec,
    anatomical_tokens,
)


def _names_a_body(plan: str) -> bool:
    return bool(ANATOMICAL_NOUNS & set(anatomical_tokens(plan)))


#: The exact plans a live run returned for the "whimsical storybook fantasy" concept. Pinned
#: verbatim rather than paraphrased: the point is that a real model, answering a real schema,
#: writes anatomy this way.
LIVE_BODY_PLANS = (
    "Tiny bipedal plant with a radish-shaped torso, two root legs, leaf arms, and a "
    "three-leaf crown.",
    "Lightweight aerial insect with a segmented body, six legs, two antennae, and four broad "
    "petal-like wings.",
    "Low quadruped with a domed shell, short clawed legs, retractable neck, and curled lizard "
    "tail.",
    "Tall digitigrade bird with two stilt legs, a pear-shaped feathered torso, vestigial wings, "
    "and a long hooked beak.",
    "Limbless serpentine mammal with a flexible furred body, shovel snout, whiskers, and a "
    "corkscrew tail.",
    "Massive hexapod ungulate with four load-bearing legs, two smaller grasping forelimbs, "
    "branching antlers, and a barrel chest.",
    "Animated hollow stone golem with a squat turret torso, two columnar arms, two arched legs, "
    "and a floating bell-shaped head.",
    "Great winged dragon with four legs, two independent membrane wings, a long neck, horned "
    "skull, and serpentine tail.",
)


@pytest.mark.parametrize("plan", LIVE_BODY_PLANS)
def test_a_body_plan_a_real_model_wrote_names_a_body(plan: str) -> None:
    assert _names_a_body(plan), plan


@pytest.mark.parametrize(
    ("adjective", "noun"),
    [
        ("legged", "legs"),
        ("winged", "wings"),
        ("limbed", "limbs"),
        ("armed", "arms"),
        ("headed", "head"),
        ("tailed", "tail"),
        ("horned", "horns"),
        ("insectoid", "insect"),
        ("tentacled", "tentacles"),
        ("carapaced", "exoskeleton"),
    ],
)
def test_both_the_adjective_and_the_plain_noun_are_recognised(adjective: str, noun: str) -> None:
    # The gap was one-sided: every adjective was present and none of the nouns were. Asserting
    # both directions keeps a future edit from reopening it on either side.
    assert adjective in ANATOMICAL_NOUNS
    assert noun in ANATOMICAL_NOUNS


@pytest.mark.parametrize(
    "plan",
    [
        "a mysterious presence of gathering dread",
        "the village baker, well liked by everyone",
        "an ominous shape at the edge of the lantern light",
        "something old and patient",
        "a rumour given form",
    ],
)
def test_prose_about_mood_or_profession_still_names_no_body(plan: str) -> None:
    # The widening must not retire the rule. Every one of these is a plan an image model cannot
    # draw a silhouette from, which is the whole reason the check exists.
    assert not _names_a_body(plan)


def test_body_alone_is_not_a_body_plan() -> None:
    # Deliberately excluded. It appears in almost any phrase, including the vague masses above,
    # so admitting it would retire the check rather than repair it.
    assert "body" not in ANATOMICAL_NOUNS
    assert "bodies" not in ANATOMICAL_NOUNS
    assert not _names_a_body("a body of gathering shadow")


def test_the_rule_is_enforced_where_it_matters() -> None:
    # The vocabulary is only worth anything because `WorldSpec` rejects a roster that misses it.
    payload = {
        "world": {"name": "Vale", "one_liner": "A quiet ruin.", "narrative": "Rain falls."},
        "mobs": [
            {"tier_label": "t1", "body_plan": "a rumour given form", "name": "M", "brief": "b"}
        ],
        "obstacles": [
            {
                "sheet_theme": "ruins",
                "props": [{"name": f"p{i}", "brief": "b"} for i in range(8)],
            }
        ],
        "items": [{"kind": f"kind-{i}", "name": f"i{i}", "brief": "b"} for i in range(8)],
        "layers": [
            {
                "id": "backdrop",
                "title": "Backdrop",
                "z_index": 0,
                "parallax": 0.0,
                "opaque": True,
                "paint_region": "full",
                "description": "d",
            },
            {
                "id": "near",
                "title": "Near",
                "z_index": 1,
                "parallax": 1.8,
                "opaque": False,
                "paint_region": "lower",
                "description": "d",
            },
        ],
    }
    with pytest.raises(ValueError, match="must contain an anatomical noun"):
        WorldSpec.model_validate(payload)
