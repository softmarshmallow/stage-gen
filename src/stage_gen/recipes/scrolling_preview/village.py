"""Strict schema and manifest projection for the optional village hub.

The village is a hub *inside* an existing run rather than a second recipe. It reuses that run's
tileset, parallax layers, portal art, items and player, and adds only its residents, their idle
strips and one sheet of settlement fixtures. That is why nothing here extends `WorldSpec`: a run
that gains a village keeps `world_spec_<tag>.json` byte-identical and keeps the same tag, so
every artifact already on disk stays cache-valid and enabling the village costs one structured
call plus nine image calls instead of a regeneration. A `village` field on `WorldSpec` would have
changed the bytes of an artifact every existing run already holds, and invalidated all of them.

Residents are held to the same body-plan discipline the mob roster is held to, against the same
word list. A request for four townsfolk is answered most readily with four interchangeable humans
in differently coloured aprons, and four NPCs that read as one NPC repeated is precisely the
failure this schema exists to make impossible: `body_plan` must name anatomy, and consecutive
plans must differ - the rule `WorldSpec` already applies to mobs, for the same reason.

Dialogue is three fixed lines per resident, and each is capped at 160 characters. The cap is a
layout fact rather than a style preference: the runtime dialogue box is one screen-fixed line
across the bottom of the viewport, and a line that overflows it is a line the player cannot read.

This module stays contract-only - schema, opt-in parsing, and the manifest block. The village
image prompts live beside `_mob_strip_prompt` in `executor.py` because they are required to be
built from the very same private facing and cell-containment directives the mob strips use, and
`executor.py` imports this module; importing it back would close a cycle.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Self

from pydantic import Field, model_validator

from stage_gen.recipes.base import JsonObject
from stage_gen.recipes.scrolling_preview.models import (
    ANATOMICAL_NOUNS,
    StrictModel,
    anatomical_tokens,
)

#: Structured-output schema name for the village bible, versioned like every other persisted
#: contract in this recipe so a later roster shape is a new name rather than a silent change.
VILLAGE_SPEC_SCHEMA_NAME = "scrolling_preview_village_v1"

#: Residents per village. Fixed rather than derived from the spec so both the stage fan-out and
#: the manifest's runtime requirements are statically known, and so enabling the village on an
#: existing run costs a bounded nine image calls: one turnaround and one idle strip per resident,
#: plus the single fixture sheet.
VILLAGE_NPC_COUNT = 4

#: Only current version of the `village` block written into `manifest_<tag>.json`. The runtime
#: reads this block and nothing else about the village. Every resident carries an explicit render
#: profile; a still sliced with an assumed frame count renders silently wrong, so `frames` must be
#: read and old blocks are rejected rather than interpreted.
VILLAGE_MANIFEST_SCHEMA_VERSION = 2

#: Fixtures per village. Exactly the cells of the one 2-row x 4-column fixture sheet: the grid
#: contract rejects an empty cell outright (`scrolling-grid-empty-cell-v1`), so a roster that does
#: not fill the sheet cannot produce a passing asset.
_VILLAGE_FIXTURE_COUNT = 8

#: Ceiling on one spoken line, in characters. See the module docstring: the dialogue box renders
#: one line at a time across the bottom of the viewport.
_VILLAGE_LINE_MAXIMUM = 160

#: People vocabulary the mob word list does not carry, unioned with it for residents only.
#:
#: `ANATOMICAL_NOUNS` was written to keep a *monster* roster from collapsing into vague masses, so
#: it names bodies a bestiary has - `humanoid`, `insectoid`, `draconic`, `carapaced` - and nothing
#: a census has. It contains no `human`, `person`, `man`, `woman`, `child`, `dwarf` or `elf`, and
#: among ordinary animals it happens to hold `deer`, `fox` and `owl` but not `mouse` or `badger`.
#:
#: Asked for four townsfolk, a model answers "elderly human baker" or "stout dwarf smith". Every
#: such answer was rejected, and the first live village burned all six provider attempts on
#: schema validation without ever reaching an image call. The rule was right and its vocabulary
#: was wrong.
#:
#: Widening the shared list instead would have loosened the mob contract, which exists for a
#: different reason and is working. So residents validate against the union and mobs are left
#: exactly as they were.
_RESIDENT_ONLY_NOUNS = frozenset(
    re.findall(
        r"[a-z]+",
        """human person people folk villager townsfolk man woman men women boy girl child
        lad lass elder adult youth crone matron gentleman lady dwarf dwarven elf elven gnome
        halfling hobbit orc goblin fae fairy sprite pixie imp giant troll ogre nymph
        mouse rat badger otter hare rabbit hedgehog squirrel weasel stoat marten mole
        tortoise turtle goat sheep ram pig boar cow ox horse pony donkey mule llama
        crow raven magpie sparrow robin finch wren duck goose swan chicken hen rooster
        moth butterfly bee beetle snail newt salamander""",
    )
)

#: The vocabulary a resident's body plan is checked against.
RESIDENT_BODY_PLAN_NOUNS = ANATOMICAL_NOUNS | _RESIDENT_ONLY_NOUNS

_VILLAGE_OPT_IN: JsonObject = {"schema_version": 1, "kind": "village_hub_v1"}


@dataclass(frozen=True, slots=True)
class VillageRenderProfile:
    """How this run's residents are drawn, as the manifest publishes it.

    One profile for the whole roster rather than one per resident: a run draws its townsfolk one
    way, and a manifest that allowed four different answers would oblige every consumer to
    implement all of them to render any of them.
    """

    frames: int
    orientation: str
    animation: str
    #: The suffix in `npc_<tag>_<i>_<state>.png`, and the `state` a runtime binding carries.
    state: str


#: What a resident is when no game contract directs the run: the original four-frame side-view
#: idle strip. Named rather than inlined so the undirected manifest block is written from the
#: same field set as the directed one.
STRIP_RESIDENT_RENDER = VillageRenderProfile(
    frames=4, orientation="side", animation="strip", state="idle"
)

#: What a resident is under a game contract authored for stills: one forward-facing cell.
STILL_RESIDENT_RENDER = VillageRenderProfile(
    frames=1, orientation="front", animation="still", state="still"
)


class VillageNpc(StrictModel):
    """One resident: who they are, how they are drawn, and the three things they say.

    `body_plan` is separate from `brief` on purpose, and carries the anatomy. `brief` is
    appearance direction for the image model - wardrobe, palette, silhouette detail - and an
    image model will happily answer a brief alone with a generic human, which is how a roster
    collapses into one repeated NPC.
    """

    role_label: str = Field(min_length=1)
    name: str = Field(min_length=1)
    body_plan: str = Field(min_length=1)
    brief: str = Field(min_length=1)
    greeting: str = Field(min_length=1, max_length=_VILLAGE_LINE_MAXIMUM)
    remark: str = Field(min_length=1, max_length=_VILLAGE_LINE_MAXIMUM)
    farewell: str = Field(min_length=1, max_length=_VILLAGE_LINE_MAXIMUM)


class VillageFixture(StrictModel):
    """One cell of the settlement fixture sheet: a stall, a well, a sign, a cart."""

    name: str = Field(min_length=1)
    brief: str = Field(min_length=1)


class VillageSpec(StrictModel):
    """The village bible: everything the village stages and the manifest are generated from."""

    name: str = Field(min_length=1)
    one_liner: str = Field(min_length=1)
    narrative: str = Field(min_length=1)
    fixtures_theme: str = Field(min_length=1)
    # `Sequence` rather than `list` so `DirectedVillageSpec` can narrow the element type. A
    # `list` field is invariant, so a subclass declaring `list[DirectedVillageNpc]` is not a
    # subtype of this one; the JSON schema and the runtime value are identical either way.
    npcs: Sequence[VillageNpc] = Field(min_length=VILLAGE_NPC_COUNT, max_length=VILLAGE_NPC_COUNT)
    fixtures: list[VillageFixture] = Field(
        min_length=_VILLAGE_FIXTURE_COUNT,
        max_length=_VILLAGE_FIXTURE_COUNT,
    )

    #: Whether `body_plan` alone has to carry the resident's anatomy.
    #:
    #: True for an undirected run, where the prose is the only thing that names a body. False for
    #: a world-directed one, where `body_kind` names it from a closed vocabulary that also
    #: supplies the anatomy sentence the image model is given - at which point demanding a noun in
    #: the prose too is a second, weaker copy of a rule already satisfied, and it is precisely the
    #: rule that burned all six provider attempts on the first live village before its word list
    #: was widened.
    _body_plan_carries_anatomy: ClassVar[bool] = True

    @model_validator(mode="after")
    def validate_cross_field_contract(self) -> Self:
        """Reject a roster that would render as one resident repeated four times.

        Every rule here is about distinguishability, which no per-field constraint can express:
        four non-empty names, four non-empty role labels and four non-empty body plans are all
        individually valid while describing the same person four times over. The consecutive
        body-plan rule is the weaker, cheaper half of that check and is deliberately kept
        identical to the mob rule in `WorldSpec` - a generator that has just written "humanoid"
        writes it again far more readily than it repeats it two entries later.

        Fixture names are checked because the fixture sheet's cells are addressed positionally by
        the runtime, and two cells named the same thing make a placement report unreadable.
        """

        names = [npc.name.strip().lower() for npc in self.npcs]
        if len(set(names)) != len(names):
            raise ValueError("village npc names must be unique")

        roles = [npc.role_label.strip().lower() for npc in self.npcs]
        if len(set(roles)) != len(roles):
            raise ValueError("village npc role labels must be unique")

        previous_plan: str | None = None
        for index, npc in enumerate(self.npcs):
            plan = npc.body_plan.strip().lower()
            if plan == previous_plan:
                raise ValueError(
                    f"npcs[{index}].body_plan must differ from npcs[{index - 1}].body_plan"
                )
            if self._body_plan_carries_anatomy and not (
                RESIDENT_BODY_PLAN_NOUNS & set(anatomical_tokens(plan))
            ):
                raise ValueError(
                    f'npcs[{index}].body_plan ("{npc.body_plan}") must name a body: one of the '
                    "recognised people or creature nouns, such as human, dwarf, badger or avian"
                )
            previous_plan = plan

        fixture_names = [fixture.name.strip().lower() for fixture in self.fixtures]
        if len(set(fixture_names)) != len(fixture_names):
            raise ValueError("village fixture names must be unique")
        return self


def parse_village_opt_in(value: object) -> JsonObject:
    """Validate the village opt-in, which carries no options at all.

    Shaped exactly like the style-anchor opt-in and validated exactly as strictly: the object
    exists so that enabling the village is an explicit, versioned request rather than a bare
    boolean, and so a later `village_hub_v2` is a different value rather than a reinterpretation
    of this one. Anything else - a truthy string, a superset with extra keys, a different kind -
    is rejected rather than coerced, because a silently ignored key here would mean a run that
    generated something other than what was asked for.
    """

    if not isinstance(value, Mapping) or dict(value) != _VILLAGE_OPT_IN:
        raise ValueError(
            'scrolling-preview village must equal {"schema_version":1,"kind":"village_hub_v1"}'
        )
    return dict(_VILLAGE_OPT_IN)


def village_enabled(input_value: Mapping[str, Any]) -> bool:
    """Whether a parsed recipe input asked for a village.

    Presence is the whole test: `parse_scrolling_preview_input` has already rejected every value
    the key could hold except the one canonical opt-in, so no caller has to re-validate it.
    """

    return "village" in input_value


def npc_turnaround_subject(npc: VillageNpc) -> str:
    """Describe one resident to the shared turnaround prompt builder.

    The role label travels with the name because it, and not the name, is what makes two
    residents read as different people in a three-view sheet: a trade puts an apron, a satchel or
    a ledger into the silhouette, where a name puts nothing there at all. The body plan follows
    so the anatomy the schema insisted on actually reaches the image model rather than stopping
    at validation.
    """

    return f"Village resident {npc.name}, {npc.role_label}, {npc.body_plan}. {npc.brief}"


def village_manifest_block(
    spec: VillageSpec,
    render: VillageRenderProfile | None = None,
) -> dict[str, object]:
    """Project the bible into the block the web runtime reads.

    Only what the runtime draws or speaks crosses this boundary. `narrative` and every npc
    `brief` and `body_plan` stay behind: they are direction for the image model, already spent by
    the time the artwork exists, and publishing them would invite a consumer to render prompt
    text as if it were content.

    Slots are positional and match the artifact names (`npc_<tag>_<i>_<state>.png`), so the
    manifest entry, the sprite sheet and the runtime placement all agree on which resident is
    which. Lines are emitted as an ordered list rather than three named fields because the
    dialogue box walks them in order and has no reason to know that the middle one is the remark.
    """

    render = render or STRIP_RESIDENT_RENDER

    return {
        "schema_version": VILLAGE_MANIFEST_SCHEMA_VERSION,
        "name": spec.name,
        "one_liner": spec.one_liner,
        "fixtures_theme": spec.fixtures_theme,
        # How the runtime must load and draw a resident, published once for the whole roster
        # because one run draws its residents one way. `frames` is the load-bearing field: the
        # sheet is sliced into this many equal columns, so a wrong value is silently wrong art.
        # `orientation` tells the runtime whether mirroring the sprite toward the player is
        # meaningful - it is for a side view and it is not for a figure already facing out.
        "render": {
            "frames": render.frames,
            "orientation": render.orientation,
            "animation": render.animation,
            "state": render.state,
        },
        "npcs": [
            {
                "slot": slot,
                "name": npc.name,
                "role_label": npc.role_label,
                "lines": [npc.greeting, npc.remark, npc.farewell],
            }
            for slot, npc in enumerate(spec.npcs)
        ],
    }
