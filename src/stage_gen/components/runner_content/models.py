"""The runner's avatar catalog: exactly one runtime actor, minimally obligated.

`player-content-v3` is deliberately not reused despite already knowing "run":
it requires `equipment` and `dialogue_art`, obligations of the platformer and
dialogue families that a runner avatar owes nobody. This catalog carries the
shared drawn-actor blocks (reference binding, motion playback) and the closed
runner motion set, and nothing else. One actor may be either one visible
character or one machine with its rider visibly aboard; in the latter case all
silhouette, proportion, collision, duck, and motion-rebase facts describe the
combined rider-and-machine figure. Obstacles and pickups reuse the platformer's
`prop-content-v2` and `item-content-v2` verbatim.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    GAME_ID_PATTERN,
    SNAKE_ID_PATTERN,
    canonical_contract_json,
    normalized_text,
    parse_toml_contract,
    sha256_bytes,
    unique_values,
)
from stage_gen.components.actor_content import (
    ContentReference,
    MotionPresentation,
    validate_motion_states,
    validate_reference_closure,
)
from stage_gen.components.sideview_actor.motion_geometry import DEFAULT_MOTION_ATLAS_GEOMETRY

RUNNER_AVATAR_SCHEMA_VERSION = 3

#: The one canonical motion-state order every runner surface derives from:
#: node ids and rebase plate bands in the recipe, and the runtime's own copy,
#: all follow this tuple. `slide` sits between the verbs and the ending so the
#: three states shipped before it keep their relative order, and `hurt` sits
#: after it for the same reason.
RUNNER_MOTION_ORDER: tuple[str, ...] = ("run", "jump", "slide", "hurt", "death")

#: The states every runner avatar owes regardless of its track: the avatar
#: always runs, the base verb is jump, and a run that cannot be survived ends.
#: `slide` is owed only by a gameplay contract that declares a duck profile,
#: and `hurt` only by one that declares `hurt_representation = "drawn_v1"` -
#: the required set is a function of what the member declares, so a runner
#: with no overhead hazards never pays for a strip it cannot use, and a
#: package whose hits are shown by the contracted blink never pays for a pose
#: no consequence plays.
RUNNER_AVATAR_BASE_MOTION_STATES = frozenset({"run", "jump", "death"})

#: The closed vocabulary a runner avatar may be drawn in.
RUNNER_AVATAR_MOTION_STATES = frozenset(RUNNER_MOTION_ORDER)


def declared_motion_states(avatar: RunnerAvatar) -> tuple[str, ...]:
    """The avatar's declared states in the canonical order."""

    declared = {entry.state for entry in avatar.motions}
    return tuple(state for state in RUNNER_MOTION_ORDER if state in declared)


class RunnerAvatar(PersistedContractModel):
    """One visible runner actor and the basis used to measure its whole silhouette.

    ``age`` is the chronological age of the visible person: the character for
    ``single_character_v1`` and the rider for ``visible_rider_machine_v1``. It
    is intentionally honest rather than an adult-content proxy. A piloted
    machine remains one runtime actor, never a rider plus a separately spawned
    machine; its ``body_kind`` selects the package-level proportion override
    measured in visible rider heads.
    """

    avatar_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    display_name: str
    body_kind: str
    age: int = Field(ge=0, le=130)
    silhouette_mode: Literal["single_character_v1", "visible_rider_machine_v1"]
    proportion_basis: Literal["character_head_v1", "visible_rider_head_v1"]
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    prompt: str
    motions: list[MotionPresentation] = Field(min_length=1)

    @field_validator("display_name", "body_kind")
    @classmethod
    def validate_scalar_text(cls, value: str, info: ValidationInfo) -> str:
        return normalized_text(value, f"avatar {info.field_name}")

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return normalized_text(value, "avatar prompt", multiline=True)

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "avatar reference_ids")
        return value

    @model_validator(mode="after")
    def validate_motions(self) -> RunnerAvatar:
        if self.silhouette_mode == "visible_rider_machine_v1":
            if self.body_kind != "piloted_machine":
                raise ValueError("visible_rider_machine_v1 requires body_kind piloted_machine")
            if self.proportion_basis != "visible_rider_head_v1":
                raise ValueError(
                    "visible_rider_machine_v1 requires proportion_basis visible_rider_head_v1"
                )
        else:
            if self.body_kind == "piloted_machine":
                raise ValueError("single_character_v1 requires a non-piloted body_kind")
            if self.proportion_basis != "character_head_v1":
                raise ValueError("single_character_v1 requires proportion_basis character_head_v1")
        validate_motion_states(
            self.motions,
            allowed_states=set(RUNNER_AVATAR_MOTION_STATES),
            label="avatar",
        )
        missing = sorted(RUNNER_AVATAR_BASE_MOTION_STATES - {entry.state for entry in self.motions})
        if missing:
            raise ValueError("avatar is missing required motion states: " + ", ".join(missing))
        # The runner's runtime plays every state as a timeline and refuses
        # anything else, so the same shape is refused HERE, before a package
        # bills its whole graph and publishes a manifest no consumer opens:
        # run loops, every other state plays once, and each declares a rate
        # and stays inside the fixed motion-atlas column count.
        geometry_columns = DEFAULT_MOTION_ATLAS_GEOMETRY.columns
        for entry in self.motions:
            expected_mode = "loop" if entry.state == "run" else "once"
            if entry.playback_mode != expected_mode:
                raise ValueError(
                    f"avatar {entry.state} motion must play {expected_mode}; "
                    f"the runner runtime refuses {entry.playback_mode}"
                )
            if entry.frames_per_second is None:
                raise ValueError(f"avatar {entry.state} motion must declare frames_per_second")
            outside = [
                index for index in entry.canonical_frame_indices if index >= geometry_columns
            ]
            if outside:
                raise ValueError(
                    f"avatar {entry.state} motion names frame {outside[0]} outside the "
                    f"{geometry_columns}-column runner atlas"
                )
        return self


class RunnerAvatarCatalog(PersistedContractModel):
    schema_version: Literal[3]
    kind: Literal["runner-avatar-v3"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    references: list[ContentReference] = Field(min_length=1, max_length=16)
    avatar: RunnerAvatar

    @model_validator(mode="after")
    def validate_closure(self) -> RunnerAvatarCatalog:
        validate_reference_closure(self.references, [self.avatar])
        return self


def load_runner_avatar_bytes(data: bytes) -> RunnerAvatarCatalog:
    return parse_toml_contract(data, model=RunnerAvatarCatalog, label="runner avatar catalog")


def canonical_runner_avatar_json(catalog: RunnerAvatarCatalog) -> bytes:
    return canonical_contract_json(catalog)


def runner_avatar_sha256(catalog: RunnerAvatarCatalog) -> str:
    return sha256_bytes(canonical_runner_avatar_json(catalog))


__all__ = [
    "RUNNER_AVATAR_BASE_MOTION_STATES",
    "RUNNER_AVATAR_MOTION_STATES",
    "RUNNER_AVATAR_SCHEMA_VERSION",
    "RUNNER_MOTION_ORDER",
    "RunnerAvatar",
    "RunnerAvatarCatalog",
    "canonical_runner_avatar_json",
    "declared_motion_states",
    "load_runner_avatar_bytes",
    "runner_avatar_sha256",
]
