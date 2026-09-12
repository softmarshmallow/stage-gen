"""The game-global voice catalog (``game-voices-v1``).

A voice is an externally-held identity - the audio twin of a digest-bound
visual reference: something the package binds by name, carries a rights
statement for, and never invents. A genre audio contract names a voice by its
catalog id and nothing else, so recasting a character is a catalog edit and a
provider's reference never appears beside gameplay data.

The catalog is game-global because every consumer of a voice - a runner's
run-start bark today, a visual novel's voiced lines later - reads the same
cast. Delivery settings (stability) are per line and live with the line;
the catalog owns who speaks, in which language, and on whose terms.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    GAME_ID_PATTERN,
    canonical_contract_json,
    parse_toml_contract,
    sha256_bytes,
    unique_values,
)
from stage_gen.components.voice_profile import VoiceProfile as GameVoice
from stage_gen.components.voice_profile import VoiceProviderBinding

GAME_VOICES_SCHEMA_VERSION = 1
GAME_VOICES_KIND = "game-voices-v1"

_LANGUAGE_CODE = r"^[a-z]{2,3}(?:-[A-Za-z]{2,4})?$"
_ISO_DATE = r"^\d{4}-\d{2}-\d{2}$"
_PROVIDER_NAME = r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$"
#: A provider's own voice reference: opaque, but never empty and never a path.
_PROVIDER_VOICE = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"

VoiceRightsStatus = Literal["unreviewed", "restricted", "redistribution-approved"]


class GameVoices(PersistedContractModel):
    schema_version: Literal[1]
    kind: Literal["game-voices-v1"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    voices: list[GameVoice] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_unique_voices(self) -> GameVoices:
        unique_values((voice.voice_id for voice in self.voices), "voice_id")
        self.voices = sorted(self.voices, key=lambda voice: voice.voice_id)
        return self

    def voice(self, voice_id: str) -> GameVoice | None:
        return next((voice for voice in self.voices if voice.voice_id == voice_id), None)

    def voice_ids(self) -> tuple[str, ...]:
        return tuple(voice.voice_id for voice in self.voices)


def load_game_voices_bytes(data: bytes) -> GameVoices:
    return parse_toml_contract(data, model=GameVoices, label="game voices contract")


def canonical_game_voices_json(contract: GameVoices) -> bytes:
    return canonical_contract_json(contract)


def game_voices_sha256(contract: GameVoices) -> str:
    return sha256_bytes(canonical_game_voices_json(contract))


__all__ = [
    "GAME_VOICES_KIND",
    "GAME_VOICES_SCHEMA_VERSION",
    "GameVoice",
    "GameVoices",
    "VoiceProviderBinding",
    "VoiceRightsStatus",
    "canonical_game_voices_json",
    "game_voices_sha256",
    "load_game_voices_bytes",
]
