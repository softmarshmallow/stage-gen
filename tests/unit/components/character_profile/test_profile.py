from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from stage_gen.components import (
    PROFILE_LIBRARY_RESOLUTION_VERSION,
    CharacterProfile,
    CharacterProfileBinding,
    CharacterProfileLoadError,
    CharacterProfileReference,
    CharacterProfileReferenceReader,
    CharacterProfileRights,
    CharacterProfileRightsStatus,
    ResolvedCharacterProfile,
    canonical_character_profile_json,
    character_profile_sha256,
    load_character_profile,
    load_character_profile_bytes,
    resolve_character_profile_binding,
)
from stage_gen.components.character_profile._filesystem import read_absolute_regular_file

PROFILE_TOML = """\
schema_version = 1
kind = "character-profile-v1"
profile_id = "mira-vale-cartographer"
revision = 1
display_name = "Mira Vale"
age_years = 29
description = "Original adult cartographer é"
visual_identity = "Warm brown skin, gray-green eyes, and a black undercut"
wardrobe = "Teal field jacket and charcoal work trousers"
invariants = ["Gray-green eyes", "Teal field jacket"]

[rights]
status = "unreviewed"
basis = ["Original test text"]
"""


def test_aggregate_component_exports_complete_character_profile_api() -> None:
    assert PROFILE_LIBRARY_RESOLUTION_VERSION.endswith("-v1")
    assert all(
        value is not None
        for value in (
            CharacterProfile,
            CharacterProfileBinding,
            CharacterProfileLoadError,
            CharacterProfileReference,
            CharacterProfileReferenceReader,
            CharacterProfileRights,
            CharacterProfileRightsStatus,
            ResolvedCharacterProfile,
            resolve_character_profile_binding,
        )
    )


def _write_profile(tmp_path: Path, contents: str, suffix: str = ".toml") -> Path:
    path = tmp_path / f"profile{suffix}"
    path.write_text(contents, encoding="utf-8")
    return path


def test_profile_binding_is_versioned_portable_and_source_digest_bound() -> None:
    binding = CharacterProfileBinding.model_validate(
        {
            "schema_version": 1,
            "kind": "character-profile-binding-v1",
            "ref": "character.toml",
            "source_sha256": "a" * 64,
        }
    )
    assert binding.ref == "character.toml"

    with pytest.raises(ValueError):
        CharacterProfileBinding.model_validate(
            {
                **binding.model_dump(mode="json"),
                "ref": "../profile.toml",
            }
        )


def test_toml_and_json_load_to_identical_canonical_utf8_bytes(tmp_path: Path) -> None:
    toml_profile = load_character_profile(_write_profile(tmp_path, PROFILE_TOML))
    canonical = canonical_character_profile_json(toml_profile)
    json_path = _write_profile(tmp_path, canonical.decode("utf-8"), ".json")
    json_profile = load_character_profile(json_path)

    assert canonical_character_profile_json(json_profile) == canonical
    assert canonical.startswith(b'{"age_years":29,"description":')
    assert "é".encode() in canonical
    assert b"\\u00e9" not in canonical
    assert canonical.endswith(b"}") and not canonical.endswith(b"\n")
    assert character_profile_sha256(json_profile) == hashlib.sha256(canonical).hexdigest()


def test_bytes_loader_parses_the_captured_source_after_path_mutation(tmp_path: Path) -> None:
    path = _write_profile(tmp_path, PROFILE_TOML)
    captured = path.read_bytes()
    path.write_text(PROFILE_TOML.replace("revision = 1", "revision = 2"), encoding="utf-8")

    profile = load_character_profile_bytes(
        captured,
        source_suffix=path.suffix,
        reference_root=path.parent,
    )

    assert profile.revision == 1
    assert load_character_profile(path).revision == 2


def test_direct_loader_reads_source_once_before_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_profile(tmp_path, PROFILE_TOML)
    reads = 0

    def mutate_after_capture(source: str | Path, *, label: str) -> bytes:
        nonlocal reads
        reads += 1
        captured = read_absolute_regular_file(source, label=label)
        path.write_text(PROFILE_TOML.replace("revision = 1", "revision = 9"), encoding="utf-8")
        return captured

    monkeypatch.setattr(
        "stage_gen.components.character_profile.loader.read_absolute_regular_file",
        mutate_after_capture,
    )
    profile = load_character_profile(path)

    assert reads == 1
    assert profile.revision == 1
    assert "revision = 9" in path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "contents,suffix,match",
    [
        (
            PROFILE_TOML.replace("revision = 1", "revision = 1\nrevision = 2"),
            ".toml",
            "syntax",
        ),
        (
            '{"schema_version":1,"schema_version":1}',
            ".json",
            "duplicate JSON key",
        ),
        (
            PROFILE_TOML.replace("age_years = 29", "age_years = 2026-08-21"),
            ".toml",
            "native date/time",
        ),
        (
            PROFILE_TOML.replace("profile_id", "profileId"),
            ".toml",
            "invalid character profile contract",
        ),
        (
            PROFILE_TOML + '\nunknown_key = "rejected"\n',
            ".toml",
            "invalid character profile contract",
        ),
        (
            PROFILE_TOML.replace("schema_version = 1", "schema_version = 2"),
            ".toml",
            "invalid character profile contract",
        ),
    ],
)
def test_loader_rejects_duplicate_temporal_camel_case_and_versioned_input(
    tmp_path: Path, contents: str, suffix: str, match: str
) -> None:
    with pytest.raises(CharacterProfileLoadError, match=match):
        load_character_profile(_write_profile(tmp_path, contents, suffix))


@pytest.mark.parametrize(
    "reference_path",
    [
        "/tmp/reference.txt",
        "../reference.txt",
        "references/../reference.txt",
        "references\\reference.txt",
        "file:reference.txt",
        "https://example.invalid/reference.txt",
        "C:/reference.txt",
        "references/name:variant.txt",
        "references//reference.txt",
        ".",
    ],
)
def test_reference_paths_are_portable_relative_only(tmp_path: Path, reference_path: str) -> None:
    payload = json.loads(
        canonical_character_profile_json(
            load_character_profile(_write_profile(tmp_path, PROFILE_TOML))
        )
    )
    payload["references"] = [
        {
            "reference_id": "identity-note",
            "path": reference_path,
            "sha256": "0" * 64,
            "media_type": "text/plain",
            "rights": payload["rights"],
        }
    ]
    with pytest.raises(CharacterProfileLoadError):
        load_character_profile(
            _write_profile(tmp_path, json.dumps(payload, ensure_ascii=False), ".json")
        )


def test_reference_bytes_are_digest_bound_and_symlinks_are_rejected(tmp_path: Path) -> None:
    profile = load_character_profile(_write_profile(tmp_path, PROFILE_TOML))
    payload = json.loads(canonical_character_profile_json(profile))
    reference = tmp_path / "identity.txt"
    reference.write_bytes(b"original identity note")
    payload["references"] = [
        {
            "reference_id": "identity-note",
            "path": "identity.txt",
            "sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
            "media_type": "text/plain",
            "rights": payload["rights"],
        }
    ]
    json_path = _write_profile(tmp_path, json.dumps(payload), ".json")
    assert load_character_profile(json_path).references[0].path == "identity.txt"

    reference.write_bytes(b"tampered")
    with pytest.raises(CharacterProfileLoadError, match="digest mismatch"):
        load_character_profile(json_path)

    target = tmp_path / "target.txt"
    target.write_bytes(b"original identity note")
    reference.unlink()
    reference.symlink_to(target)
    with pytest.raises(CharacterProfileLoadError, match="symlink"):
        load_character_profile(json_path)


def test_direct_loader_rejects_symlinked_profile_ancestor(tmp_path: Path) -> None:
    authored = tmp_path / "authored"
    authored.mkdir()
    profile_path = _write_profile(authored, PROFILE_TOML)
    linked = tmp_path / "linked-authored"
    linked.symlink_to(authored, target_is_directory=True)

    with pytest.raises(CharacterProfileLoadError, match=r"source.*symlink"):
        load_character_profile(linked / profile_path.name)


def test_bytes_loader_rejects_symlinked_reference_root_ancestor(tmp_path: Path) -> None:
    authored = tmp_path / "authored"
    authored.mkdir()
    linked = tmp_path / "linked-authored"
    linked.symlink_to(authored, target_is_directory=True)

    with pytest.raises(CharacterProfileLoadError, match=r"reference_root.*symlink"):
        load_character_profile_bytes(
            PROFILE_TOML.encode("utf-8"),
            source_suffix=".toml",
            reference_root=linked,
        )


def test_direct_loader_rejects_symlinked_reference_ancestor(tmp_path: Path) -> None:
    profile = load_character_profile(_write_profile(tmp_path, PROFILE_TOML))
    payload = json.loads(canonical_character_profile_json(profile))
    external = tmp_path / "external"
    external.mkdir()
    reference = external / "identity.txt"
    reference.write_bytes(b"original identity note")
    (tmp_path / "references").symlink_to(external, target_is_directory=True)
    payload["references"] = [
        {
            "reference_id": "identity-note",
            "path": "references/identity.txt",
            "sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
            "media_type": "text/plain",
            "rights": payload["rights"],
        }
    ]
    json_path = _write_profile(tmp_path, json.dumps(payload), ".json")

    with pytest.raises(CharacterProfileLoadError, match=r"reference.*symlink"):
        load_character_profile(json_path)


def test_revision_is_part_of_digest_but_profile_id_is_stable(tmp_path: Path) -> None:
    first = load_character_profile(_write_profile(tmp_path, PROFILE_TOML))
    second = load_character_profile(
        _write_profile(tmp_path, PROFILE_TOML.replace("revision = 1", "revision = 2"))
    )
    assert first.profile_id == second.profile_id
    assert character_profile_sha256(first) != character_profile_sha256(second)


@pytest.mark.parametrize(
    "rights_update",
    [
        {"status": "unknown"},
        {"status": "unreviewed", "reviewed_at": "2026-08-21T00:00:00Z"},
        {"status": "restricted"},
        {
            "status": "redistribution-approved",
            "basis": [],
            "reviewed_at": "2026-08-21T00:00:00Z",
        },
    ],
)
def test_rights_states_fail_closed(tmp_path: Path, rights_update: dict[str, object]) -> None:
    profile = load_character_profile(_write_profile(tmp_path, PROFILE_TOML))
    payload = json.loads(canonical_character_profile_json(profile))
    payload["rights"] = rights_update
    with pytest.raises(CharacterProfileLoadError, match="invalid character profile contract"):
        load_character_profile(_write_profile(tmp_path, json.dumps(payload), ".json"))


def test_reviewed_rights_need_no_license_or_notice(tmp_path: Path) -> None:
    profile = load_character_profile(_write_profile(tmp_path, PROFILE_TOML))
    payload = json.loads(canonical_character_profile_json(profile))
    payload["rights"] = {
        "status": "redistribution-approved",
        "basis": ["Authenticated task owner approved the exact source."],
        "reviewed_at": "2026-08-21T00:00:00Z",
    }
    reviewed = load_character_profile(_write_profile(tmp_path, json.dumps(payload), ".json"))
    assert reviewed.rights.status == "redistribution-approved"


def test_repository_sample_is_strict_original_and_reference_free() -> None:
    """The shipped profile is a member of the game package that binds it."""

    repository = Path(__file__).resolve().parents[4]
    path = repository / "library/games/larkfield/character.toml"
    profile = load_character_profile(path)
    assert profile.profile_id == "nao-kirishima"
    assert profile.rights.status == "unreviewed"
    assert profile.references == []
