"""Content-bound cache validation for scrolling-preview artifacts."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from stage_gen.config import TransparencyMode


def force_regeneration(env: dict[str, str] | None = None) -> bool:
    values = os.environ if env is None else env
    return values.get("STAGE_GEN_FORCE") == "1"


def valid_artifact_pair(
    artifact_path: str | Path,
    *,
    transparency_mode: TransparencyMode | None = None,
    validator: Callable[[Path, dict[str, Any]], bool] | None = None,
    force: bool | None = None,
) -> bool:
    """Require artifact bytes, matching v1 sidecar, and requested mode.

    A media-specific caller can additionally verify dimensions/alpha through
    ``validator``.  Existence alone never satisfies this cache contract.
    """

    if force if force is not None else force_regeneration():
        return False
    artifact = Path(artifact_path)
    sidecar_path = Path(f"{artifact}.meta.json")
    try:
        raw = artifact.read_bytes()
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not raw or not isinstance(sidecar, dict) or sidecar.get("schema_version") != 1:
        return False
    digest = sidecar.get("artifact")
    if not isinstance(digest, dict):
        return False
    if digest.get("bytes") != len(raw):
        return False
    if digest.get("sha256") != hashlib.sha256(raw).hexdigest():
        return False
    if transparency_mode is not None:
        params = sidecar.get("params")
        transparency = params.get("transparency") if isinstance(params, dict) else None
        metadata = params.get("metadata") if isinstance(params, dict) else None
        recorded_mode = (
            transparency.get("mode")
            if isinstance(transparency, dict)
            else metadata.get("transparency_mode")
            if isinstance(metadata, dict)
            else None
        )
        if recorded_mode != transparency_mode:
            return False
    return validator(artifact, sidecar) if validator is not None else True
