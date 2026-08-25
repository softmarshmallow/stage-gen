"""The resident render profile: how a village NPC is drawn, as opposed to how a player is.

The village shipped by reusing the mob pipeline wholesale. A resident was a mob: a three-view
turnaround, then a four-frame side-view idle strip, held to the mob facing review and the mob
grid contract. That got a village onto the screen quickly and it was the wrong shape for what a
resident actually is, in three separate ways that only became visible once one was standing in
front of the player.

*Three of the four frames were never drawn to the screen.* The runtime constructs a resident on
frame zero and never calls `play` - villagers are still by design. The strip was paid for at four
cells across a 2400x800 sheet, and three quarters of it was discarded at load: the resident the
player actually saw was one 600x800 cell.

*The one frame that was kept showed a person in profile.* A side-view strip is authored to
`REQUIRED_SIDE_VIEW_FACING`, so a townsperson faced the right-hand edge of the screen while the
player stood in front of them talking. The runtime then mirrored that sprite whenever the player
walked past, so a shopkeeper turned their back on approach from one side.

*A resident had no way to be doing anything.* Their whole art direction was `body_plan` and
`brief` - what they are and what they look like. Four aproned humans differing only in palette is
the roster this produced, and the schema could not express "the baker is holding bread".

So residents get their own render profile rather than a flag on the mob one. A still is a single
drawn cell, it faces the viewer, and it may carry a stance and something in its hands - both
chosen from the closed vocabulary in `components.game_contract.vocabulary`, so the roster's
poses are reviewed words rather than whatever prose a model wrote that afternoon.

Everything the player keeps, a still resident keeps: the build gate still applies, and the head-
matched scale reference is still measured, because a resident drawn at the wrong build renders at
the wrong height whether or not it animates. What a still does not keep is the side-facing review
and the fixed-side-view frame-symmetry check, and neither is a relaxation - a front view has no
left/right facing to be wrong about, and a single cell has no second frame to compare against.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar, Self, cast

from pydantic import Field, model_validator

from stage_gen.components.game_contract import (
    EMPTY_HANDED_PROP,
    GameVocabulary,
)
from stage_gen.recipes.scrolling_preview.village import (
    VILLAGE_NPC_COUNT,
    VILLAGE_SPEC_SCHEMA_NAME,
    VillageNpc,
    VillageSpec,
)

#: Structured-output schema name for a game-directed roster. A new name rather than a new
#: version of the undirected one, because the two are generated under different rules and a run
#: holds exactly one of them: an undirected run's `village_spec_<tag>.json` must keep parsing
#: byte-for-byte as what it was.
DIRECTED_VILLAGE_SPEC_SCHEMA_NAME = "scrolling_preview_directed_village_v1"

#: Stance a resident takes when a game has turned poses off. The vocabulary's plainest entry:
#: standing straight, weight even, arms down.
NEUTRAL_STANCE = "standing_at_ease"


class DirectedVillageNpc(VillageNpc):
    """One resident of a game-directed village, posed and holding something.

    The three added fields are identifiers from a closed vocabulary, not prose, and that is the
    whole point of them. `body_kind` decides the resident's build - the game's proportion table
    is keyed on it - and supplies the anatomy sentence the image model is actually drawn from;
    `stance` and `holding` decide what the resident is doing. A model answering this schema
    picks from an enum, so it cannot invent a pose the prompt builder has no wording for.
    """

    body_kind: str = Field(min_length=1)
    stance: str = Field(min_length=1)
    holding: str = Field(min_length=1)


class DirectedVillageSpec(VillageSpec):
    """A village bible written under an authored game contract."""

    npcs: Sequence[DirectedVillageNpc] = Field(
        min_length=VILLAGE_NPC_COUNT, max_length=VILLAGE_NPC_COUNT
    )

    # `body_kind` names the anatomy from a reviewed list and the prompt builder renders that
    # list's own sentence, so the prose no longer has to carry a noun. See the field's comment
    # on `VillageSpec`.
    _body_plan_carries_anatomy: ClassVar[bool] = False

    @model_validator(mode="after")
    def validate_directed_roster(self) -> Self:
        """Reject a directed roster whose residents are indistinguishable in what they do.

        Body kinds are deliberately *not* required to differ: a village of four humans is an
        ordinary village, and forcing four different species onto a market square produces a
        menagerie rather than a town. What must differ is the pair of a stance and a held prop -
        two residents in the same pose holding the same thing are the repeated-NPC failure this
        roster schema exists to prevent, wearing different clothes.
        """

        signatures = [(npc.stance, npc.holding) for npc in self.npcs]
        if len(set(signatures)) != len(signatures):
            raise ValueError(
                "village npcs must differ in stance or held prop; two residents in the same pose "
                "holding the same thing read as one resident drawn twice"
            )
        return self


def village_spec_shape(*, directed: bool) -> tuple[type[VillageSpec], str]:
    """The roster model and structured-output schema name a run of this kind writes and reads.

    One function rather than a hard-coded model at each site, because three sites need this
    answer and each one that got it wrong failed silently in a different way: the executor's
    reader would have dropped every resident's pose, the manifest's reader dropped the whole
    village from a run that reported ten green stages, and the cache validator made the roster
    permanently un-resumable so nine images regenerated on every run.

    A declared village bible is not optional at its readers: a missing file or a parse failure is
    invalid authored output and must raise. Keeping the shape decision in one function prevents a
    directed strip roster from being mistaken for the undirected contract merely because its
    render animation is not a still.
    """

    return (
        (DirectedVillageSpec, DIRECTED_VILLAGE_SPEC_SCHEMA_NAME)
        if directed
        else (VillageSpec, VILLAGE_SPEC_SCHEMA_NAME)
    )


def validate_directed_roster_vocabulary(
    spec: DirectedVillageSpec,
    vocabulary: GameVocabulary,
) -> None:
    """Hold every identifier on a directed roster to the approved vocabulary.

    Separate from the pydantic validators for the same reason `GameContract.validate_against` is:
    the vocabulary is a packaged file, and a model that read it during validation could not be
    constructed in a test without it. The structured-output schema already carries these as enums,
    so in a live run this is a second, independent check on a value a provider has already been
    constrained to - which is exactly the belt the recipe applies everywhere else.
    """

    for index, npc in enumerate(spec.npcs):
        body = vocabulary.body(npc.body_kind)
        if not body.people:
            raise ValueError(
                f"npcs[{index}].body_kind {npc.body_kind!r} is not a body a village resident has"
            )
        vocabulary.stance(npc.stance)
        vocabulary.prop(npc.holding)


def directed_village_spec_json_schema(
    vocabulary: GameVocabulary,
    *,
    allow_pose: bool,
    allow_held_prop: bool,
) -> dict[str, object]:
    """Build the roster schema with the vocabulary inlined as enums.

    A game that has turned poses or props off narrows the enum to a single member rather than
    dropping the field. Keeping the shape fixed means one model, one manifest projection and one
    prompt builder regardless of what a game allows, and a one-member enum states the intent to
    the provider more plainly than an absent field does - "everyone stands at ease" rather than
    "decide for yourself".
    """

    schema = DirectedVillageSpec.model_json_schema()
    definitions = cast(dict[str, Any], schema.get("$defs", {}))
    npc_schema = cast(dict[str, Any], definitions[DirectedVillageNpc.__name__])
    properties = cast(dict[str, Any], npc_schema["properties"])
    _apply_enum(properties, "body_kind", vocabulary.people_body_kinds)
    _apply_enum(
        properties,
        "stance",
        vocabulary.stance_names if allow_pose else (NEUTRAL_STANCE,),
    )
    _apply_enum(
        properties,
        "holding",
        vocabulary.prop_names if allow_held_prop else (EMPTY_HANDED_PROP,),
    )
    return schema


def _apply_enum(properties: dict[str, Any], field: str, values: tuple[str, ...]) -> None:
    if not values:
        raise ValueError(f"{field} vocabulary must offer at least one value")
    entry = cast(dict[str, Any], properties[field])
    # `minLength` is dropped rather than kept alongside the enum. A strict provider schema that
    # carries both a closed enum and a string constraint is describing the same restriction
    # twice, and the enum is the one that means something here.
    entry.pop("minLength", None)
    entry["enum"] = list(values)


def resident_still_subject(
    npc: DirectedVillageNpc,
    *,
    vocabulary: GameVocabulary,
) -> str:
    """Describe one still resident to the prompt builder, anatomy and action included.

    The order is anatomy, then identity, then what they are doing, and it is the order the
    silhouette is built in. An image model given "Village resident Elowen, herbalist" draws a
    generic figure and then decorates it; given the body first it draws that body. The role label
    travels because a trade puts an apron or a satchel into the outline where a name puts
    nothing, and the stance and prop travel as the vocabulary's own sentences rather than as
    their identifiers - `leaning_on_counter` is a key, "standing with one forearm resting on a
    waist-high counter edge" is a pose.
    """

    body = vocabulary.body(npc.body_kind)
    stance = vocabulary.stance(npc.stance)
    action = stance.direction
    if npc.holding != EMPTY_HANDED_PROP:
        action = f"{action}, {vocabulary.prop(npc.holding).direction}"
    return (
        f"{body.anatomy}. This is {npc.name}, {npc.role_label}: {npc.body_plan}. "
        f"{npc.brief} They are {action}."
    )


__all__ = [
    "DIRECTED_VILLAGE_SPEC_SCHEMA_NAME",
    "NEUTRAL_STANCE",
    "DirectedVillageNpc",
    "DirectedVillageSpec",
    "directed_village_spec_json_schema",
    "village_spec_shape",
    "resident_still_subject",
    "validate_directed_roster_vocabulary",
]
