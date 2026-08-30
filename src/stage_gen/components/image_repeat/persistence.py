"""Cancellation-aware all-or-nothing persistence for image-repeat artifacts."""

from __future__ import annotations

import asyncio
import contextlib
import os
import threading
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from gnode import AbortError, CancellationToken, redact_secrets

PersistenceCheckpoint = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class PendingImageRepeatFile:
    role: str
    path: Path
    data: bytes


class _TaskPersistenceCancelled(Exception):
    pass


async def persist_image_repeat_files(
    files: Sequence[PendingImageRepeatFile],
    *,
    cancellation: CancellationToken | None,
    secrets: tuple[str, ...],
    checkpoint: PersistenceCheckpoint | None = None,
) -> None:
    """Install every successful output, manifest, and sidecar or install none."""

    task_cancelled = threading.Event()
    worker = asyncio.create_task(
        asyncio.to_thread(
            _persist_image_repeat_files,
            tuple(files),
            cancellation,
            task_cancelled,
            checkpoint,
        )
    )
    try:
        await asyncio.shield(worker)
        if cancellation is not None:
            cancellation.raise_if_cancelled()
    except asyncio.CancelledError:
        task_cancelled.set()
        with contextlib.suppress(BaseException):
            await asyncio.shield(worker)
        await asyncio.to_thread(_remove_committed, tuple(files))
        raise
    except AbortError as error:
        await asyncio.to_thread(_remove_committed, tuple(files))
        raise AbortError(redact_secrets(str(error), secrets)) from None


def _persist_image_repeat_files(
    files: tuple[PendingImageRepeatFile, ...],
    cancellation: CancellationToken | None,
    task_cancelled: threading.Event,
    checkpoint: PersistenceCheckpoint | None,
) -> None:
    if not files:
        raise ValueError("image-repeat persistence requires at least one file")
    parents = {item.path.parent.resolve() for item in files}
    if len(parents) != 1:
        raise ValueError("image-repeat persistence targets must share one output directory")
    parent = next(iter(parents))
    parent.mkdir(parents=True, exist_ok=True)
    temporary: list[tuple[PendingImageRepeatFile, Path]] = []
    installed: list[PendingImageRepeatFile] = []
    try:
        _raise_if_cancelled(cancellation, task_cancelled)
        for item in files:
            _raise_if_cancelled(cancellation, task_cancelled)
            temp = parent / f".{item.path.name}.{uuid.uuid4().hex}.repeat-tmp"
            _write_exclusive(temp, item.data)
            temporary.append((item, temp))
            _checkpoint(checkpoint, f"staged:{item.role}")
            _raise_if_cancelled(cancellation, task_cancelled)
        for item, temp in temporary:
            _raise_if_cancelled(cancellation, task_cancelled)
            os.link(temp, item.path)
            installed.append(item)
            _checkpoint(checkpoint, f"installed:{item.role}")
            _raise_if_cancelled(cancellation, task_cancelled)
        _sync_directory(parent)
        _checkpoint(checkpoint, "synced")
        _raise_if_cancelled(cancellation, task_cancelled)
    except BaseException:
        for item in reversed(installed):
            with contextlib.suppress(OSError):
                item.path.unlink()
        with contextlib.suppress(OSError):
            _sync_directory(parent)
        raise
    finally:
        for _item, temp in temporary:
            with contextlib.suppress(OSError):
                temp.unlink()


def _write_exclusive(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _checkpoint(checkpoint: PersistenceCheckpoint | None, name: str) -> None:
    if checkpoint is not None:
        checkpoint(name)


def _raise_if_cancelled(
    cancellation: CancellationToken | None,
    task_cancelled: threading.Event,
) -> None:
    if task_cancelled.is_set():
        raise _TaskPersistenceCancelled("task cancelled during image-repeat persistence")
    if cancellation is not None:
        cancellation.raise_if_cancelled()


def _remove_committed(files: tuple[PendingImageRepeatFile, ...]) -> None:
    parents: set[Path] = set()
    for item in files:
        parents.add(item.path.parent)
        try:
            current = item.path.read_bytes()
        except OSError:
            continue
        if current == item.data:
            with contextlib.suppress(OSError):
                item.path.unlink()
    for parent in parents:
        with contextlib.suppress(OSError):
            _sync_directory(parent)
