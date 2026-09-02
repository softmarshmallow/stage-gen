"""Strict, allowlisted loading of provider credentials from dotenv text."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal, cast

ProviderEnvKey = Literal[
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "FAL_KEY",
    "ELEVENLABS_API_KEY",
]
PROVIDER_ENV_KEYS: tuple[ProviderEnvKey, ...] = (
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "FAL_KEY",
    "ELEVENLABS_API_KEY",
)

_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
_ALLOWLIST_MENTION = re.compile(
    r"^\s*(?:export\s+)?(OPENAI_API_KEY|OPENROUTER_API_KEY|FAL_KEY|ELEVENLABS_API_KEY)\b"
)


def parse_provider_env(
    text: str,
    *,
    source_label: str = ".env",
) -> dict[ProviderEnvKey, str]:
    """Parse only provider credentials and reject unsafe allowlisted entries."""

    values: dict[ProviderEnvKey, str] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        match = _ASSIGNMENT.match(line)
        if match is None:
            mention = _ALLOWLIST_MENTION.match(line)
            if mention is not None:
                key = mention.group(1)
                raise ValueError(
                    f"{source_label} contains malformed assignment for {key} on line {line_number}"
                )
            continue

        raw_key, raw_value = match.groups()
        if raw_key not in PROVIDER_ENV_KEYS:
            continue

        key = cast(ProviderEnvKey, raw_key)
        if key in values:
            raise ValueError(f"{source_label} contains duplicate key: {key}")

        value = _parse_dotenv_value(
            raw_value,
            key=key,
            source_label=source_label,
            line_number=line_number,
        )
        if not value:
            raise ValueError(f"{source_label} contains an empty value for {key}")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError(f"{source_label} contains an unsafe value for {key}")
        values[key] = value
    return values


def load_provider_dotenv(path: Path) -> dict[ProviderEnvKey, str]:
    """Load a regular UTF-8 dotenv file without following symlinks."""

    if path.is_symlink():
        raise ValueError(".env must be a regular file")
    if not path.exists():
        return {}
    if not path.is_file():
        raise ValueError(".env must be a regular file")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(".env must be valid UTF-8") from error
    return parse_provider_env(text)


def _parse_dotenv_value(
    raw: str,
    *,
    key: ProviderEnvKey,
    source_label: str,
    line_number: int,
) -> str:
    value = raw.strip()
    if not value:
        return ""
    if value.startswith('"'):
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, TypeError) as error:
            raise ValueError(
                f"{source_label} contains malformed quoted value for {key} on line {line_number}"
            ) from error
        if not isinstance(decoded, str):
            raise ValueError(
                f"{source_label} contains malformed quoted value for {key} on line {line_number}"
            )
        return decoded
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            raise ValueError(
                f"{source_label} contains malformed quoted value for {key} on line {line_number}"
            )
        return value[1:-1]
    unquoted = re.sub(r"\s+#.*$", "", value).strip()
    if '"' in unquoted or "'" in unquoted:
        raise ValueError(
            f"{source_label} contains malformed quoted value for {key} on line {line_number}"
        )
    return unquoted
