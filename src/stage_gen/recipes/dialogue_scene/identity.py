"""Deterministic dialogue recipe identities over the shared canonical digests."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from stage_gen.canonical import canonical_json_bytes, canonical_sha256, content_sha256

__all__ = [
    "RECIPE_VERSION",
    "canonical_json_bytes",
    "canonical_sha256",
    "content_sha256",
    "run_identity",
    "stage_identity",
]

RECIPE_VERSION = 5


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
