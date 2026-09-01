"""Authored runner audio: event bindings and portable effect realization.

The runner owns when its seven semantic audio events occur. This contract owns
which named effect answers each event and how the current provider-free
oscillator realization sounds. The web consumer translates that portable DSP
shape into Web Audio; it does not invent cue voices.

Future generated sound effects extend ``RunnerEffectRealization`` with another
discriminated realization while preserving the event-to-effect bindings.
Provider or model identifiers never belong in this authored contract.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    GAME_ID_PATTERN,
    SNAKE_ID_PATTERN,
    canonical_contract_json,
    normalized_text,
    parse_toml_contract,
    sha256_bytes,
)

RUNNER_AUDIO_SCHEMA_VERSION = 1

RunnerAudioEvent = Literal[
    "takeoff",
    "air_jump",
    "land",
    "slide",
    "hazard_cleared",
    "collect",
    "death",
]


class RunnerAudioBindings(PersistedContractModel):
    """Every semantic runner event explicitly names one effect identity."""

    takeoff: str = Field(pattern=SNAKE_ID_PATTERN, max_length=64)
    air_jump: str = Field(pattern=SNAKE_ID_PATTERN, max_length=64)
    land: str = Field(pattern=SNAKE_ID_PATTERN, max_length=64)
    slide: str = Field(pattern=SNAKE_ID_PATTERN, max_length=64)
    hazard_cleared: str = Field(pattern=SNAKE_ID_PATTERN, max_length=64)
    collect: str = Field(pattern=SNAKE_ID_PATTERN, max_length=64)
    death: str = Field(pattern=SNAKE_ID_PATTERN, max_length=64)

    def effect_ids(self) -> tuple[str, ...]:
        return (
            self.takeoff,
            self.air_jump,
            self.land,
            self.slide,
            self.hazard_cleared,
            self.collect,
            self.death,
        )


class OscillatorSweepRealization(PersistedContractModel):
    """One short, provider-free oscillator sweep with an exponential envelope."""

    kind: Literal["oscillator_sweep_v1"]
    waveform: Literal["sine", "square", "sawtooth", "triangle"]
    start_frequency_hz: float = Field(ge=20.0, le=20_000.0)
    end_frequency_hz: float = Field(ge=20.0, le=20_000.0)
    duration_milliseconds: int = Field(ge=20, le=2_000)
    gain: float = Field(gt=0.0, le=1.0)
    #: Multiplies pitch by ``1 + event_strength * value``. Zero disables it.
    strength_pitch_multiplier: float = Field(ge=0.0, le=2.0)


# One realization is implemented today. Keep this alias as the explicit
# extension seam for generated-file realizations in the next audio contract.
RunnerEffectRealization = OscillatorSweepRealization


class RunnerSoundEffect(PersistedContractModel):
    effect_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=64)
    display_name: str
    realization: RunnerEffectRealization

    @model_validator(mode="after")
    def validate_display_name(self) -> RunnerSoundEffect:
        self.display_name = normalized_text(self.display_name, "runner effect display_name")
        return self


class RunnerAudioContract(PersistedContractModel):
    schema_version: Literal[1]
    kind: Literal["runner-audio-v1"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    bindings: RunnerAudioBindings
    effects: list[RunnerSoundEffect] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_effect_closure(self) -> RunnerAudioContract:
        ids = [effect.effect_id for effect in self.effects]
        if len(ids) != len(set(ids)):
            raise ValueError("runner audio effect_id values must be unique")
        declared = set(ids)
        referenced = set(self.bindings.effect_ids())
        missing = sorted(referenced - declared)
        if missing:
            raise ValueError(f"runner audio bindings reference unknown effects: {missing}")
        unused = sorted(declared - referenced)
        if unused:
            raise ValueError(f"runner audio declares unused effects: {unused}")
        self.effects = sorted(self.effects, key=lambda effect: effect.effect_id)
        return self

    def effect(self, effect_id: str) -> RunnerSoundEffect:
        for effect in self.effects:
            if effect.effect_id == effect_id:
                return effect
        raise ValueError(f"unknown runner audio effect_id: {effect_id}")


def load_runner_audio_bytes(data: bytes) -> RunnerAudioContract:
    return parse_toml_contract(data, model=RunnerAudioContract, label="runner audio contract")


def canonical_runner_audio_json(contract: RunnerAudioContract) -> bytes:
    return canonical_contract_json(contract)


def runner_audio_sha256(contract: RunnerAudioContract) -> str:
    return sha256_bytes(canonical_runner_audio_json(contract))


__all__ = [
    "RUNNER_AUDIO_SCHEMA_VERSION",
    "OscillatorSweepRealization",
    "RunnerAudioBindings",
    "RunnerAudioContract",
    "RunnerAudioEvent",
    "RunnerEffectRealization",
    "RunnerSoundEffect",
    "canonical_runner_audio_json",
    "load_runner_audio_bytes",
    "runner_audio_sha256",
]
