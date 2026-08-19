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
    fixture["sidecar"]["artifact"] = {
        "sha256": digest,
        "bytes": len(payload),
        "media_type": "audio/mpeg",
    }
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


def _capture_record(kind: str) -> dict[str, Any]:
    extension, media_type = ("mp4", "video/mp4") if kind == "video" else ("png", "image/png")
    attestation = f"independent-visual-attestation-{kind}-2026-08-16"
    capture: dict[str, Any] = {
        "tool": "Playwright browser capture",
        "version": "1.55.0",
        "params": {
            "browser": "chromium",
            "viewport": {"width": 1280, "height": 720},
            "device_scale_factor": 1,
        },
        "source": {"path": "web/app/page.tsx", "sha256": "b" * 64},
        "generator": {
            "pathAtCapture": "web/tests/gameplay/harness.ts",
            "ref": f"sha256:{'e' * 64}",
            "sha256": "e" * 64,
        },
        "fixtureGenerator": {
            "pathAtCapture": "web/fixtures/showcase.json",
            "ref": f"sha256:{'c' * 64}",
            "sha256": "c" * 64,
        },
        "verifier": {"path": "web/tests/gameplay/harness.ts", "sha256": "f" * 64},
        "fixture": {"path": "web/fixtures/showcase.json", "sha256": "c" * 64},
        "timeline": {"path": "docs/showcase/timeline.json", "sha256": "d" * 64},
    }
    if kind == "video":
        capture["mp4"] = {
            "container": "mp4",
            "video_codec": "h264",
            "pixel_format": "yuv420p",
            "width": 1280,
            "height": 720,
            "frame_rate": 30,
            "duration_seconds": 30.0,
            "fast_start": True,
            "audio_codec": None,
        }
    return {
        "entry": {
            "path": f"docs/showcase/gameplay.{extension}",
            "kind": kind,
            "reviewStatus": "repository-approved",
            "synthIdExpected": False,
            "visualReview": {
                "status": "approved",
                "result": "pass",
                "independent": True,
                "reviewedBy": "independent verification subagent",
                "authorityBasis": "reviewer distinct from the browser capture producer",
                "reviewedAt": "2026-08-16T00:00:00.000Z",
                "attestationId": attestation,
                "attestedAt": "2026-08-16T00:00:00.000Z",
            },
        },
        "observed": {"sha256": "a" * 64, "bytes": 2048},
        "sidecar": {
            "schema_version": 1,
            "artifact": {"sha256": "a" * 64, "bytes": 2048, "media_type": media_type},
            "capture": capture,
            "rights": {
                "status": "redistribution-approved",
                "notice": "SHOWCASE-NOTICE.md",
                "license_id": "LicenseRef-Project-Showcase",
                "attribution": [],
                "basis": ["Artifact-specific browser capture authorization", attestation],
                "reviewed_at": "2026-08-16T00:00:00.000Z",
            },
        },
    }


def test_accepts_strict_deterministic_video_and_poster_records() -> None:
    assert validate_published_media_record(_capture_record("video")) == []
    assert validate_published_media_record(_capture_record("image")) == []


def test_rejects_incomplete_or_unsafe_browser_capture_governance() -> None:
    video = _capture_record("video")
    del video["entry"]["kind"]
    video["entry"]["synthIdExpected"] = True
    video["entry"]["visualReview"]["independent"] = False
    video["entry"]["visualReview"]["result"] = "fail"
    video["sidecar"]["artifact"]["media_type"] = "video/webm"
    video["sidecar"]["capture"]["tool"] = ""
    video["sidecar"]["capture"]["params"] = {}
    video["sidecar"]["capture"]["source"] = {"path": "../private.ts", "sha256": "bad"}
    video["sidecar"]["capture"]["generator"] = {
        "pathAtCapture": "../private.ts",
        "ref": "file:private.ts",
        "sha256": "bad",
    }
    video["sidecar"]["capture"]["verifier"] = {
        "path": "/private/verify.ts",
        "sha256": "bad",
    }
    video["sidecar"]["capture"]["mp4"]["video_codec"] = "vp9"
    video["sidecar"]["capture"]["mp4"]["width"] = 1279
    video["sidecar"]["capture"]["mp4"]["fast_start"] = False
    video["sidecar"]["rights"]["basis"] = ["Artifact-specific browser capture authorization"]

    failures = validate_published_media_record(video)

    expected = {
        "inventory kind must explicitly declare video or image",
        "inventory synthIdExpected must explicitly be false for browser capture",
        "inventory visualReview.independent must be true",
        "inventory visualReview.result must be pass",
        "sidecar artifact media_type must match the artifact extension",
        "sidecar.capture.tool must be a stable value",
        "sidecar.capture.params must be a non-empty JSON object",
        "sidecar.capture.source.path must be repository-relative and canonical",
        "sidecar.capture.source.sha256 must be a content digest",
        "sidecar.capture.generator.pathAtCapture must be repository-relative and canonical",
        "sidecar.capture.generator.sha256 must be a content digest",
        "sidecar.capture.generator.ref must match its sha256 content identifier",
        "sidecar.capture.verifier.path must be repository-relative and canonical",
        "sidecar.capture.verifier.sha256 must be a content digest",
        "sidecar.capture.mp4.video_codec must be h264",
        "sidecar.capture.mp4.width must be a supported even integer",
        "sidecar.capture.mp4.fast_start must be true",
        "sidecar.rights.basis must include the visual attestation identifier",
    }
    assert expected <= set(failures)

    poster = _capture_record("image")
    poster["sidecar"]["capture"]["mp4"] = copy.deepcopy(
        _capture_record("video")["sidecar"]["capture"]["mp4"]
    )
    assert "sidecar.capture.mp4 is only valid for video" in validate_published_media_record(poster)


def _write_capture_publication(repo: Path) -> Path:
    source_paths = {
        "source": repo / "web/app/page.tsx",
        "verifier": repo / "web/tests/gameplay/harness.ts",
        "fixture": repo / "web/fixtures/showcase.json",
        "timeline": repo / "docs/showcase/timeline.json",
    }
    for label, path in source_paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"synthetic {label} input", encoding="utf-8")
    media_root = repo / "docs/showcase"
    notice = media_root / "SHOWCASE-NOTICE.md"
    notice.write_text("Synthetic artifact-specific permission.", encoding="utf-8")
    entries: list[dict[str, Any]] = []
    for kind in ("video", "image"):
        record = _capture_record(kind)
        artifact = media_root / ("gameplay.mp4" if kind == "video" else "gameplay.png")
        payload = f"synthetic {kind} bytes; not encoded media".encode()
        artifact.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        record["entry"]["path"] = artifact.relative_to(repo).as_posix()
        record["observed"] = {"sha256": digest, "bytes": len(payload)}
        record["sidecar"]["artifact"].update({"sha256": digest, "bytes": len(payload)})
        for label, path in source_paths.items():
            record["sidecar"]["capture"][label] = {
                "path": path.relative_to(repo).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        sidecar_bytes = json.dumps(record["sidecar"]).encode()
        Path(f"{artifact}.meta.json").write_bytes(sidecar_bytes)
        record["entry"]["sidecarSha256"] = hashlib.sha256(sidecar_bytes).hexdigest()
        entries.append(record["entry"])
    inventory = repo / "docs/generated-media-inventory.json"
    inventory.parent.mkdir(exist_ok=True)
    inventory.write_text(
        json.dumps({"schemaVersion": 1, "roots": ["docs/showcase"], "media": entries}),
        encoding="utf-8",
    )
    return inventory


def test_capture_generator_is_historical_while_verifier_tracks_current_code() -> None:
    record = _capture_record("video")
    capture = record["sidecar"]["capture"]
    assert capture["generator"]["sha256"] != capture["verifier"]["sha256"]
    assert validate_published_media_record(record) == []

    capture["generator"]["ref"] = f"sha256:{'0' * 64}"
    assert (
        "sidecar.capture.generator.ref must match its sha256 content identifier"
        in validate_published_media_record(record)
    )


def test_capture_fixture_generator_preserves_historical_content_identity() -> None:
    record = _capture_record("video")
    capture = record["sidecar"]["capture"]
    assert capture["fixtureGenerator"]["sha256"] == capture["fixture"]["sha256"]
    assert validate_published_media_record(record) == []

    capture["fixtureGenerator"]["pathAtCapture"] = "../private-fixture.ts"
    capture["fixtureGenerator"]["ref"] = "sha256:not-a-digest"
    failures = validate_published_media_record(record)
    assert (
        "sidecar.capture.fixtureGenerator.pathAtCapture must be repository-relative and canonical"
        in failures
    )
    assert (
        "sidecar.capture.fixtureGenerator.ref must match its sha256 content identifier" in failures
    )


def test_browser_capture_publication_checks_hashes_shared_notice_and_symlinks(
    tmp_path: Path,
) -> None:
    inventory = _write_capture_publication(tmp_path)
    assert check_generated_media_publication(tmp_path, inventory).failures == ()

    timeline = tmp_path / "docs/showcase/timeline.json"
    timeline.write_text("changed timeline", encoding="utf-8")
    failures = check_generated_media_publication(tmp_path, inventory).failures
    assert sum("sidecar.capture.timeline digest does not match" in item for item in failures) == 2

    timeline.unlink()
    target = tmp_path / "timeline-target.json"
    target.write_text("synthetic target", encoding="utf-8")
    timeline.symlink_to(target)
    failures = check_generated_media_publication(tmp_path, inventory).failures
    assert sum("sidecar.capture.timeline.path is unsafe" in item for item in failures) == 2


def test_browser_capture_video_and_poster_must_share_notice(tmp_path: Path) -> None:
    inventory = _write_capture_publication(tmp_path)
    poster_sidecar = tmp_path / "docs/showcase/gameplay.png.meta.json"
    value = cast(dict[str, Any], json.loads(poster_sidecar.read_text(encoding="utf-8")))
    second_notice = poster_sidecar.parent / "POSTER-NOTICE.md"
    second_notice.write_text("Different notice.", encoding="utf-8")
    value["rights"]["notice"] = second_notice.name
    poster_sidecar.write_text(json.dumps(value), encoding="utf-8")

    failures = check_generated_media_publication(tmp_path, inventory).failures

    assert "browser capture video and poster must share one adjacent rights notice" in failures


def test_browser_capture_verifier_digest_tracks_current_hardened_code(tmp_path: Path) -> None:
    inventory = _write_capture_publication(tmp_path)
    verifier = tmp_path / "web/tests/gameplay/harness.ts"
    verifier.write_text("changed hardened verifier", encoding="utf-8")

    failures = check_generated_media_publication(tmp_path, inventory).failures

    assert sum("sidecar.capture.verifier digest does not match" in item for item in failures) == 2


def test_browser_capture_inventory_binds_exact_sidecar_bytes(tmp_path: Path) -> None:
    inventory = _write_capture_publication(tmp_path)
    sidecar = tmp_path / "docs/showcase/gameplay.mp4.meta.json"
    sidecar.write_bytes(sidecar.read_bytes() + b"\n")

    failures = check_generated_media_publication(tmp_path, inventory).failures

    assert (
        sum(
            "inventory sidecarSha256 does not match adjacent provenance sidecar" in item
            for item in failures
        )
        == 1
    )


def test_media_git_size_limits_are_enforced_without_large_fixtures() -> None:
    for kind, maximum in (("video", 25 * 1024 * 1024), ("image", 5 * 1024 * 1024)):
        value = _capture_record(kind)
        value["observed"]["bytes"] = maximum + 1
        value["sidecar"]["artifact"]["bytes"] = maximum + 1
        assert f"{kind} exceeds the Git publication size limit" in validate_published_media_record(
            value
        )


def test_current_repository_generated_media_inventory_remains_strictly_valid() -> None:
    repository = Path(__file__).parents[2]
    inventory_path = repository / "docs/generated-media-inventory.json"
    result = check_generated_media_publication(repository, inventory_path)
    assert result.failures == ()
    assert result.media_count == 4

    inventory = cast(dict[str, Any], json.loads(inventory_path.read_text(encoding="utf-8")))
    entries = {entry["path"]: entry for entry in cast(list[dict[str, Any]], inventory["media"])}
    expected = {
        "docs/media/gameplay-showcase.mp4": (
            "5ed3ba2648dc96d904bc38c9d98457aee2e66ebe08ff2d7921204d38fb9161b8",
            7_087_068,
        ),
        "docs/media/gameplay-showcase.poster.png": (
            "61c2e77b41df4e0fa28df060e831593312232ad84c05d81005e136867fc4554f",
            891_557,
        ),
    }
    approval_manifest = cast(
        dict[str, Any],
        json.loads(
            (repository / "fixtures/gameplay-demo/approval-manifest.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    approved_assets = cast(list[dict[str, Any]], approval_manifest["assets"])
    expected_asset_records = {
        (
            asset["id"],
            f"fixtures/gameplay-demo/{asset['path']}",
            asset["sha256"],
            asset["bytes"],
        )
        for asset in approved_assets
    }
    assets_promoted_after_capture = {
        (
            "ladder",
            "fixtures/gameplay-demo/ladder.png",
            "a89b1d865b651806b1457ab1fc37da4d0a54ff28daf5566ec4011483c732faa6",
            172_703,
        ),
        (
            "character-climb",
            "fixtures/gameplay-demo/character-climb.png",
            "782fcda99a7296ab746c21d05014214503d4af280541b1f115031cf4d70dc56e",
            39_677,
        ),
    }
    assert len(expected_asset_records) == 20
    assert assets_promoted_after_capture <= expected_asset_records
    assert all(asset["visualReview"]["status"] == "approved" for asset in approved_assets)
    assert all(asset["visualReview"]["result"] == "pass" for asset in approved_assets)
    assert all(asset["visualReview"]["independent"] is True for asset in approved_assets)
    assert all(asset["rights"]["status"] == "redistribution-approved" for asset in approved_assets)
    publication_text = inventory_path.read_text(encoding="utf-8")
    publication_text += (repository / "docs/media/gameplay-showcase.LICENSE.md").read_text(
        encoding="utf-8"
    )
    for path, (digest, byte_count) in expected.items():
        review = cast(dict[str, Any], entries[path]["visualReview"])
        assert review["artifactSha256"] == digest
        assert review["artifactBytes"] == byte_count
        assert review["verificationReportSha256"] == (
            "c312124fadd636ff510bd290db231b20523089f78d77b06a8e490c374377c2f8"
        )
        sidecar_path = repository / f"{path}.meta.json"
        assert (
            entries[path]["sidecarSha256"] == hashlib.sha256(sidecar_path.read_bytes()).hexdigest()
        )
        sidecar = cast(dict[str, Any], json.loads(sidecar_path.read_text(encoding="utf-8")))
        assert sidecar["state"] == "redistribution-approved"
        assert sidecar["visualReview"]["artifactSha256"] == digest
        assert sidecar["visualReview"]["artifactBytes"] == byte_count
        assert sidecar["visualReview"]["evidence"]["sha256"] == (
            "c312124fadd636ff510bd290db231b20523089f78d77b06a8e490c374377c2f8"
        )
        capture = cast(dict[str, Any], sidecar["capture"])
        assert capture["producerManifest"] == {
            "path": "fixtures/gameplay-demo/asset-manifest.json",
            "sha256": "edf1b2913afeae906275588e745023ead6797ca7ed7839a72c0789243fd7b8ca",
            "bytes": 78_630,
        }
        assert capture["approvalManifest"] == {
            "path": "fixtures/gameplay-demo/approval-manifest.json",
            "sha256": "7818a18ea177ed47203e1d47d22b1d669055f13b4eb113801326c7cd86629048",
            "bytes": 16_869,
        }
        asset_set = cast(dict[str, Any], capture["assetSet"])
        assert asset_set["count"] == 18
        assert asset_set["aggregate"]["sha256"] == (
            "6bb9d428aead88df25e91dfe7761382e23673a77c5a1d2a1622019554184d30a"
        )
        historical_asset_records = {
            (asset["id"], asset["path"], asset["sha256"], asset["bytes"])
            for asset in cast(list[dict[str, Any]], asset_set["assets"])
        }
        assert historical_asset_records.isdisjoint(assets_promoted_after_capture)
        assert historical_asset_records == expected_asset_records - assets_promoted_after_capture
        publication_text += sidecar_path.read_text(encoding="utf-8")

    assert "6bb9d428aead88df25e91dfe7761382e23673a77c5a1d2a1622019554184d30a" in publication_text
    for retired in (
        "original synthetic fixture assets",
        "ec3c200b40ccd12521b5535ed46a3b7256ec1dc4fee1acfde2ec95c1540e694c",
        "6da7281ac29f91f20cb65099088af357420906946bdfde0df7974ec8e844bdec",
        "independent-visual-attestation-gameplay-showcase-2026-08-16",
    ):
        assert retired not in publication_text
