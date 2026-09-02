"""Authored runner audio: event bindings and portable effect realizations.

The runner owns when its eight semantic audio events occur. This contract owns
which named effect answers each event and how each effect is realized: either
the provider-free oscillator sweep the web consumer synthesizes, or a generated
clip the graph buys once and the consumer plays back. The event-to-effect
bindings are the same either way, so a cue can change realization without
remapping gameplay. Provider or model identifiers never belong in this
authored contract.
"""

from __future__ import annotations

from typing import Annotated, Literal

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
from stage_gen.components.sound_effect import GeneratedClipRealization

RUNNER_AUDIO_SCHEMA_VERSION = 2

RunnerAudioEvent = Literal[
    "takeoff",
    "air_jump",
    "land",
    "slide",
    "hazard_cleared",
    "collect",
    "hurt",
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
    #: A survivable hit: the frame a vitals drain connects. Silent in a
    #: one-hit-kill package, where death answers the contact instead.
    hurt: str = Field(pattern=SNAKE_ID_PATTERN, max_length=64)
    death: str = Field(pattern=SNAKE_ID_PATTERN, max_length=64)

    def effect_ids(self) -> tuple[str, ...]:
        return (
            self.takeoff,
            self.air_jump,
            self.land,
            self.slide,
            self.hazard_cleared,
            self.collect,
            self.hurt,
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


RunnerEffectRealization = Annotated[
    OscillatorSweepRealization | GeneratedClipRealization,
    Field(discriminator="kind"),
]


class RunnerSoundEffect(PersistedContractModel):
    effect_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=64)
    display_name: str
    realization: RunnerEffectRealization

    @model_validator(mode="after")
    def validate_display_name(self) -> RunnerSoundEffect:
        self.display_name = normalized_text(self.display_name, "runner effect display_name")
        return self


class RunnerAudioContract(PersistedContractModel):
    schema_version: Literal[2]
    kind: Literal["runner-audio-v2"]
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

    def generated_effects(self) -> tuple[RunnerSoundEffect, ...]:
        """The effects that cost a provider operation, in canonical order."""

        return tuple(
            effect
            for effect in self.effects
            if isinstance(effect.realization, GeneratedClipRealization)
        )


def load_runner_audio_bytes(data: bytes) -> RunnerAudioContract:
    return parse_toml_contract(data, model=RunnerAudioContract, label="runner audio contract")


def canonical_runner_audio_json(contract: RunnerAudioContract) -> bytes:
    return canonical_contract_json(contract)


def runner_audio_sha256(contract: RunnerAudioContract) -> str:
    return sha256_bytes(canonical_runner_audio_json(contract))


__all__ = [
    "RUNNER_AUDIO_SCHEMA_VERSION",
    "GeneratedClipRealization",
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
