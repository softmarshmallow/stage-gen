from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from stage_gen.components.character_profile import (
    CharacterProfile,
    CharacterProfileReferenceReader,
    load_character_profile_bytes,
    resolve_character_profile_binding,
)

PROFILE = """\
schema_version = 1
kind = "character-profile-v1"
profile_id = "test-character"
revision = 1
display_name = "Test Character"
age_years = 30
description = "Original adult test character"
visual_identity = "Dark hair and amber eyes"
wardrobe = "Green field coat"
invariants = ["Amber eyes"]

[rights]
status = "unreviewed"
basis = ["Original test text"]
"""


def _source(root: Path) -> Path:
    source = root / "characters/test-character/profile.toml"
    source.parent.mkdir(parents=True)
    source.write_text(PROFILE, encoding="utf-8")
    return source


def _binding(source: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "character-profile-binding-v1",
        "ref": "characters/test-character/profile.toml",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }


def test_shared_library_resolver_binds_source_canonical_identity_and_provenance(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    resolved = resolve_character_profile_binding(_binding(source), package_root=tmp_path)
    rerun = resolve_character_profile_binding(_binding(source), package_root=tmp_path)

    assert resolved.source_path == source
    assert resolved.canonical_bytes == rerun.canonical_bytes
    assert resolved.canonical_sha256 == rerun.canonical_sha256
    assert resolved.source_provenance.sha256 == resolved.source_sha256
    assert resolved.source_provenance.media_type == "application/toml"


def test_shared_library_resolver_rejects_symlinked_root_and_source(
    tmp_path: Path,
) -> None:
    actual = tmp_path / "actual"
    source = _source(actual)
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(actual, target_is_directory=True)
    with pytest.raises(ValueError, match="root must not traverse a symlink"):
        resolve_character_profile_binding(_binding(source), package_root=linked_root)

    source.unlink()
    external = tmp_path / "external.toml"
    external.write_text(PROFILE, encoding="utf-8")
    source.symlink_to(external)
    with pytest.raises(ValueError, match="regular non-symlink file"):
        resolve_character_profile_binding(_binding(external), package_root=actual)


def test_shared_library_resolver_requires_explicit_existing_root(tmp_path: Path) -> None:
    source = _source(tmp_path)
    with pytest.raises(ValueError, match="existing directory"):
        resolve_character_profile_binding(_binding(source), package_root=tmp_path / "missing")


def test_shared_library_resolver_parses_the_same_captured_bytes_it_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path)
    binding = _binding(source)

    def mutate_after_capture(
        data: bytes,
        *,
        source_suffix: str,
        reference_root: str | Path | None = None,
        reference_reader: CharacterProfileReferenceReader | None = None,
    ) -> CharacterProfile:
        source.write_text(PROFILE.replace("revision = 1", "revision = 9"), encoding="utf-8")
        return load_character_profile_bytes(
            data,
            source_suffix=source_suffix,
            reference_root=reference_root,
            reference_reader=reference_reader,
        )

    monkeypatch.setattr(
        "stage_gen.components.character_profile.library.load_character_profile_bytes",
        mutate_after_capture,
    )
    resolved = resolve_character_profile_binding(binding, package_root=tmp_path)
    assert resolved.profile.revision == 1
    assert resolved.source_sha256 == binding["source_sha256"]
