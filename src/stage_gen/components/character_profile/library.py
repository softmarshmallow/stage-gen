"""Secure resolution of digest-bound profiles from an explicit authored library root."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from stage_gen.contracts import InputProvenance

from ._filesystem import (
    SecureCharacterProfilePathError,
    open_absolute_directory,
    read_relative_regular_file,
)
from .loader import (
    canonical_character_profile_json,
    load_character_profile_bytes,
)
from .models import CharacterProfile, CharacterProfileBinding

PROFILE_LIBRARY_RESOLUTION_VERSION = "character-profile-library-resolution-v1"


@dataclass(frozen=True, slots=True)
class ResolvedCharacterProfile:
    binding: CharacterProfileBinding
    profile: CharacterProfile
    source_path: Path
    source_bytes: bytes
    canonical_bytes: bytes

    @property
    def source_sha256(self) -> str:
        return hashlib.sha256(self.source_bytes).hexdigest()

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    @property
    def source_provenance(self) -> InputProvenance:
        return InputProvenance(
            ref=self.binding.ref,
            sha256=self.source_sha256,
            source="content",
            bytes=len(self.source_bytes),
            media_type="application/toml",
        )

    def identity(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "kind": "resolved-character-profile-v1",
            "resolution_version": PROFILE_LIBRARY_RESOLUTION_VERSION,
            "binding": self.binding.model_dump(mode="json"),
            "profile_id": self.profile.profile_id,
            "revision": self.profile.revision,
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
            "canonical_bytes": len(self.canonical_bytes),
            "rights_status": self.profile.rights.status,
        }


def resolve_character_profile_binding(
    value: object,
    *,
    character_library_root: str | Path,
) -> ResolvedCharacterProfile:
    """Resolve one exact library binding without following filesystem symlinks."""

    binding = CharacterProfileBinding.model_validate(value)
    parts = PurePosixPath(binding.ref).parts
    if len(parts) != 4 or parts[:2] != ("library", "characters") or parts[3] != "profile.toml":
        raise ValueError(
            "character_profile ref must equal library/characters/<profile_id>/profile.toml"
        )
    root = Path(character_library_root).absolute()
    try:
        with open_absolute_directory(root, label="character library root") as root_fd:
            source_bytes = read_relative_regular_file(
                root_fd,
                parts,
                label="character profile source",
            )
            if hashlib.sha256(source_bytes).hexdigest() != binding.source_sha256:
                raise ValueError("character profile source_sha256 mismatch")

            def read_reference(path: str) -> bytes:
                profile_directory = parts[:-1]
                return read_relative_regular_file(
                    root_fd,
                    (*profile_directory, *PurePosixPath(path).parts),
                    label=f"character reference {path}",
                )

            profile = load_character_profile_bytes(
                source_bytes,
                source_suffix=".toml",
                reference_reader=read_reference,
            )
            if profile.profile_id != parts[2]:
                raise ValueError("character profile profile_id must match its library directory")
            canonical_bytes = canonical_character_profile_json(profile)
            return ResolvedCharacterProfile(
                binding=binding,
                profile=profile,
                source_path=root.joinpath(*parts),
                source_bytes=source_bytes,
                canonical_bytes=canonical_bytes,
            )
    except SecureCharacterProfilePathError as error:
        raise ValueError(str(error)) from error
