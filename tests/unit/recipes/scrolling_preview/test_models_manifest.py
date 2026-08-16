from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from stage_gen.config import TransparencyMode
from stage_gen.contracts import BinaryArtifact, ProvenanceInput
from stage_gen.recipes.scrolling_preview.manifest import write_scrolling_preview_manifest
from stage_gen.recipes.scrolling_preview.models import WorldSpec
from stage_gen.reliability import sha256_hex, write_artifact_with_provenance


def valid_world() -> dict[str, object]:
    kinds = [
        "sun-coin",
        "spore-vial",
        "rune-shard",
        "gate-key",
        "bone-charm",
        "signal-map",
        "flint-tool",
        "thorn-blade",
    ]
    return {
        "world": {"name": "Vale", "one_liner": "A quiet ruin.", "narrative": "Rain falls."},
        "mobs": [
            {
                "tier_label": "scout",
                "body_plan": "winged avian",
                "name": "Mote",
                "brief": "A pale bird.",
            },
            {
                "tier_label": "apex",
                "body_plan": "four-legged quadruped",
                "name": "Maw",
                "brief": "A stone beast.",
            },
        ],
        "obstacles": [
            {
                "sheet_theme": "mossy ruins",
                "props": [{"name": f"prop {index}", "brief": "weathered"} for index in range(8)],
            }
        ],
        "items": [
            {"kind": kind, "name": f"item {index}", "brief": "small"}
            for index, kind in enumerate(kinds)
        ],
        "layers": [
            {
                "id": "deep_sky",
                "title": "Deep sky",
                "z_index": 0,
                "parallax": 0.0,
                "opaque": True,
                "paint_region": "all canvas",
                "description": "Clouds",
            },
            {
                "id": "near_ruins",
                "title": "Near ruins",
                "z_index": 1,
                "parallax": 0.5,
                "opaque": False,
                "paint_region": "lower half",
                "description": "Arches",
            },
        ],
    }


def test_world_schema_enforces_cross_asset_invariants() -> None:
    parsed = WorldSpec.model_validate(valid_world())
    assert len(parsed.items) == 8
    duplicate = valid_world()
    duplicate["mobs"][1]["body_plan"] = "winged avian"  # type: ignore[index]
    with pytest.raises(ValidationError, match="must differ"):
        WorldSpec.model_validate(duplicate)


async def test_manifest_v2_copies_only_approved_fallback(tmp_path: Path) -> None:
    fallback = tmp_path / "fallback.mp3"
    fallback.write_bytes(b"offline-music")
    notice = tmp_path / "fallback.LICENSE.md"
    notice.write_text("approved notice", encoding="utf-8")
    sha = hashlib.sha256(fallback.read_bytes()).hexdigest()
    sidecar = {
        "schema_version": 1,
        "artifact": {"sha256": sha, "bytes": fallback.stat().st_size, "media_type": "audio/mpeg"},
        "references": [],
        "refs": [],
        "inputs": [
            {
                "ref": f"sha256:{sha}",
                "sha256": sha,
                "source": "content",
                "bytes": fallback.stat().st_size,
                "media_type": "audio/mpeg",
            }
        ],
        "rights": {
            "status": "redistribution-approved",
            "license_id": "CC0-1.0",
            "notice": notice.name,
            "attribution": [],
            "basis": [f"sha256:{sha}"],
            "reviewed_at": "2026-08-14T00:00:00Z",
        },
    }
    await asyncio.to_thread(
        Path(f"{fallback}.meta.json").write_text,
        json.dumps(sidecar),
        encoding="utf-8",
    )
    run_dir = tmp_path / "out" / "tag-ai"
    result = await write_scrolling_preview_manifest(
        run_dir=run_dir,
        tag="tag-ai",
        transparency_mode=TransparencyMode.AI,
        fallback_music_path=fallback,
    )
    manifest_text = await asyncio.to_thread(Path(result.manifest_path).read_text)
    manifest = json.loads(manifest_text)
    assert manifest["schemaVersion"] == 2
    assert manifest["transparencyMode"] == "ai"
    assert manifest["music"]["source"] == "generated-fallback"
    assert manifest["music"]["rightsStatus"] == "redistribution-approved"
    assert ".raw.png" not in "".join(manifest["artifacts"])
    assert await asyncio.to_thread(Path(result.manifest_provenance_path).is_file)


async def test_manifest_uses_real_bundled_fallback_without_live_calls(tmp_path: Path) -> None:
    result = await write_scrolling_preview_manifest(
        run_dir=tmp_path / "run",
        tag="bundled-ai",
        transparency_mode=TransparencyMode.AI,
    )
    manifest_text = await asyncio.to_thread(Path(result.manifest_path).read_text, encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert result.music_source == "generated-fallback"
    assert result.music_rights_status == "redistribution-approved"
    assert await asyncio.to_thread(Path(result.music_path).read_bytes)
    assert manifest["music"]["rightsStatus"] == "redistribution-approved"


@pytest.mark.parametrize(
    "reference",
    [".hidden/source.bin", "source.bin?query=1", r"folder\source.bin", "/tmp/source.bin"],
)
async def test_manifest_rejects_nonportable_fallback_references(
    tmp_path: Path, reference: str
) -> None:
    fallback = tmp_path / "fallback.mp3"
    fallback.write_bytes(b"offline-music")
    notice = tmp_path / "fallback.LICENSE.md"
    notice.write_text("approved notice", encoding="utf-8")
    sha = hashlib.sha256(fallback.read_bytes()).hexdigest()
    sidecar = {
        "schema_version": 1,
        "artifact": {"sha256": sha, "bytes": len(fallback.read_bytes())},
        "references": [reference],
        "refs": [reference],
        "inputs": [],
        "rights": {
            "status": "redistribution-approved",
            "license_id": "CC0-1.0",
            "notice": notice.name,
            "attribution": [],
            "basis": [f"sha256:{sha}"],
            "reviewed_at": "2026-08-14T00:00:00Z",
        },
    }
    await asyncio.to_thread(
        Path(f"{fallback}.meta.json").write_text,
        json.dumps(sidecar),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="stable non-temporary reference"):
        await write_scrolling_preview_manifest(
            run_dir=tmp_path / "out",
            tag="unsafe-ai",
            transparency_mode=TransparencyMode.AI,
            fallback_music_path=fallback,
        )


@pytest.mark.parametrize("status", ["unreviewed", "restricted"])
async def test_manifest_rejects_unapproved_repository_fallback(tmp_path: Path, status: str) -> None:
    fallback = _fallback_fixture(tmp_path, status=status)
    run_dir = tmp_path / "run"
    with pytest.raises(ValueError, match="not publication-approved"):
        await write_scrolling_preview_manifest(
            run_dir=run_dir,
            tag=f"{status}-ai",
            transparency_mode=TransparencyMode.AI,
            fallback_music_path=fallback,
        )
    assert not (run_dir / f"music_{status}-ai.mp3").exists()


async def test_manifest_rejects_fallback_digest_mismatch(tmp_path: Path) -> None:
    fallback = _fallback_fixture(tmp_path, digest="0" * 64)
    with pytest.raises(ValueError, match="artifact digest does not match"):
        await write_scrolling_preview_manifest(
            run_dir=tmp_path / "run",
            tag="bad-digest-ai",
            transparency_mode=TransparencyMode.AI,
            fallback_music_path=fallback,
        )


async def test_manifest_rejects_approved_fallback_without_notice(tmp_path: Path) -> None:
    fallback = _fallback_fixture(tmp_path, write_notice=False)
    with pytest.raises(ValueError, match="rights notice is missing"):
        await write_scrolling_preview_manifest(
            run_dir=tmp_path / "run",
            tag="missing-notice-ai",
            transparency_mode=TransparencyMode.AI,
            fallback_music_path=fallback,
        )


async def test_manifest_reports_missing_per_run_and_fallback_music(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="generate-music capability"):
        await write_scrolling_preview_manifest(
            run_dir=tmp_path / "run",
            tag="missing-music-ai",
            transparency_mode=TransparencyMode.AI,
            fallback_music_path=tmp_path / "missing.mp3",
        )


async def test_manifest_preserves_existing_unreviewed_per_run_music(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    music = run_dir / "music_custom-ai.mp3"
    await asyncio.to_thread(music.write_bytes, b"per-run")
    sidecar = Path(f"{music}.meta.json")
    await asyncio.to_thread(
        sidecar.write_text,
        json.dumps(
            {
                "rights": {
                    "status": "unreviewed",
                    "license_id": None,
                    "notice": "No redistribution review recorded.",
                    "attribution": [],
                    "basis": [],
                    "reviewed_at": None,
                }
            },
        ),
        encoding="utf-8",
    )

    result = await write_scrolling_preview_manifest(
        run_dir=run_dir,
        tag="custom-ai",
        transparency_mode=TransparencyMode.AI,
        fallback_music_path=tmp_path / "missing.mp3",
    )

    assert result.music_source == "per-run"
    assert result.music_rights_status == "unreviewed"
    assert await asyncio.to_thread(music.read_bytes) == b"per-run"
    assert await asyncio.to_thread(sidecar.is_file)


async def test_manifest_accepts_executor_shaped_lineage_and_is_idempotent(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    tag = "executor-chroma"

    def pair(
        name: str,
        data: bytes,
        *,
        params: dict[str, object],
        validation: dict[str, object],
        refs: list[str] | None = None,
    ) -> Path:
        path = run_dir / name
        write_artifact_with_provenance(
            path,
            BinaryArtifact(data=data, media_type="image/png"),
            ProvenanceInput(
                provider="local",
                model="offline",
                prompt=f"create {name}",
                refs=refs or [],
                params=params,
                validation=validation,
                attempts=1,
            ),
        )
        return path

    pair(
        f"concept_{tag}.png",
        b"opaque",
        params={"metadata": {"stage": "concept"}},
        validation={},
    )
    raw_name = f"character_{tag}_combined_strip_idle.raw.png"
    raw_data = b"raw-strip"
    pair(
        raw_name,
        raw_data,
        params={"metadata": {"transparency_mode": "chroma"}},
        validation={
            "exact_contract_dimensions": True,
            "output_width": 2400,
            "output_height": 800,
        },
    )
    strip_name = f"character_{tag}_combined_strip_idle.png"
    strip_data = b"canonical-strip"
    pair(
        strip_name,
        strip_data,
        params={
            "transparency": {
                "mode": "chroma",
                "retained_raw_path": raw_name,
                "raw_sha256": sha256_hex(raw_data),
                "output_sha256": sha256_hex(strip_data),
                "processor": {"kind": "chroma-key", "version": "1"},
            }
        },
        validation={
            "alpha_nontrivial": True,
            "transparent_pixels": 1,
            "nontransparent_pixels": 1,
            "dimensions_preserved": True,
            "output_width": 2400,
            "output_height": 800,
        },
        refs=[raw_name],
    )
    master_name = f"character_{tag}_combined.png"
    master_data = b"master"
    pair(
        master_name,
        master_data,
        params={
            "transparency": {
                "mode": "chroma",
                "source_paths": {"idle": strip_name},
                "source_hashes": [{"path": strip_name, "sha256": sha256_hex(strip_data)}],
                "output_sha256": sha256_hex(master_data),
                "processor": "deterministic-alpha-composite",
            }
        },
        validation={
            "alpha_nontrivial": True,
            "transparent_pixels": 1,
            "nontransparent_pixels": 1,
            "dimensions_preserved": True,
            "output_width": 2400,
            "output_height": 3440,
        },
        refs=[strip_name],
    )
    slice_name = f"character_{tag}-fromcombined_idle.png"
    slice_data = b"slice"
    pair(
        slice_name,
        slice_data,
        params={
            "transparency": {
                "mode": "chroma",
                "source_path": master_name,
                "source_sha256": sha256_hex(master_data),
                "output_sha256": sha256_hex(slice_data),
                "processor": "master-sheet-slice",
            }
        },
        validation={
            "alpha_nontrivial": True,
            "transparent_pixels": 1,
            "nontransparent_pixels": 1,
            "dimensions_preserved": True,
            "output_width": 2400,
            "output_height": 688,
        },
        refs=[master_name],
    )

    first = await write_scrolling_preview_manifest(
        run_dir=run_dir,
        tag=tag,
        transparency_mode=TransparencyMode.CHROMA,
    )
    first_manifest_bytes = await asyncio.to_thread(Path(first.manifest_path).read_bytes)
    first_provenance_bytes = await asyncio.to_thread(
        Path(first.manifest_provenance_path).read_bytes
    )
    second = await write_scrolling_preview_manifest(
        run_dir=run_dir,
        tag=tag,
        transparency_mode=TransparencyMode.CHROMA,
    )
    manifest_text = await asyncio.to_thread(Path(second.manifest_path).read_text, encoding="utf-8")
    manifest = json.loads(manifest_text)
    entries = {entry["path"]: entry for entry in manifest["canonicalArtifacts"]}
    assert entries[master_name]["transparency"]["lineage"]["sourcePaths"] == [strip_name]
    assert entries[slice_name]["transparency"]["lineage"]["sourcePaths"] == [master_name]
    assert Path(first.manifest_provenance_path).name not in manifest["artifacts"]
    assert second.music_source == first.music_source == "generated-fallback"
    assert second.music_rights_status == first.music_rights_status
    assert second.music_notice_path == first.music_notice_path
    assert await asyncio.to_thread(Path(second.manifest_path).read_bytes) == first_manifest_bytes
    assert (
        await asyncio.to_thread(Path(second.manifest_provenance_path).read_bytes)
        == first_provenance_bytes
    )


def _fallback_fixture(
    root: Path,
    *,
    status: str = "redistribution-approved",
    digest: str | None = None,
    write_notice: bool = True,
) -> Path:
    fallback = root / "fallback.mp3"
    data = b"offline-fallback-fixture"
    fallback.write_bytes(data)
    actual_digest = hashlib.sha256(data).hexdigest()
    notice_name = "fallback.LICENSE.md"
    if write_notice:
        (root / notice_name).write_text("Synthetic asset notice.\n", encoding="utf-8")
    rights: dict[str, object]
    if status == "unreviewed":
        rights = {
            "status": status,
            "license_id": None,
            "notice": "No redistribution review recorded.",
            "attribution": [],
            "basis": [],
            "reviewed_at": None,
        }
    else:
        rights = {
            "status": status,
            "license_id": "LicenseRef-Synthetic-Test"
            if status == "redistribution-approved"
            else None,
            "notice": notice_name,
            "attribution": [],
            "basis": [f"sha256:{actual_digest}"],
            "reviewed_at": "2026-08-14T00:00:00.000Z",
        }
    sidecar = {
        "schema_version": 1,
        "artifact": {
            "sha256": digest or actual_digest,
            "bytes": len(data),
            "media_type": "audio/mpeg",
        },
        "references": [],
        "refs": [],
        "inputs": [
            {
                "ref": f"sha256:{actual_digest}",
                "sha256": actual_digest,
                "source": "content",
                "bytes": len(data),
                "media_type": "audio/mpeg",
            }
        ],
        "rights": rights,
    }
    Path(f"{fallback}.meta.json").write_text(json.dumps(sidecar), encoding="utf-8")
    return fallback
