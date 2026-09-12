"""Durable, bounded tool-invocation evidence independent of model admission.

This wraps public gnode Tools; it adds no model conversation or retry loop.
Pass backend.secrets explicitly. The journal never reads keys or environment
files. Sanitization affects persisted evidence only, never the actual handler
arguments or its return value. It deliberately loses sensitive/oversized data.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import json
import math
import os
import re
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote

from gnode import AbortError, Tool, ToolInvocationError, ToolResult


class EventRecorder(Protocol):
    def __call__(self, event: str, **fields: object) -> None: ...


MAX_ARGUMENT_BYTES = 16384
MAX_REPLY_BYTES = 8192
MAX_EVENT_BYTES = 65536
MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_RECORDED_IMAGES = 64
_EPISODE = re.compile("[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_KEY = re.compile("[A-Za-z_$][A-Za-z0-9_.$-]{0,79}")
_SENSITIVE_KEY = re.compile(
    (
        "(?:^|_)(?:api_key|access_token|refresh_token|token|password|se"
        "cret|credential|authorization|private_key)(?:$|_)"
    ),
    re.IGNORECASE,
)
_REFERENCE = re.compile("\\b[a-z][a-z0-9+.-]*://|\\bdata:|\\bblob:", re.IGNORECASE)
_PATH = re.compile("(?:^|[\\s\\\"'(=:])(?:/|~[/\\\\]|[A-Za-z]:[/\\\\]|\\\\\\\\)")
_CREDENTIAL = re.compile(
    (
        "\\bsk-(?:or-v1-)?[A-Za-z0-9_-]{10,}|\\bBearer\\s+\\S+|-----BEG"
        "IN [^-]*PRIVATE KEY-----|\\b(?:api[_ -]?key|access[_ -]?token|"
        "password|authorization)\\s*[:=]\\s*\\S+"
    ),
    re.IGNORECASE,
)
_EMBEDDED = re.compile("(?:[A-Za-z0-9+/]{256,}={0,2})")
_IMAGE = re.compile("data:image/(png|jpeg|webp|gif);base64,([A-Za-z0-9+/=]+)")


class ToolJournalError(AbortError):
    """Persistence failure stops the episode without retrying tool side effects."""


class SubmitJournalStopped(asyncio.CancelledError):
    """Escape the service's catch-all rejected-submit branch on journal failure."""


def _sha_text(value: str) -> str:
    digest = hashlib.sha256()
    for start in range(0, len(value), 65536):
        digest.update(value[start : start + 65536].encode("utf-8", errors="replace"))
    return digest.hexdigest()


def _redacted(reason: str, value: object = None) -> dict[str, object]:
    result: dict[str, object] = {"redacted": reason}
    if isinstance(value, str):
        result["text_sha256"] = _sha_text(value)
    elif isinstance(value, bytes):
        result.update(sha256=hashlib.sha256(value).hexdigest(), bytes=len(value))
    return result


class _Sanitizer:
    def __init__(self, secrets: tuple[str, ...], limit: int) -> None:
        self.secrets = secrets
        self.remaining = limit
        self.nodes = 0

    def reason(self, value: str) -> str | None:
        if any(secret in value for secret in self.secrets):
            return "configured_secret"
        decoded = unquote(unquote(value))
        if any(secret in decoded for secret in self.secrets) or _CREDENTIAL.search(decoded):
            return "credential"
        if _REFERENCE.search(decoded):
            return "embedded_reference"
        if _PATH.search(decoded):
            return "absolute_path"
        if _EMBEDDED.search(decoded):
            return "embedded_payload"
        return None

    def value(self, value: object, depth: int = 0) -> object:
        self.nodes += 1
        if self.nodes > 256 or depth > 8 or self.remaining <= 0:
            return _redacted("structure_limit")
        self.remaining -= 16
        if value is None or isinstance(value, bool):
            return value
        if isinstance(value, int) and value.bit_length() > 1024:
            return _redacted("number_size_limit")
        if isinstance(value, int | float):
            return value if math.isfinite(value) else _redacted("nonfinite_number")
        if isinstance(value, str):
            reason = self.reason(value)
            if reason:
                return _redacted(reason, value)
            encoded = value.encode("utf-8", errors="replace")
            if len(encoded) > min(2048, self.remaining):
                return _redacted("string_limit", value)
            self.remaining -= len(encoded)
            return value
        if isinstance(value, bytes):
            return _redacted("embedded_bytes", value)
        if isinstance(value, Mapping):
            mapping_result: dict[str, object] = {}
            for index, (key, item) in enumerate(value.items()):
                if index >= 64 or self.remaining <= 0 or self.nodes >= 256:
                    mapping_result["_journal_truncated"] = True
                    break
                if not isinstance(key, str) or not _KEY.fullmatch(key) or self.reason(key):
                    key = "redacted_key_" + str(index)
                self.remaining -= len(key) + 4
                mapping_result[key] = (
                    _redacted("sensitive_field")
                    if _SENSITIVE_KEY.search(key)
                    else self.value(item, depth + 1)
                )
            return mapping_result
        if isinstance(value, Sequence):
            sequence_result: list[object] = []
            for index, item in enumerate(value):
                if index >= 64 or self.remaining <= 0 or self.nodes >= 256:
                    sequence_result.append(_redacted("sequence_limit"))
                    break
                sequence_result.append(self.value(item, depth + 1))
            return sequence_result
        return _redacted("unsupported_type")


def _bounded_value(value: object, secrets: tuple[str, ...], limit: int) -> object:
    safe = _Sanitizer(secrets, limit).value(value)
    encoded = json.dumps(safe, ensure_ascii=True, allow_nan=False).encode()
    if len(encoded) > limit:
        return _redacted("serialized_structure_limit")
    return safe


def _reply(value: str, secrets: tuple[str, ...]) -> dict[str, object]:
    result: dict[str, object] = {"original_text_sha256": _sha_text(value)}
    if len(value) > MAX_REPLY_BYTES * 2:
        result["text"] = "[omitted: reply size limit]"
        result["truncated"] = True
        return result
    try:
        parsed = json.loads(value)
    except (ValueError, RecursionError):
        parsed = value
    safe = _bounded_value(parsed, secrets, MAX_REPLY_BYTES)
    text = safe if isinstance(safe, str) else json.dumps(safe, ensure_ascii=True, allow_nan=False)
    result["text"] = text
    result["truncated"] = text != value
    return result


def _image_hashes(images: tuple[str, ...]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for image in images[:MAX_RECORDED_IMAGES]:
        if len(image) <= MAX_IMAGE_BYTES * 4 // 3 + 64:
            match = _IMAGE.fullmatch(image)
            if match:
                try:
                    payload = base64.b64decode(match[2], validate=True)
                    if len(payload) <= MAX_IMAGE_BYTES:
                        result.append(
                            {
                                "sha256": hashlib.sha256(payload).hexdigest(),
                                "bytes": len(payload),
                                "media_type": "image/" + match[1],
                            }
                        )
                        continue
                except ValueError:
                    pass
        result.append({"reference_sha256": _sha_text(image), "content_not_hashed": True})
    if len(images) > MAX_RECORDED_IMAGES:
        result.append({"omitted_image_count": len(images) - MAX_RECORDED_IMAGES})
    return result


def _safe_directory(root: Path, episode_id: str) -> Path:
    root = Path(root).absolute()
    if any(path.is_symlink() for path in (root, *root.parents)):
        raise ValueError("Journal root cannot have symlinked parents")
    root.mkdir(parents=True, exist_ok=True)
    target = root / episode_id
    if target.is_symlink():
        raise ValueError("Journal episode directory cannot be a symlink")
    target.mkdir(exist_ok=True)
    return target


def _atomic_record(path: Path, value: dict[str, object], secrets: tuple[str, ...]) -> None:
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("Journal record cannot have symlinked parents")
    payload = json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False).encode() + b"\n"
    if len(payload) > MAX_EVENT_BYTES:
        raise ValueError("Journal record exceeds its byte limit")
    if any(secret.encode() in payload for secret in secrets):
        raise ValueError("Journal record contains a configured secret")
    descriptor, temporary = tempfile.mkstemp(prefix=".event-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)
        parent_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _configuration(
    root: Path, episode_id: str, secrets: Sequence[str]
) -> tuple[Path, tuple[str, ...]]:
    if not isinstance(episode_id, str) or not _EPISODE.fullmatch(episode_id):
        raise ValueError("Journal episode_id must be a portable non-path identifier")
    if any(not isinstance(secret, str) for secret in secrets):
        raise ValueError("Journal secrets must be explicitly supplied strings")
    secrets = tuple(secret for secret in secrets if secret)
    directory = _safe_directory(root, episode_id)
    return (directory, tuple(secrets))


def _recorder(
    directory: Path, episode_id: str, tool_name: str, secrets: tuple[str, ...]
) -> EventRecorder:
    invocation_id = uuid.uuid4().hex
    base = {
        "schema_version": 1,
        "episode_id": episode_id,
        "invocation_id": invocation_id,
        "tool_name": tool_name,
    }

    def record(event: str, **fields: object) -> None:
        value = {
            **base,
            "event": event,
            "at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            **fields,
        }
        try:
            _atomic_record(directory / f"{invocation_id}.{event}.json", value, secrets)
        except Exception:
            if tool_name == "submit":
                raise SubmitJournalStopped("Submit journal persistence failed") from None
            raise ToolJournalError(
                "Tool journal persistence failed; do not repeat unknown side effects"
            ) from None

    return record


def journal_tools(
    tools: Sequence[Tool], root: Path, episode_id: str, *, secrets: Sequence[str] = ()
) -> tuple[Tool, ...]:
    """Wrap tools with start/finish records under root/episode_id.

    Pass a dedicated run journal directory as root and backend.secrets explicitly.
    A start without a finish denotes an interrupted or unrecorded completion,
    never a successful call. IDs are journal-local; gnode's public handler API
    does not expose the provider tool-call ID. The separate meter retains those.
    """
    directory, safe_secrets = _configuration(root, episode_id, secrets)
    wrapped = []
    for tool in tools:

        async def invoke(arguments: Mapping[str, object], *, tool: Tool = tool) -> ToolResult:
            record = _recorder(directory, episode_id, tool.name, safe_secrets)
            record("started", arguments=_bounded_value(arguments, safe_secrets, MAX_ARGUMENT_BYTES))
            started = time.monotonic()
            try:
                result = tool.handler(arguments)
                if inspect.isawaitable(result):
                    result = await result
                if not isinstance(result, ToolResult):
                    raise TypeError("Tool handlers must return a ToolResult")
            except BaseException as error:
                status = (
                    "cancelled"
                    if isinstance(error, asyncio.CancelledError)
                    else "refused"
                    if isinstance(error, ToolInvocationError)
                    else "error"
                )
                try:
                    record(
                        "finished",
                        status=status,
                        duration_seconds=time.monotonic() - started,
                        error={
                            "type": type(error).__name__,
                            "message": _reply(str(error), safe_secrets),
                        },
                    )
                except ToolJournalError:
                    if isinstance(error, asyncio.CancelledError):
                        raise error from None
                    raise
                raise
            record(
                "finished",
                status="succeeded",
                duration_seconds=time.monotonic() - started,
                reply=_reply(result.text, safe_secrets),
                images=_image_hashes(result.images),
            )
            return result

        wrapped.append(Tool(tool.name, tool.description, tool.parameters, handler=invoke))
    return tuple(wrapped)


def journal_submit[ParseInput, ParseOutput](
    parse: Callable[[ParseInput], ParseOutput],
    root: Path,
    episode_id: str,
    *,
    secrets: Sequence[str] = (),
) -> Callable[[ParseInput], ParseOutput]:
    """Wrap a synchronous ToolLoopRequest.parse callback without owning admission.

    `parsed` means this callback returned; later validation, serialization and
    artifact persistence still belong to ToolLoopService. Its rejected-submit
    branch catches all Exception subclasses. Persistence failure therefore uses
    SubmitJournalStopped (CancelledError), and the host must retain that terminal
    failure. Regular schema/semantic refusals are re-raised unchanged.
    """
    if not callable(parse) or inspect.iscoroutinefunction(parse):
        raise ValueError("Submit parse must be a synchronous callable")
    directory, safe_secrets = _configuration(root, episode_id, secrets)

    def invoke(arguments: ParseInput) -> ParseOutput:
        record = _recorder(directory, episode_id, "submit", safe_secrets)
        record("started", arguments=_bounded_value(arguments, safe_secrets, MAX_ARGUMENT_BYTES))
        started = time.monotonic()
        try:
            result = parse(arguments)
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise TypeError("Submit parse must return synchronously")
        except BaseException as error:
            record(
                "finished",
                status="cancelled" if isinstance(error, asyncio.CancelledError) else "refused",
                duration_seconds=time.monotonic() - started,
                error={"type": type(error).__name__, "message": _reply(str(error), safe_secrets)},
            )
            raise
        record(
            "finished",
            status="parsed",
            duration_seconds=time.monotonic() - started,
            scope="parse_callback_only_not_artifact_admission",
            value=_bounded_value(result, safe_secrets, MAX_ARGUMENT_BYTES),
        )
        return result

    return invoke
