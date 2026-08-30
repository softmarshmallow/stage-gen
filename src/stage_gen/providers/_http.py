from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from typing import Any

import httpx

from gnode import JsonObject, ProviderResponseMetadata, redact_secrets

_SAFE_ERROR_MESSAGE_SUMMARIES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\binvalid (?:json )?schema\b", re.IGNORECASE), "invalid schema"),
    (
        re.compile(r"\brequired must include every key\b", re.IGNORECASE),
        "required must include every key",
    ),
    (re.compile(r"\bunsupported parameter\b", re.IGNORECASE), "unsupported parameter"),
    (re.compile(r"\bresponse_format\b", re.IGNORECASE), "response_format"),
)
_SAFE_ERROR_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:-]{1,96}$")


def assert_success(
    response: httpx.Response,
    label: str,
    *,
    include_safe_error_detail: bool = False,
    redactions: Sequence[str] = (),
) -> None:
    if not response.is_success:
        message = f"{label} returned HTTP {response.status_code}"
        if include_safe_error_detail:
            detail = _safe_http_error_detail(response, redactions)
            if detail:
                message = f"{message}: {detail}"
        raise ValueError(message)


def _safe_http_error_detail(response: httpx.Response, redactions: Sequence[str]) -> str:
    """Return an allowlisted, bounded provider diagnostic without response spillover."""

    try:
        payload: object = response.json()
    except (ValueError, UnicodeDecodeError):
        return ""
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return ""
    candidate = error
    metadata = error.get("metadata")
    raw = metadata.get("raw") if isinstance(metadata, dict) else None
    if isinstance(raw, str):
        try:
            raw_payload = json.loads(raw)
        except (TypeError, ValueError):
            pass
        else:
            raw_error = raw_payload.get("error") if isinstance(raw_payload, dict) else None
            if isinstance(raw_error, dict):
                candidate = raw_error

    parts: list[str] = []
    raw_message = candidate.get("message")
    if isinstance(raw_message, str):
        message = redact_secrets(raw_message, redactions)
        summaries = [
            summary for pattern, summary in _SAFE_ERROR_MESSAGE_SUMMARIES if pattern.search(message)
        ]
        if summaries:
            parts.append(f"message={', '.join(dict.fromkeys(summaries))}")
    for key in ("type", "code", "param"):
        value = candidate.get(key)
        if isinstance(value, str | int) and not isinstance(value, bool):
            safe = redact_secrets(str(value), redactions)
            if _SAFE_ERROR_IDENTIFIER.fullmatch(safe):
                parts.append(f"{key}={safe}")
    return _bounded_text("; ".join(parts), 720)


def _bounded_text(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1]}…"


def json_object(response: httpx.Response, label: str) -> JsonObject:
    try:
        value: Any = response.json()
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError(f"{label} returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} returned a non-object JSON response")
    return value


def response_metadata(
    response: httpx.Response,
    payload: JsonObject | None = None,
) -> ProviderResponseMetadata:
    request_id = (
        response.headers.get("x-request-id")
        or response.headers.get("x-openrouter-request-id")
        or response.headers.get("request-id")
    )
    created_raw = payload.get("created") if payload else None
    created = (
        created_raw
        if isinstance(created_raw, (int, float))
        and not isinstance(created_raw, bool)
        and math.isfinite(created_raw)
        else None
    )
    usage_raw = payload.get("usage") if payload else None
    usage = dict(usage_raw) if isinstance(usage_raw, dict) else None
    return ProviderResponseMetadata(request_id=request_id, created=created, usage=usage)


def normalized_base_url(value: str, label: str) -> str:
    normalized = value.strip().rstrip("/")
    if not normalized:
        raise ValueError(f"{label} must be non-empty")
    return normalized
