"""Allowlisted provider credential import."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

from gnode import atomic_write_text
from stage_gen.provider_env import (
    PROVIDER_ENV_KEYS,
    REQUIRED_PROVIDER_ENV_KEYS,
    ProviderEnvKey,
    parse_provider_env,
)


class ImportProviderEnvResult(TypedDict):
    destination: str
    imported: list[ProviderEnvKey]
    count: int


def import_provider_env(
    source_path: str | Path, destination_path: str | Path
) -> ImportProviderEnvResult:
    source = Path(source_path).resolve()
    destination = Path(destination_path).resolve()
    if source == destination:
        raise ValueError("source and destination must differ")
    values = parse_provider_env(source.read_text(encoding="utf-8"), source_label="source")
    missing = [key for key in REQUIRED_PROVIDER_ENV_KEYS if key not in values]
    if missing:
        suffix = "" if len(missing) == 1 else "s"
        raise ValueError(f"source is missing required key{suffix}: {', '.join(missing)}")
    imported = [key for key in PROVIDER_ENV_KEYS if key in values]
    payload = "".join(f"{key}={json.dumps(values[key], ensure_ascii=False)}\n" for key in imported)
    atomic_write_text(destination, payload, mode=0o600)
    return {
        "destination": str(destination),
        "imported": imported,
        "count": len(imported),
    }
