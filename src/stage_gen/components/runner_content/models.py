"""The runner's avatar catalog: exactly one drawn character, minimally obligated.

`player-content-v3` is deliberately not reused despite already knowing "run":
it requires `equipment` and `dialogue_art`, obligations of the platformer and
dialogue families that a runner avatar owes nobody. This catalog carries the
shared drawn-actor blocks (reference binding, motion playback) and the closed
runner motion set, and nothing else. Obstacles and pickups reuse the
platformer's `prop-content-v2` and `item-content-v2` verbatim.
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

RUNNER_AVATAR_SCHEMA_VERSION = 1

#: The closed motion vocabulary a runner avatar is drawn in, and every state is
#: required: the avatar always runs, the one verb is jump, and a hit ends the
#: run. A later duck or slide widens this set additively.
RUNNER_AVATAR_MOTION_STATES = frozenset({"run", "jump", "death"})


class RunnerAvatar(PersistedContractModel):
    avatar_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    display_name: str
    body_kind: str
    age: int = Field(ge=18, le=130)
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
        validate_motion_states(
            self.motions,
            allowed_states=set(RUNNER_AVATAR_MOTION_STATES),
            label="avatar",
        )
        missing = sorted(RUNNER_AVATAR_MOTION_STATES - {entry.state for entry in self.motions})
        if missing:
            raise ValueError("avatar is missing required motion states: " + ", ".join(missing))
        return self


class RunnerAvatarCatalog(PersistedContractModel):
    schema_version: Literal[1]
    kind: Literal["runner-avatar-v1"]
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
    "RUNNER_AVATAR_MOTION_STATES",
    "RUNNER_AVATAR_SCHEMA_VERSION",
    "RunnerAvatar",
    "RunnerAvatarCatalog",
    "canonical_runner_avatar_json",
    "load_runner_avatar_bytes",
    "runner_avatar_sha256",
]
