"""Canonical serialization and deterministic dialogue recipe identities."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

RECIPE_VERSION = 5


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
    """One run identity, over the recipe version and the authored document together.

    The version rides the digest so a recipe change moves every identity, rather
    than two documents that happen to canonicalize alike sharing a run.
    """

    digest_input = {"recipe_version": RECIPE_VERSION, "request": request}
    return f"dialogue-{canonical_sha256(digest_input)[:24]}"


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
