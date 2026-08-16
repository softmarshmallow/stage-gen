"""Scrolling-preview schema-v2 manifest and music publication gate."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from stage_gen.config import TransparencyMode
from stage_gen.contracts import (
    ArtifactProvenance,
    ArtifactRights,
    BinaryArtifact,
    ProvenanceInput,
    SoftwareIdentity,
)
from stage_gen.manifests import to_canonical_manifest_entry
from stage_gen.reliability import (
    build_artifact_provenance,
    is_portable_artifact_reference,
    write_artifact_with_provenance,
)
from stage_gen.resources import bundled_music_path

MusicRightsStatus = Literal["unreviewed", "restricted", "redistribution-approved", "unrecorded"]


@dataclass(frozen=True, slots=True)
class ManifestWriteResult:
    manifest_path: str
    manifest_provenance_path: str
    music_path: str
    music_provenance_path: str
    music_source: Literal["per-run", "generated-fallback"]
    music_rights_status: MusicRightsStatus
    music_notice_path: str | None = None

    @property
    def artifacts(self) -> tuple[str, ...]:
        paths = [
            self.manifest_path,
            self.manifest_provenance_path,
            self.music_path,
            self.music_provenance_path,
        ]
        if self.music_notice_path is not None:
            paths.append(self.music_notice_path)
        return tuple(paths)


def _default_fallback() -> Path:
    return bundled_music_path()


async def write_scrolling_preview_manifest(
    *,
    run_dir: str | Path,
    tag: str,
    transparency_mode: TransparencyMode = TransparencyMode.AI,
    fallback_music_path: str | Path | None = None,
) -> ManifestWriteResult:
    return await asyncio.to_thread(
        _write_scrolling_preview_manifest,
        Path(run_dir),
        tag,
        transparency_mode,
        Path(fallback_music_path) if fallback_music_path is not None else _default_fallback(),
    )


def _write_scrolling_preview_manifest(
    run_dir: Path,
    tag: str,
    mode: TransparencyMode,
    fallback_music: Path,
) -> ManifestWriteResult:
    run_dir.mkdir(parents=True, exist_ok=True)
    music_path = run_dir / f"music_{tag}.mp3"
    music = _ensure_run_music_pair(music_path, fallback_music)

    manifest_path = run_dir / f"manifest_{tag}.json"
    names = sorted(path.name for path in run_dir.iterdir())
    artifacts = [
        name
        for name in names
        if not name.startswith(".")
        and name not in {manifest_path.name, f"{manifest_path.name}.meta.json"}
        and ".raw.png" not in name
    ]
    canonical = _collect_canonical_images(run_dir, set(names), mode)
    music_meta = Path(f"{music_path}.meta.json")
    manifest: dict[str, Any] = {
        "schemaVersion": 2,
        "recipe": "scrolling-preview",
        "tag": tag,
        "transparencyMode": mode,
        "artifacts": artifacts,
        "canonicalArtifacts": canonical,
        "music": {
            "path": music_path.name,
            "provenancePath": music_meta.name,
            "source": music["source"],
            "generationCapability": "generate-music",
            "rightsStatus": music["rights_status"],
            **(
                {"rightsNoticePath": Path(music["notice_path"]).name}
                if music.get("notice_path")
                else {}
            ),
        },
    }
    payload = f"{json.dumps(manifest, indent=2, ensure_ascii=False)}\n".encode()
    provenance_path = _write_local_artifact_pair(
        manifest_path,
        payload,
        media_type="application/json",
        prompt="assemble scrolling-preview run manifest",
        refs=[
            music_path.name,
            music_meta.name,
            *([Path(music["notice_path"]).name] if music.get("notice_path") else []),
        ],
        params={
            "recipe": "scrolling-preview",
            "tag": tag,
            "transparency_mode": mode,
            "music_source": music["source"],
            "music_rights_status": music["rights_status"],
            "fallback_policy": ("copy only when per-run music is absent and publication-approved"),
        },
        validation={
            "music_artifact_present": True,
            "music_provenance_present": True,
            "music_rights_status": music["rights_status"],
            "music_notice_present": True if music.get("notice_path") else None,
            "retained_raw_excluded_from_top_level": all(
                ".raw.png" not in path for path in artifacts
            ),
            "canonical_transparency_entries": sum(
                1 for entry in canonical if "transparency" in entry
            ),
        },
    )
    return ManifestWriteResult(
        manifest_path=str(manifest_path),
        manifest_provenance_path=str(provenance_path),
        music_path=str(music_path),
        music_provenance_path=str(music_meta),
        music_source=music["source"],
        music_rights_status=music["rights_status"],
        music_notice_path=music.get("notice_path"),
    )


def _collect_canonical_images(
    run_dir: Path, names: set[str], mode: TransparencyMode
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    canonical_names = sorted(
        name
        for name in names
        if name.endswith(".png") and not name.startswith(".") and not name.endswith(".raw.png")
    )
    for canonical_name in canonical_names:
        provenance_name = f"{canonical_name}.meta.json"
        if provenance_name not in names:
            raise ValueError(f"canonical artifact provenance is missing for {canonical_name}")
        sidecar = _read_sidecar(run_dir / provenance_name, canonical_name)
        _verify_artifact_binding(run_dir / canonical_name, sidecar, canonical_name)
        raw_name = re.sub(r"\.png$", ".raw.png", canonical_name, flags=re.IGNORECASE)
        if raw_name in names:
            raw_provenance = f"{raw_name}.meta.json"
            if raw_provenance not in names:
                raise ValueError(f"transparent artifact pair is incomplete for {canonical_name}")
            raw_sidecar = _read_sidecar(run_dir / raw_provenance, raw_name)
            _verify_artifact_binding(run_dir / raw_name, raw_sidecar, raw_name)
            transparency = _generated_transparency(
                run_dir,
                sidecar,
                raw_sidecar,
                mode,
                canonical_name,
                raw_name,
                provenance_name,
                raw_provenance,
            )
            results.append(
                to_canonical_manifest_entry(
                    {
                        "path": raw_name,
                        "provenancePath": raw_provenance,
                        "transparency": transparency,
                    }
                )
            )
            continue
        params = sidecar["params"]
        transparency = params.get("transparency")
        if isinstance(transparency, dict):
            results.append(
                {
                    "path": canonical_name,
                    "provenancePath": provenance_name,
                    "transparency": _derived_transparency(
                        run_dir,
                        names,
                        sidecar,
                        transparency,
                        mode,
                        canonical_name,
                        provenance_name,
                    ),
                }
            )
            continue
        metadata = params.get("metadata")
        opaque = isinstance(metadata, dict) and (
            metadata.get("stage") == "concept" or metadata.get("opaque") is True
        )
        if not opaque:
            raise ValueError(
                f"artifact {canonical_name} has neither transparency derivation "
                "nor opaque provenance"
            )
        results.append({"path": canonical_name, "provenancePath": provenance_name})
    return results


def _read_sidecar(path: Path, artifact_name: str) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"canonical provenance is invalid for {artifact_name}") from error
    if (
        not isinstance(parsed, dict)
        or parsed.get("schema_version") != 1
        or not isinstance(parsed.get("artifact"), dict)
        or not isinstance(parsed["artifact"].get("sha256"), str)
        or not isinstance(parsed.get("params"), dict)
    ):
        raise ValueError(f"canonical provenance is invalid for {artifact_name}")
    return parsed


def _generated_transparency(
    run_dir: Path,
    sidecar: dict[str, Any],
    raw_sidecar: dict[str, Any],
    mode: TransparencyMode,
    canonical: str,
    raw: str,
    canonical_meta: str,
    raw_meta: str,
) -> dict[str, Any]:
    transparency = sidecar["params"].get("transparency")
    if not isinstance(transparency, dict) or transparency.get("mode") != str(mode):
        raise ValueError(f"canonical transparency mode mismatch for {canonical}")
    raw_params = raw_sidecar["params"]
    raw_metadata = raw_params.get("metadata")
    if not isinstance(raw_metadata, dict) or raw_metadata.get("transparency_mode") != str(mode):
        raise ValueError(f"retained raw transparency mode mismatch for {canonical}")
    retained = transparency.get("retained_raw_path")
    if not isinstance(retained, str) or _run_relative_path(run_dir, retained) != raw:
        raise ValueError(f"retained raw lineage mismatch for {canonical}")
    raw_digest = _artifact_sha256(raw_sidecar, raw)
    canonical_digest = _artifact_sha256(sidecar, canonical)
    if transparency.get("raw_sha256") != raw_digest:
        raise ValueError(f"retained raw digest mismatch for {canonical}")
    if transparency.get("output_sha256") != canonical_digest:
        raise ValueError(f"canonical output digest mismatch for {canonical}")
    _validate_alpha_contract(sidecar, canonical)
    raw_validation = raw_sidecar.get("validation")
    if (
        not isinstance(raw_validation, dict)
        or raw_validation.get("exact_contract_dimensions") is not True
    ):
        raise ValueError(f"retained raw dimensions are unvalidated for {canonical}")
    validation = sidecar["validation"]
    if raw_validation.get("output_width") != validation.get("output_width") or raw_validation.get(
        "output_height"
    ) != validation.get("output_height"):
        raise ValueError(f"retained raw dimensions mismatch for {canonical}")
    tool = sidecar.get("tool")
    processor = transparency.get("processor")
    derivation: dict[str, Any] = {"kind": "ai-background-removal" if mode == "ai" else "chroma-key"}
    derivation["sourceSha256"] = raw_digest
    derivation["outputSha256"] = canonical_digest
    if (
        isinstance(tool, dict)
        and isinstance(tool.get("name"), str)
        and isinstance(tool.get("version"), str)
    ):
        derivation["tool"] = {"name": tool["name"], "version": tool["version"]}
    elif isinstance(processor, dict) and isinstance(processor.get("kind"), str):
        derivation["tool"] = {"name": processor["kind"], "version": "1"}
    return {
        "mode": mode,
        "canonicalPath": canonical,
        "retainedRawPath": raw,
        "canonicalProvenancePath": canonical_meta,
        "rawProvenancePath": raw_meta,
        "lineage": {
            "kind": "generated",
            "sourcePaths": [raw],
            "sourceProvenancePaths": [raw_meta],
        },
        "derivation": derivation,
    }


def _derived_transparency(
    run_dir: Path,
    names: set[str],
    sidecar: dict[str, Any],
    transparency: dict[str, Any],
    mode: TransparencyMode,
    canonical: str,
    canonical_meta: str,
) -> dict[str, Any]:
    if transparency.get("mode") != str(mode):
        raise ValueError(f"canonical transparency mode mismatch for {canonical}")
    source_path = transparency.get("source_path")
    source_paths_value = transparency.get("source_paths")
    if isinstance(source_path, str):
        source_values = [source_path]
    elif isinstance(source_paths_value, dict):
        source_values = [value for value in source_paths_value.values() if isinstance(value, str)]
    else:
        source_values = []
    if not source_values:
        raise ValueError(f"derived transparency lineage is missing for {canonical}")
    source_names = [_run_relative_path(run_dir, source) for source in source_values]
    source_meta = [f"{source}.meta.json" for source in source_names]
    for source, meta in zip(source_names, source_meta, strict=True):
        if source not in names or meta not in names:
            raise ValueError(f"derived transparency source is missing for {canonical}")
        source_sidecar = _read_sidecar(run_dir / meta, source)
        _verify_artifact_binding(run_dir / source, source_sidecar, source)
        source_transparency = source_sidecar["params"].get("transparency")
        if not isinstance(source_transparency, dict) or source_transparency.get("mode") != str(
            mode
        ):
            raise ValueError(f"derived transparency source mode mismatch for {canonical}")
    _validate_derived_hashes(sidecar, transparency, source_names, source_meta, run_dir, canonical)
    _validate_alpha_contract(sidecar, canonical)
    processor = transparency.get("processor")
    processor_name = (
        processor
        if isinstance(processor, str)
        else processor.get("kind", "")
        if isinstance(processor, dict)
        else ""
    )
    if "slice" in processor_name:
        kind = "png-slice"
    elif "composite" in processor_name:
        kind = "alpha-composite"
    else:
        raise ValueError(f"unknown derived transparency processor for {canonical}")
    derivation: dict[str, Any] = {"kind": kind}
    if isinstance(transparency.get("source_sha256"), str):
        derivation["sourceSha256"] = transparency["source_sha256"]
    if isinstance(transparency.get("output_sha256"), str):
        derivation["outputSha256"] = transparency["output_sha256"]
    tool = sidecar.get("tool")
    if (
        isinstance(tool, dict)
        and isinstance(tool.get("name"), str)
        and isinstance(tool.get("version"), str)
    ):
        derivation["tool"] = {"name": tool["name"], "version": tool["version"]}
    return {
        "mode": mode,
        "canonicalPath": canonical,
        "canonicalProvenancePath": canonical_meta,
        "derivation": derivation,
        "lineage": {
            "kind": "derived",
            "sourcePaths": source_names,
            "sourceProvenancePaths": source_meta,
        },
    }


def _run_relative_path(run_dir: Path, artifact_path: str) -> str:
    path = Path(artifact_path)
    resolved = path.resolve() if path.is_absolute() else (run_dir / path).resolve()
    try:
        relative = resolved.relative_to(run_dir.resolve())
    except ValueError as error:
        raise ValueError(
            "derived transparency source must stay inside the run directory"
        ) from error
    if str(relative) in {"", "."}:
        raise ValueError("derived transparency source must stay inside the run directory")
    return relative.as_posix()


def _artifact_sha256(sidecar: dict[str, Any], artifact_name: str) -> str:
    artifact = sidecar.get("artifact")
    digest = artifact.get("sha256") if isinstance(artifact, dict) else None
    if not isinstance(digest, str):
        raise ValueError(f"canonical provenance is invalid for {artifact_name}")
    return digest


def _verify_artifact_binding(path: Path, sidecar: dict[str, Any], artifact_name: str) -> None:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ValueError(f"canonical artifact is missing for {artifact_name}") from error
    artifact = sidecar.get("artifact")
    if (
        not isinstance(artifact, dict)
        or artifact.get("sha256") != hashlib.sha256(data).hexdigest()
        or artifact.get("bytes") != len(data)
    ):
        raise ValueError(f"canonical artifact binding mismatch for {artifact_name}")


def _validate_alpha_contract(sidecar: dict[str, Any], artifact_name: str) -> None:
    validation = sidecar.get("validation")
    if (
        not isinstance(validation, dict)
        or validation.get("alpha_nontrivial") is not True
        or validation.get("dimensions_preserved") is not True
        or not isinstance(validation.get("output_width"), int)
        or not isinstance(validation.get("output_height"), int)
        or int(validation["output_width"]) <= 0
        or int(validation["output_height"]) <= 0
        or not isinstance(validation.get("transparent_pixels"), int)
        or not isinstance(validation.get("nontransparent_pixels"), int)
        or int(validation["transparent_pixels"]) <= 0
        or int(validation["nontransparent_pixels"]) <= 0
    ):
        raise ValueError(f"canonical alpha validation is invalid for {artifact_name}")


def _validate_derived_hashes(
    sidecar: dict[str, Any],
    transparency: dict[str, Any],
    source_names: list[str],
    source_meta: list[str],
    run_dir: Path,
    canonical: str,
) -> None:
    output_digest = _artifact_sha256(sidecar, canonical)
    if transparency.get("output_sha256") != output_digest:
        raise ValueError(f"derived output digest mismatch for {canonical}")
    source_digests = {
        source: _artifact_sha256(_read_sidecar(run_dir / meta, source), source)
        for source, meta in zip(source_names, source_meta, strict=True)
    }
    recorded = transparency.get("source_hashes")
    if isinstance(recorded, list):
        recorded_digests: dict[str, str] = {}
        for item in recorded:
            if not isinstance(item, dict):
                raise ValueError(f"derived source digests are invalid for {canonical}")
            path = item.get("path")
            digest = item.get("sha256")
            if not isinstance(path, str) or not isinstance(digest, str):
                raise ValueError(f"derived source digests are invalid for {canonical}")
            recorded_digests[_run_relative_path(run_dir, path)] = digest
        if recorded_digests != source_digests:
            raise ValueError(f"derived source digest mismatch for {canonical}")
        return
    singular = transparency.get("source_sha256")
    if len(source_names) != 1 or singular != source_digests[source_names[0]]:
        raise ValueError(f"derived source digests are missing for {canonical}")


def _ensure_run_music_pair(target: Path, fallback: Path) -> dict[str, Any]:
    target_meta = Path(f"{target}.meta.json")
    if target.exists() or target_meta.exists():
        if not target.is_file() or not target_meta.is_file():
            raise ValueError("per-run music must include both artifact and provenance")
        copied_fallback = _existing_fallback_metadata(target, target_meta, fallback)
        if copied_fallback is not None:
            return copied_fallback
        sidecar = _json_object(target_meta, "per-run music provenance")
        return {
            "source": "per-run",
            "rights_status": _optional_rights_status(
                sidecar.get("rights"), "per-run music provenance"
            ),
        }
    fallback_meta = Path(f"{fallback}.meta.json")
    if not fallback.is_file() or not fallback_meta.is_file():
        raise ValueError(
            "scrolling-preview music is missing; generate a per-run artifact with the "
            "generate-music capability or provide a redistribution-approved bundled fallback"
        )
    validated = _validate_fallback(fallback, fallback_meta)
    notice_target = target.parent / validated["notice_name"]
    if notice_target.exists() and notice_target.read_bytes() != validated["notice_bytes"]:
        raise ValueError(
            f"bundled fallback notice target already exists: {validated['notice_name']}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    installed: list[Path] = []
    temporary: list[Path] = []
    try:
        for destination, data in (
            (target, validated["artifact_bytes"]),
            (target_meta, validated["sidecar_text"].encode()),
            *(() if notice_target.exists() else ((notice_target, validated["notice_bytes"]),)),
        ):
            handle, temp_name = tempfile.mkstemp(
                prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
            )
            temp = Path(temp_name)
            temporary.append(temp)
            with os.fdopen(handle, "wb") as stream:
                os.chmod(temp, 0o600)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, destination)
            temporary.remove(temp)
            installed.append(destination)
    except Exception:
        for path in installed:
            path.unlink(missing_ok=True)
        raise
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)
    return {
        "source": "generated-fallback",
        "rights_status": validated["rights"]["status"],
        "notice_path": str(notice_target),
    }


def _existing_fallback_metadata(
    target: Path, target_meta: Path, fallback: Path
) -> dict[str, Any] | None:
    fallback_meta = Path(f"{fallback}.meta.json")
    if not fallback.is_file() or not fallback_meta.is_file():
        return None
    try:
        if (
            target.read_bytes() != fallback.read_bytes()
            or target_meta.read_bytes() != fallback_meta.read_bytes()
        ):
            return None
    except OSError:
        return None
    validated = _validate_fallback(fallback, fallback_meta)
    notice_target = target.parent / validated["notice_name"]
    if not notice_target.is_file() or notice_target.read_bytes() != validated["notice_bytes"]:
        raise ValueError("bundled fallback notice is missing or does not match its source")
    return {
        "source": "generated-fallback",
        "rights_status": validated["rights"]["status"],
        "notice_path": str(notice_target),
    }


def _validate_fallback(fallback: Path, meta: Path) -> dict[str, Any]:
    artifact_bytes = fallback.read_bytes()
    sidecar_text = meta.read_text(encoding="utf-8")
    try:
        sidecar = json.loads(sidecar_text)
    except json.JSONDecodeError as error:
        raise ValueError("bundled fallback provenance is not valid JSON") from error
    if (
        not isinstance(sidecar, dict)
        or sidecar.get("schema_version") != 1
        or not isinstance(sidecar.get("artifact"), dict)
    ):
        raise ValueError("bundled fallback provenance is invalid")
    digest = sidecar["artifact"]
    if digest.get("sha256") != hashlib.sha256(artifact_bytes).hexdigest():
        raise ValueError("bundled fallback artifact digest does not match its provenance")
    if digest.get("bytes") != len(artifact_bytes):
        raise ValueError("bundled fallback artifact byte count does not match its provenance")
    rights = _parse_rights(sidecar.get("rights"))
    if rights["status"] != "redistribution-approved":
        raise ValueError(
            "bundled fallback is not publication-approved "
            f"(rights.status={rights['status']}); generate per-run music or record "
            "an approved asset license and notice"
        )
    _assert_publishable_references(sidecar, rights)
    notice_name = _publication_notice_name(rights["notice"])
    fallback_directory = fallback.parent.resolve()
    notice = (fallback_directory / notice_name).resolve()
    try:
        notice.relative_to(fallback_directory)
    except ValueError as error:
        raise ValueError("bundled fallback rights notice must stay beside the artifact") from error
    if not notice.is_file():
        raise ValueError(f"bundled fallback rights notice is missing: {notice_name}")
    notice_bytes = notice.read_bytes()
    if not notice_bytes:
        raise ValueError(f"bundled fallback rights notice is empty: {notice_name}")
    return {
        "artifact_bytes": artifact_bytes,
        "sidecar_text": sidecar_text,
        "notice_bytes": notice_bytes,
        "notice_name": notice_name,
        "rights": rights,
    }


def _parse_rights(value: object) -> dict[str, Any]:
    try:
        rights = ArtifactRights.model_validate(value)
    except ValueError as error:
        raise ValueError("bundled fallback rights are missing or invalid") from error
    return rights.model_dump(mode="json")


def _optional_rights_status(value: object, label: str) -> MusicRightsStatus:
    if value is None:
        return "unrecorded"
    try:
        status = _parse_rights(value)["status"]
        if status == "unreviewed":
            return "unreviewed"
        if status == "restricted":
            return "restricted"
        if status == "redistribution-approved":
            return "redistribution-approved"
        raise ValueError(f"{label} rights are invalid")
    except ValueError as error:
        raise ValueError(f"{label} rights are invalid") from error


def _assert_publishable_references(sidecar: dict[str, Any], rights: dict[str, Any]) -> None:
    for key in ("references", "refs"):
        refs = sidecar.get(key)
        if refs is None:
            continue
        if not isinstance(refs, list) or not all(isinstance(value, str) for value in refs):
            raise ValueError(f"bundled fallback {key} are invalid")
        for reference in refs:
            _assert_portable(reference, key)
    inputs = sidecar.get("inputs")
    if inputs is not None:
        if not isinstance(inputs, list):
            raise ValueError("bundled fallback inputs are invalid")
        for item in inputs:
            if not isinstance(item, dict) or not isinstance(item.get("ref"), str):
                raise ValueError("bundled fallback input reference is invalid")
            _assert_portable(item["ref"], "input ref")
    for basis in rights["basis"]:
        _assert_portable(basis, "rights basis")


def _assert_portable(reference: str, label: str) -> None:
    if not is_portable_artifact_reference(reference):
        raise ValueError(f"bundled fallback {label} must use a stable non-temporary reference")


def _publication_notice_name(notice: str) -> str:
    stripped = notice.strip()
    if (
        not stripped
        or stripped != Path(stripped).name
        or stripped in {".", ".."}
        or "\\" in stripped
        or re.match(r"^[a-z][a-z0-9+.-]*:", stripped, re.IGNORECASE)
    ):
        raise ValueError("bundled fallback rights notice must name an adjacent file")
    return stripped


def _json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} is not valid JSON") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be an object")
    return parsed


def _write_local_artifact_pair(
    path: Path,
    payload: bytes,
    *,
    media_type: str,
    prompt: str,
    refs: list[str],
    params: dict[str, Any],
    validation: dict[str, Any],
) -> Path:
    artifact = BinaryArtifact(data=payload, media_type=media_type)
    provenance = ProvenanceInput(
        provider="local",
        model="deterministic-manifest",
        prompt=prompt,
        refs=refs,
        params=params,
        validation=validation,
        component=SoftwareIdentity(name="@stage-gen/stage-gen", version="0.0.0"),
        tool=SoftwareIdentity(name="scrolling-preview-manifest", version="1"),
        attempts=1,
    )
    sidecar = Path(f"{path}.meta.json")
    if path.is_file() and sidecar.is_file() and path.read_bytes() == payload:
        try:
            existing = ArtifactProvenance.model_validate_json(sidecar.read_text(encoding="utf-8"))
            expected = build_artifact_provenance(
                artifact,
                provenance.model_copy(update={"timestamp": existing.ts}),
            )
        except (OSError, ValueError):
            pass
        else:
            if existing == expected:
                return sidecar
    return write_artifact_with_provenance(path, artifact, provenance)
