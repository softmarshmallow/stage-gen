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

from pydantic import Field, field_validator, model_validator

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

GAME_VOICES_SCHEMA_VERSION = 1
GAME_VOICES_KIND = "game-voices-v1"

_LANGUAGE_CODE = r"^[a-z]{2,3}(?:-[A-Za-z]{2,4})?$"
_ISO_DATE = r"^\d{4}-\d{2}-\d{2}$"
_PROVIDER_NAME = r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$"
#: A provider's own voice reference: opaque, but never empty and never a path.
_PROVIDER_VOICE = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"

VoiceRightsStatus = Literal["unreviewed", "restricted", "redistribution-approved"]


class VoiceProviderBinding(PersistedContractModel):
    """Which provider voice a catalog voice resolves to, and when that was checked."""

    name: str = Field(pattern=_PROVIDER_NAME, max_length=32)
    voice: str = Field(pattern=_PROVIDER_VOICE, max_length=128)
    #: ISO date the reference was last seen on the provider. Hosted voices come
    #: and go; an old date is a prompt to re-verify, not a gate.
    verified_on: str = Field(pattern=_ISO_DATE)


class GameVoice(PersistedContractModel):
    voice_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=64)
    display_name: str
    #: The language the voice is cast in; omitted lets the route infer it from
    #: the text. Passed to the provider verbatim when present.
    language_code: str | None = Field(default=None, pattern=_LANGUAGE_CODE)
    #: Casting notes for a person, never sent to a provider.
    casting: str
    rights_status: VoiceRightsStatus
    rights_basis: list[str] = Field(default_factory=list, max_length=16)
    provider: VoiceProviderBinding

    @field_validator("display_name", "casting")
    @classmethod
    def validate_text(cls, value: str, info: object) -> str:
        return normalized_text(value, f"voice {getattr(info, 'field_name', 'text')}")

    @field_validator("rights_basis")
    @classmethod
    def validate_rights_basis(cls, value: list[str]) -> list[str]:
        normalized = [normalized_text(entry, "voice rights basis") for entry in value]
        unique_values(normalized, "voice rights basis")
        return normalized

    @model_validator(mode="after")
    def validate_rights(self) -> GameVoice:
        if self.rights_status != "unreviewed" and not self.rights_basis:
            raise ValueError(
                f"voice {self.voice_id} claims {self.rights_status} rights without a basis"
            )
        return self


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
