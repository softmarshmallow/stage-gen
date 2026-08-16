from __future__ import annotations

import math
from typing import Any

import httpx

from stage_gen.components._types import JsonObject, ProviderResponseMetadata


def assert_success(response: httpx.Response, label: str) -> None:
    if not response.is_success:
        raise ValueError(f"{label} returned HTTP {response.status_code}")


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
