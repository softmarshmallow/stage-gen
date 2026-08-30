"""Cooperative cancellation shared by retries, stages, and subprocesses."""

from __future__ import annotations

import asyncio
from typing import NoReturn

from .redaction import redact_secrets


class CancellationError(Exception):
    """Compatibility base for caller-requested cancellation errors."""


class AbortError(CancellationError):
    """A caller-requested cancellation; retry boundaries must not retry it."""

    name = "AbortError"


class CancellationToken:
    """Small asyncio-friendly cancellation primitive with a sanitized reason."""

    __slots__ = ("_event", "_reason", "_secrets")

    def __init__(self, *, secrets: tuple[str, ...] = ()) -> None:
        self._event = asyncio.Event()
        self._reason = "cancelled"
        self._secrets = secrets

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str:
        return redact_secrets(self._reason, self._secrets)

    def cancel(self, reason: str | BaseException = "cancelled") -> None:
        if self.cancelled:
            return
        self._reason = str(reason) or "cancelled"
        self._event.set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            self._raise()

    async def wait(self) -> str:
        await self._event.wait()
        return self.reason

    def _raise(self) -> NoReturn:
        raise AbortError(f"operation cancelled: {self.reason}")
