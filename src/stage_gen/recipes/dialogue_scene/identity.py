"""Canonical serialization and deterministic dialogue recipe identities."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

RECIPE_VERSION = 3
PROFILE_RECIPE_VERSION = 4


def canonical_json_bytes(value: object) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", exclude_none=True)
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def content_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_identity(request: object) -> str:
    if _request_schema_version(request) == 3:
        digest_input = {
            "recipe_version": PROFILE_RECIPE_VERSION,
            "request": request,
        }
        return f"dialogue-{canonical_sha256(digest_input)[:24]}"
    return f"dialogue-{canonical_sha256(request)[:24]}"


def stage_identity(
    *,
    run_id: str,
    stage: str,
    dependencies: Mapping[str, str],
    generation: int,
    inputs: Mapping[str, Any] | None = None,
    recipe_version: int = RECIPE_VERSION,
) -> str:
    return canonical_sha256(
        {
            "recipe_version": recipe_version,
            "run_id": run_id,
            "stage": stage,
            "dependencies": dict(sorted(dependencies.items())),
            "generation": generation,
            "inputs": dict(inputs or {}),
        }
    )


def _request_schema_version(request: object) -> object:
    if isinstance(request, BaseModel):
        return getattr(request, "schema_version", None)
    if isinstance(request, Mapping):
        return request.get("schema_version")
    return None
