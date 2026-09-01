"""Recipe-neutral canonical serialization and content digests.

Hoisted out of the dialogue recipe's identity module once a second recipe
(the point-and-click room) started importing it across the recipe boundary:
recipes share no code with each other, so what two of them need lives here.
Recipe-specific identity (RECIPE_VERSION, run/stage identities) stays with its
recipe; these helpers carry no recipe vocabulary at all.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel


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
