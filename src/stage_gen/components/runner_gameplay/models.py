"""The runner's gameplay contract: named profiles, no authored numbers.

An infinite runner's feel is three closed names - how it runs, how it jumps,
what a hit means - plus a ramp. Each name declares its admission arithmetic as
an SDK constant (the `experience_curve` idiom: the contract names the feel,
the consumer owns the numbers), so a track is provable against the jump it
will be played with before any art is paid for. Scoring is runtime-owned:
distance plus pickups, with nothing to author in v1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from pydantic import Field, field_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    GAME_ID_PATTERN,
    KEBAB_ID_PATTERN,
    canonical_contract_json,
    parse_toml_contract,
    sha256_bytes,
)

RUNNER_GAMEPLAY_SCHEMA_VERSION = 1

SpeedProfile = Literal["steady_runner_v1"]
JumpProfileName = Literal["single_arc_v1"]
CollisionPolicy = Literal["end_run_v1"]
RampProfile = Literal["gentle_ramp_v1"]


@dataclass(frozen=True, slots=True)
class JumpProfile:
    """The admission arithmetic one jump name declares.

    `max_clear_gap_columns` is the widest bottom-row pit run the avatar can
    clear at any admitted speed; `max_rise_tiles` is the tallest step the arc
    lands on. Track admission proves every authored chunk against these before
    a single image is generated, which is what makes an unclearable gap an
    authoring error instead of a playtest discovery.
    """

    max_clear_gap_columns: int
    max_rise_tiles: int


JUMP_PROFILES: Final[dict[str, JumpProfile]] = {
    "single_arc_v1": JumpProfile(max_clear_gap_columns=3, max_rise_tiles=2),
}


class RunnerRun(PersistedContractModel):
    speed_profile: SpeedProfile
    jump_profile: JumpProfileName
    collision_policy: CollisionPolicy


class RunnerRamp(PersistedContractModel):
    profile: RampProfile


class RunnerGameplayContract(PersistedContractModel):
    schema_version: Literal[1]
    kind: Literal["runner-gameplay-v1"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    #: The single track this gameplay is played on. Exactly one in v1: an
    #: endless run has no map graph, and a second track is a second member.
    track_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    run: RunnerRun
    ramp: RunnerRamp

    @field_validator("track_id")
    @classmethod
    def validate_track_id(cls, value: str) -> str:
        return value

    def jump_profile(self) -> JumpProfile:
        return JUMP_PROFILES[self.run.jump_profile]


def load_runner_gameplay_bytes(data: bytes) -> RunnerGameplayContract:
    return parse_toml_contract(data, model=RunnerGameplayContract, label="runner gameplay contract")


def canonical_runner_gameplay_json(contract: RunnerGameplayContract) -> bytes:
    return canonical_contract_json(contract)


def runner_gameplay_sha256(contract: RunnerGameplayContract) -> str:
    return sha256_bytes(canonical_runner_gameplay_json(contract))


__all__ = [
    "JUMP_PROFILES",
    "RUNNER_GAMEPLAY_SCHEMA_VERSION",
    "CollisionPolicy",
    "JumpProfile",
    "JumpProfileName",
    "RampProfile",
    "RunnerGameplayContract",
    "RunnerRamp",
    "RunnerRun",
    "SpeedProfile",
    "canonical_runner_gameplay_json",
    "load_runner_gameplay_bytes",
    "runner_gameplay_sha256",
]
