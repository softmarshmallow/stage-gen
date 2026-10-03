"""The run record: one append-only event log of what every invocation of a run did.

Every run writes the same event vocabulary (``gnode-run-events-v1``), so one reader
projects any run.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

#: The one event vocabulary every run log is written in.
RUN_EVENTS_SCHEMA_VERSION = 1
RUN_EVENTS_KIND = "gnode-run-events-v1"


class JsonlTraceSink:
    """Write a JSONL event log without persisting absolute paths or secrets.

    A new log is created exclusively. With ``append``, an existing log is continued
    instead: that is how a resumed run keeps one record, under the run's lock.
    """

    def __init__(self, path: Path, *, append: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if append else os.O_EXCL)
        descriptor = os.open(path, flags, 0o600)
        self._stream = os.fdopen(descriptor, "a" if append else "w", encoding="utf-8")

    def emit(self, event: Mapping[str, object]) -> None:
        self._stream.write(json.dumps(dict(event), sort_keys=True, separators=(",", ":")))
        self._stream.write("\n")
        self._stream.flush()

    def close(self) -> None:
        self._stream.close()


__all__ = ["RUN_EVENTS_KIND", "RUN_EVENTS_SCHEMA_VERSION", "JsonlTraceSink"]
