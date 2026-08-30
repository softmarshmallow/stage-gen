"""The point-and-click room contract: an authored text IR for one puzzle room.

A room is a composition document, not code: the author declares the scene, the
hotspots, the items, and the interaction graph, and the system supplies the
vocabulary — verbs, effects, and the deterministic machinery that proves the
room can be finished before anything is generated or played. Generation fills
in art and narration only; puzzle logic never comes from a model.

This is the recipe's whole gameplay vocabulary on purpose. A verb or effect a
room cannot express here is a system change, landed at this declared taxonomy
path (``2d/roomview/pointclick``), never smuggled in through prompt text.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from gnode import PersistedContractModel

POINTCLICK_ROOM_SCHEMA_VERSION = 1
POINTCLICK_ROOM_KIND = "pointclick-room-v1"

SNAKE_ID = Annotated[
    str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", min_length=1, max_length=64)
]
BRIEF = Annotated[str, StringConstraints(min_length=1, max_length=2_000)]
LABEL = Annotated[str, StringConstraints(min_length=1, max_length=96)]

#: The closed verb vocabulary. ``inspect`` reads; ``use`` acts, optionally with
#: a held item. Two verbs are the whole grammar on purpose — Machinarium-class
#: rooms need no more, and a small grammar keeps solvability decidable at a
#: glance.
Verb = Literal["inspect", "use"]


class SceneDeclaration(PersistedContractModel):
    brief: BRIEF
    width: int = Field(default=1280, ge=640, le=1920)
    height: int = Field(default=720, ge=360, le=1080)


class RoomStyle(PersistedContractModel):
    label: LABEL
    keywords: list[LABEL] = Field(default_factory=list)
    avoid: list[LABEL] = Field(default_factory=list)


class HotspotRegion(PersistedContractModel):
    """Normalized rectangle: placement for a sprite, hit area either way."""

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_bounds(self) -> HotspotRegion:
        if self.x + self.w > 1.0 + 1e-9 or self.y + self.h > 1.0 + 1e-9:
            raise ValueError("hotspot region must stay inside the scene")
        return self


class Hotspot(PersistedContractModel):
    hotspot_id: SNAKE_ID
    label: LABEL
    #: ``sprite`` hotspots get their own generated transparent object placed at
    #: the region; ``scenery`` hotspots are painted into the backdrop and carry
    #: a hit area only.
    art: Literal["sprite", "scenery"] = "sprite"
    brief: BRIEF
    region: HotspotRegion
    #: A hidden hotspot exists but cannot be seen or clicked until an effect
    #: reveals it.
    hidden: bool = False


class Item(PersistedContractModel):
    item_id: SNAKE_ID
    label: LABEL
    brief: BRIEF


class Effect(PersistedContractModel):
    """Exactly one field set: the closed effect vocabulary."""

    set_flag: SNAKE_ID | None = None
    grant_item: SNAKE_ID | None = None
    remove_item: SNAKE_ID | None = None
    reveal_hotspot: SNAKE_ID | None = None

    @model_validator(mode="after")
    def validate_single(self) -> Effect:
        declared = [
            value
            for value in (self.set_flag, self.grant_item, self.remove_item, self.reveal_hotspot)
            if value is not None
        ]
        if len(declared) != 1:
            raise ValueError("an effect declares exactly one action")
        return self


class Trigger(PersistedContractModel):
    verb: Verb
    hotspot: SNAKE_ID
    #: Only ``use`` may take a held item; ``inspect`` never does.
    item: SNAKE_ID | None = None

    @model_validator(mode="after")
    def validate_verb_item(self) -> Trigger:
        if self.verb == "inspect" and self.item is not None:
            raise ValueError("inspect never takes an item")
        return self


class Interaction(PersistedContractModel):
    """One edge of the puzzle graph: trigger + guards -> effects."""

    on: Trigger
    #: Flags that must already be set for this interaction to be available.
    requires: list[SNAKE_ID] = Field(default_factory=list)
    #: Fires at most once when it has effects; a pure narration line repeats.
    effects: list[Effect] = Field(default_factory=list)
    #: Authored narration; ``None`` asks generation for a line in the room's
    #: voice. Narration is flavor — the puzzle never depends on it.
    narration: BRIEF | None = None


class WinCondition(PersistedContractModel):
    requires: list[SNAKE_ID] = Field(min_length=1)
    narration: BRIEF | None = None


class PointClickRoom(PersistedContractModel):
    schema_version: Literal[1]
    kind: Literal["pointclick-room-v1"]
    room_id: SNAKE_ID
    display_name: LABEL
    revision: int = Field(ge=1)
    style: RoomStyle
    scene: SceneDeclaration
    hotspots: list[Hotspot] = Field(min_length=1)
    items: list[Item] = Field(default_factory=list)
    interactions: list[Interaction] = Field(min_length=1)
    win: WinCondition

    @model_validator(mode="after")
    def validate_references(self) -> PointClickRoom:
        hotspot_ids = [hotspot.hotspot_id for hotspot in self.hotspots]
        item_ids = [item.item_id for item in self.items]
        if len(hotspot_ids) != len(set(hotspot_ids)):
            raise ValueError("hotspot ids must be unique")
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("item ids must be unique")
        known_hotspots = set(hotspot_ids)
        known_items = set(item_ids)
        granted: set[str] = set()
        flags: set[str] = set()
        for interaction in self.interactions:
            if interaction.on.hotspot not in known_hotspots:
                raise ValueError(f"interaction names unknown hotspot {interaction.on.hotspot}")
            if interaction.on.item is not None and interaction.on.item not in known_items:
                raise ValueError(f"interaction names unknown item {interaction.on.item}")
            for effect in interaction.effects:
                if effect.grant_item is not None:
                    if effect.grant_item not in known_items:
                        raise ValueError(f"effect grants unknown item {effect.grant_item}")
                    granted.add(effect.grant_item)
                if effect.remove_item is not None and effect.remove_item not in known_items:
                    raise ValueError(f"effect removes unknown item {effect.remove_item}")
                if (
                    effect.reveal_hotspot is not None
                    and effect.reveal_hotspot not in known_hotspots
                ):
                    raise ValueError(f"effect reveals unknown hotspot {effect.reveal_hotspot}")
                if effect.set_flag is not None:
                    flags.add(effect.set_flag)
        orphan_items = sorted(known_items - granted)
        if orphan_items:
            raise ValueError(
                "items must be obtainable through an effect: " + ", ".join(orphan_items)
            )
        unreachable_flags = sorted(set(self.win.requires) - flags)
        if unreachable_flags:
            raise ValueError(
                "win requires flags no interaction sets: " + ", ".join(unreachable_flags)
            )
        hidden = {hotspot.hotspot_id for hotspot in self.hotspots if hotspot.hidden}
        revealable = {
            effect.reveal_hotspot
            for interaction in self.interactions
            for effect in interaction.effects
            if effect.reveal_hotspot is not None
        }
        unrevealable = sorted(hidden - revealable)
        if unrevealable:
            raise ValueError("hidden hotspots must be revealable: " + ", ".join(unrevealable))
        return self


@dataclass(frozen=True, slots=True)
class RoomState:
    """One node of the reachable state space, canonical and hashable."""

    flags: tuple[str, ...] = ()
    inventory: tuple[str, ...] = ()
    revealed: tuple[str, ...] = ()
    fired: tuple[int, ...] = ()


def _interaction_available(room: PointClickRoom, index: int, state: RoomState) -> bool:
    interaction = room.interactions[index]
    if interaction.effects and index in state.fired:
        return False
    if any(flag not in state.flags for flag in interaction.requires):
        return False
    hotspot = next(h for h in room.hotspots if h.hotspot_id == interaction.on.hotspot)
    if hotspot.hidden and hotspot.hotspot_id not in state.revealed:
        return False
    return not (interaction.on.item is not None and interaction.on.item not in state.inventory)


def _fireable(room: PointClickRoom, state: RoomState) -> list[int]:
    """The interactions a PLAYER can actually fire from this state.

    The runtime dispatches a click to the FIRST available interaction whose
    trigger matches, so two interactions sharing one trigger signature are
    never both reachable at once - the earlier one shadows the later until it
    has fired. The proof searches exactly that machine, not a more permissive
    one, or it would admit rooms no player can finish.
    """

    chosen: dict[tuple[str, str, str | None], int] = {}
    for index in range(len(room.interactions)):
        if not _interaction_available(room, index, state):
            continue
        trigger = room.interactions[index].on
        signature = (trigger.verb, trigger.hotspot, trigger.item)
        if signature not in chosen:
            chosen[signature] = index
    return sorted(chosen.values())


def _apply(room: PointClickRoom, index: int, state: RoomState) -> RoomState:
    interaction = room.interactions[index]
    flags = set(state.flags)
    inventory = set(state.inventory)
    revealed = set(state.revealed)
    for effect in interaction.effects:
        if effect.set_flag is not None:
            flags.add(effect.set_flag)
        if effect.grant_item is not None:
            inventory.add(effect.grant_item)
        if effect.remove_item is not None:
            inventory.discard(effect.remove_item)
        if effect.reveal_hotspot is not None:
            revealed.add(effect.reveal_hotspot)
    fired = set(state.fired)
    if interaction.effects:
        fired.add(index)
    return RoomState(
        flags=tuple(sorted(flags)),
        inventory=tuple(sorted(inventory)),
        revealed=tuple(sorted(revealed)),
        fired=tuple(sorted(fired)),
    )


class RoomSolvabilityReport(PersistedContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["pointclick-solvability-v1"] = "pointclick-solvability-v1"
    solvable: bool
    #: One shortest interaction sequence reaching the win condition, as indices
    #: into ``interactions`` — evidence, not gameplay.
    solution: tuple[int, ...] = ()
    reachable_states: int = Field(ge=1)
    #: Interactions no reachable state can ever fire — dead authoring.
    unreachable_interactions: tuple[int, ...] = ()


def prove_room_solvable(room: PointClickRoom) -> RoomSolvabilityReport:
    """Breadth-first proof over the exact reachable state space.

    The space is tiny by construction (flags, items, and reveals are all
    bounded by the authored document), so the proof is exhaustive rather than
    sampled: a room that cannot be finished is refused before any art is paid
    for, and interactions that can never fire are named.
    """

    start = RoomState()
    seen = {start}
    frontier: deque[tuple[RoomState, tuple[int, ...]]] = deque([(start, ())])
    solution: tuple[int, ...] | None = None
    ever_fired: set[int] = set()
    while frontier:
        state, path = frontier.popleft()
        if solution is None and all(flag in state.flags for flag in room.win.requires):
            solution = path
        for index in _fireable(room, state):
            ever_fired.add(index)
            successor = _apply(room, index, state)
            if successor in seen:
                continue
            seen.add(successor)
            frontier.append((successor, (*path, index)))
    unreachable = tuple(index for index in range(len(room.interactions)) if index not in ever_fired)
    return RoomSolvabilityReport(
        solvable=solution is not None,
        solution=solution or (),
        reachable_states=len(seen),
        unreachable_interactions=unreachable,
    )


__all__ = [
    "POINTCLICK_ROOM_KIND",
    "POINTCLICK_ROOM_SCHEMA_VERSION",
    "Effect",
    "Hotspot",
    "HotspotRegion",
    "Interaction",
    "Item",
    "PointClickRoom",
    "RoomSolvabilityReport",
    "RoomState",
    "RoomStyle",
    "SceneDeclaration",
    "Trigger",
    "Verb",
    "WinCondition",
    "prove_room_solvable",
]
