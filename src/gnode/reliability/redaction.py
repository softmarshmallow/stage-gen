"""Secret, embedded-media, and persistence redaction."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence

type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | list[JsonValue] | dict[str, JsonValue]

_DATA_URL = re.compile(r"data:([^\s;,\"')]+)(?:;[^,\s]*)?;base64,[A-Za-z0-9+/_=-]+", re.IGNORECASE)
_BASE64_FIELD = re.compile(
    r"((?:b64_json|base64|audio_data|image_data)[\"']?\s*[:=]\s*[\"'])"
    r"[A-Za-z0-9+/_=-]+([\"'])",
    re.IGNORECASE,
)
_AUTHORIZATION = re.compile(r"(authorization\s*[:=]\s*)(?:bearer|key)\s+[^\s,\"'}]+", re.IGNORECASE)
_CREDENTIAL_FIELD = re.compile(
    r"([\"']?(?:api[_-]?key|token|secret|credential)[\"']?\s*[:=]\s*[\"'])"
    r"[^\"']+([\"'])",
    re.IGNORECASE,
)
_OPENAI_KEY = re.compile(r"\bsk-(?:or-)?[A-Za-z0-9_-]{8,}\b")
_LONG_BASE64 = re.compile(r"\b[A-Za-z0-9+/]{80,}={0,2}\b")
_SENSITIVE_KEY = re.compile(r"(?:api[_-]?key|authorization|token|secret|credential)", re.I)


def redact_secrets(value: str, secrets: Sequence[str] = ()) -> str:
    """Remove known and structurally recognizable credentials/media payloads."""

    redacted = value
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    redacted = _DATA_URL.sub(r"data:\1;base64,[REDACTED]", redacted)
    redacted = _BASE64_FIELD.sub(r"\1[REDACTED]\2", redacted)
    redacted = _AUTHORIZATION.sub(r"\1[REDACTED]", redacted)
    redacted = _CREDENTIAL_FIELD.sub(r"\1[REDACTED]\2", redacted)
    redacted = _OPENAI_KEY.sub("[REDACTED]", redacted)
    return _LONG_BASE64.sub("[REDACTED_BASE64]", redacted)


def sanitize_for_persistence(
    value: object,
    secrets: Sequence[str] = (),
    *,
    key: str = "",
) -> JsonValue:
    """Convert JSON-like input to a redacted, serialization-safe value."""

    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        if _SENSITIVE_KEY.search(key):
            return "[REDACTED]"
        if value.lower().startswith("data:") and "," in value:
            media_type = value[5:].split(",", 1)[0].split(";", 1)[0].lower()
            return f"data:{media_type};base64,[REDACTED]"
        return redact_secrets(value, secrets)
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for child_key, child_value in value.items():
            if not isinstance(child_key, str):
                raise TypeError("provenance object keys must be strings")
            safe_key = redact_secrets(child_key, secrets)
            if safe_key in result:
                raise ValueError("provenance keys collide after secret redaction")
            result[safe_key] = sanitize_for_persistence(child_value, secrets, key=child_key)
        return result
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | memoryview):
        return [sanitize_for_persistence(item, secrets, key=key) for item in value]
    safe_key = redact_secrets(key, secrets) if key else "root"
    raise TypeError(f"provenance contains unsupported value at {safe_key}")


def sanitize_exception(error: BaseException, secrets: Sequence[str] = ()) -> Exception:
    """Return an exception whose text cannot expose configured secrets."""

    return Exception(redact_secrets(str(error), secrets))
