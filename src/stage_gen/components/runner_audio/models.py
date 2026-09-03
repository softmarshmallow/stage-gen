"""Authored runner audio: event bindings and portable effect realizations.

The runner owns when its nine semantic audio events occur. This contract owns
which named effect answers each event and how each effect is realized: the
provider-free oscillator sweep the web consumer synthesizes, a generated clip
the graph buys once from a text-to-sound route, or a spoken line - a *bark* -
the graph buys once from a text-to-speech route on a voice the game's catalog
declares. The event-to-effect bindings are the same in every case, so a cue
can change realization without remapping gameplay.

Eight of the events are consequences of player verbs and every package binds
all eight. The ninth, ``stage_start``, is an announcement - the frame the
stage-start moment opens, before the first run of a boot - and silence is a
legitimate announcement, so it is the one binding a package may leave out.
The contract also owns what the soundtrack does at the
run's edges - the interactive-music vocabulary of an action, a fade time, and
a fade curve on death and restart, and an optional duck under the hurt cue -
while the soundtrack catalog itself stays a separate member. Provider or model
identifiers never belong in this authored contract.
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
from stage_gen.components.speech import SpokenLineRealization

RUNNER_AUDIO_SCHEMA_VERSION = 4

RunnerAudioEvent = Literal[
    "stage_start",
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
    """Every player-verb event explicitly names one effect identity; the announcement may not."""

    #: The stage-start moment's first frame, once per boot. Optional: an
    #: announcement may be silent, where a verb's consequence may not.
    stage_start: str | None = Field(default=None, pattern=SNAKE_ID_PATTERN, max_length=64)
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
            *(() if self.stage_start is None else (self.stage_start,)),
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
    OscillatorSweepRealization | GeneratedClipRealization | SpokenLineRealization,
    Field(discriminator="kind"),
]

#: The run edges the soundtrack answers. ``death`` and ``restart`` are the run
#: phase edges; ``hurt`` is the survivable-hit frame, the same one the effect
#: binding of that name cues.
RunnerMusicEvent = Literal["death", "restart", "hurt"]

#: Fade shapes as Web Audio defines them: ``linear`` interpolates gain;
#: ``exponential`` interpolates geometrically to a near-zero floor, the
#: equal-loudness feel middleware exp/log curves approximate.
MusicFadeCurve = Literal["linear", "exponential"]

_MAX_FADE_SECONDS = 10.0


class MusicDeathTransition(PersistedContractModel):
    """The soundtrack's action when the run ends.

    The death stinger is the effect bound to ``death``; it plays over this
    action, never instead of it. A zero fade is the arcade hard cut.
    """

    action: Literal["stop", "pause", "continue"]
    fade_seconds: float = Field(ge=0.0, le=_MAX_FADE_SECONDS)
    curve: MusicFadeCurve


class MusicRestartTransition(PersistedContractModel):
    """The soundtrack's action when a fresh run starts after death.

    ``play`` starts the next shuffled track from the top; ``resume`` continues
    the paused one. Which is legal follows from the death action.
    """

    action: Literal["play", "resume", "continue"]
    fade_seconds: float = Field(ge=0.0, le=_MAX_FADE_SECONDS)
    curve: MusicFadeCurve


class MusicDuck(PersistedContractModel):
    """Auto-ducking: the music dips under the hurt stinger and recovers."""

    #: The music's gain factor while ducked, relative to its playing level.
    duck_gain: float = Field(gt=0.0, lt=1.0)
    fade_seconds: float = Field(ge=0.0, le=_MAX_FADE_SECONDS)
    hold_seconds: float = Field(ge=0.0, le=_MAX_FADE_SECONDS)
    recovery_seconds: float = Field(ge=0.0, le=_MAX_FADE_SECONDS)
    curve: MusicFadeCurve


_LEGAL_PAIRS = {"stop": "play", "pause": "resume", "continue": "continue"}


class RunnerMusicTransitions(PersistedContractModel):
    """What the soundtrack does at the run's edges.

    Every value here is consumer mixing: no generation cache identity includes
    it, so tuning after listening is a re-plan and never a redraw. The table is
    inert when the package declares no soundtrack member.
    """

    death: MusicDeathTransition
    restart: MusicRestartTransition
    hurt: MusicDuck | None = None

    @model_validator(mode="after")
    def validate_pairing(self) -> RunnerMusicTransitions:
        expected = _LEGAL_PAIRS[self.death.action]
        if self.restart.action != expected:
            raise ValueError(
                f"runner audio music.restart.action must be {expected!r} when "
                f"music.death.action is {self.death.action!r}, got {self.restart.action!r}"
            )
        return self


class RunnerSoundEffect(PersistedContractModel):
    effect_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=64)
    display_name: str
    realization: RunnerEffectRealization

    @model_validator(mode="after")
    def validate_display_name(self) -> RunnerSoundEffect:
        self.display_name = normalized_text(self.display_name, "runner effect display_name")
        return self


class RunnerAudioContract(PersistedContractModel):
    schema_version: Literal[4]
    kind: Literal["runner-audio-v4"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    bindings: RunnerAudioBindings
    effects: list[RunnerSoundEffect] = Field(min_length=1, max_length=32)
    music: RunnerMusicTransitions

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
        """The effects that cost a text-to-sound operation, in canonical order."""

        return tuple(
            effect
            for effect in self.effects
            if isinstance(effect.realization, GeneratedClipRealization)
        )

    def spoken_lines(self) -> tuple[RunnerSoundEffect, ...]:
        """The effects that cost a text-to-speech operation, in canonical order."""

        return tuple(
            effect
            for effect in self.effects
            if isinstance(effect.realization, SpokenLineRealization)
        )

    def bought_generated_effects(self) -> tuple[RunnerSoundEffect, ...]:
        """The generated clips a run actually buys: those without a pinned take."""

        return tuple(
            effect
            for effect in self.generated_effects()
            if isinstance(effect.realization, GeneratedClipRealization)
            and effect.realization.pinned is None
        )

    def bought_spoken_lines(self) -> tuple[RunnerSoundEffect, ...]:
        """The spoken lines a run actually buys: those without a pinned take."""

        return tuple(
            effect
            for effect in self.spoken_lines()
            if isinstance(effect.realization, SpokenLineRealization)
            and effect.realization.pinned is None
        )

    def pinned_effects(self) -> tuple[RunnerSoundEffect, ...]:
        """The effects whose bytes the package already carries, in canonical order.

        A pinned take is republished through admission and costs no provider
        operation, whatever kind it was bought as.
        """

        return tuple(
            effect
            for effect in self.effects
            if isinstance(effect.realization, GeneratedClipRealization | SpokenLineRealization)
            and effect.realization.pinned is not None
        )

    def voice_ids(self) -> tuple[str, ...]:
        """Every catalog voice the contract names, deduplicated, in canonical order."""

        return tuple(
            sorted(
                {
                    effect.realization.voice_id
                    for effect in self.effects
                    if isinstance(effect.realization, SpokenLineRealization)
                }
            )
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
    "MusicDeathTransition",
    "MusicDuck",
    "MusicFadeCurve",
    "MusicRestartTransition",
    "OscillatorSweepRealization",
    "RunnerAudioBindings",
    "RunnerAudioContract",
    "RunnerAudioEvent",
    "RunnerEffectRealization",
    "RunnerMusicEvent",
    "RunnerMusicTransitions",
    "RunnerSoundEffect",
    "SpokenLineRealization",
    "canonical_runner_audio_json",
    "load_runner_audio_bytes",
    "runner_audio_sha256",
]
