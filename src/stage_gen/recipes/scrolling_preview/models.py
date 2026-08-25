"""Strict world-design schema for the scrolling-preview recipe."""

from __future__ import annotations

import re
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class WorldHeader(StrictModel):
    name: str = Field(min_length=1)
    one_liner: str = Field(min_length=1)
    narrative: str = Field(min_length=1)


class Mob(StrictModel):
    tier_label: str = Field(min_length=1)
    body_plan: str = Field(min_length=1)
    name: str = Field(min_length=1)
    brief: str = Field(min_length=1)


class ObstacleProp(StrictModel):
    name: str = Field(min_length=1)
    brief: str = Field(min_length=1)


class ObstacleSheet(StrictModel):
    sheet_theme: str = Field(min_length=1)
    props: list[ObstacleProp] = Field(min_length=8, max_length=8)


class Item(StrictModel):
    kind: str = Field(min_length=1)
    name: str = Field(min_length=1)
    brief: str = Field(min_length=1)


class WorldLayer(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    title: str = Field(min_length=1)
    z_index: int = Field(ge=0)
    parallax: float = Field(ge=0, le=2)
    opaque: bool
    paint_region: str = Field(min_length=1)
    description: str = Field(min_length=1)


#: Plain body-part and body-class nouns, unioned into `ANATOMICAL_NOUNS` below.
#:
#: The original list is called nouns and is mostly *adjectives*. It has `legged`, `winged`,
#: `limbed`, `armed`, `headed`, `tailed`, `horned`, `antlered` and `insectoid`, and none of
#: `legs`, `wings`, `limbs`, `arms`, `head`, `tail`, `horns`, `antennae` or `insect`. There is no
#: stemming anywhere in the check - `anatomical_tokens` lowercases and strips punctuation and
#: nothing else - so the two forms are unrelated strings.
#:
#: That makes the rule reject the most natural way to write a body plan. Measured on a live run:
#: "Lightweight aerial insect with a segmented body, six legs, two antennae, and four broad
#: petal-like wings" matched nothing in the list and failed, while the same creature described as
#: "six-legged winged insectoid" would have passed. The `world-spec` stage burned all six provider
#: attempts on it and the run ended with two artifacts on disk.
#:
#: `body` is deliberately absent. It appears in almost any phrase, including the vague masses the
#: rule exists to reject, so admitting it would retire the check rather than repair it.
_BODY_PART_NOUNS = frozenset(
    re.findall(
        r"[a-z]+",
        """leg legs arm arms limb limbs head heads tail tails wing wings
        horn horns antler antlers antenna antennae feeler feelers claw claws talon talons
        paw paws hoof hooves fin fins fang fangs tusk tusks pincer pincers mandible mandibles
        tentacle tentacles tendril tendrils beak snout muzzle torso thorax abdomen exoskeleton
        mane plume ruff insect mammal marsupial ungulate hexapod octopod""",
    )
)

#: Words that name a body: a `body_plan` containing none of them is prose about mood or
#: profession rather than a description an image model can draw a silhouette from. Shared
#: rather than private because the village schema in `village.py` holds its residents to the
#: same rule as the mob roster, and a second copy of this list would drift from this one.
ANATOMICAL_NOUNS = _BODY_PART_NOUNS | frozenset(
    re.findall(
        r"[a-z]+",
        """humanoid biped bipedal quadruped quadrupedal insectoid arachnid spider
        spiderlike serpent serpentine wormlike wyrm snake winged wingless avian bird
        birdlike wormoid aquatic fish fishlike amphibian amphibious reptilian reptile
        lizard skeletal skeleton ape apelike feline cat catlike canine dog wolf centaur
        centauroid golem elemental cephalopod tendrilled tentacled octopoid crustacean
        crab crablike knucklewalker mollusc slug sluglike mite rodent ratlike mantis
        beetle beetlelike lobster horned antlered tailed limbed legged armed headed
        winger drone mech mechanoid android anthropoid saurian draconic dragon dragonoid
        trilobite polyp starfish jelly jellyfish construct automaton shell shelled
        carapaced carapace tank walker hopper swimmer flier flyer bat batlike deer stag owl
        owlish bear fox frog toad monkey primate primatoid scorpion centipede millipede
        crustaceous shrub fungal plantlike treant treelike blob amorphous ooze slime ghost
        ghostly spectral wraith specter phantom spirit spectre""",
    )
)

_ITEM_BUCKETS: tuple[tuple[str, frozenset[str]], ...] = (
    ("currency", frozenset(["token", "coin", "chip", "cred", "credit", "buck", "bit", "yen"])),
    ("vessel", frozenset(["vial", "phial", "flask", "bottle", "ampoule"])),
    ("fragment", frozenset(["shard", "fragment", "piece", "sliver", "chunk"])),
)


def anatomical_tokens(value: str) -> list[str]:
    """Split a phrase into the bare alphabetic words the noun sets are matched against.

    Punctuation, digits and separators are dropped rather than kept, so "six-limbed" and
    "six limbed" both yield "limbed" and a hyphenated body plan is not silently read as
    containing no anatomical noun. Public for the same reason `ANATOMICAL_NOUNS` is: the village
    schema matches residents against the identical token set.
    """

    return [
        cleaned
        for token in re.split(r"[\s\-_/]+", value.lower())
        if (cleaned := re.sub(r"[^a-z]", "", token))
    ]


class WorldSpec(StrictModel):
    world: WorldHeader
    mobs: list[Mob] = Field(min_length=1)
    obstacles: list[ObstacleSheet] = Field(min_length=1)
    items: list[Item] = Field(min_length=8, max_length=8)
    layers: list[WorldLayer] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def validate_cross_field_contract(self) -> Self:
        previous_plan: str | None = None
        for index, mob in enumerate(self.mobs):
            plan = mob.body_plan.strip().lower()
            if plan == previous_plan:
                raise ValueError(
                    f"mobs[{index}].body_plan must differ from mobs[{index - 1}].body_plan"
                )
            if not (ANATOMICAL_NOUNS & set(anatomical_tokens(plan))):
                raise ValueError(
                    f'mobs[{index}].body_plan ("{mob.body_plan}") must contain an anatomical noun'
                )
            previous_plan = plan

        kinds = [item.kind.strip().lower() for item in self.items]
        if len(set(kinds)) != len(kinds):
            raise ValueError("item kinds must be unique")
        for bucket_name, words in _ITEM_BUCKETS:
            hits = [kind for kind in kinds if words & set(anatomical_tokens(kind))]
            if len(hits) > 1:
                raise ValueError(
                    "item kinds must use semantically distinct categories; "
                    f"repeated {bucket_name} noun"
                )

        themes = [sheet.sheet_theme.strip().lower() for sheet in self.obstacles]
        if len(set(themes)) != len(themes):
            raise ValueError("obstacle sheet themes must be unique")

        opaque = [layer for layer in self.layers if layer.opaque]
        if len(opaque) != 1:
            raise ValueError(f"exactly one layer must have opaque=true; got {len(opaque)}")
        if opaque[0].z_index != 0:
            raise ValueError("the opaque layer must have z_index=0")
        if opaque[0].parallax != 0:
            raise ValueError("the opaque layer must have parallax=0")
        return self
