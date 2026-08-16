from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

FIXTURES = Path(__file__).parents[2] / "docs/check-fixtures"


def _load_media_rights() -> ModuleType:
    path = Path(__file__).parents[2] / "scripts/media_rights.py"
    spec = importlib.util.spec_from_file_location("stage_gen_media_rights", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MEDIA_RIGHTS = _load_media_rights()
check_generated_media_publication = MEDIA_RIGHTS.check_generated_media_publication
validate_published_media_copy = MEDIA_RIGHTS.validate_published_media_copy
validate_published_media_record = MEDIA_RIGHTS.validate_published_media_record


def _fixture(name: str) -> dict[str, Any]:
    value = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return cast(dict[str, Any], value)


def test_accepts_an_artifact_specific_approval_record_without_decoding_media() -> None:
    assert validate_published_media_record(_fixture("media-rights-approved.json")) == []


def test_rejects_unreviewed_rights_mismatched_facts_and_temp_source_refs() -> None:
    failures = validate_published_media_record(_fixture("media-rights-unreviewed.json"))
    assert "inventory reviewStatus must be repository-approved" in failures
    assert "sidecar artifact digest does not match media bytes" in failures
    assert "sidecar artifact byte size does not match media bytes" in failures
    assert "sidecar.inputs[0].ref must be a stable non-file identifier" in failures
    assert "sidecar.rights is required for repository publication" in failures


def test_rejects_non_integer_and_out_of_range_media_byte_counts() -> None:
    cases: tuple[tuple[object, object], ...] = (
        (1, True),
        (1, 1.0),
        (-1, -1),
        (0, 0),
        (9_007_199_254_740_992, 9_007_199_254_740_992),
    )
    for observed_bytes, artifact_bytes in cases:
        value = _fixture("media-rights-approved.json")
        value["observed"]["bytes"] = observed_bytes
        value["sidecar"]["artifact"]["bytes"] = artifact_bytes
        failures = validate_published_media_record(value)
        assert "sidecar artifact byte size does not match media bytes" in failures

    valid = _fixture("media-rights-approved.json")
    valid["observed"]["bytes"] = 1
    valid["sidecar"]["artifact"]["bytes"] = 1
    assert validate_published_media_record(valid) == []


def test_rejects_non_positive_or_non_integer_observed_and_input_byte_counts() -> None:
    invalid_values: tuple[object, ...] = (
        True,
        1.0,
        -1,
        0,
        9_007_199_254_740_992,
    )
    for invalid in invalid_values:
        observed = _fixture("media-rights-approved.json")
        observed["observed"]["bytes"] = invalid
        assert (
            "observed media digest and byte size are required"
            in validate_published_media_record(observed)
        )

        source = _fixture("media-rights-approved.json")
        source["sidecar"]["inputs"][0]["bytes"] = invalid
        assert (
            "sidecar.inputs[0].bytes must be a positive integer"
            in validate_published_media_record(source)
        )


def test_does_not_infer_generated_media_rights_from_bsd_or_blanket_cc0() -> None:
    bsd = _fixture("media-rights-approved.json")
    bsd["sidecar"]["rights"]["license_id"] = "BSD-3-Clause"
    assert (
        "the repository source license cannot be inherited by generated media"
        in validate_published_media_record(bsd)
    )

    cc0 = _fixture("media-rights-approved.json")
    cc0["sidecar"]["rights"]["license_id"] = "CC0-1.0"
    cc0["sidecar"]["rights"]["basis"] = ["provider provenance only"]
    failures = validate_published_media_record(cc0)
    assert "CC0 requires an artifact-specific rights-holder dedication basis" in failures
    assert "sidecar.rights.basis cannot rely only on provider provenance" in failures


def test_requires_role_based_listening_attestation_without_legal_name() -> None:
    value = _fixture("media-rights-approved.json")
    del value["entry"]["listeningReview"]["authorityBasis"]
    value["entry"]["listeningReview"]["result"] = "approved"
    failures = validate_published_media_record(value)
    assert "inventory listeningReview.authorityBasis is required" in failures
    assert "inventory listeningReview.result must record the protected-material finding" in failures


def test_requires_generated_media_copies_to_remain_byte_identical() -> None:
    digest = "a" * 64
    canonical_entry = {"path": "canonical/generated/audio.mp3"}
    entry = {"path": "copies/generated/audio.mp3", "copyOf": canonical_entry["path"]}
    observed = {
        "sha256": digest,
        "sidecarSha256": digest,
        "noticeSha256": digest,
    }
    assert (
        validate_published_media_copy(
            {
                "entry": entry,
                "canonicalEntry": canonical_entry,
                "observed": observed,
                "canonicalObserved": copy.deepcopy(observed),
            }
        )
        == []
    )
    failures = validate_published_media_copy(
        {
            "entry": entry,
            "canonicalEntry": canonical_entry,
            "observed": {**observed, "sidecarSha256": "b" * 64},
            "canonicalObserved": observed,
        }
    )
    assert "provenance sidecar must match copyOf exactly" in failures


def _write_synthetic_publication(repo: Path) -> tuple[Path, Path]:
    media_root = repo / "media"
    media_root.mkdir()
    artifact = media_root / "clip.mp3"
    payload = b"synthetic publication bytes, not encoded media"
    artifact.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    notice = media_root / "NOTICE.md"
    notice.write_text("Synthetic fixture permission record.", encoding="utf-8")
    fixture = _fixture("media-rights-approved.json")
    fixture["entry"]["path"] = "media/clip.mp3"
    fixture["observed"] = {"sha256": digest, "bytes": len(payload)}
    fixture["sidecar"]["artifact"] = {"sha256": digest, "bytes": len(payload)}
    fixture["sidecar"]["rights"]["notice"] = notice.name
    sidecar = artifact.with_name(f"{artifact.name}.meta.json")
    sidecar.write_text(json.dumps(fixture["sidecar"]), encoding="utf-8")
    inventory = repo / "inventory.json"
    inventory.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "roots": ["media"],
                "media": [fixture["entry"]],
            }
        ),
        encoding="utf-8",
    )
    return inventory, artifact


def test_publication_discovery_validates_bytes_sidecar_notice_and_inventory(
    tmp_path: Path,
) -> None:
    inventory, artifact = _write_synthetic_publication(tmp_path)
    assert check_generated_media_publication(tmp_path, inventory).failures == ()

    artifact.write_bytes(b"changed")
    failures = check_generated_media_publication(tmp_path, inventory).failures
    assert any("sidecar artifact digest does not match media bytes" in item for item in failures)
    assert any("sidecar artifact byte size does not match media bytes" in item for item in failures)


def test_publication_discovery_rejects_unlisted_media_and_symlinks(tmp_path: Path) -> None:
    inventory, artifact = _write_synthetic_publication(tmp_path)
    (artifact.parent / "unlisted.mp3").write_bytes(b"synthetic")
    (artifact.parent / "linked.mp3").symlink_to(artifact)

    failures = check_generated_media_publication(tmp_path, inventory).failures

    assert any("binary media is not enumerated" in item for item in failures)
    assert any("generated-media roots cannot contain symlinks" in item for item in failures)


def test_publication_discovery_rejects_unsafe_roots_and_missing_sidecars(
    tmp_path: Path,
) -> None:
    inventory, artifact = _write_synthetic_publication(tmp_path)
    artifact.with_name(f"{artifact.name}.meta.json").unlink()
    value = cast(dict[str, Any], json.loads(inventory.read_text(encoding="utf-8")))
    value["roots"].append("../outside")
    inventory.write_text(json.dumps(value), encoding="utf-8")

    failures = check_generated_media_publication(tmp_path, inventory).failures

    assert any("inventory root is unsafe" in item for item in failures)
    assert any("adjacent provenance sidecar is missing" in item for item in failures)


def test_publication_inventory_rejects_repository_root_and_normalized_aliases(
    tmp_path: Path,
) -> None:
    inventory, artifact = _write_synthetic_publication(tmp_path)
    original = cast(dict[str, Any], json.loads(inventory.read_text(encoding="utf-8")))
    unsafe_roots = (".", "./", ".//", "media/..", str(tmp_path.resolve()))
    for unsafe_root in unsafe_roots:
        value = copy.deepcopy(original)
        value["roots"] = [unsafe_root]
        inventory.write_text(json.dumps(value), encoding="utf-8")
        failures = check_generated_media_publication(tmp_path, inventory).failures
        assert any("inventory root is unsafe" in item for item in failures)

    unsafe_entries = (
        ".",
        "./media/clip.mp3",
        "media/../media/clip.mp3",
        str(artifact.resolve()),
    )
    for unsafe_entry in unsafe_entries:
        value = copy.deepcopy(original)
        value["media"][0]["path"] = unsafe_entry
        inventory.write_text(json.dumps(value), encoding="utf-8")
        failures = check_generated_media_publication(tmp_path, inventory).failures
        assert "generated-media inventory contains an unsafe media path" in failures


def test_publication_inventory_rejects_direct_and_indirect_symlink_loops(
    tmp_path: Path,
) -> None:
    inventory, _artifact = _write_synthetic_publication(tmp_path)
    original = cast(dict[str, Any], json.loads(inventory.read_text(encoding="utf-8")))
    (tmp_path / "direct-loop").symlink_to("direct-loop", target_is_directory=True)
    (tmp_path / "indirect-a").symlink_to("indirect-b", target_is_directory=True)
    (tmp_path / "indirect-b").symlink_to("indirect-a", target_is_directory=True)

    for unsafe_root in ("direct-loop", "indirect-a"):
        value = copy.deepcopy(original)
        value["roots"] = [unsafe_root]
        inventory.write_text(json.dumps(value), encoding="utf-8")
        failures = check_generated_media_publication(tmp_path, inventory).failures
        assert "generated-media inventory root is unsafe" in failures
        assert str(tmp_path) not in "\n".join(failures)

    for unsafe_entry in ("direct-loop", "indirect-a/clip.mp3"):
        value = copy.deepcopy(original)
        value["media"][0]["path"] = unsafe_entry
        inventory.write_text(json.dumps(value), encoding="utf-8")
        failures = check_generated_media_publication(tmp_path, inventory).failures
        assert "generated-media inventory contains an unsafe media path" in failures
        assert str(tmp_path) not in "\n".join(failures)


def test_publication_inventory_rejects_ordinary_and_broken_symlink_aliases(
    tmp_path: Path,
) -> None:
    inventory, artifact = _write_synthetic_publication(tmp_path)
    original = cast(dict[str, Any], json.loads(inventory.read_text(encoding="utf-8")))
    (tmp_path / "media-alias").symlink_to("media", target_is_directory=True)
    (tmp_path / "broken-root").symlink_to("missing-root", target_is_directory=True)
    (tmp_path / "clip-alias.mp3").symlink_to(artifact.relative_to(tmp_path))
    (tmp_path / "broken-entry.mp3").symlink_to("missing.mp3")

    for unsafe_root in ("media-alias", "broken-root"):
        value = copy.deepcopy(original)
        value["roots"] = [unsafe_root]
        inventory.write_text(json.dumps(value), encoding="utf-8")
        failures = check_generated_media_publication(tmp_path, inventory).failures
        assert "generated-media inventory root is unsafe" in failures

    for unsafe_entry in ("clip-alias.mp3", "broken-entry.mp3"):
        value = copy.deepcopy(original)
        value["media"][0]["path"] = unsafe_entry
        inventory.write_text(json.dumps(value), encoding="utf-8")
        failures = check_generated_media_publication(tmp_path, inventory).failures
        assert "generated-media inventory contains an unsafe media path" in failures


def test_publication_inventory_sanitizes_path_resolution_os_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory, _artifact = _write_synthetic_publication(tmp_path)

    def fail_resolve(_path: Path, *, strict: bool = False) -> Path:
        del strict
        raise OSError(f"synthetic secret at {tmp_path}")

    monkeypatch.setattr(Path, "resolve", fail_resolve)
    failures = check_generated_media_publication(tmp_path, inventory).failures

    assert failures == (
        "generated-media inventory root is unsafe",
        "generated-media inventory contains an unsafe media path",
    )
    rendered = "\n".join(failures)
    assert "synthetic secret" not in rendered
    assert str(tmp_path) not in rendered


def test_publication_inventory_requires_exact_integer_schema_version(tmp_path: Path) -> None:
    inventory, _artifact = _write_synthetic_publication(tmp_path)
    original = cast(dict[str, Any], json.loads(inventory.read_text(encoding="utf-8")))
    for invalid in (True, False, 1.0, "1", 0, 2):
        value = copy.deepcopy(original)
        value["schemaVersion"] = invalid
        inventory.write_text(json.dumps(value), encoding="utf-8")
        assert check_generated_media_publication(tmp_path, inventory).failures == (
            "generated-media inventory schemaVersion must be 1",
        )

    inventory.write_text(json.dumps(original), encoding="utf-8")
    assert check_generated_media_publication(tmp_path, inventory).failures == ()
