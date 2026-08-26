"""Generated-media publication validation with artifact-specific media inspection."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, cast
from urllib.parse import parse_qsl, urlsplit

from stage_gen.media import inspect_image

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
MAX_TOTAL_MEDIA_BYTES = 100 * 1024 * 1024
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
GENERATED_IMAGE = "generated_image"
GENERATED_IMAGE_DERIVATIVE = "generated_image_derivative"
GAME_CONCEPT_COVER = "game_concept_cover_v1"
CONCEPT_GALLERY_PREFIX = ("concept-studio", "gallery")
CONCEPT_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
THEME_ART_DIRECTION_COMPARISON = "theme_art_direction_comparison_v1"
LOWER_SNAKE_FIELD = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
HTTP_URL = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
FILE_OR_DATA_REF = re.compile(r"\bfile:|\bdata:[^,\s]*,", re.IGNORECASE)
ABSOLUTE_UNIX_PATH = re.compile(
    r"(?:^|[\s\"'(<>=:\[,;])/(?:[^/\s\"'<>(),;]+/)*[^/\s\"'<>(),;]+"
    r"(?=$|[\s\"'<>),;\]])",
    re.IGNORECASE,
)
TILDE_PATH = re.compile(r"(?:^|[\s\"'(<>=:])~(?:[^/\\\s]+)?(?:[/\\]|$)")
WINDOWS_DRIVE_PATH = re.compile(r"(?<![A-Za-z0-9+.-])[A-Za-z]:[\\/]")
TEMPORARY_RELATIVE_PATH = re.compile(
    r"(?:^|[\\/\s])(?:tmp|private[\\/]tmp|var[\\/]folders)(?:[\\/]|$)",
    re.IGNORECASE,
)
PARENT_PATH_SEGMENT = re.compile(r"(?:^|[\\/])\.\.(?:[\\/]|$)")
AUTHORIZATION_VALUE = re.compile(
    r"\b(?:authorization|proxy-authorization)\s*:\s*(?:"
    r"(?:bearer|basic|key|token)\s+[A-Za-z0-9._~+/=-]{8,}|"
    r"(?:sk|rk)-[A-Za-z0-9_-]{16,}|[A-Za-z0-9._~+/=-]{20,})"
    r"(?=$|[\s,;])|"
    r"\b(?:api[-_ ]?key|access[-_ ]?token)\s*[:=]\s*[A-Za-z0-9._~+/=-]{8,}|"
    r"\bbearer\s+[A-Za-z0-9._~+/=-]{8,}|\b(?:sk|rk)-[A-Za-z0-9_-]{16,}",
    re.IGNORECASE,
)
SIGNED_QUERY_VALUE = re.compile(
    r"(?:\?|&)(?:access_token|api_key|client_secret|expires|password|se|sig|signature|token|"
    r"x-amz-credential|x-amz-security-token|x-amz-signature|x-goog-credential|"
    r"x-goog-signature)=",
    re.IGNORECASE,
)
SIGNED_QUERY_FIELDS = frozenset(
    {
        "access_token",
        "api_key",
        "client_secret",
        "expires",
        "password",
        "se",
        "sig",
        "signature",
        "token",
        "x-amz-credential",
        "x-amz-security-token",
        "x-amz-signature",
        "x-goog-credential",
        "x-goog-signature",
    }
)
THEME_HANDLE_NAMES = (
    "sexual_content",
    "nudity_exposure",
    "hostile_action",
    "injury_detail",
    "substance_depiction",
    "threat_disturbance",
)


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


def _utf8_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _theme_identity_digest(canonical: str, skill_name: str, skill_digest: str) -> str:
    identity = json.dumps(
        {
            "canonical_theme_json": canonical,
            "theme_skill_name": skill_name,
            "theme_skill_sha256": skill_digest,
        },
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    )
    return _utf8_digest(identity)


def _has_non_lower_snake_key(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            not isinstance(key, str)
            or LOWER_SNAKE_FIELD.fullmatch(key) is None
            or _has_non_lower_snake_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_has_non_lower_snake_key(item) for item in value)
    return False


def _contains_unstable_ref(value: object) -> bool:
    if isinstance(value, str):
        return UNSTABLE_REF.search(value) is not None
    if isinstance(value, dict):
        return any(_contains_unstable_ref(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_unstable_ref(item) for item in value)
    return False


def _string_contains_signed_url(value: str) -> bool:
    if SIGNED_QUERY_VALUE.search(value) is not None:
        return True
    for match in HTTP_URL.finditer(value):
        try:
            parsed = urlsplit(match.group(0).rstrip(".,);]"))
            query = parse_qsl(parsed.query, keep_blank_values=True)
        except ValueError:
            return True
        if parsed.username is not None or parsed.password is not None:
            return True
        if any(key.lower() in SIGNED_QUERY_FIELDS for key, _item in query):
            return True
    return False


def _string_contains_filesystem_ref(value: str) -> bool:
    if FILE_OR_DATA_REF.search(value) is not None:
        return True
    without_urls = HTTP_URL.sub("", value)
    return any(
        pattern.search(without_urls) is not None
        for pattern in (
            ABSOLUTE_UNIX_PATH,
            TILDE_PATH,
            WINDOWS_DRIVE_PATH,
            TEMPORARY_RELATIVE_PATH,
            PARENT_PATH_SEGMENT,
        )
    )


def _sensitive_field_name(value: str) -> bool:
    normalized = value.lower().replace("-", "_")
    exact = {
        "access_token",
        "api_key",
        "authorization",
        "authorization_header",
        "credential",
        "credentials",
        "password",
        "private_key",
        "proxy_authorization",
        "refresh_token",
        "secret",
        "secret_key",
        "sig",
        "signature",
        "token",
    }
    sensitive_suffixes = (
        "_access_key",
        "_access_key_id",
        "_api_key",
        "_authorization",
        "_authorization_header",
        "_credential",
        "_credentials",
        "_password",
        "_private_key",
        "_secret",
        "_secret_key",
        "_signature",
        "_token",
    )
    provider_key = re.fullmatch(
        r"(?:anthropic|aws|azure|fal|google|groq|hf|huggingface|openai|openrouter|replicate)_key",
        normalized,
    )
    return (
        normalized in exact or normalized.endswith(sensitive_suffixes) or provider_key is not None
    )


def _contains_forbidden_derivative_material(value: object) -> bool:
    if isinstance(value, str):
        return (
            _string_contains_filesystem_ref(value)
            or AUTHORIZATION_VALUE.search(value) is not None
            or _string_contains_signed_url(value)
        )
    if isinstance(value, dict):
        return any(
            not isinstance(key, str)
            or _sensitive_field_name(key)
            or _contains_forbidden_derivative_material(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_derivative_material(item) for item in value)
    return False


def _is_generated_image_derivative(entry: JsonObject) -> bool:
    return entry.get("provenance_kind") == GENERATED_IMAGE_DERIVATIVE


def _is_generated_image(entry: JsonObject) -> bool:
    return entry.get("provenance_kind") == GENERATED_IMAGE


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


def _concept_gallery_package(value: object) -> PurePosixPath | None:
    if not _safe_relative_path(value):
        return None
    path = PurePosixPath(cast(str, value))
    parts = path.parts
    if (
        len(parts) < 4
        or parts[:2] != CONCEPT_GALLERY_PREFIX
        or len(parts[2]) > 80
        or CONCEPT_ID.fullmatch(parts[2]) is None
    ):
        return None
    return PurePosixPath(*parts[:3])


def _within_concept_gallery_package(value: object, package: PurePosixPath | None) -> bool:
    if package is None or not _safe_relative_path(value):
        return False
    path = PurePosixPath(cast(str, value))
    try:
        relative = path.relative_to(package)
    except ValueError:
        return False
    return relative != PurePosixPath(".")


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


def _validate_derivative_inputs(sidecar: JsonObject, errors: list[str]) -> list[str]:
    inputs = sidecar.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        errors.append("sidecar.inputs must contain content-addressed generated-image sources")
        return []
    references: list[str] = []
    roles: list[str] = []
    for index, raw_input in enumerate(inputs):
        source_input = _record(raw_input)
        if source_input is None:
            errors.append(f"sidecar.inputs[{index}] must be an object")
            continue
        role = source_input.get("role")
        if not _stable_text(role):
            errors.append(f"sidecar.inputs[{index}].role must be stable")
        elif isinstance(role, str):
            roles.append(role)
        reference = source_input.get("ref")
        digest = source_input.get("sha256")
        if not _valid_digest(digest):
            errors.append(f"sidecar.inputs[{index}].sha256 must be a content digest")
        if (
            not isinstance(reference, str)
            or not _valid_digest(digest)
            or reference != f"sha256:{digest}"
        ):
            errors.append(f"sidecar.inputs[{index}].ref must match its sha256 content identifier")
        else:
            references.append(reference)
        if "path" in source_input:
            errors.append(
                f"sidecar.inputs[{index}] must use content identity instead of a source path"
            )
        if not _positive_safe_integer(source_input.get("bytes")):
            errors.append(f"sidecar.inputs[{index}].bytes must be a positive integer")
        media_type = source_input.get("media_type")
        if not isinstance(media_type, str) or not media_type.startswith("image/"):
            errors.append(f"sidecar.inputs[{index}].media_type must describe an image")
        for field in ("width", "height"):
            if not _positive_safe_integer(source_input.get(field)):
                errors.append(f"sidecar.inputs[{index}].{field} must be a positive integer")
        prompt = source_input.get("original_prompt")
        if not _stable_text(prompt):
            errors.append(f"sidecar.inputs[{index}].original_prompt must contain the full prompt")
        elif source_input.get("prompt_sha256") != _utf8_digest(cast(str, prompt)):
            errors.append(
                f"sidecar.inputs[{index}].prompt_sha256 must digest the full exact UTF-8 prompt"
            )
        if source_input.get("prompt_hash_scope") != "full_exact_utf8_string":
            errors.append(
                f"sidecar.inputs[{index}].prompt_hash_scope must declare the full exact prompt"
            )
        rights_basis = source_input.get("rights_basis")
        valid_basis = (
            isinstance(rights_basis, list)
            and bool(rights_basis)
            and all(
                _stable_text(item) and isinstance(item, str) and UNSTABLE_REF.search(item) is None
                for item in rights_basis
            )
        )
        if not valid_basis:
            errors.append(
                f"sidecar.inputs[{index}].rights_basis must contain source-specific reviewed values"
            )
        elif isinstance(reference, str) and not any(
            reference in cast(str, item) for item in cast(list[object], rights_basis)
        ):
            errors.append(
                f"sidecar.inputs[{index}].rights_basis must bind the exact "
                "source content identifier"
            )
    if len(roles) != len(set(roles)):
        errors.append("sidecar.inputs roles must be unique")
    if len(references) != len(set(references)):
        errors.append("sidecar.inputs content identifiers must be unique")
    return references


def _validate_derivative_transformation(
    sidecar: JsonObject,
    references: list[str],
    artifact: JsonObject | None,
    errors: list[str],
) -> None:
    if "capture" in sidecar:
        errors.append("generated-image derivative sidecar must use transformation, never capture")
    transformation = _record(sidecar.get("transformation"))
    if transformation is None:
        errors.append("sidecar.transformation is required for a generated-image derivative")
        return
    for field in ("tool", "version"):
        if not _stable_text(transformation.get(field)):
            errors.append(f"sidecar.transformation.{field} must be a stable value")
    params = transformation.get("params")
    if not isinstance(params, dict) or not params or not _valid_capture_params(params):
        errors.append("sidecar.transformation.params must be a non-empty stable JSON object")
        return
    if _contains_unstable_ref(params):
        errors.append("sidecar.transformation.params must not contain private or temporary paths")
    if params.get("input_refs") != references:
        errors.append("sidecar.transformation.params.input_refs must bind every source in order")
    if not _stable_text(params.get("operation")):
        errors.append("sidecar.transformation.params.operation must be stable")
    output = _record(params.get("output"))
    if output is None:
        errors.append("sidecar.transformation.params.output must bind the derivative output")
    else:
        if not _stable_text(output.get("media_type")):
            errors.append("sidecar.transformation.params.output.media_type must be stable")
        for field in ("width", "height"):
            if not _positive_safe_integer(output.get(field)):
                errors.append(
                    f"sidecar.transformation.params.output.{field} must be a positive integer"
                )
        if artifact is not None:
            for field in ("media_type", "width", "height"):
                if output.get(field) != artifact.get(field):
                    errors.append(
                        f"sidecar.transformation.params.output.{field} must match the artifact"
                    )


def _validate_model_identity(
    record: JsonObject,
    value_field: str,
    status_field: str,
    label: str,
    errors: list[str],
) -> None:
    value = record.get(value_field)
    if value is None:
        if record.get(status_field) != "unavailable_from_builtin_image_tool":
            errors.append(f"{label}.{status_field} must explain the unavailable value")
    elif not _stable_text(value) or record.get(status_field) != "reported":
        errors.append(f"{label}.{value_field} must be stable and {status_field} must be reported")


def _validate_seed_identity(
    record: JsonObject,
    value_field: str,
    status_field: str,
    label: str,
    errors: list[str],
) -> None:
    value = record.get(value_field)
    if value is None:
        if record.get(status_field) != "unavailable_from_builtin_image_tool":
            errors.append(f"{label}.{status_field} must explain the unavailable value")
    elif not _safe_integer(value) or record.get(status_field) != "reported":
        errors.append(
            f"{label}.{value_field} must be an integer and {status_field} must be reported"
        )


def _validate_derivative_generation(
    sidecar: JsonObject,
    references: list[str],
    errors: list[str],
) -> None:
    generation = _record(sidecar.get("generation"))
    if generation is None or set(generation) != {"shared_seed", "compiled_variant"}:
        errors.append("sidecar.generation must contain shared_seed and compiled_variant records")
        return
    shared_seed = _record(generation.get("shared_seed"))
    compiled = _record(generation.get("compiled_variant"))
    if shared_seed is None or compiled is None or len(references) != 2:
        errors.append("sidecar.generation must bind exactly two derivative inputs")
        return
    expected_seed_fields = {
        "tool",
        "artifact_ref",
        "reference_refs",
        "model",
        "model_status",
        "numeric_seed",
        "numeric_seed_status",
        "attempt_count",
    }
    if set(shared_seed) != expected_seed_fields:
        errors.append("sidecar.generation.shared_seed fields are incomplete or unsupported")
    if not _stable_text(shared_seed.get("tool")):
        errors.append("sidecar.generation.shared_seed.tool must be stable")
    if shared_seed.get("artifact_ref") != references[0]:
        errors.append("sidecar.generation.shared_seed.artifact_ref must bind the seed input")
    if shared_seed.get("reference_refs") != []:
        errors.append("sidecar.generation.shared_seed.reference_refs must be empty")
    _validate_model_identity(
        shared_seed,
        "model",
        "model_status",
        "sidecar.generation.shared_seed",
        errors,
    )
    _validate_seed_identity(
        shared_seed,
        "numeric_seed",
        "numeric_seed_status",
        "sidecar.generation.shared_seed",
        errors,
    )
    seed_attempts = shared_seed.get("attempt_count")
    if not _positive_safe_integer(seed_attempts) or cast(int, seed_attempts) > 6:
        errors.append("sidecar.generation.shared_seed.attempt_count must be within [1, 6]")

    expected_compiled_fields = {
        "artifact_ref",
        "reference_refs",
        "canonical_theme_json",
        "theme_digest",
        "compiler_provider",
        "compiler_model",
        "compiler_version",
        "compiler_attempt_count",
        "skill_name",
        "skill_ref",
        "skill_sha256",
        "plan_ref",
        "plan_sha256",
        "image_tool",
        "image_model",
        "image_model_status",
        "image_attempt_count",
        "numeric_seed",
        "numeric_seed_status",
        "selected_candidate_attempt",
        "bounded_image_candidate_regenerations",
        "raw_selected_source_visual_status",
    }
    if set(compiled) != expected_compiled_fields:
        errors.append("sidecar.generation.compiled_variant fields are incomplete or unsupported")
    if compiled.get("artifact_ref") != references[1]:
        errors.append(
            "sidecar.generation.compiled_variant.artifact_ref must bind the selected input"
        )
    if compiled.get("reference_refs") != [references[0]]:
        errors.append(
            "sidecar.generation.compiled_variant.reference_refs must bind only the shared seed"
        )
    for field in ("compiler_provider", "compiler_model", "skill_name", "image_tool"):
        if not _stable_text(compiled.get(field)):
            errors.append(f"sidecar.generation.compiled_variant.{field} must be stable")
    if not _positive_safe_integer(compiled.get("compiler_version")):
        errors.append(
            "sidecar.generation.compiled_variant.compiler_version must be a positive integer"
        )
    compiler_attempts = compiled.get("compiler_attempt_count")
    if not _positive_safe_integer(compiler_attempts) or cast(int, compiler_attempts) > 6:
        errors.append(
            "sidecar.generation.compiled_variant.compiler_attempt_count must be within [1, 6]"
        )
    image_attempts = compiled.get("image_attempt_count")
    if not _positive_safe_integer(image_attempts) or cast(int, image_attempts) > 6:
        errors.append(
            "sidecar.generation.compiled_variant.image_attempt_count must be within [1, 6]"
        )
    selected_candidate = compiled.get("selected_candidate_attempt")
    if not _positive_safe_integer(selected_candidate):
        errors.append(
            "sidecar.generation.compiled_variant.selected_candidate_attempt must be a "
            "positive integer"
        )
    regenerations = compiled.get("bounded_image_candidate_regenerations")
    if (
        not _safe_integer(regenerations)
        or cast(int, regenerations) < 0
        or cast(int, regenerations) > 2
    ):
        errors.append(
            "sidecar.generation.compiled_variant.bounded_image_candidate_regenerations "
            "must be within [0, 2]"
        )
    elif _positive_safe_integer(selected_candidate) and cast(int, selected_candidate) > (
        cast(int, regenerations) + 1
    ):
        errors.append(
            "sidecar.generation.compiled_variant.selected_candidate_attempt must not exceed "
            "the initial candidate plus regenerations"
        )
    for digest_field, ref_field in (
        ("skill_sha256", "skill_ref"),
        ("plan_sha256", "plan_ref"),
    ):
        digest = compiled.get(digest_field)
        if not _valid_digest(digest):
            errors.append(
                f"sidecar.generation.compiled_variant.{digest_field} must be a content digest"
            )
        if not isinstance(digest, str) or compiled.get(ref_field) != f"sha256:{digest}":
            errors.append(
                f"sidecar.generation.compiled_variant.{ref_field} must match {digest_field}"
            )
    _validate_model_identity(
        compiled,
        "image_model",
        "image_model_status",
        "sidecar.generation.compiled_variant",
        errors,
    )
    _validate_seed_identity(
        compiled,
        "numeric_seed",
        "numeric_seed_status",
        "sidecar.generation.compiled_variant",
        errors,
    )
    if not _stable_text(compiled.get("raw_selected_source_visual_status")):
        errors.append(
            "sidecar.generation.compiled_variant.raw_selected_source_visual_status must be stable"
        )

    canonical = compiled.get("canonical_theme_json")
    try:
        decoded = _record(json.loads(canonical)) if isinstance(canonical, str) else None
    except json.JSONDecodeError:
        decoded = None
    canonical_encoding = (
        json.dumps(decoded, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        if decoded is not None
        else None
    )
    handles = _record(decoded.get("handles")) if decoded is not None else None
    valid_handles = (
        handles is not None
        and tuple(handles) == THEME_HANDLE_NAMES
        and all(
            _safe_integer(handles.get(name)) and 0 <= cast(int, handles[name]) <= 4
            for name in THEME_HANDLE_NAMES
        )
    )
    if (
        decoded is None
        or canonical_encoding != canonical
        or decoded.get("schema_version") != 1
        or decoded.get("compiler_version") != compiled.get("compiler_version")
        or not valid_handles
    ):
        errors.append(
            "sidecar.generation.compiled_variant.canonical_theme_json must be canonical "
            "and contain the six validated handles"
        )
    skill_name = compiled.get("skill_name")
    skill_digest = compiled.get("skill_sha256")
    if (
        not isinstance(canonical, str)
        or not isinstance(skill_name, str)
        or not isinstance(skill_digest, str)
        or compiled.get("theme_digest")
        != _theme_identity_digest(canonical, skill_name, skill_digest)
    ):
        errors.append(
            "sidecar.generation.compiled_variant.theme_digest must bind canonical theme "
            "and compiler skill identity"
        )


def _validate_concept_cover_publication_transform(
    value: object,
    normalization: JsonObject,
    artifact: JsonObject | None,
    errors: list[str],
) -> None:
    publication_transform = _record(value)
    expected_fields = {
        "tool",
        "version",
        "operation",
        "input_sha256",
        "output_sha256",
        "output_media_type",
        "width",
        "height",
        "settings",
    }
    if publication_transform is None:
        errors.append("sidecar.generation.publication_transform must be an object")
        return
    if set(publication_transform) != expected_fields:
        errors.append(
            "game_concept_cover_v1 publication_transform fields are incomplete or unsupported"
        )
    for field in ("tool", "version", "operation"):
        if not _stable_text(publication_transform.get(field)):
            errors.append(
                f"sidecar.generation.publication_transform.{field} must be a stable value"
            )

    normalization_digest = normalization.get("output_sha256")
    if publication_transform.get("input_sha256") != normalization_digest or not _valid_digest(
        normalization_digest
    ):
        errors.append(
            "sidecar.generation.publication_transform.input_sha256 must match the "
            "normalization output"
        )
    artifact_digest = artifact.get("sha256") if artifact is not None else None
    if publication_transform.get("output_sha256") != artifact_digest or not _valid_digest(
        artifact_digest
    ):
        errors.append(
            "sidecar.generation.publication_transform.output_sha256 must match the artifact"
        )
    if artifact is not None:
        for transform_field, artifact_field in (
            ("output_media_type", "media_type"),
            ("width", "width"),
            ("height", "height"),
        ):
            if publication_transform.get(transform_field) != artifact.get(artifact_field):
                errors.append(
                    f"sidecar.generation.publication_transform.{transform_field} must match "
                    "the artifact"
                )

    for field in ("width", "height"):
        if not _positive_safe_integer(publication_transform.get(field)):
            errors.append(
                f"sidecar.generation.publication_transform.{field} must be a positive integer"
            )
    output_media_type = publication_transform.get("output_media_type")
    if not isinstance(output_media_type, str) or not output_media_type.startswith("image/"):
        errors.append(
            "sidecar.generation.publication_transform.output_media_type must describe an image"
        )

    settings = _record(publication_transform.get("settings"))
    expected_settings_fields = {"quality", "resize_width", "resize_height", "metadata"}
    if settings is None:
        errors.append("sidecar.generation.publication_transform.settings must be an object")
        return
    if set(settings) != expected_settings_fields:
        errors.append(
            "game_concept_cover_v1 publication_transform.settings fields are incomplete "
            "or unsupported"
        )
    quality = settings.get("quality")
    if not _safe_integer(quality) or not 0 <= cast(int, quality) <= 100:
        errors.append(
            "sidecar.generation.publication_transform.settings.quality must be within [0, 100]"
        )
    for settings_field, transform_field in (
        ("resize_width", "width"),
        ("resize_height", "height"),
    ):
        value = settings.get(settings_field)
        if not _positive_safe_integer(value):
            errors.append(
                f"sidecar.generation.publication_transform.settings.{settings_field} "
                "must be a positive integer"
            )
        elif value != publication_transform.get(transform_field):
            errors.append(
                f"sidecar.generation.publication_transform.settings.{settings_field} "
                f"must match publication_transform.{transform_field}"
            )
    if settings.get("metadata") != "none":
        errors.append("sidecar.generation.publication_transform.settings.metadata must be none")


def _validate_concept_cover_generation(
    sidecar: JsonObject,
    artifact: JsonObject | None,
    errors: list[str],
) -> None:
    generation = _record(sidecar.get("generation"))
    base_generation_fields = {
        "prompt",
        "prompt_sha256",
        "prompt_hash_scope",
        "provider",
        "model",
        "attempt_count",
        "retry_count",
        "n",
        "input_references",
        "source",
        "normalization",
    }
    if generation is None:
        errors.append("sidecar.generation is required for game_concept_cover_v1")
        return
    if set(generation) not in (
        base_generation_fields,
        base_generation_fields | {"publication_transform"},
    ):
        errors.append("game_concept_cover_v1 generation fields are incomplete or unsupported")

    prompt = generation.get("prompt")
    if not _stable_text(prompt):
        errors.append("sidecar.generation.prompt must contain the full exact prompt")
    elif generation.get("prompt_sha256") != _utf8_digest(cast(str, prompt)):
        errors.append("sidecar.generation.prompt_sha256 must digest the full exact UTF-8 prompt")
    if generation.get("prompt_hash_scope") != "full_exact_utf8_string":
        errors.append("sidecar.generation.prompt_hash_scope must declare the full exact prompt")
    for field in ("provider", "model"):
        if not _stable_text(generation.get(field)):
            errors.append(f"sidecar.generation.{field} must be a stable value")

    attempt_count = generation.get("attempt_count")
    if not _positive_safe_integer(attempt_count) or cast(int, attempt_count) > 6:
        errors.append("sidecar.generation.attempt_count must be within [1, 6]")
    retry_count = generation.get("retry_count")
    if (
        not _safe_integer(retry_count)
        or cast(int, retry_count) < 0
        or (
            _positive_safe_integer(attempt_count)
            and cast(int, retry_count) != cast(int, attempt_count) - 1
        )
    ):
        errors.append("sidecar.generation.retry_count must equal attempt_count minus one")
    if type(generation.get("n")) is not int or generation.get("n") != 1:
        errors.append("sidecar.generation.n must be exactly 1")
    if generation.get("input_references") != []:
        errors.append("sidecar.generation.input_references must be empty for game_concept_cover_v1")

    source = _record(generation.get("source"))
    expected_source_fields = {"media_type", "sha256", "bytes", "width", "height"}
    if source is None:
        errors.append("sidecar.generation.source must record the returned source media")
    else:
        if set(source) != expected_source_fields:
            errors.append("game_concept_cover_v1 source fields are incomplete or unsupported")
        media_type = source.get("media_type")
        if not isinstance(media_type, str) or not media_type.startswith("image/"):
            errors.append("sidecar.generation.source.media_type must describe an image")
        if not _valid_digest(source.get("sha256")):
            errors.append("sidecar.generation.source.sha256 must be a content digest")
        if not _positive_safe_integer(source.get("bytes")):
            errors.append("sidecar.generation.source.bytes must be a positive integer")
        for field in ("width", "height"):
            if not _positive_safe_integer(source.get(field)):
                errors.append(f"sidecar.generation.source.{field} must be a positive integer")

    normalization = _record(generation.get("normalization"))
    expected_normalization_fields = {
        "tool",
        "version",
        "operation",
        "input_sha256",
        "output_sha256",
        "output_media_type",
        "width",
        "height",
    }
    if normalization is None:
        errors.append("sidecar.generation.normalization must record deterministic normalization")
        return
    if set(normalization) != expected_normalization_fields:
        errors.append("game_concept_cover_v1 normalization fields are incomplete or unsupported")
    for field in ("tool", "version", "operation"):
        if not _stable_text(normalization.get(field)):
            errors.append(f"sidecar.generation.normalization.{field} must be a stable value")
    source_digest = source.get("sha256") if source is not None else None
    if normalization.get("input_sha256") != source_digest or not _valid_digest(source_digest):
        errors.append("sidecar.generation.normalization.input_sha256 must match the source media")
    if not _valid_digest(normalization.get("output_sha256")):
        errors.append("sidecar.generation.normalization.output_sha256 must be a content digest")
    normalization_media_type = normalization.get("output_media_type")
    if not isinstance(normalization_media_type, str) or not normalization_media_type.startswith(
        "image/"
    ):
        errors.append("sidecar.generation.normalization.output_media_type must describe an image")
    for field in ("width", "height"):
        if not _positive_safe_integer(normalization.get(field)):
            errors.append(f"sidecar.generation.normalization.{field} must be a positive integer")

    if "publication_transform" in generation:
        if normalization.get("output_media_type") != "image/png":
            errors.append(
                "sidecar.generation.normalization.output_media_type must be image/png when "
                "publication_transform is present"
            )
        _validate_concept_cover_publication_transform(
            generation.get("publication_transform"),
            normalization,
            artifact,
            errors,
        )
    else:
        artifact_digest = artifact.get("sha256") if artifact is not None else None
        if normalization.get("output_sha256") != artifact_digest or not _valid_digest(
            artifact_digest
        ):
            errors.append("sidecar.generation.normalization.output_sha256 must match the artifact")
        if artifact is not None:
            for normalization_field, artifact_field in (
                ("output_media_type", "media_type"),
                ("width", "width"),
                ("height", "height"),
            ):
                if normalization.get(normalization_field) != artifact.get(artifact_field):
                    errors.append(
                        f"sidecar.generation.normalization.{normalization_field} must match "
                        "the artifact"
                    )


def _validate_concept_cover_metadata(
    entry: JsonObject,
    path: str,
    sidecar: JsonObject,
    errors: list[str],
) -> None:
    package = _concept_gallery_package(path)
    if package is None:
        errors.append("inventory artifact path must be inside concept-studio/gallery/<concept_id>")
    if _has_non_lower_snake_key(entry):
        errors.append("generated-image inventory fields must use lower_snake_case")
    if _has_non_lower_snake_key(sidecar):
        errors.append("generated-image sidecar fields must use lower_snake_case")
    if _contains_forbidden_derivative_material({"entry": entry, "sidecar": sidecar}):
        errors.append(
            "generated-image records must not contain private, temporary, file, data, "
            "authorization, credential, or signed-URL material"
        )
    if sidecar.get("provenance_kind") != GENERATED_IMAGE:
        errors.append("sidecar.provenance_kind must match generated_image")
    if entry.get("lineage_kind") != GAME_CONCEPT_COVER:
        errors.append("inventory lineage_kind must select supported game_concept_cover_v1")
    if sidecar.get("lineage_kind") != entry.get("lineage_kind"):
        errors.append("sidecar.lineage_kind must match inventory lineage_kind")

    expected_entry_fields = {
        "path",
        "provenance_kind",
        "lineage_kind",
        "kind",
        "sidecar_sha256",
        "review_status",
        "synth_id_expected",
        "visual_review",
    }
    expected_sidecar_fields = {
        "schema_version",
        "provenance_kind",
        "lineage_kind",
        "state",
        "artifact",
        "concept",
        "generation",
        "visual_review",
        "rights",
    }
    if set(entry) != expected_entry_fields:
        errors.append("game_concept_cover_v1 inventory fields are incomplete or unsupported")
    if set(sidecar) != expected_sidecar_fields:
        errors.append("game_concept_cover_v1 sidecar fields are incomplete or unsupported")
    if type(sidecar.get("schema_version")) is not int or sidecar.get("schema_version") != 1:
        errors.append("generated-image sidecar schema_version must be 1")
    if sidecar.get("state") != "redistribution-approved":
        errors.append("generated-image sidecar state must be redistribution-approved")

    artifact = _record(sidecar.get("artifact"))
    expected_artifact_fields = {"path", "media_type", "width", "height", "sha256", "bytes"}
    if artifact is None:
        errors.append("sidecar.artifact is required for game_concept_cover_v1")
    else:
        if set(artifact) != expected_artifact_fields:
            errors.append("game_concept_cover_v1 artifact fields are incomplete or unsupported")
        if artifact.get("path") != path:
            errors.append("sidecar.artifact.path must match the inventory artifact path")
        for field in ("width", "height"):
            if not _positive_safe_integer(artifact.get(field)):
                errors.append(f"sidecar.artifact.{field} must be a positive integer")

    concept = _record(sidecar.get("concept"))
    expected_concept_fields = {"path", "sha256", "bytes"}
    if concept is None:
        errors.append("sidecar.concept must bind the concept document")
    else:
        if set(concept) != expected_concept_fields:
            errors.append("game_concept_cover_v1 concept fields are incomplete or unsupported")
        concept_path = concept.get("path")
        if not _safe_relative_path(concept_path) or concept_path == path:
            errors.append("sidecar.concept.path must be a distinct repository-relative path")
        if not _within_concept_gallery_package(concept_path, package):
            errors.append(
                "sidecar.concept.path must stay inside the artifact concept gallery package"
            )
        if not _valid_digest(concept.get("sha256")):
            errors.append("sidecar.concept.sha256 must be a content digest")
        if not _positive_safe_integer(concept.get("bytes")):
            errors.append("sidecar.concept.bytes must be a positive integer")

    for label, review in (
        ("inventory visual_review", _record(entry.get("visual_review"))),
        ("sidecar.visual_review", _record(sidecar.get("visual_review"))),
    ):
        report_path = review.get("verification_report_path") if review is not None else None
        if not _within_concept_gallery_package(report_path, package):
            errors.append(
                f"{label}.verification_report_path must stay inside the artifact "
                "concept gallery package"
            )

    sidecar_review = _record(sidecar.get("visual_review"))
    evidence = _record(sidecar_review.get("evidence")) if sidecar_review is not None else None
    evidence_path = evidence.get("path") if evidence is not None else None
    if not _within_concept_gallery_package(evidence_path, package):
        errors.append(
            "sidecar.visual_review.evidence.path must stay inside the artifact "
            "concept gallery package"
        )

    rights = _record(sidecar.get("rights"))
    notice = rights.get("notice") if rights is not None else None
    if (
        not _safe_relative_path(notice)
        or len(PurePosixPath(cast(str, notice)).parts) != 1
        or notice in {".", ".."}
    ):
        errors.append(
            "sidecar.rights.notice must name an adjacent file in the concept gallery package"
        )

    _validate_concept_cover_generation(sidecar, artifact, errors)


def _validate_derivative_review(
    entry: JsonObject,
    sidecar: JsonObject,
    basis: object,
    errors: list[str],
    *,
    record_label: str = "generated-image derivative",
) -> None:
    if entry.get("synth_id_expected") is not False:
        errors.append(f"inventory synth_id_expected must explicitly be false for {record_label}")
    inventory_review = _record(entry.get("visual_review"))
    sidecar_review = _record(sidecar.get("visual_review"))
    if inventory_review is None:
        errors.append(f"inventory visual_review is required for {record_label}")
        return
    if sidecar_review is None:
        errors.append(f"sidecar.visual_review is required for {record_label}")
        return
    artifact = _record(sidecar.get("artifact"))
    artifact_digest = artifact.get("sha256") if artifact is not None else None
    artifact_bytes = artifact.get("bytes") if artifact is not None else None
    shared_fields = (
        "status",
        "result",
        "independent",
        "reviewed_by",
        "authority_basis",
        "reviewed_at",
        "attestation_id",
        "attested_at",
        "artifact_sha256",
        "artifact_bytes",
        "verification_report_path",
        "verification_report_sha256",
        "verification_report_bytes",
    )
    for label, review in (
        ("inventory visual_review", inventory_review),
        ("sidecar.visual_review", sidecar_review),
    ):
        if review.get("status") != "approved":
            errors.append(f"{label}.status must be approved")
        if review.get("result") != VISUAL_REVIEW_RESULT:
            errors.append(f"{label}.result must be pass")
        if review.get("independent") is not True:
            errors.append(f"{label}.independent must be true")
        if not _stable_text(review.get("reviewed_by")):
            errors.append(f"{label}.reviewed_by must be a stable reviewer identity or role")
        if not _stable_text(review.get("authority_basis")):
            errors.append(f"{label}.authority_basis is required")
        if not _valid_timestamp(review.get("reviewed_at")):
            errors.append(f"{label}.reviewed_at must be an ISO UTC timestamp")
        if review.get("artifact_sha256") != artifact_digest:
            errors.append(f"{label}.artifact_sha256 must match the artifact")
        if review.get("artifact_bytes") != artifact_bytes:
            errors.append(f"{label}.artifact_bytes must match the artifact")
        report_path = review.get("verification_report_path")
        if not _safe_relative_path(report_path):
            errors.append(f"{label}.verification_report_path must be repository-relative")
        if not _valid_digest(review.get("verification_report_sha256")):
            errors.append(f"{label}.verification_report_sha256 must be a content digest")
        if not _positive_safe_integer(review.get("verification_report_bytes")):
            errors.append(f"{label}.verification_report_bytes must be a positive integer")
        attestation_id = review.get("attestation_id")
        if (
            not _stable_text(attestation_id)
            or not isinstance(attestation_id, str)
            or UNSTABLE_REF.search(attestation_id) is not None
        ):
            errors.append(f"{label}.attestation_id must be stable")
        elif not isinstance(basis, list) or attestation_id not in basis:
            errors.append("sidecar.rights.basis must include the visual attestation identifier")
        if not _valid_timestamp(review.get("attested_at")) or review.get(
            "attested_at"
        ) != review.get("reviewed_at"):
            errors.append(f"{label}.attested_at must match reviewed_at")
    for field in shared_fields:
        if inventory_review.get(field) != sidecar_review.get(field):
            errors.append(f"inventory and sidecar visual_review.{field} must match")
    if not _stable_text(sidecar_review.get("acceptance_spec")):
        errors.append("sidecar.visual_review.acceptance_spec is required")
    evidence = _record(sidecar_review.get("evidence"))
    if evidence is None:
        errors.append("sidecar.visual_review.evidence is required")
    else:
        if evidence.get("verdict") != "pass":
            errors.append("sidecar.visual_review.evidence.verdict must be pass")
        if evidence.get("path") != sidecar_review.get("verification_report_path"):
            errors.append("sidecar.visual_review.evidence.path must match the review report")
        if evidence.get("sha256") != sidecar_review.get("verification_report_sha256"):
            errors.append("sidecar.visual_review.evidence.sha256 must match the review report")
        if evidence.get("bytes") != sidecar_review.get("verification_report_bytes"):
            errors.append("sidecar.visual_review.evidence.bytes must match the review report")
        digest = evidence.get("sha256")
        if not isinstance(digest, str) or evidence.get("ref") != f"sha256:{digest}":
            errors.append("sidecar.visual_review.evidence.ref must match its sha256")


def _validate_derivative_metadata(
    entry: JsonObject,
    path: str,
    sidecar: JsonObject,
    errors: list[str],
) -> None:
    if _has_non_lower_snake_key(entry):
        errors.append("generated-image derivative inventory fields must use lower_snake_case")
    if _has_non_lower_snake_key(sidecar):
        errors.append("generated-image derivative sidecar fields must use lower_snake_case")
    if _contains_forbidden_derivative_material({"entry": entry, "sidecar": sidecar}):
        errors.append(
            "generated-image derivative records must not contain private, temporary, file, "
            "data, authorization, credential, or signed-URL material"
        )
    if sidecar.get("provenance_kind") != GENERATED_IMAGE_DERIVATIVE:
        errors.append("sidecar.provenance_kind must match generated_image_derivative")
    entry_lineage = entry.get("lineage_kind")
    sidecar_lineage = sidecar.get("lineage_kind")
    if entry_lineage != THEME_ART_DIRECTION_COMPARISON:
        errors.append(
            "inventory lineage_kind must select supported theme_art_direction_comparison_v1"
        )
    if sidecar_lineage != entry_lineage:
        errors.append("sidecar.lineage_kind must match inventory lineage_kind")
    theme_subtype = (
        entry_lineage == THEME_ART_DIRECTION_COMPARISON
        or sidecar_lineage == THEME_ART_DIRECTION_COMPARISON
    )
    if theme_subtype:
        expected_entry_fields = {
            "path",
            "provenance_kind",
            "lineage_kind",
            "kind",
            "sidecar_sha256",
            "review_status",
            "synth_id_expected",
            "visual_review",
        }
        expected_sidecar_fields = {
            "schema_version",
            "provenance_kind",
            "lineage_kind",
            "state",
            "artifact",
            "inputs",
            "generation",
            "transformation",
            "visual_review",
            "rights",
        }
        if set(entry) != expected_entry_fields:
            errors.append(
                "theme_art_direction_comparison_v1 inventory fields are incomplete or unsupported"
            )
        if set(sidecar) != expected_sidecar_fields:
            errors.append(
                "theme_art_direction_comparison_v1 sidecar fields are incomplete or unsupported"
            )
    if type(sidecar.get("schema_version")) is not int or sidecar.get("schema_version") != 1:
        errors.append("generated-image derivative sidecar schema_version must be 1")
    if sidecar.get("state") != "redistribution-approved":
        errors.append("generated-image derivative sidecar state must be redistribution-approved")
    artifact = _record(sidecar.get("artifact"))
    if artifact is not None and artifact.get("path") != path:
        errors.append("sidecar.artifact.path must match the inventory artifact path")
    if artifact is not None:
        for field in ("width", "height"):
            if not _positive_safe_integer(artifact.get(field)):
                errors.append(f"sidecar.artifact.{field} must be a positive integer")
    references = _validate_derivative_inputs(sidecar, errors)
    if entry_lineage == THEME_ART_DIRECTION_COMPARISON and sidecar_lineage == entry_lineage:
        _validate_derivative_generation(sidecar, references, errors)
    _validate_derivative_transformation(sidecar, references, artifact, errors)


def _validate_rights(
    entry: JsonObject,
    sidecar: JsonObject,
    *,
    kind: str | None,
    observed: JsonObject | None,
    errors: list[str],
) -> None:
    derivative = _is_generated_image_derivative(entry)
    generated_image = _is_generated_image(entry)
    lower_snake_generated_image = derivative or generated_image
    if lower_snake_generated_image:
        if entry.get("review_status") != "repository-approved":
            errors.append("inventory review_status must be repository-approved")
    elif entry.get("reviewStatus") != "repository-approved":
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
        if lower_snake_generated_image:
            notice_digest = rights.get("notice_sha256")
            notice_bytes = rights.get("notice_bytes")
            if not _valid_digest(notice_digest):
                errors.append("sidecar.rights.notice_sha256 must be a content digest")
            elif observed is None or notice_digest != observed.get("notice_sha256"):
                errors.append("sidecar.rights.notice_sha256 must match the adjacent notice")
            if not _positive_safe_integer(notice_bytes):
                errors.append("sidecar.rights.notice_bytes must be a positive integer")
            elif observed is None or notice_bytes != observed.get("notice_bytes"):
                errors.append("sidecar.rights.notice_bytes must match the adjacent notice")
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
    if derivative:
        _validate_derivative_review(entry, sidecar, basis, errors)
    elif generated_image:
        _validate_derivative_review(
            entry,
            sidecar,
            basis,
            errors,
            record_label="generated image",
        )
    elif kind == "audio":
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
    derivative = _is_generated_image_derivative(entry)
    generated_image = _is_generated_image(entry)
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
    if derivative:
        if kind != "image":
            errors.append("generated_image_derivative provenance requires an image artifact")
        _validate_derivative_metadata(entry, path, sidecar, errors)
    elif generated_image:
        if kind != "image":
            errors.append("generated_image provenance requires an image artifact")
        _validate_concept_cover_metadata(entry, path, sidecar, errors)
    elif "provenance_kind" in entry:
        errors.append("inventory provenance_kind is unsupported")
    elif kind == "audio":
        _validate_source_inputs(sidecar, errors)
    elif kind in CAPTURE_KINDS:
        _validate_capture_metadata(sidecar, kind, errors)
    _validate_rights(entry, sidecar, kind=kind, observed=observed, errors=errors)
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


def _validate_generated_image_artifact_file(
    path: Path,
    media_path: str,
    sidecar: JsonObject,
    failures: list[str],
) -> None:
    artifact = _record(sidecar.get("artifact"))
    media_type = artifact.get("media_type") if artifact is not None else None
    expected_media_type = media_type if isinstance(media_type, str) else None
    try:
        facts = inspect_image(path.read_bytes(), expected_media_type=expected_media_type)
    except (OSError, ValueError):
        failures.append(
            f"{media_path}: generated image artifact must be a decodable image matching "
            "its declared media type"
        )
        return
    if artifact is None:
        return
    if facts.width != artifact.get("width") or facts.height != artifact.get("height"):
        failures.append(f"{media_path}: decoded image dimensions must match sidecar.artifact")
    if facts.media_type != artifact.get("media_type"):
        failures.append(f"{media_path}: decoded image media type must match sidecar.artifact")


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


def _validate_derivative_review_file(
    repo: Path,
    media_path: str,
    sidecar: JsonObject,
    failures: list[str],
) -> None:
    review = _record(sidecar.get("visual_review"))
    evidence = _record(review.get("evidence")) if review is not None else None
    path = evidence.get("path") if evidence is not None else None
    digest = evidence.get("sha256") if evidence is not None else None
    byte_count = evidence.get("bytes") if evidence is not None else None
    if not _safe_repo_path(repo, path) or path == media_path:
        failures.append(f"{media_path}: sidecar.visual_review.evidence.path is unsafe")
        return
    evidence_path = repo / cast(str, path)
    try:
        evidence_path.lstat()
    except OSError:
        failures.append(f"{media_path}: visual review evidence file is missing")
        return
    if evidence_path.is_symlink() or not evidence_path.is_file():
        failures.append(f"{media_path}: visual review evidence must be a regular file")
        return
    evidence_bytes = evidence_path.read_bytes()
    if not _valid_digest(digest) or hashlib.sha256(evidence_bytes).hexdigest() != digest:
        failures.append(f"{media_path}: visual review evidence digest does not match")
    if not _positive_safe_integer(byte_count) or len(evidence_bytes) != byte_count:
        failures.append(f"{media_path}: visual review evidence byte size does not match")


def _validate_concept_file(
    repo: Path,
    media_path: str,
    sidecar: JsonObject,
    failures: list[str],
) -> None:
    concept = _record(sidecar.get("concept"))
    path = concept.get("path") if concept is not None else None
    digest = concept.get("sha256") if concept is not None else None
    byte_count = concept.get("bytes") if concept is not None else None
    if not _safe_repo_path(repo, path) or path == media_path:
        failures.append(f"{media_path}: sidecar.concept.path is unsafe")
        return
    concept_path = repo / cast(str, path)
    try:
        concept_path.lstat()
    except OSError:
        failures.append(f"{media_path}: concept document is missing")
        return
    if concept_path.is_symlink() or not concept_path.is_file():
        failures.append(f"{media_path}: concept document must be a regular file")
        return
    concept_bytes = concept_path.read_bytes()
    if not _valid_digest(digest) or hashlib.sha256(concept_bytes).hexdigest() != digest:
        failures.append(f"{media_path}: concept document digest does not match")
    if not _positive_safe_integer(byte_count) or len(concept_bytes) != byte_count:
        failures.append(f"{media_path}: concept document byte size does not match")


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
    capture_notice_paths_by_license: dict[str, set[str]] = {}
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
            "notice_sha256": None,
            "notice_bytes": None,
        }
        kind = _media_kind(entry, path, [])
        derivative = _is_generated_image_derivative(entry)
        generated_image = _is_generated_image(entry)
        lower_snake_generated_image = derivative or generated_image
        if lower_snake_generated_image:
            inventory_sidecar_digest = entry.get("sidecar_sha256")
            if not _valid_digest(inventory_sidecar_digest):
                record_label = (
                    "generated image" if generated_image else "generated-image derivative"
                )
                failures.append(f"{path}: inventory sidecar_sha256 is required for {record_label}")
            elif inventory_sidecar_digest != observed["sidecarSha256"]:
                failures.append(
                    f"{path}: inventory sidecar_sha256 does not match adjacent provenance sidecar"
                )
        elif kind in CAPTURE_KINDS:
            inventory_sidecar_digest = entry.get("sidecarSha256")
            if not _valid_digest(inventory_sidecar_digest):
                failures.append(f"{path}: inventory sidecarSha256 is required for browser capture")
            elif inventory_sidecar_digest != observed["sidecarSha256"]:
                failures.append(
                    f"{path}: inventory sidecarSha256 does not match adjacent provenance sidecar"
                )
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
                observed["notice_sha256"] = observed["noticeSha256"]
                observed["notice_bytes"] = notice_path.stat().st_size
                if kind in CAPTURE_KINDS and not lower_snake_generated_image and rights is not None:
                    license_id = rights.get("license_id")
                    if isinstance(license_id, str):
                        capture_notice_paths_by_license.setdefault(license_id, set()).add(
                            notice_path.relative_to(repo).as_posix()
                        )
        observations[path] = observed
        if derivative:
            _validate_derivative_review_file(repo, path, sidecar, failures)
        elif generated_image:
            _validate_generated_image_artifact_file(absolute, path, sidecar, failures)
            _validate_derivative_review_file(repo, path, sidecar, failures)
            _validate_concept_file(repo, path, sidecar, failures)
        elif kind in CAPTURE_KINDS:
            _validate_capture_source_files(repo, path, sidecar, failures)
        for failure in validate_published_media_record(
            {"entry": entry, "observed": observed, "sidecar": sidecar}
        ):
            failures.append(f"{path}: {failure}")

    if any(len(paths) > 1 for paths in capture_notice_paths_by_license.values()):
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
