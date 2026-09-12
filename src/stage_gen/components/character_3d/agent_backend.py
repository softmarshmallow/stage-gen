"""Persistent per-attempt accounting around gnode's existing tool-loop backend.

Reservations use a configured input-token assumption, not a provider-enforced
spend cap. Unknown charges remain liabilities. The gnode service owns retries.
Only public gnode APIs are used; this module never creates a chat loop.
"""

from __future__ import annotations

import asyncio
import base64
import contextvars
import fcntl
import hashlib
import json
import math
import os
import re
import tempfile
import time
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol, cast

import httpx

from gnode import (
    AbortError,
    ProviderToolLoopStep,
    ToolLoopMessage,
    ToolLoopModelV1,
    ToolLoopStepRequest,
)
from stage_gen.components.character_3d.context import project_image_history

JsonObject = dict[str, Any]


class ToolLoopBackendFactory(Protocol):
    def __call__(
        self, *, api_key: str, model: str, client: httpx.AsyncClient
    ) -> ToolLoopModelV1: ...


_SOURCE = "https://openrouter.ai/api/v1/models"
_RECEIPT_ID = re.compile("^[A-Za-z0-9._:/-]{1,256}$")
_IMAGE = re.compile("^data:image/(png|jpeg|webp|gif);base64,([A-Za-z0-9+/=]+)$")


def _money(value: object, label: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite nonnegative decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label} must be a finite nonnegative decimal") from None
    if not result.is_finite() or result < 0:
        raise ValueError(f"{label} must be a finite nonnegative decimal")
    return result


def _positive_int(value: object, label: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


@dataclass(frozen=True)
class AgentBudget:
    """One ledger's shared budget; max_steps counts dispatches including retries."""

    max_usd: str
    max_steps: int
    max_wall_seconds: float
    input_token_reserve: int = 32768
    max_completion_tokens: int = 8192
    max_images: int = 12
    max_text_bytes: int = 98304
    max_image_bytes: int = 32 * 1024 * 1024
    recent_image_limit: int | None = None
    review_holdback_usd: str | None = None

    def __post_init__(self) -> None:
        if _money(self.max_usd, "max_usd") <= 0:
            raise ValueError("max_usd must be positive")
        object.__setattr__(self, "max_usd", str(_money(self.max_usd, "max_usd")))
        if self.review_holdback_usd is not None:
            holdback = _money(self.review_holdback_usd, "review_holdback_usd")
            if holdback >= _money(self.max_usd, "max_usd"):
                raise ValueError("review_holdback_usd must leave a positive producer allowance")
            object.__setattr__(self, "review_holdback_usd", str(holdback))
        for name in (
            "max_steps",
            "input_token_reserve",
            "max_completion_tokens",
            "max_images",
            "max_text_bytes",
            "max_image_bytes",
        ):
            _positive_int(getattr(self, name), name)
        if self.recent_image_limit is not None:
            _positive_int(self.recent_image_limit, "recent_image_limit")
            if self.recent_image_limit > self.max_images:
                raise ValueError("Recent image limit must fit the transcript image allowance")
        if (
            isinstance(self.max_wall_seconds, bool)
            or not isinstance(self.max_wall_seconds, int | float)
            or (not math.isfinite(self.max_wall_seconds))
            or (self.max_wall_seconds <= 0)
        ):
            raise ValueError("max_wall_seconds must be positive and finite")

    def record(self) -> JsonObject:
        """Keep the historical ledger shape when the optional policy is absent."""
        result = asdict(self)
        if self.review_holdback_usd is None:
            result.pop("review_holdback_usd")
        return result


class EpisodeBudgetHints:
    """Expose the existing service's counters without owning a loop or a retry.

    Hints are transient request projections, so old notes do not accumulate in
    the conversation. Only returned turns count; failed transport attempts stay
    in the metered backend's separate shared dispatch ledger. Token accounting
    intentionally follows ToolLoopService's reported integer total_tokens rule.
    """

    spec_version: ClassVar[Literal[1]] = 1

    def __init__(
        self,
        backend: ToolLoopModelV1,
        *,
        max_steps: int,
        max_total_tokens: int,
        read_only: bool = False,
    ) -> None:
        if type(read_only) is not bool:
            raise ValueError("read_only must be a host-authored boolean")
        self.provider, self.model, self.secrets = (backend.provider, backend.model, backend.secrets)
        self._backend = backend
        self.max_steps = _positive_int(max_steps, "max_steps")
        self.max_total_tokens = _positive_int(max_total_tokens, "max_total_tokens")
        self.completed_steps = 0
        self.counted_total_tokens = 0
        self.unreported_usage_steps = 0
        bind_role = getattr(backend, "bind_episode_role", None)
        if bind_role is not None:
            bind_role("reviewer" if read_only else "producer")

    def snapshot(self) -> dict[str, int]:
        return {
            "max_steps": self.max_steps,
            "max_total_tokens": self.max_total_tokens,
            "completed_steps": self.completed_steps,
            "remaining_steps": max(0, self.max_steps - self.completed_steps),
            "counted_total_tokens": self.counted_total_tokens,
            "remaining_counted_tokens": max(0, self.max_total_tokens - self.counted_total_tokens),
            "unreported_usage_steps": self.unreported_usage_steps,
        }

    def exhaustion_reason(self) -> str:
        if self.counted_total_tokens > self.max_total_tokens:
            return "episode_token_limit_exceeded"
        if self.completed_steps >= self.max_steps:
            return "episode_step_limit_exhausted"
        return "episode_service_exhausted"

    async def step(self, request: ToolLoopStepRequest) -> ProviderToolLoopStep:
        note = ToolLoopMessage(
            "user",
            "Host episode budget before this response: "
            + json.dumps(self.snapshot(), sort_keys=True)
            + (
                ". Remaining steps include this response. Token usage includes "
                "repeated input context; missing usage is unreported, not zero "
                "actual usage. If the next returned response crosses the cumula"
                "tive token cap, its tools including submit will not run. Submi"
                "t a real candidate or an honest review promptly; budget pressu"
                "re never justifies accepting missing or failed evidence. Share"
                "d USD, dispatch, payload and worker caps also apply and may st"
                "op earlier."
            ),
        )
        result = await self._backend.step(replace(request, messages=(*request.messages, note)))
        self.completed_steps += 1
        usage = result.response_metadata.usage
        tokens = usage.get("total_tokens") if usage else None
        if type(tokens) is int:
            self.counted_total_tokens += tokens
        else:
            self.unreported_usage_steps += 1
        return result

    async def aclose(self) -> None:
        await self._backend.aclose()


@dataclass(frozen=True)
class ModelPricing:
    """Public OpenRouter model metadata snapshot supplied by the composition root."""

    snapshot: Mapping[str, object]
    checked_at: str
    source_url: str = _SOURCE

    def __post_init__(self) -> None:
        date.fromisoformat(self.checked_at)
        if self.source_url != _SOURCE:
            raise ValueError("Pricing must identify the public OpenRouter model catalog")
        copied = json.loads(json.dumps(dict(self.snapshot), allow_nan=False))
        if not isinstance(copied.get("id"), str) or not copied["id"]:
            raise ValueError("Pricing snapshot needs its model id")
        _positive_int(copied.get("context_length"), "context_length")
        pricing = copied.get("pricing")
        if not isinstance(pricing, dict):
            raise ValueError("Pricing snapshot needs pricing")
        overrides = pricing.get("overrides", [])
        if not isinstance(overrides, list):
            raise ValueError("Invalid pricing overrides")
        for row in [pricing, *overrides]:
            if not isinstance(row, dict):
                raise ValueError("Invalid pricing tier")
            _money(row.get("prompt"), "prompt price")
            _money(row.get("completion"), "completion price")
            for field in ("input_cache_read", "input_cache_write"):
                if field in row:
                    _money(row[field], f"{field} price")
            if row is not pricing:
                _positive_int(row.get("min_prompt_tokens"), "tier threshold")
        object.__setattr__(self, "snapshot", copied)

    @property
    def model(self) -> str:
        return cast(str, self.snapshot["id"])

    @property
    def context_length(self) -> int:
        return cast(int, self.snapshot["context_length"])

    def estimate(self, input_tokens: int, completion_tokens: int) -> Decimal:
        pricing = cast(JsonObject, self.snapshot["pricing"])
        rows = [
            pricing,
            *(
                row
                for row in pricing.get("overrides", [])
                if input_tokens >= row["min_prompt_tokens"]
            ),
        ]
        prompt = max(
            _money(row[field], f"{field} price")
            for row in rows
            for field in ("prompt", "input_cache_write")
            if field in row
        )
        completion = max(_money(row["completion"], "completion price") for row in rows)
        return prompt * input_tokens + completion * completion_tokens

    def record(self) -> dict[str, object]:
        return {
            "source_url": self.source_url,
            "checked_at": self.checked_at,
            "model": self.snapshot,
        }


class AgentBudgetStopped(AbortError):
    """The service's retry owner must stop without another backend dispatch."""


class AgentPayloadStopped(AgentBudgetStopped):
    """A fixed diagnostic code, without serializing request or exception content."""

    def __init__(self, reason: str) -> None:
        allowed = {
            "payload_image_history_limit",
            "payload_completion_token_limit",
            "payload_image_count_limit",
            "payload_image_byte_limit",
            "payload_invalid_image",
            "payload_text_byte_limit",
        }
        if reason not in allowed:
            raise ValueError("Unknown payload refusal code")
        self.reason = reason
        super().__init__(reason)


def ledger_stats(state: JsonObject) -> JsonObject:
    """Project accounting and the latest safe refusal without changing admission.

    A producer holdback refusal is not a permanent halt: a reviewer may still
    spend its reserved funds. Expose that last event separately, and stop
    reporting it after a later dispatch/event supersedes it.
    """
    result = {
        "dispatch_count": state["dispatch_count"],
        "known_cost_usd": state["known_cost_usd"],
        "liability_usd": state["liability_usd"],
        "unknown_charge_count": sum(
            attempt.get("charge_status") != "reported" for attempt in state["attempts"]
        ),
        "halt_reason": state["halt_reason"],
    }
    events = state.get("events", [])
    last = events[-1] if events else {}
    if last.get("event") in {"dispatch_refused", "payload_refused"}:
        allowed = {
            "wall_time_limit",
            "dispatch_limit",
            "reservation_exceeds_remaining_budget",
            "episode_budget_role_required",
            "episode_budget_role_mismatch",
            "review_holdback_would_be_spent",
            "reported_cost_exceeded_reservation",
            "total_budget_exceeded",
            "payload_image_history_limit",
            "payload_completion_token_limit",
            "payload_image_count_limit",
            "payload_image_byte_limit",
            "payload_invalid_image",
            "payload_text_byte_limit",
            "payload_invalid_parameters",
        }
        reason = last.get("reason")
        result["last_refusal"] = {
            "event": last["event"],
            "reason": reason
            if isinstance(reason, str) and reason in allowed
            else "unclassified_refusal",
            "after_dispatch_count": state["dispatch_count"],
        }
    return result


def _safe_id(value: object) -> str | None:
    return value if isinstance(value, str) and _RECEIPT_ID.fullmatch(value) else None


def _usage(value: object) -> dict[str, object]:
    """Keep numeric accounting fields only; never arbitrary provider text."""
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, object] = {}
    for key in (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cost",
        "cost_details",
        "prompt_tokens_details",
        "completion_tokens_details",
    ):
        item = value.get(key)
        if isinstance(item, Mapping):
            result[key] = {
                str(k): v
                for k, v in item.items()
                if re.fullmatch("[a-z_]{1,64}", str(k))
                and type(v) in (int, float)
                and math.isfinite(v)
                and (v >= 0)
            }
        elif (
            type(item) in (int, float)
            and math.isfinite(cast(int | float, item))
            and (cast(int | float, item) >= 0)
        ):
            result[key] = item
    return result


class _ReceiptCollector:
    def __init__(self) -> None:
        self.current = contextvars.ContextVar[JsonObject | None]("agent_receipt", default=None)

    async def response(self, response: httpx.Response) -> None:
        receipt = self.current.get()
        if receipt is None:
            return
        receipt["http_status"] = response.status_code
        receipt["request_id"] = _safe_id(
            response.headers.get("x-request-id") or response.headers.get("x-openrouter-request-id")
        )
        await response.aread()
        try:
            payload = response.json()
        except (ValueError, UnicodeDecodeError):
            return
        if isinstance(payload, dict):
            receipt["generation_id"] = _safe_id(payload.get("id"))
            receipt["usage"] = _usage(payload.get("usage"))


class MeteredToolLoopBackend:
    spec_version: ClassVar[Literal[1]] = 1

    def __init__(
        self,
        backend: ToolLoopModelV1,
        *,
        ledger_dir: Path,
        limits: AgentBudget,
        pricing: ModelPricing,
        episode_id: str | None = None,
        _collector: _ReceiptCollector | None = None,
        _owned_client: httpx.AsyncClient | None = None,
    ) -> None:
        if backend.provider != "openrouter" or backend.model != pricing.model:
            raise ValueError("Backend and verified pricing identity must match")
        if limits.input_token_reserve + limits.max_completion_tokens > pricing.context_length:
            raise ValueError("Configured token reservation exceeds model context")
        self.provider, self.model, self.secrets = (backend.provider, backend.model, backend.secrets)
        self._backend, self._limits, self._pricing = (backend, limits, pricing)
        self._episode_id = episode_id or "episode-" + uuid.uuid4().hex
        self._episode_role: str | None = None
        if not re.fullmatch("[A-Za-z0-9_.:-]{1,192}", self._episode_id):
            raise ValueError("episode_id must be a safe non-path identifier")
        self._collector, self._owned_client = (_collector, _owned_client)
        unresolved = Path(ledger_dir).absolute()
        if any(p.is_symlink() for p in (unresolved, *unresolved.parents)):
            raise ValueError("Ledger directory must not have symlinked parents")
        unresolved.mkdir(parents=True, exist_ok=True)
        self._directory = unresolved.resolve(strict=True)
        with self._locked() as state:
            if state is None:
                state = {
                    "schema_version": 1,
                    "started_at_unix": time.time(),
                    "limits": limits.record(),
                    "pricing": pricing.record(),
                    "halt_reason": None,
                    "attempts": [],
                    "events": [],
                }
                self._save(state)
            elif state.get("limits") != limits.record() or state.get("pricing") != pricing.record():
                raise ValueError("Existing ledger limits/pricing cannot silently change")

    def bind_episode_role(self, role: str) -> None:
        """Host-only classification; a model argument cannot change its spending role."""
        if role not in {"producer", "reviewer"}:
            raise ValueError("Episode role must be producer or reviewer")
        if self._episode_role not in {None, role}:
            raise ValueError("An episode cannot change its budget role")
        if self._limits.review_holdback_usd is not None:
            with self._locked() as state:
                state = cast(JsonObject, state)
                for attempt in state["attempts"]:
                    request = attempt["request"]
                    if (
                        request["episode_id"] == self._episode_id
                        and request.get("episode_role") != role
                    ):
                        raise ValueError("Persisted episode budget role differs")
        self._episode_role = role

    def _headroom(self, state: JsonObject, amount: Decimal) -> JsonObject:
        budget = _money(self._limits.max_usd, "budget")
        liability = _money(state["liability_usd"], "liability")
        known = _money(state["known_cost_usd"], "known cost")
        holdback = (
            _money(self._limits.review_holdback_usd or "0", "review holdback")
            if self._episode_role != "reviewer"
            else Decimal(0)
        )
        remaining = max(Decimal(0), budget - liability)
        spendable = max(Decimal(0), remaining - holdback)
        dispatches = max(0, self._limits.max_steps - len(state["attempts"]))
        return {
            "scope": "shared_agent_allocation",
            "episode_role": self._episode_role or "unbound",
            "remaining_usd": str(remaining),
            "known_actual_usd": str(known),
            "unresolved_liability_usd": str(max(Decimal(0), liability - known)),
            "protected_next_review_usd": str(holdback),
            "spendable_usd": str(spendable),
            "next_request_reservation_usd": str(amount),
            "remaining_paid_dispatches": dispatches,
            "affordable_reservations": min(dispatches, int(spendable / amount))
            if amount > 0
            else dispatches,
        }

    @contextmanager
    def _locked(self) -> Iterator[JsonObject | None]:
        path = self._directory / "ledger.lock"
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            state_path = self._directory / "ledger.json"
            if state_path.is_symlink():
                raise ValueError("Ledger file must not be a symlink")
            state = json.loads(state_path.read_text()) if state_path.exists() else None
            yield state
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _save(self, state: JsonObject) -> None:
        state["dispatch_count"] = len(state["attempts"])
        state["known_cost_usd"] = str(
            sum((_money(a.get("known_cost_usd", 0), "cost") for a in state["attempts"]), Decimal(0))
        )
        state["liability_usd"] = str(
            sum((_money(a["liability_usd"], "liability") for a in state["attempts"]), Decimal(0))
        )
        encoded = (json.dumps(state, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
        if any(secret and secret.encode() in encoded for secret in self.secrets):
            raise ValueError("Refusing secret-bearing accounting metadata")
        descriptor, temporary = tempfile.mkstemp(prefix=".ledger-", dir=self._directory)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._directory / "ledger.json")
            directory = os.open(self._directory, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def _payload(self, request: ToolLoopStepRequest) -> tuple[ToolLoopStepRequest, JsonObject]:
        if self._limits.recent_image_limit is not None:
            try:
                request = project_image_history(request, self._limits.recent_image_limit)
            except ValueError:
                raise AgentPayloadStopped("payload_image_history_limit") from None
        tokens = (
            request.max_tokens
            if request.max_tokens is not None
            else self._limits.max_completion_tokens
        )
        _positive_int(tokens, "max_tokens")
        if tokens > self._limits.max_completion_tokens:
            raise AgentPayloadStopped("payload_completion_token_limit")
        dollar_note = None
        if self._limits.review_holdback_usd is not None:
            amount = self._pricing.estimate(self._limits.input_token_reserve, tokens)
            with self._locked() as state:
                state = cast(JsonObject, state)
                dollar_note = self._headroom(state, amount)
            note = ToolLoopMessage(
                "user",
                "Host USD headroom before this request: "
                + json.dumps(dollar_note, sort_keys=True)
                + (
                    ". Advisory snapshot; the ledger checks again atomically before"
                    " dispatch. The upcoming reservation is included in affordable_"
                    "reservations. If only one producer reservation fits, submit th"
                    "e best real candidate now with unresolved issues. Do not spend"
                    " protected review funds or lower review requirements. Reservat"
                    "ions are planning assumptions, not provider-enforced charge ca"
                    "ps."
                ),
            )
            request = replace(request, messages=(*request.messages, note))
        text_bytes = 0
        images: list[JsonObject] = []
        image_bytes = 0
        for message in request.messages:
            text_bytes += len(message.text.encode())
            for call in message.tool_calls:
                text_bytes += len(json.dumps(dict(call.arguments), allow_nan=False).encode())
            for image in message.images:
                if len(images) >= self._limits.max_images:
                    raise AgentPayloadStopped("payload_image_count_limit")
                if len(image) > (self._limits.max_image_bytes - image_bytes) * 4 // 3 + 64:
                    raise AgentPayloadStopped("payload_image_byte_limit")
                match = _IMAGE.fullmatch(image)
                if match is None:
                    raise AgentPayloadStopped("payload_invalid_image")
                try:
                    data = base64.b64decode(match[2], validate=True)
                except ValueError:
                    raise AgentPayloadStopped("payload_invalid_image") from None
                image_bytes += len(data)
                if image_bytes > self._limits.max_image_bytes:
                    raise AgentPayloadStopped("payload_image_byte_limit")
                images.append(
                    {
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "bytes": len(data),
                        "media_type": "image/" + match[1],
                    }
                )
        tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": dict(tool.parameters),
            }
            for tool in request.tools
        ]
        tool_bytes = json.dumps(tools, sort_keys=True, allow_nan=False).encode()
        text_bytes += len(tool_bytes)
        if text_bytes > self._limits.max_text_bytes:
            raise AgentPayloadStopped("payload_text_byte_limit")
        if len(images) > self._limits.max_images:
            raise AgentPayloadStopped("payload_image_count_limit")
        if sum(image["bytes"] for image in images) > self._limits.max_image_bytes:
            raise AgentPayloadStopped("payload_image_byte_limit")
        payload: JsonObject = {
            "episode_id": self._episode_id,
            "messages": [
                {
                    "role": m.role,
                    "text_sha256": hashlib.sha256(m.text.encode()).hexdigest(),
                    "image_count": len(m.images),
                    "tool_call_count": len(m.tool_calls),
                }
                for m in request.messages
            ],
            "text_bytes": text_bytes,
            "images": images,
            "tools_sha256": hashlib.sha256(tool_bytes).hexdigest(),
            "tool_names": [tool.name for tool in request.tools],
            "input_token_reserve": self._limits.input_token_reserve,
            "max_tokens": tokens,
            "reservation_policy": "configured_input_assumption_not_provider_cap",
        }
        if dollar_note is not None:
            payload.update(episode_role=self._episode_role, budget_advisory=dollar_note)
        return (replace(request, max_tokens=tokens), payload)

    def _reserve(self, payload: JsonObject) -> tuple[str, float]:
        amount = self._pricing.estimate(self._limits.input_token_reserve, payload["max_tokens"])
        with self._locked() as state:
            state = cast(JsonObject, state)
            now = time.time()
            remaining = self._limits.max_wall_seconds - (now - state["started_at_unix"])
            reason = state["halt_reason"]
            if not reason and remaining <= 0:
                reason = "wall_time_limit"
            if not reason and len(state["attempts"]) >= self._limits.max_steps:
                reason = "dispatch_limit"
            if not reason and _money(state["liability_usd"], "liability") + amount > _money(
                self._limits.max_usd, "budget"
            ):
                reason = "reservation_exceeds_remaining_budget"
            if not reason and self._limits.review_holdback_usd is not None:
                if self._episode_role not in {"producer", "reviewer"}:
                    reason = "episode_budget_role_required"
                elif any(
                    item["request"]["episode_id"] == self._episode_id
                    and item["request"].get("episode_role") != self._episode_role
                    for item in state["attempts"]
                ):
                    reason = "episode_budget_role_mismatch"
                elif amount > _money(self._headroom(state, amount)["spendable_usd"], "spendable"):
                    reason = "review_holdback_would_be_spent"
            if reason:
                state["events"].append(
                    {"event": "dispatch_refused", "at_unix": now, "reason": reason}
                )
                self._save(state)
                raise AgentBudgetStopped(f"Agent dispatch stopped: {reason}")
            attempt_id = uuid.uuid4().hex
            state["attempts"].append(
                {
                    "attempt_id": attempt_id,
                    "status": "reserved",
                    "reserved_at_unix": now,
                    "reservation_usd": str(amount),
                    "liability_usd": str(amount),
                    "request": payload,
                }
            )
            state["events"].append(
                {"event": "reserved_before_dispatch", "attempt_id": attempt_id, "at_unix": now}
            )
            self._save(state)
            return (attempt_id, remaining)

    def _settle(
        self,
        attempt_id: str,
        receipt: JsonObject,
        result: ProviderToolLoopStep | None,
        error: BaseException | None,
    ) -> str | None:
        with self._locked() as state:
            state = cast(JsonObject, state)
            entry = next(a for a in state["attempts"] if a["attempt_id"] == attempt_id)
            usage = _usage(receipt.get("usage"))
            entry.update(
                {
                    "status": "error" if error else "response",
                    "settled_at_unix": time.time(),
                    "receipt": {k: v for k, v in receipt.items() if k != "usage"},
                    "usage": usage,
                }
            )
            if error:
                entry["error_type"] = type(error).__name__
            if result:
                entry["response"] = {
                    "text_sha256": hashlib.sha256(result.text.encode()).hexdigest(),
                    "tool_calls": [
                        {
                            "call_id": _safe_id(call.call_id),
                            "name": _safe_id(call.name),
                            "arguments_sha256": hashlib.sha256(
                                json.dumps(
                                    dict(call.arguments), sort_keys=True, allow_nan=False
                                ).encode()
                            ).hexdigest(),
                        }
                        for call in result.tool_calls
                    ],
                }
            if "cost" in usage:
                entry["known_cost_usd"] = str(_money(usage["cost"], "reported cost"))
                entry["liability_usd"] = entry["known_cost_usd"]
                entry["charge_status"] = "reported"
            else:
                entry["charge_status"] = "unknown_reserved"
            violations = []
            prompt, completion = (usage.get("prompt_tokens"), usage.get("completion_tokens"))
            if type(prompt) is int and prompt > self._limits.input_token_reserve:
                violations.append("input_token_reserve_exceeded")
            if type(completion) is int and completion > entry["request"]["max_tokens"]:
                violations.append("completion_token_limit_exceeded")
            if "cost" not in usage and (type(prompt) is int or type(completion) is int):
                estimated = self._pricing.estimate(
                    max(self._limits.input_token_reserve, prompt if type(prompt) is int else 0),
                    max(
                        entry["request"]["max_tokens"], completion if type(completion) is int else 0
                    ),
                )
                entry["liability_usd"] = str(
                    max(estimated, _money(entry["liability_usd"], "liability"))
                )
            if "known_cost_usd" in entry and _money(entry["known_cost_usd"], "cost") > _money(
                entry["reservation_usd"], "reservation"
            ):
                violations.append("reported_cost_exceeded_reservation")
            total = sum(
                (_money(a["liability_usd"], "liability") for a in state["attempts"]), Decimal(0)
            )
            if total > _money(self._limits.max_usd, "budget"):
                violations.append("total_budget_exceeded")
            if time.time() - state["started_at_unix"] > self._limits.max_wall_seconds:
                violations.append("wall_time_limit")
            if violations:
                entry["violations"] = violations
                state["halt_reason"] = state["halt_reason"] or violations[0]
            state["events"].append(
                {
                    "event": "attempt_recorded",
                    "attempt_id": attempt_id,
                    "status": entry["status"],
                    "at_unix": time.time(),
                }
            )
            self._save(state)
            return cast(str | None, state["halt_reason"])

    async def step(self, request: ToolLoopStepRequest) -> ProviderToolLoopStep:
        reason: str | None
        try:
            request, payload = self._payload(request)
        except (AgentBudgetStopped, ValueError, TypeError) as error:
            reason = (
                error.reason
                if isinstance(error, AgentPayloadStopped)
                else "payload_invalid_parameters"
            )
            with self._locked() as state:
                state = cast(JsonObject, state)
                state["halt_reason"] = state["halt_reason"] or reason
                state["events"].append(
                    {"event": "payload_refused", "at_unix": time.time(), "reason": reason}
                )
                self._save(state)
            raise AgentBudgetStopped(f"Agent payload refused: {reason}") from None
        try:
            attempt_id, remaining = self._reserve(payload)
        except AgentBudgetStopped:
            raise
        except Exception:
            raise AgentBudgetStopped("Agent accounting unavailable before dispatch") from None
        receipt: JsonObject = {}
        token = self._collector.current.set(receipt) if self._collector else None
        try:
            async with asyncio.timeout(remaining):
                result = await self._backend.step(request)
        except BaseException as error:
            try:
                reason = self._settle(attempt_id, receipt, None, error)
            except Exception:
                if isinstance(error, asyncio.CancelledError):
                    raise error from None
                raise AgentBudgetStopped("Agent accounting unavailable after dispatch") from None
            if reason and (not isinstance(error, asyncio.CancelledError)):
                raise AgentBudgetStopped(f"Agent dispatch stopped: {reason}") from None
            raise
        else:
            metadata = result.response_metadata
            receipt.setdefault("request_id", _safe_id(metadata.request_id))
            receipt.setdefault("usage", _usage(metadata.usage))
            try:
                reason = self._settle(attempt_id, receipt, result, None)
            except Exception:
                raise AgentBudgetStopped("Agent accounting unavailable after dispatch") from None
            if reason:
                raise AgentBudgetStopped(f"Agent dispatch stopped: {reason}")
            return result
        finally:
            if self._collector and token is not None:
                self._collector.current.reset(token)

    def snapshot(self) -> JsonObject:
        """Read persistent accounting, including unresolved crash reservations."""
        with self._locked() as state:
            state = cast(JsonObject, state)
            return state

    def stats(self) -> JsonObject:
        """Compact accounting for orchestration reports; never prompt or image data."""
        return ledger_stats(self.snapshot())

    async def aclose(self) -> None:
        try:
            await self._backend.aclose()
        finally:
            if self._owned_client:
                await self._owned_client.aclose()


def create_metered_backend(
    *,
    backend_factory: ToolLoopBackendFactory,
    api_key: str,
    model: str,
    ledger_dir: Path,
    limits: AgentBudget,
    pricing: ModelPricing,
    episode_id: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> MeteredToolLoopBackend:
    """Meter one injected public backend without selecting its provider."""
    collector = _ReceiptCollector()
    client = httpx.AsyncClient(
        timeout=None, transport=transport, event_hooks={"response": [collector.response]}
    )
    backend = backend_factory(api_key=api_key, model=model, client=client)
    return MeteredToolLoopBackend(
        backend,
        ledger_dir=ledger_dir,
        limits=limits,
        pricing=pricing,
        episode_id=episode_id,
        _collector=collector,
        _owned_client=client,
    )
