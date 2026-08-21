"""Provider-neutral authored character-profile API."""

from .library import (
    PROFILE_LIBRARY_RESOLUTION_VERSION,
    ResolvedCharacterProfile,
    resolve_character_profile_binding,
)
from .loader import (
    CharacterProfileLoadError,
    CharacterProfileReferenceReader,
    canonical_character_profile_json,
    character_profile_sha256,
    load_character_profile,
    load_character_profile_bytes,
)
from .models import (
    CharacterProfile,
    CharacterProfileBinding,
    CharacterProfileReference,
    CharacterProfileRights,
    CharacterProfileRightsStatus,
)

__all__ = [
    "CharacterProfile",
    "CharacterProfileBinding",
    "CharacterProfileLoadError",
    "CharacterProfileReference",
    "CharacterProfileReferenceReader",
    "CharacterProfileRights",
    "CharacterProfileRightsStatus",
    "PROFILE_LIBRARY_RESOLUTION_VERSION",
    "ResolvedCharacterProfile",
    "canonical_character_profile_json",
    "character_profile_sha256",
    "load_character_profile",
    "load_character_profile_bytes",
    "resolve_character_profile_binding",
]
