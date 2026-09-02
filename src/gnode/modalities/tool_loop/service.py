from __future__ import annotations

import inspect
import json
from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
from typing import Literal, Self

from gnode.contracts import BinaryArtifact, ProvenanceInput, SoftwareIdentity
from gnode.reliability import (
    RetryContext,
    RetryPolicy,
    hash_input_reference,
    redact_secrets,
    retry_with_backoff,
    sanitize_reference,
    write_artifact_with_provenance_async,
)

from .models import (
    SUBMIT_TOOL_NAME,
    ProviderToolLoopStep,
    ToolCall,
    ToolHandler,
    ToolInvocationError,
    ToolLoopExhausted,
    ToolLoopMessage,
    ToolLoopModelV1,
    ToolLoopRequest,
    ToolLoopResult,
    ToolLoopStepRequest,
    ToolLoopTraceEntry,
    ToolResult,
    ToolSpec,
)

type TraceOutcome = Literal["ok", "error", "accepted", "rejected"]

_DETAIL_LIMIT = 400
_RENDERED_RESULTS = "The rendered result(s) of your tool call(s):"
_NO_TOOL_CALL_NUDGE = (
    f"Every turn must call a tool. Use the tools to inspect, then finish with `{SUBMIT_TOOL_NAME}`."
)


class ToolLoopService[T]:
    """The single owner of one episode: steps, per-step retries, admission, persistence.

    Ring-1 services are one attempt by contract. This is the documented
    exception: an episode is one provider *operation* made of bounded steps.
    Each step's transport is retried by the ordinary retry owner; the loop
    itself is work, not retry, and stops on the first admitted ``submit`` or
    when the step or token budget is spent.
    """

    def __init__(
        self,
        backend: ToolLoopModelV1,
        *,
        component: SoftwareIdentity,
        tool: SoftwareIdentity,
        retry_policy: RetryPolicy | None = None,
        now: datetime | None = None,
    ) -> None:
        self._backend = backend
        self._component = component
        self._tool = tool
        self._retry_policy = retry_policy
        self._now = now

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        del exc_type, exc, traceback
        await self.aclose()

    async def aclose(self) -> None:
        await self._backend.aclose()

    async def run(self, request: ToolLoopRequest[T]) -> ToolLoopResult[T]:
        tools = {tool.name: tool for tool in request.tools}
        specs = request.tool_specs
        messages: list[ToolLoopMessage] = []
        if request.system:
            messages.append(ToolLoopMessage("system", request.system))
        messages.append(
            ToolLoopMessage(
                "user",
                request.instructions,
                images=tuple(reference.url for reference in request.references),
            )
        )
        trace: list[ToolLoopTraceEntry] = []
        request_ids: list[str] = []
        total_tokens: int | None = None
        submitted: tuple[T, bytes, dict[str, object]] | None = None
        steps = 0

        for step in range(1, request.max_steps + 1):
            steps = step
            turn = await self._turn(request, messages, specs)
            if turn.response_metadata.request_id:
                request_ids.append(turn.response_metadata.request_id)
            total_tokens = _accumulate_tokens(total_tokens, turn.response_metadata.usage)
            budget = request.max_total_tokens
            if budget is not None and (total_tokens or 0) > budget:
                raise ToolLoopExhausted(
                    f"tool loop spent {total_tokens} tokens against a budget of "
                    f"{request.max_total_tokens} after {step} steps"
                )
            messages.append(ToolLoopMessage("assistant", turn.text, tool_calls=turn.tool_calls))
            if not turn.tool_calls:
                messages.append(ToolLoopMessage("user", _NO_TOOL_CALL_NUDGE))
                continue

            images: list[str] = []
            for call in turn.tool_calls:
                if call.name == SUBMIT_TOOL_NAME:
                    if submitted is not None:
                        # One accepted submit ends the episode; a second one is ignored.
                        reply = "ignored: already submitted"
                        entry: TraceOutcome = "rejected"
                    else:
                        try:
                            submitted = self._admit(request, call.arguments)
                        except Exception as exc:
                            reply = f"{SUBMIT_TOOL_NAME} rejected: {self._safe(exc)}"
                            entry = "rejected"
                        else:
                            reply = f"{SUBMIT_TOOL_NAME} accepted"
                            entry = "accepted"
                    messages.append(ToolLoopMessage("tool", reply, tool_call_id=call.call_id))
                    trace.append(self._entry(step, call, entry, reply))
                    continue
                tool = tools.get(call.name)
                if tool is None:
                    reply = f"unknown tool {call.name}; available: {', '.join(sorted(tools))}"
                    messages.append(ToolLoopMessage("tool", reply, tool_call_id=call.call_id))
                    trace.append(self._entry(step, call, "error", reply))
                    continue
                try:
                    result = await _invoke(tool.handler, call.arguments)
                except ToolInvocationError as exc:
                    reply = f"{call.name} refused: {self._safe(exc)}"
                    messages.append(ToolLoopMessage("tool", reply, tool_call_id=call.call_id))
                    trace.append(self._entry(step, call, "error", reply))
                    continue
                messages.append(ToolLoopMessage("tool", result.text, tool_call_id=call.call_id))
                images.extend(result.images)
                trace.append(self._entry(step, call, "ok", result.text))
            if submitted is not None:
                break
            if images:
                messages.append(ToolLoopMessage("user", _RENDERED_RESULTS, images=tuple(images)))
        if submitted is None:
            raise ToolLoopExhausted(
                f"tool loop made no admitted {SUBMIT_TOOL_NAME} within {request.max_steps} steps"
            )

        value, artifact_data, caller_validation = submitted
        params: dict[str, object] = {
            "instructions_sha256": sha256(request.instructions.encode()).hexdigest(),
            "tools": [
                {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": dict(spec.parameters),
                }
                for spec in specs
            ],
            "submit_schema": dict(request.submit_schema),
            "strict": True,
            "require_parameters": True,
            "max_steps": request.max_steps,
        }
        if request.system:
            params["system"] = request.system
            params["system_sha256"] = sha256(request.system.encode()).hexdigest()
        if request.max_total_tokens is not None:
            params["max_total_tokens"] = request.max_total_tokens
        if request.temperature is not None:
            params["temperature"] = request.temperature
        if request.max_tokens is not None:
            params["max_tokens"] = request.max_tokens
        if request.metadata:
            params["metadata"] = dict(request.metadata)
        if request.artifact_value is not None:
            params["artifact_value"] = "caller-canonicalized"
        if request.validate is not None:
            params["validated"] = True
        response: dict[str, object] = {
            "steps": steps,
            "trace": [entry.as_dict() for entry in trace],
        }
        if request_ids:
            response["request_ids"] = request_ids
        if total_tokens is not None:
            response["total_tokens"] = total_tokens
        provenance_path = await write_artifact_with_provenance_async(
            request.artifact_path,
            BinaryArtifact(data=artifact_data, media_type="application/json"),
            ProvenanceInput(
                schema_version=request.provenance_schema_version,
                provider=self._backend.provider,
                model=self._backend.model,
                seed=None,
                prompt=request.instructions,
                refs=[
                    reference.provenance_ref or sanitize_reference(reference.url)
                    for reference in request.references
                ],
                inputs=[
                    hash_input_reference(reference.url, reference.provenance_ref)
                    for reference in request.references
                ],
                params=params,
                validation={
                    "submitted": True,
                    "json": "parsed",
                    "schema": "caller-validated",
                    **caller_validation,
                },
                component=self._component,
                tool=self._tool,
                attempts=1,
                response=response,
            ),
            secrets=self._backend.secrets,
            now=self._now,
        )
        return ToolLoopResult(
            value=value,
            steps=steps,
            provider=self._backend.provider,
            model=self._backend.model,
            provenance_path=str(provenance_path),
            trace=tuple(trace),
            total_tokens=total_tokens,
        )

    async def _turn(
        self,
        request: ToolLoopRequest[T],
        messages: list[ToolLoopMessage],
        specs: tuple[ToolSpec, ...],
    ) -> ProviderToolLoopStep:
        step_request = ToolLoopStepRequest(
            messages=tuple(messages),
            tools=specs,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        async def attempt(context: RetryContext) -> ProviderToolLoopStep:
            del context
            return await self._backend.step(step_request)

        return await retry_with_backoff(
            attempt,
            policy=self._retry_policy,
            label=f"{self._backend.provider} tool loop step",
            secrets=self._backend.secrets,
            timeout_s=request.timeout_seconds,
            cancellation=request.cancellation,
        )

    def _admit(
        self, request: ToolLoopRequest[T], arguments: Mapping[str, object]
    ) -> tuple[T, bytes, dict[str, object]]:
        value = request.parse(arguments)
        artifact_value = (
            request.artifact_value(value) if request.artifact_value is not None else arguments
        )
        validation = request.validate(value) if request.validate is not None else None
        if validation is not None and not isinstance(validation, Mapping):
            raise ValueError("tool-loop validator must return a mapping or None")
        return value, _serialize_json_artifact(artifact_value), dict(validation or {})

    def _safe(self, exc: Exception) -> str:
        return _bounded(redact_secrets(str(exc) or type(exc).__name__, self._backend.secrets))

    def _entry(
        self, step: int, call: ToolCall, outcome: TraceOutcome, detail: str
    ) -> ToolLoopTraceEntry:
        return ToolLoopTraceEntry(
            step=step,
            call_id=call.call_id,
            tool=call.name,
            arguments=call.arguments,
            outcome=outcome,
            detail=_bounded(redact_secrets(detail, self._backend.secrets)),
        )


async def _invoke(handler: ToolHandler, arguments: Mapping[str, object]) -> ToolResult:
    result = handler(arguments)
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, ToolResult):
        raise TypeError("tool handlers must return a ToolResult")
    return result


def _accumulate_tokens(total: int | None, usage: Mapping[str, object] | None) -> int | None:
    if not usage:
        return total
    value = usage.get("total_tokens")
    if isinstance(value, bool) or not isinstance(value, int):
        return total
    return (total or 0) + value


def _bounded(value: str, limit: int = _DETAIL_LIMIT) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1]}…"


def _serialize_json_artifact(value: object) -> bytes:
    try:
        return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
    except (TypeError, ValueError) as exc:
        raise ValueError("submitted value was not standards-compliant JSON") from exc
