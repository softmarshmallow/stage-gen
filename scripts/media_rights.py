"""Generated-media publication validation without media decoding."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, cast

JsonObject = dict[str, Any]

MEDIA_EXTENSIONS = frozenset(
    {
        ".aac",
        ".flac",
        ".gif",
        ".jpeg",
        ".jpg",
        ".m4a",
        ".mp3",
        ".mp4",
        ".ogg",
        ".png",
        ".wav",
        ".webm",
        ".webp",
    }
)
AUDIO_EXTENSIONS = frozenset({".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"})
IMAGE_EXTENSIONS = frozenset({".gif", ".jpeg", ".jpg", ".png", ".webp"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".webm"})
CAPTURE_KINDS = frozenset({"image", "video"})
MEDIA_TYPES_BY_EXTENSION = {
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
    ".ogg": "audio/ogg",
    ".png": "image/png",
    ".wav": "audio/wav",
    ".webm": "video/webm",
    ".webp": "image/webp",
}
MEDIA_SIZE_LIMITS = {
    "audio": 20 * 1024 * 1024,
    "image": 5 * 1024 * 1024,
    "video": 25 * 1024 * 1024,
}
MAX_TOTAL_MEDIA_BYTES = 50 * 1024 * 1024
SHA256 = re.compile(r"^[a-f0-9]{64}$")
ISO_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$")
UNSTABLE_REF = re.compile(
    r"^(?:file:|data:|[A-Za-z]:[\\/])|(?:^|[\\/])(?:tmp|private/tmp|var/folders|Users)(?:[\\/]|$)|(?:^|[\\/])\.\.(?:[\\/]|$)",
    re.IGNORECASE,
)
PLACEHOLDER = re.compile(r"^(?:tbd|todo|pending|unknown|none|n/a)$", re.IGNORECASE)
PROVENANCE_ONLY = re.compile(
    r"^\s*(?:provider|model)?\s*provenance(?:\s+only)?[.!]?\s*$", re.IGNORECASE
)
LISTENING_RESULT = "no recognizable protected composition, lyrics, performer, voice, brand, or mark"
VISUAL_REVIEW_RESULT = "pass"
MAX_SAFE_INTEGER = 9_007_199_254_740_991


@dataclass(frozen=True, slots=True)
class PublicationCheckResult:
    failures: tuple[str, ...]
    media_count: int


def _record(value: object) -> JsonObject | None:
    if not isinstance(value, dict):
        return None
    return cast(JsonObject, value)


def _stable_text(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value.strip()) > 2
        and PLACEHOLDER.fullmatch(value.strip()) is None
    )


def _valid_timestamp(value: object) -> bool:
    if not isinstance(value, str) or ISO_TIMESTAMP.fullmatch(value) is None:
        return False
    try:
        datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        return False
    return True


def _safe_integer(value: object) -> bool:
    return type(value) is int and abs(value) <= MAX_SAFE_INTEGER


def _positive_safe_integer(value: object) -> bool:
    return _safe_integer(value) and cast(int, value) > 0


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def _safe_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    pure = PurePosixPath(value)
    if not pure.parts or pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        return False
    return pure.as_posix() == value


def _safe_repo_path(repo: Path, value: object) -> bool:
    if not _safe_relative_path(value):
        return False
    pure = PurePosixPath(cast(str, value))
    try:
        absolute = (repo / pure).resolve(strict=False)
        relative = absolute.relative_to(repo.resolve(strict=False)).as_posix()
    except (OSError, RuntimeError, ValueError):
        return False
    return relative == value


def _finite_number(value: object) -> bool:
    return type(value) in {int, float} and math.isfinite(cast(float, value))


def _valid_capture_params(value: object, *, depth: int = 0) -> bool:
    if depth > 8:
        return False
    if value is None or isinstance(value, (str, bool)):
        return True
    if type(value) is int:
        return abs(value) <= MAX_SAFE_INTEGER
    if type(value) is float:
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_valid_capture_params(item, depth=depth + 1) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str)
            and bool(key.strip())
            and _valid_capture_params(item, depth=depth + 1)
            for key, item in value.items()
        )
    return False


def _media_kind(entry: JsonObject, path: str, errors: list[str]) -> str | None:
    extension = Path(path).suffix.lower()
    if extension in AUDIO_EXTENSIONS:
        inferred = "audio"
    elif extension in IMAGE_EXTENSIONS:
        inferred = "image"
    elif extension in VIDEO_EXTENSIONS:
        inferred = "video"
    else:
        errors.append("inventory media path has an unsupported extension")
        return None
    declared = entry.get("kind")
    if inferred == "audio":
        if declared not in {None, "audio"}:
            errors.append("inventory kind does not match the audio artifact")
    elif declared not in CAPTURE_KINDS:
        errors.append("inventory kind must explicitly declare video or image")
    elif declared != inferred:
        errors.append("inventory kind does not match the artifact extension")
    return inferred


def _validate_artifact_media_type(
    path: str,
    kind: str | None,
    artifact: JsonObject | None,
    errors: list[str],
) -> None:
    expected = MEDIA_TYPES_BY_EXTENSION.get(Path(path).suffix.lower())
    media_type = artifact.get("media_type") if artifact is not None else None
    if expected is None or media_type != expected:
        errors.append("sidecar artifact media_type must match the artifact extension")
    if kind == "video" and expected != "video/mp4":
        errors.append("browser capture video must use MP4")


def _validate_capture_source_record(
    capture: JsonObject,
    label: str,
    errors: list[str],
) -> str | None:
    source = _record(capture.get(label))
    if source is None:
        errors.append(f"sidecar.capture.{label} must record a path and SHA-256 digest")
        return None
    path = source.get("path")
    if not _safe_relative_path(path):
        errors.append(f"sidecar.capture.{label}.path must be repository-relative and canonical")
    if not _valid_digest(source.get("sha256")):
        errors.append(f"sidecar.capture.{label}.sha256 must be a content digest")
    return path if isinstance(path, str) else None


def _validate_capture_historical_record(
    capture: JsonObject,
    label: str,
    errors: list[str],
    *,
    required: bool,
) -> None:
    generator = _record(capture.get(label))
    if generator is None:
        if required:
            errors.append(
                f"sidecar.capture.{label} must preserve the capture-time content identity"
            )
        return
    path = generator.get("pathAtCapture")
    digest = generator.get("sha256")
    reference = generator.get("ref")
    if not _safe_relative_path(path):
        errors.append(
            f"sidecar.capture.{label}.pathAtCapture must be repository-relative and canonical"
        )
    if not _valid_digest(digest):
        errors.append(f"sidecar.capture.{label}.sha256 must be a content digest")
    if not isinstance(digest, str) or reference != f"sha256:{digest}":
        errors.append(f"sidecar.capture.{label}.ref must match its sha256 content identifier")


def _validate_capture_generator_record(capture: JsonObject, errors: list[str]) -> None:
    _validate_capture_historical_record(capture, "generator", errors, required=True)
    if "fixtureGenerator" in capture:
        _validate_capture_historical_record(
            capture,
            "fixtureGenerator",
            errors,
            required=False,
        )


def _validate_mp4_constraints(capture: JsonObject, errors: list[str]) -> None:
    mp4 = _record(capture.get("mp4"))
    if mp4 is None:
        errors.append("sidecar.capture.mp4 constraints are required for video")
        return
    if mp4.get("container") != "mp4":
        errors.append("sidecar.capture.mp4.container must be mp4")
    if mp4.get("video_codec") != "h264":
        errors.append("sidecar.capture.mp4.video_codec must be h264")
    if mp4.get("pixel_format") != "yuv420p":
        errors.append("sidecar.capture.mp4.pixel_format must be yuv420p")
    for field, maximum in (("width", 3840), ("height", 2160)):
        value = mp4.get(field)
        if (
            not _positive_safe_integer(value)
            or cast(int, value) > maximum
            or cast(int, value) % 2 != 0
        ):
            errors.append(f"sidecar.capture.mp4.{field} must be a supported even integer")
    frame_rate = mp4.get("frame_rate")
    if not _finite_number(frame_rate) or not 0 < cast(float, frame_rate) <= 60:
        errors.append("sidecar.capture.mp4.frame_rate must be within (0, 60]")
    duration = mp4.get("duration_seconds")
    if not _finite_number(duration) or not 0 < cast(float, duration) <= 120:
        errors.append("sidecar.capture.mp4.duration_seconds must be within (0, 120]")
    if mp4.get("fast_start") is not True:
        errors.append("sidecar.capture.mp4.fast_start must be true")
    if "audio_codec" not in mp4 or mp4.get("audio_codec") not in {None, "aac"}:
        errors.append("sidecar.capture.mp4.audio_codec must be null or aac")


def _validate_capture_metadata(sidecar: JsonObject, kind: str, errors: list[str]) -> None:
    if type(sidecar.get("schema_version")) is not int or sidecar.get("schema_version") != 1:
        errors.append("browser capture sidecar schema_version must be 1")
    capture = _record(sidecar.get("capture"))
    if capture is None:
        errors.append("sidecar.capture metadata is required for browser capture")
        return
    for field in ("tool", "version"):
        if not _stable_text(capture.get(field)):
            errors.append(f"sidecar.capture.{field} must be a stable value")
    params = capture.get("params")
    if not isinstance(params, dict) or not params or not _valid_capture_params(params):
        errors.append("sidecar.capture.params must be a non-empty JSON object")
    _validate_capture_generator_record(capture, errors)
    paths = [
        path
        for label in ("source", "verifier", "fixture", "timeline")
        if (path := _validate_capture_source_record(capture, label, errors)) is not None
    ]
    if len(paths) == 4 and len(set(paths)) != 4:
        errors.append(
            "sidecar.capture current source, verifier, fixture, and timeline paths must be distinct"
        )
    if kind == "video":
        _validate_mp4_constraints(capture, errors)
    elif "mp4" in capture:
        errors.append("sidecar.capture.mp4 is only valid for video")


def _validate_source_inputs(sidecar: JsonObject, errors: list[str]) -> None:
    inputs = sidecar.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        errors.append("sidecar.inputs must contain content-addressed source records")
        return
    for index, raw_input in enumerate(inputs):
        source_input = _record(raw_input)
        if source_input is None:
            errors.append(f"sidecar.inputs[{index}] must be an object")
            continue
        reference = source_input.get("ref")
        digest = source_input.get("sha256")
        byte_count = source_input.get("bytes")
        if (
            not _stable_text(reference)
            or not isinstance(reference, str)
            or UNSTABLE_REF.search(reference) is not None
        ):
            errors.append(f"sidecar.inputs[{index}].ref must be a stable non-file identifier")
        if not _valid_digest(digest):
            errors.append(f"sidecar.inputs[{index}].sha256 must be a content digest")
        elif reference != f"sha256:{digest}":
            errors.append(f"sidecar.inputs[{index}].ref must match its sha256 content identifier")
        if not _positive_safe_integer(byte_count):
            errors.append(f"sidecar.inputs[{index}].bytes must be a positive integer")


def _validate_rights(
    entry: JsonObject,
    sidecar: JsonObject,
    *,
    kind: str | None,
    errors: list[str],
) -> None:
    if entry.get("reviewStatus") != "repository-approved":
        errors.append("inventory reviewStatus must be repository-approved")
    rights = _record(sidecar.get("rights"))
    if rights is None:
        errors.append("sidecar.rights is required for repository publication")
    else:
        if rights.get("status") != "redistribution-approved":
            errors.append("sidecar.rights.status must be redistribution-approved")
        for key, label in (("notice", "notice"), ("license_id", "license_id")):
            value = rights.get(key)
            if (
                not _stable_text(value)
                or not isinstance(value, str)
                or UNSTABLE_REF.search(value) is not None
            ):
                errors.append(f"sidecar.rights.{label} must be a stable reviewed value")
        basis_value = rights.get("basis")
        valid_basis = (
            isinstance(basis_value, list)
            and bool(basis_value)
            and all(
                _stable_text(item) and isinstance(item, str) and UNSTABLE_REF.search(item) is None
                for item in basis_value
            )
        )
        if not valid_basis:
            errors.append("sidecar.rights.basis must contain stable reviewed values")
        elif isinstance(basis_value, list) and all(
            PROVENANCE_ONLY.fullmatch(cast(str, item)) is not None for item in basis_value
        ):
            errors.append("sidecar.rights.basis cannot rely only on provider provenance")
        if not _valid_timestamp(rights.get("reviewed_at")):
            errors.append("sidecar.rights.reviewed_at must be an ISO UTC timestamp")
        if rights.get("license_id") == "BSD-3-Clause":
            errors.append("the repository source license cannot be inherited by generated media")
        if rights.get("license_id") == "CC0-1.0" and not (
            isinstance(basis_value, list)
            and any(
                isinstance(item, str)
                and re.search("artifact-specific rights-holder dedication", item, re.IGNORECASE)
                for item in basis_value
            )
        ):
            errors.append("CC0 requires an artifact-specific rights-holder dedication basis")
    basis = rights.get("basis") if rights is not None else None
    if kind == "audio":
        _validate_audio_review(entry, basis, errors)
    elif kind in CAPTURE_KINDS:
        _validate_visual_review(entry, basis, errors)


def _validate_audio_review(entry: JsonObject, basis: object, errors: list[str]) -> None:
    synth_id = _record(entry.get("synthId"))
    if synth_id is None:
        errors.append("inventory synthId review record is required")
    else:
        if synth_id.get("expected") is not True:
            errors.append("inventory synthId.expected must record the expected watermark")
        if not isinstance(synth_id.get("independentlyVerified"), bool):
            errors.append("inventory synthId.independentlyVerified must be explicit")
    review = _record(entry.get("listeningReview"))
    if review is None or review.get("status") != "approved":
        errors.append("inventory listeningReview.status must be approved")
        return
    if not _stable_text(review.get("reviewedBy")):
        errors.append("inventory listeningReview.reviewedBy is required")
    if not _stable_text(review.get("authorityBasis")):
        errors.append("inventory listeningReview.authorityBasis is required")
    if review.get("result") != LISTENING_RESULT:
        errors.append("inventory listeningReview.result must record the protected-material finding")
    if review.get("approvalScope") != "project-controlled rights, if any":
        errors.append("inventory listeningReview.approvalScope must remain artifact-scoped")
    if not _valid_timestamp(review.get("reviewedAt")):
        errors.append("inventory listeningReview.reviewedAt must be an ISO UTC timestamp")
    attestation_id = review.get("attestationId")
    if (
        not _stable_text(attestation_id)
        or not isinstance(attestation_id, str)
        or UNSTABLE_REF.search(attestation_id) is not None
    ):
        errors.append("inventory listeningReview.attestationId must be stable")
    elif not isinstance(basis, list) or attestation_id not in basis:
        errors.append("sidecar.rights.basis must include the listening attestation identifier")
    if not _valid_timestamp(review.get("attestedAt")) or review.get("attestedAt") != review.get(
        "reviewedAt"
    ):
        errors.append("inventory listeningReview.attestedAt must match reviewedAt")


def _validate_visual_review(entry: JsonObject, basis: object, errors: list[str]) -> None:
    if entry.get("synthIdExpected") is not False:
        errors.append("inventory synthIdExpected must explicitly be false for browser capture")
    review = _record(entry.get("visualReview"))
    if review is None or review.get("status") != "approved":
        errors.append("inventory visualReview.status must be approved")
        return
    if review.get("result") != VISUAL_REVIEW_RESULT:
        errors.append("inventory visualReview.result must be pass")
    if review.get("independent") is not True:
        errors.append("inventory visualReview.independent must be true")
    if not _stable_text(review.get("reviewedBy")):
        errors.append("inventory visualReview.reviewedBy is required")
    if not _stable_text(review.get("authorityBasis")):
        errors.append("inventory visualReview.authorityBasis is required")
    if not _valid_timestamp(review.get("reviewedAt")):
        errors.append("inventory visualReview.reviewedAt must be an ISO UTC timestamp")
    attestation_id = review.get("attestationId")
    if (
        not _stable_text(attestation_id)
        or not isinstance(attestation_id, str)
        or UNSTABLE_REF.search(attestation_id) is not None
    ):
        errors.append("inventory visualReview.attestationId must be stable")
    elif not isinstance(basis, list) or attestation_id not in basis:
        errors.append("sidecar.rights.basis must include the visual attestation identifier")
    if not _valid_timestamp(review.get("attestedAt")) or review.get("attestedAt") != review.get(
        "reviewedAt"
    ):
        errors.append("inventory visualReview.attestedAt must match reviewedAt")


def validate_published_media_record(value: object) -> list[str]:
    wrapper = _record(value)
    if wrapper is None:
        return ["inventory entry path is required"]
    entry = _record(wrapper.get("entry"))
    observed = _record(wrapper.get("observed"))
    sidecar = _record(wrapper.get("sidecar"))
    if entry is None or not _stable_text(entry.get("path")):
        return ["inventory entry path is required"]
    if sidecar is None:
        return ["sidecar must be a JSON object"]
    errors: list[str] = []
    path = cast(str, entry["path"])
    kind = _media_kind(entry, path, errors)
    observed_digest = observed.get("sha256") if observed is not None else None
    observed_bytes = observed.get("bytes") if observed is not None else None
    if not _valid_digest(observed_digest) or not _positive_safe_integer(observed_bytes):
        errors.append("observed media digest and byte size are required")
    elif kind is not None and cast(int, observed_bytes) > MEDIA_SIZE_LIMITS[kind]:
        errors.append(f"{kind} exceeds the Git publication size limit")
    artifact = _record(sidecar.get("artifact"))
    if artifact is None or artifact.get("sha256") != observed_digest:
        errors.append("sidecar artifact digest does not match media bytes")
    artifact_bytes = artifact.get("bytes") if artifact is not None else None
    if not _positive_safe_integer(artifact_bytes) or artifact_bytes != observed_bytes:
        errors.append("sidecar artifact byte size does not match media bytes")
    _validate_artifact_media_type(path, kind, artifact, errors)
    if kind == "audio":
        _validate_source_inputs(sidecar, errors)
    elif kind in CAPTURE_KINDS:
        _validate_capture_metadata(sidecar, kind, errors)
    _validate_rights(entry, sidecar, kind=kind, errors=errors)
    return errors


def validate_published_media_copy(value: object) -> list[str]:
    wrapper = _record(value)
    if wrapper is None:
        return ["copyOf must name an inventoried canonical artifact"]
    entry = _record(wrapper.get("entry"))
    canonical_entry = _record(wrapper.get("canonicalEntry"))
    observed = _record(wrapper.get("observed"))
    canonical_observed = _record(wrapper.get("canonicalObserved"))
    if entry is None or not _stable_text(entry.get("copyOf")):
        return ["copyOf must name an inventoried canonical artifact"]
    errors: list[str] = []
    if canonical_entry is None or canonical_entry.get("path") != entry.get("copyOf"):
        errors.append("copyOf must resolve to an inventoried canonical artifact")
    for field, label in (
        ("sha256", "media bytes"),
        ("sidecarSha256", "provenance sidecar"),
        ("noticeSha256", "rights notice"),
    ):
        digest = observed.get(field) if observed is not None else None
        canonical_digest = canonical_observed.get(field) if canonical_observed is not None else None
        if not _valid_digest(digest) or not _valid_digest(canonical_digest):
            errors.append(f"{label} copy digests are required")
        elif digest != canonical_digest:
            errors.append(f"{label} must match copyOf exactly")
    return errors


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_capture_source_files(
    repo: Path,
    media_path: str,
    sidecar: JsonObject,
    failures: list[str],
) -> None:
    capture = _record(sidecar.get("capture"))
    if capture is None:
        return
    for label in ("source", "verifier", "fixture", "timeline"):
        source = _record(capture.get(label))
        path = source.get("path") if source is not None else None
        digest = source.get("sha256") if source is not None else None
        if not _safe_repo_path(repo, path) or path == media_path:
            failures.append(f"{media_path}: sidecar.capture.{label}.path is unsafe")
            continue
        source_path = repo / cast(str, path)
        try:
            source_path.lstat()
        except OSError:
            failures.append(f"{media_path}: sidecar.capture.{label} file is missing")
            continue
        if source_path.is_symlink() or not source_path.is_file():
            failures.append(
                f"{media_path}: sidecar.capture.{label} must be a non-symlink regular file"
            )
        elif _valid_digest(digest) and _sha256_file(source_path) != digest:
            failures.append(f"{media_path}: sidecar.capture.{label} digest does not match")


def _discover_media(repo: Path, roots: list[object], failures: list[str]) -> list[str]:
    media: list[str] = []

    def visit(directory: Path) -> None:
        for candidate in sorted(directory.iterdir()):
            relative = candidate.relative_to(repo).as_posix()
            if candidate.is_symlink():
                failures.append(f"{relative}: generated-media roots cannot contain symlinks")
            elif candidate.is_dir():
                visit(candidate)
            elif candidate.suffix.lower() in MEDIA_EXTENSIONS:
                media.append(relative)

    for root in roots:
        if not _safe_repo_path(repo, root):
            failures.append("generated-media inventory root is unsafe")
            continue
        root_path = repo / cast(str, root)
        if not root_path.exists():
            failures.append(f"generated-media inventory root is missing: {root}")
        elif root_path.is_symlink():
            failures.append(f"{root}: generated-media roots cannot contain symlinks")
        elif not root_path.is_dir():
            failures.append(f"generated-media inventory root is not a directory: {root}")
        else:
            visit(root_path)
    return sorted(media)


def check_generated_media_publication(repo: Path, inventory_path: Path) -> PublicationCheckResult:
    failures: list[str] = []
    try:
        inventory = _record(json.loads(inventory_path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        inventory = None
    if inventory is None:
        return PublicationCheckResult(("generated-media inventory is missing or invalid JSON",), 0)
    schema_version = inventory.get("schemaVersion")
    if type(schema_version) is not int or schema_version != 1:
        return PublicationCheckResult(("generated-media inventory schemaVersion must be 1",), 0)
    roots = inventory.get("roots")
    media_entries = inventory.get("media")
    if not isinstance(roots, list) or not isinstance(media_entries, list):
        return PublicationCheckResult(
            ("generated-media inventory roots and media must be arrays",), 0
        )

    discovered = _discover_media(repo, roots, failures)
    total_media_bytes = sum((repo / path).stat().st_size for path in discovered)
    if total_media_bytes > MAX_TOTAL_MEDIA_BYTES:
        failures.append("generated media exceeds the Git publication total-size limit")
    entries: dict[str, JsonObject] = {}
    for raw_entry in media_entries:
        entry = _record(raw_entry)
        path = entry.get("path") if entry is not None else None
        if entry is None or not _safe_repo_path(repo, path):
            failures.append("generated-media inventory contains an unsafe media path")
            continue
        path_text = cast(str, path)
        if path_text in entries:
            failures.append(f"{path_text}: duplicate inventory entry")
        entries[path_text] = entry
    for path in discovered:
        if path not in entries:
            failures.append(f"{path}: binary media is not enumerated in the inventory")

    observations: dict[str, JsonObject] = {}
    capture_notice_paths: set[str] = set()
    for path, entry in entries.items():
        if path not in discovered:
            failures.append(f"{path}: inventory entry does not resolve to discovered binary media")
            continue
        absolute = repo / path
        sidecar_path = Path(f"{absolute}.meta.json")
        if not sidecar_path.exists():
            failures.append(f"{path}: adjacent provenance sidecar is missing")
            continue
        if sidecar_path.is_symlink() or not sidecar_path.is_file():
            failures.append(f"{path}: adjacent provenance sidecar must be a regular file")
            continue
        try:
            sidecar_bytes = sidecar_path.read_bytes()
            sidecar = _record(json.loads(sidecar_bytes.decode("utf-8")))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            sidecar = None
            sidecar_bytes = b""
        if sidecar is None:
            failures.append(f"{path}: adjacent provenance sidecar is invalid JSON")
            continue
        observed: JsonObject = {
            "bytes": absolute.stat().st_size,
            "sha256": _sha256_file(absolute),
            "sidecarSha256": hashlib.sha256(sidecar_bytes).hexdigest(),
            "noticeSha256": None,
        }
        rights = _record(sidecar.get("rights"))
        notice = rights.get("notice") if rights is not None else None
        if not isinstance(notice, str) or Path(notice).name != notice or notice in {".", ".."}:
            failures.append(f"{path}: sidecar rights notice must name an adjacent file")
        else:
            notice_path = absolute.parent / notice
            if not notice_path.exists():
                failures.append(f"{path}: sidecar rights notice is missing")
            elif notice_path.is_symlink() or not notice_path.is_file():
                failures.append(f"{path}: sidecar rights notice must be a regular file")
            else:
                observed["noticeSha256"] = _sha256_file(notice_path)
                kind = _media_kind(entry, path, [])
                if kind in CAPTURE_KINDS:
                    capture_notice_paths.add(notice_path.relative_to(repo).as_posix())
        observations[path] = observed
        if _media_kind(entry, path, []) in CAPTURE_KINDS:
            _validate_capture_source_files(repo, path, sidecar, failures)
        for failure in validate_published_media_record(
            {"entry": entry, "observed": observed, "sidecar": sidecar}
        ):
            failures.append(f"{path}: {failure}")

    if len(capture_notice_paths) > 1:
        failures.append("browser capture video and poster must share one adjacent rights notice")

    for path, entry in entries.items():
        copy_of = entry.get("copyOf")
        if copy_of is None:
            continue
        if not _safe_repo_path(repo, copy_of) or copy_of == path:
            failures.append(f"{path}: copyOf is unsafe or self-referential")
            continue
        canonical_path = cast(str, copy_of)
        for failure in validate_published_media_copy(
            {
                "entry": entry,
                "canonicalEntry": entries.get(canonical_path),
                "observed": observations.get(path),
                "canonicalObserved": observations.get(canonical_path),
            }
        ):
            failures.append(f"{path}: {failure}")
    return PublicationCheckResult(tuple(failures), len(discovered))
