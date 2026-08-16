from __future__ import annotations

import asyncio
import math
from typing import Any

import pytest

from stage_gen.reliability import (
    AbortError,
    CancellationError,
    CancellationToken,
    RetryContext,
    RetryExhaustedError,
    RetryPolicy,
    retry_with_backoff,
)


def _other_pending_tasks() -> set[asyncio.Task[object]]:
    current = asyncio.current_task()
    return {task for task in asyncio.all_tasks() if task is not current and not task.done()}


@pytest.mark.asyncio
async def test_retries_failures_and_reports_one_based_attempt() -> None:
    seen: list[tuple[int, int, int]] = []

    async def operation(context: RetryContext) -> int:
        attempt = context.attempt
        seen.append((attempt, context.retry, context.max_attempts))
        if attempt < 3:
            raise TypeError("network unavailable")
        return attempt

    result = await retry_with_backoff(
        operation,
        policy=RetryPolicy(initial_delay_s=0),
    )
    assert result == 3
    assert seen == [(1, 0, 6), (2, 1, 6), (3, 2, 6)]


@pytest.mark.asyncio
async def test_exhaustion_is_six_attempts_and_redacts_cause() -> None:
    secret = "sk-or-v1-super-secret"
    calls = 0

    async def operation(_context: object) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError(f"Authorization: Bearer {secret}")

    with pytest.raises(RetryExhaustedError) as captured:
        await retry_with_backoff(
            operation,
            policy=RetryPolicy(initial_delay_s=0),
            label=f"provider {secret}",
            secrets=(secret,),
        )
    assert calls == 6
    assert captured.value.attempts == 6
    assert captured.value.retries == 5
    assert secret not in str(captured.value)
    assert secret not in str(captured.value.__cause__)


@pytest.mark.parametrize("max_attempts", [1, 5, 7, 100])
def test_retry_policy_rejects_any_attempt_limit_other_than_six(max_attempts: int) -> None:
    with pytest.raises(ValueError, match="exactly 6"):
        RetryPolicy(max_attempts=max_attempts)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("initial_delay_s", True),
        ("initial_delay_s", "0.5"),
        ("initial_delay_s", math.nan),
        ("initial_delay_s", math.inf),
        ("initial_delay_s", -0.1),
        ("max_delay_s", math.nan),
        ("max_delay_s", math.inf),
        ("max_delay_s", -0.1),
        ("backoff_factor", False),
        ("backoff_factor", "2"),
        ("backoff_factor", math.nan),
        ("backoff_factor", math.inf),
        ("backoff_factor", 0),
        ("backoff_factor", -1),
        ("attempt_timeout_s", True),
        ("attempt_timeout_s", "300"),
        ("attempt_timeout_s", math.nan),
        ("attempt_timeout_s", math.inf),
        ("attempt_timeout_s", 0),
        ("attempt_timeout_s", -1),
    ],
)
def test_retry_policy_rejects_invalid_timing_values(field: str, value: object) -> None:
    kwargs: Any = {field: value}
    with pytest.raises(ValueError, match=rf"{field} must be"):
        RetryPolicy(**kwargs)


@pytest.mark.parametrize("timeout_s", [True, "1", math.nan, math.inf, 0, -1])
@pytest.mark.asyncio
async def test_retry_override_rejects_invalid_timeout_without_calling_operation(
    timeout_s: object,
) -> None:
    called = False

    async def operation(_context: object) -> None:
        nonlocal called
        called = True

    with pytest.raises(ValueError, match="timeout_s must be a positive finite number"):
        await retry_with_backoff(operation, timeout_s=timeout_s)  # type: ignore[arg-type]
    assert not called


@pytest.mark.asyncio
async def test_caller_cancellation_aborts_active_attempt_without_retry() -> None:
    token = CancellationToken()
    started = asyncio.Event()
    calls = 0

    async def operation(_context: object) -> None:
        nonlocal calls
        calls += 1
        started.set()
        await asyncio.Event().wait()

    pending = asyncio.create_task(
        retry_with_backoff(
            operation,
            cancellation=token,
            policy=RetryPolicy(initial_delay_s=0),
            secrets=("private cancellation",),
        )
    )
    await started.wait()
    token.cancel("private cancellation")
    with pytest.raises(AbortError) as captured:
        await pending
    assert captured.value.name == "AbortError"
    assert isinstance(captured.value, CancellationError)
    assert calls == 1
    assert "private cancellation" not in str(captured.value)


@pytest.mark.asyncio
async def test_api_ordered_outer_cancellation_reaps_active_attempt() -> None:
    token = CancellationToken()
    started = asyncio.Event()
    reaped = asyncio.Event()
    baseline = _other_pending_tasks()

    async def operation(_context: object) -> None:
        started.set()
        try:
            await asyncio.Future[None]()
        finally:
            reaped.set()

    pending = asyncio.create_task(retry_with_backoff(operation, cancellation=token))
    await started.wait()
    token.cancel("run cancelled by request")
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    await asyncio.sleep(0)
    assert reaped.is_set()
    assert _other_pending_tasks() == baseline


@pytest.mark.asyncio
async def test_outer_cancellation_reaps_token_aware_backoff() -> None:
    token = CancellationToken()
    sleeping = asyncio.Event()
    reaped = asyncio.Event()
    baseline = _other_pending_tasks()

    async def operation(_context: object) -> None:
        raise RuntimeError("retry")

    async def sleep(_delay: float) -> None:
        sleeping.set()
        try:
            await asyncio.Future[None]()
        finally:
            reaped.set()

    pending = asyncio.create_task(retry_with_backoff(operation, cancellation=token, sleep=sleep))
    await sleeping.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    await asyncio.sleep(0)
    assert reaped.is_set()
    assert _other_pending_tasks() == baseline


@pytest.mark.asyncio
async def test_per_attempt_timeout_retries_all_six_and_cleans_tasks() -> None:
    calls = 0
    cleaned = 0

    async def operation(_context: object) -> None:
        nonlocal calls, cleaned
        calls += 1
        try:
            await asyncio.Event().wait()
        finally:
            cleaned += 1

    with pytest.raises(RetryExhaustedError, match="timed out"):
        await retry_with_backoff(
            operation,
            policy=RetryPolicy(initial_delay_s=0, attempt_timeout_s=0.001),
        )
    assert calls == 6
    assert cleaned == 6


@pytest.mark.asyncio
async def test_cancellation_interrupts_backoff_before_another_attempt() -> None:
    token = CancellationToken()
    sleeping = asyncio.Event()
    calls = 0

    async def operation(_context: object) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("retry")

    async def sleep(_delay: float) -> None:
        sleeping.set()
        await asyncio.Event().wait()

    pending = asyncio.create_task(retry_with_backoff(operation, cancellation=token, sleep=sleep))
    await sleeping.wait()
    token.cancel("stop")
    with pytest.raises(CancellationError):
        await pending
    assert calls == 1


@pytest.mark.asyncio
async def test_backoff_is_capped_and_failure_hook_observes_sanitized_errors() -> None:
    delays: list[float] = []
    hook_errors: list[str] = []

    async def operation(_context: object) -> None:
        raise RuntimeError("secret-value")

    async def sleep(delay: float) -> None:
        delays.append(delay)

    def hook(_context: object, error: Exception, _delay: float) -> None:
        hook_errors.append(str(error))

    with pytest.raises(RetryExhaustedError):
        await retry_with_backoff(
            operation,
            secrets=("secret-value",),
            sleep=sleep,
            on_attempt_failure=hook,
        )
    assert delays == [0.5, 1.0, 2.0, 4.0, 8.0]
    assert all("secret-value" not in error for error in hook_errors)
