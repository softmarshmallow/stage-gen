"""The cache: files by content, step results by identity, paid calls by request.

``.gnode/cache`` holds three things:

- ``files/``: every file any step produced or read, under the SHA-256 of its bytes;
- ``results/``: one record per step identity: its outputs (by digest), its facts, and
  the digests of the files it read, re-checked before the record is trusted;
- ``calls/``: one record per paid capability call, keyed by capability, route
  fingerprint, canonical request and take. A retried, resumed or re-run step that makes
  an identical request is answered here and billed nothing.

Records are written atomically, files before the records that name them, so a crash
never leaves a record whose bytes are missing.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gnode.workflow.values import Collection, FactsReader, FileValue, canonical_json, digest_of

RESULT_KIND = "gnode-result-v1"
CALL_KIND = "gnode-call-v1"


class StoreError(ValueError):
    pass


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".", suffix=".part")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _json_value(file: FileValue) -> Any:
    return {
        "digest": file.digest,
        "kind": file.kind,
        "name": file.name,
        "size": file.size,
        **({"key": file.key} if file.key is not None else {}),
    }


@dataclass(frozen=True, slots=True)
class CallRecord:
    """A paid call's answer: the files it returned, its data, what it cost."""

    files: Mapping[str, FileValue]
    data: Any
    cost_usd: float | None


class Store:
    """One cache directory."""

    def __init__(self, root: Path, *, facts_reader: FactsReader | None = None) -> None:
        self.root = root
        self.facts_reader = facts_reader

    # ------------------------------------------------------------------ files

    def file_path(self, digest: str) -> Path:
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise StoreError(f"not a SHA-256 digest: {digest!r}")
        return self.root / "files" / digest[:2] / digest

    def put_bytes(self, data: bytes, *, kind: str, name: str, key: str | None = None) -> FileValue:
        digest = hashlib.sha256(data).hexdigest()
        path = self.file_path(digest)
        if not path.is_file() or path.stat().st_size != len(data):
            _atomic_write(path, data)
        return self.file(digest, kind=kind, name=name, size=len(data), key=key)

    def put_file(self, source: Path, *, kind: str, name: str) -> FileValue:
        return self.put_bytes(source.read_bytes(), kind=kind, name=name)

    def file(
        self, digest: str, *, kind: str, name: str, size: int, key: str | None = None
    ) -> FileValue:
        path = self.file_path(digest)
        content: Any = None
        if kind == "json" or kind.endswith("+json") or kind == "annotations":
            content = json.loads(path.read_bytes())
        elif kind.startswith("text") and size <= 1_000_000:
            content = path.read_text(encoding="utf-8")
        return FileValue(
            digest=digest,
            kind=kind,
            name=name,
            size=size,
            key=key,
            content=content,
            facts_reader=self.facts_reader,
            location=str(path),
        )

    def has(self, file: FileValue) -> bool:
        path = self.file_path(file.digest)
        return path.is_file() and path.stat().st_size == file.size

    def verify(self, file: FileValue) -> bool:
        path = self.file_path(file.digest)
        return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == file.digest

    # ---------------------------------------------------------------- results

    def _result_path(self, identity: str) -> Path:
        return self.root / "results" / identity[:2] / f"{identity}.json"

    def save_result(
        self,
        identity: str,
        *,
        type_identity: str,
        outputs: Mapping[str, Any],
        facts: Mapping[str, Any],
        read: Mapping[str, str],
        cost_usd: float | None,
    ) -> None:
        record = {
            "kind": RESULT_KIND,
            "identity": identity,
            "type": type_identity,
            "outputs": {name: self._encode(value) for name, value in outputs.items()},
            "facts": dict(facts),
            "read": dict(sorted(read.items())),
            "cost_usd": cost_usd,
        }
        _atomic_write(self._result_path(identity), canonical_json(record))

    def load_result(
        self, identity: str, *, read: Mapping[str, str]
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """``(outputs, facts)`` for ``identity`` when its record and every file are intact.

        ``read`` is what the step reads now; a record made from other bytes is not
        trusted, whatever its identity says.
        """

        path = self._result_path(identity)
        if not path.is_file():
            return None
        try:
            record = json.loads(path.read_bytes())
        except (OSError, ValueError):
            return None
        if record.get("kind") != RESULT_KIND or record.get("identity") != identity:
            return None
        if record.get("read") != dict(sorted(read.items())):
            return None
        try:
            outputs = {name: self._decode(value) for name, value in record["outputs"].items()}
        except (KeyError, StoreError, ValueError, OSError):
            return None
        if not all(self.has(file) for file in _files_in(outputs)):
            return None
        return outputs, dict(record.get("facts", {}))

    def _encode(self, value: Any) -> Any:
        if isinstance(value, FileValue):
            return {"file": _json_value(value)}
        if isinstance(value, Collection):
            return {"collection": [[key, self._encode(item)] for key, item in value.items]}
        if isinstance(value, list):
            return {"list": [self._encode(item) for item in value]}
        if value is None:
            return {"none": True}
        raise StoreError(f"a step output is a file, a list or a collection, not {value!r}")

    def _decode(self, value: Any) -> Any:
        if "file" in value:
            entry = value["file"]
            return self.file(
                entry["digest"],
                kind=entry["kind"],
                name=entry["name"],
                size=entry["size"],
                key=entry.get("key"),
            )
        if "collection" in value:
            return Collection(tuple((key, self._decode(item)) for key, item in value["collection"]))
        if "list" in value:
            return [self._decode(item) for item in value["list"]]
        if value.get("none"):
            return None
        raise StoreError("unreadable output record")

    def has_result(self, identity: str) -> bool:
        return self._result_path(identity).is_file()

    # ------------------------------------------------------------------ calls

    @staticmethod
    def call_key(*, capability: str, route: str, request: Any, take: int) -> str:
        return digest_of(
            {"capability": capability, "route": route, "request": request, "take": take}
        )

    def _call_path(self, key: str) -> Path:
        return self.root / "calls" / key[:2] / f"{key}.json"

    def load_call(self, key: str) -> CallRecord | None:
        path = self._call_path(key)
        if not path.is_file():
            return None
        try:
            record = json.loads(path.read_bytes())
            files = {name: self._decode({"file": entry}) for name, entry in record["files"].items()}
        except (OSError, ValueError, KeyError, StoreError):
            return None
        if record.get("kind") != CALL_KIND or not all(self.has(file) for file in files.values()):
            return None
        return CallRecord(files, record.get("data"), record.get("cost_usd"))

    def save_call(self, key: str, record: CallRecord) -> None:
        document = {
            "kind": CALL_KIND,
            "key": key,
            "files": {name: _json_value(file) for name, file in record.files.items()},
            "data": record.data,
            "cost_usd": record.cost_usd,
        }
        _atomic_write(self._call_path(key), canonical_json(document))


def _files_in(value: Any) -> list[FileValue]:
    if isinstance(value, FileValue):
        return [value]
    if isinstance(value, Collection):
        return [file for _, item in value.items for file in _files_in(item)]
    if isinstance(value, Mapping):
        return [file for item in value.values() for file in _files_in(item)]
    if isinstance(value, list):
        return [file for item in value for file in _files_in(item)]
    return []


def files_in(value: Any) -> list[FileValue]:
    """Every file a value holds, in order."""

    return _files_in(value)


__all__ = ["CallRecord", "Store", "StoreError", "files_in"]
