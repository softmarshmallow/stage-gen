"""Explicit provider voice identity, casting notes, and rights for speech assets."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    SNAKE_ID_PATTERN,
    normalized_text,
    unique_values,
)

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


class VoiceProfile(PersistedContractModel):
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
    def validate_rights(self) -> VoiceProfile:
        if self.rights_status != "unreviewed" and not self.rights_basis:
            raise ValueError(
                f"voice {self.voice_id} claims {self.rights_status} rights without a basis"
            )
        return self


__all__ = ["VoiceProfile", "VoiceProviderBinding", "VoiceRightsStatus"]
