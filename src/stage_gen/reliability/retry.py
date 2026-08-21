"""The single retry owner for every model/provider operation."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import math
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from numbers import Real
from typing import Any

from .cancellation import AbortError, CancellationError, CancellationToken
from .redaction import redact_secrets

AI_RETRY_COUNT = 5
MAX_AI_ATTEMPTS = 6
DEFAULT_AI_ATTEMPT_TIMEOUT_S = 300.0

Sleep = Callable[[float], Awaitable[None]]
AttemptFailureHook = Callable[["RetryContext", Exception, float], object]


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = MAX_AI_ATTEMPTS
    initial_delay_s: float = 0.5
    backoff_factor: float = 2.0
    max_delay_s: float = 8.0
    attempt_timeout_s: float = DEFAULT_AI_ATTEMPT_TIMEOUT_S

    def __post_init__(self) -> None:
        if isinstance(self.max_attempts, bool) or not isinstance(self.max_attempts, int):
            raise ValueError("max_attempts must be an integer")
        if self.max_attempts != MAX_AI_ATTEMPTS:
            raise ValueError(f"max_attempts must be exactly {MAX_AI_ATTEMPTS}")
        _validate_timing(self.initial_delay_s, "initial_delay_s", allow_zero=True)
        _validate_timing(self.max_delay_s, "max_delay_s", allow_zero=True)
        _validate_timing(self.backoff_factor, "backoff_factor", allow_zero=False)
        _validate_timing(self.attempt_timeout_s, "attempt_timeout_s", allow_zero=False)


@dataclass(frozen=True, slots=True)
class RetryContext:
    attempt: int
    retry: int
    max_attempts: int
    cancellation: CancellationToken | None

    def raise_if_cancelled(self) -> None:
        if self.cancellation is not None:
            self.cancellation.raise_if_cancelled()


class AttemptTimeoutError(TimeoutError):
    """One retryable attempt exceeded its deadline."""


@dataclass(frozen=True, slots=True)
class RetryFailureRecord:
    """Redacted, typed evidence for one failed retry attempt."""

    attempt: int
    error_type: str
    message: str
    code: str | None = None
    row: int | None = None
    column: int | None = None

    def as_dict(self) -> dict[str, object]:
        record: dict[str, object] = {
            "attempt": self.attempt,
            "error_type": self.error_type,
            "message": self.message,
        }
        if self.code is not None:
            record["code"] = self.code
        if self.row is not None:
            record["row"] = self.row
        if self.column is not None:
            record["column"] = self.column
        return record


class RetryExhaustedError(Exception):
    """All configured attempts failed."""

    def __init__(
        self,
        label: str,
        cause: Exception,
        attempts: int,
        failure_history: Sequence[RetryFailureRecord] = (),
    ) -> None:
        self.attempts = attempts
        self.retries = attempts - 1
        self.cause = cause
        self.failure_history = tuple(failure_history)
        super().__init__(
            f"{label} failed after {attempts} attempts ({attempts - 1} retries): {cause}"
        )


async def retry_with_backoff[T](
    operation: Callable[[RetryContext], Awaitable[T]],
    *,
    policy: RetryPolicy | None = None,
    label: str = "AI operation",
    secrets: Sequence[str] = (),
    timeout_s: float | None = None,
    cancellation: CancellationToken | None = None,
    sleep: Sleep = asyncio.sleep,
    on_attempt_failure: AttemptFailureHook | None = None,
) -> T:
    """Run once, then retry failures according to the shared bounded policy."""

    active_policy = policy or RetryPolicy()
    if timeout_s is not None:
        _validate_timing(timeout_s, "timeout_s", allow_zero=False)
        active_policy = replace(active_policy, attempt_timeout_s=timeout_s)
    safe_label = redact_secrets(label.strip() or "AI operation", secrets)
    delay_s = active_policy.initial_delay_s
    last_error: Exception = Exception("unknown failure")
    failure_history: list[RetryFailureRecord] = []

    for attempt in range(1, active_policy.max_attempts + 1):
        _raise_if_cancelled(cancellation, secrets)
        context = RetryContext(
            attempt=attempt,
            retry=attempt - 1,
            max_attempts=active_policy.max_attempts,
            cancellation=cancellation,
        )
        try:
            return await _run_attempt(
                operation,
                context,
                timeout_s=active_policy.attempt_timeout_s,
                label=safe_label,
                cancellation=cancellation,
            )
        except asyncio.CancelledError:
            raise
        except CancellationError as error:
            raise AbortError(redact_secrets(str(error), secrets)) from None
        except Exception as error:
            safe_message = redact_secrets(str(error), secrets)
            failure_history.append(
                _retry_failure_record(error, attempt=attempt, message=safe_message, secrets=secrets)
            )
            last_error = Exception(safe_message)

        if attempt == active_policy.max_attempts:
            break
        next_delay_s = min(delay_s, active_policy.max_delay_s)
        if on_attempt_failure is not None:
            hook_result = on_attempt_failure(context, last_error, next_delay_s)
            if inspect.isawaitable(hook_result):
                await hook_result
        if next_delay_s > 0:
            try:
                await _sleep_with_cancellation(sleep, next_delay_s, cancellation)
            except CancellationError as error:
                raise AbortError(redact_secrets(str(error), secrets)) from None
        delay_s = min(delay_s * active_policy.backoff_factor, active_policy.max_delay_s)

    exhausted = RetryExhaustedError(
        safe_label,
        last_error,
        active_policy.max_attempts,
        failure_history,
    )
    raise exhausted from last_error


def _retry_failure_record(
    error: Exception,
    *,
    attempt: int,
    message: str,
    secrets: Sequence[str],
) -> RetryFailureRecord:
    """Capture stable diagnostics without retaining the original exception."""

    error_type = redact_secrets(
        f"{type(error).__module__}.{type(error).__qualname__}",
        secrets,
    )
    raw_code = getattr(error, "code", None)
    code = redact_secrets(raw_code, secrets) if isinstance(raw_code, str) else None
    raw_row = getattr(error, "row", None)
    row = raw_row if isinstance(raw_row, int) and not isinstance(raw_row, bool) else None
    raw_column = getattr(error, "column", None)
    column = (
        raw_column if isinstance(raw_column, int) and not isinstance(raw_column, bool) else None
    )
    return RetryFailureRecord(
        attempt=attempt,
        error_type=error_type,
        message=message,
        code=code,
        row=row,
        column=column,
    )


async def _run_attempt[T](
    operation: Callable[[RetryContext], Awaitable[T]],
    context: RetryContext,
    *,
    timeout_s: float,
    label: str,
    cancellation: CancellationToken | None,
) -> T:
    operation_task: asyncio.Future[T] = asyncio.ensure_future(operation(context))
    cancellation_task = (
        asyncio.create_task(cancellation.wait()) if cancellation is not None else None
    )
    waiters: set[asyncio.Future[Any]] = {operation_task}
    if cancellation_task is not None:
        waiters.add(cancellation_task)
    try:
        done, _pending = await asyncio.wait(
            waiters, timeout=timeout_s, return_when=asyncio.FIRST_COMPLETED
        )
        if cancellation is not None and cancellation.cancelled:
            await _cancel_task(operation_task)
            cancellation.raise_if_cancelled()
        if operation_task in done:
            return operation_task.result()
        await _cancel_task(operation_task)
        raise AttemptTimeoutError(f"{label} timed out after {_format_seconds(timeout_s)}s")
    finally:
        await _cancel_task(operation_task)
        if cancellation_task is not None:
            await _cancel_task(cancellation_task)


async def _sleep_with_cancellation(
    sleep: Sleep,
    delay_s: float,
    cancellation: CancellationToken | None,
) -> None:
    if cancellation is None:
        await sleep(delay_s)
        return
    cancellation.raise_if_cancelled()
    sleep_task: asyncio.Future[None] = asyncio.ensure_future(sleep(delay_s))
    cancellation_task = asyncio.create_task(cancellation.wait())
    waiters: set[asyncio.Future[Any]] = {sleep_task, cancellation_task}
    try:
        await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
        if cancellation.cancelled:
            await _cancel_task(sleep_task)
            cancellation.raise_if_cancelled()
        await sleep_task
    finally:
        await _cancel_task(sleep_task)
        await _cancel_task(cancellation_task)


async def _cancel_task(task: asyncio.Future[Any]) -> None:
    if not task.done():
        task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await task


def _format_seconds(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def _validate_timing(value: object, label: str, *, allow_zero: bool) -> None:
    qualifier = "non-negative" if allow_zero else "positive"
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{label} must be a {qualifier} finite number")
    if value < 0 or (not allow_zero and value == 0):
        raise ValueError(f"{label} must be a {qualifier} finite number")


def _raise_if_cancelled(cancellation: CancellationToken | None, secrets: Sequence[str]) -> None:
    if cancellation is None:
        return
    try:
        cancellation.raise_if_cancelled()
    except CancellationError as error:
        raise AbortError(redact_secrets(str(error), secrets)) from None
