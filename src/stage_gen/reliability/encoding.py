"""Strict decoding, hashing, MIME, and stable-reference helpers."""

from __future__ import annotations

import base64
import binascii
import hashlib
import ipaddress
import re
import socket
from urllib.parse import SplitResult, urlsplit, urlunsplit

from stage_gen.contracts import InputProvenance

_BASE64 = re.compile(r"^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$")
_DATA_REFERENCE = re.compile(r"^data:([^;,]+);base64,(.+)$", re.IGNORECASE | re.DOTALL)
_DIGEST_REFERENCE = re.compile(r"^sha256:[a-f0-9]{64}$")
_WINDOWS_ABSOLUTE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")
_NUMERIC_IPV4_HOST = re.compile(r"^[0-9A-Fa-fxX.]+$")


def sha256_hex(value: bytes | bytearray | memoryview | str) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else bytes(value)
    return hashlib.sha256(data).hexdigest()


def decode_base64_strict(value: object, label: str = "base64 data") -> bytes:
    if not isinstance(value, str) or not value or len(value) % 4 or not _BASE64.fullmatch(value):
        raise ValueError(f"{label} is not valid base64")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(f"{label} is not valid base64") from error
    if not decoded:
        raise ValueError(f"{label} decoded to empty bytes")
    return decoded


def assert_media_type(value: object, family: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{family} media type is missing")
    normalized = value.strip().lower()
    if not normalized.startswith(f"{family}/") or ";" in normalized:
        raise ValueError(f"invalid {family} media type: {value}")
    return normalized


def sanitize_reference(reference: str) -> str:
    trimmed = reference.strip()
    data_match = re.match(r"^data:([^;,]+)(?:;[^,]*)?,", trimmed, re.IGNORECASE)
    if data_match:
        return f"data:{data_match.group(1).lower()};base64,[REDACTED]"
    try:
        parsed = urlsplit(trimmed)
    except ValueError:
        return trimmed
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return trimmed
    host = parsed.hostname.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        port = None
    netloc = f"{host}:{port}" if port is not None else host
    return urlunsplit(SplitResult(parsed.scheme.lower(), netloc, parsed.path, "", ""))


def hash_input_reference(reference: str, provenance_ref: str | None = None) -> InputProvenance:
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError("input reference must be a non-empty string")
    stable_ref = provenance_ref.strip() if provenance_ref and provenance_ref.strip() else None
    stable_ref = stable_ref or sanitize_reference(reference)
    data_match = _DATA_REFERENCE.fullmatch(reference.strip())
    if data_match:
        data = decode_base64_strict(data_match.group(2), "input reference data")
        return InputProvenance(
            ref=stable_ref,
            sha256=sha256_hex(data),
            source="content",
            bytes=len(data),
            media_type=data_match.group(1).lower(),
        )
    sanitized = sanitize_reference(reference)
    return InputProvenance(ref=stable_ref, sha256=sha256_hex(sanitized), source="reference")


def is_temporary_artifact_reference(value: object) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().replace("\\", "/").lower()
    if normalized.startswith(("/tmp/", "/private/tmp/", "/var/folders/")):
        return True
    if "/appdata/local/temp/" in normalized:
        return True
    return any(
        segment in {"tmp", "temp"} or segment.endswith(".tmp") for segment in normalized.split("/")
    )


def is_portable_artifact_reference(value: object) -> bool:
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if _DIGEST_REFERENCE.fullmatch(value):
        return True
    if is_temporary_artifact_reference(value):
        return False
    if value.lower().startswith(("file:", "data:")) or value.startswith("/"):
        return False
    if _WINDOWS_ABSOLUTE.match(value):
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if parsed.scheme:
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            return False
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            return False
        return not _is_private_hostname(parsed.hostname)
    if any(character in value for character in (":", "?", "#", "\\")):
        return False
    segments = value.split("/")
    return all(
        segment not in {"", ".", ".."} and not segment.startswith(".") for segment in segments
    )


def _is_private_hostname(hostname: str) -> bool:
    host = hostname.lower().strip("[]")
    if host.endswith("."):
        host = host[:-1]
        if not host or host.endswith("."):
            return True
    if not host or host.startswith(".") or ".." in host:
        return True
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return True
    if "%" in host:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        legacy_address = _parse_legacy_ipv4(host)
        if legacy_address is None:
            return False
        # URL clients accept legacy integer, hexadecimal, octal, and shortened
        # IPv4 spellings. Reject every such non-canonical spelling, even when it
        # happens to resolve to a globally routed address.
        if host != str(legacy_address):
            return True
        return not legacy_address.is_global
    return not address.is_global


def _parse_legacy_ipv4(host: str) -> ipaddress.IPv4Address | None:
    if not _NUMERIC_IPV4_HOST.fullmatch(host):
        return None
    try:
        packed = socket.inet_aton(host)
    except OSError:
        return None
    return ipaddress.IPv4Address(packed)
