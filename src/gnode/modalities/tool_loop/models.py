"""Ring 1 — the bounded tool-loop agent.

A tool loop is one *episode*: a chat model with image input is handed
caller-supplied pure tools, a system prompt, instructions, and a budget, and
must end by calling the reserved ``submit`` tool with a payload the caller
parses and admits. The model decides; the caller's tools render and the
caller's admission judges. Nothing here names a provider, touches a network,
or reads a path — the sandbox is exactly the tool list.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Literal, Protocol

from gnode.modalities._types import (
    REFERENCE_URL_RE,
    ProviderResponseMetadata,
    canonicalize_strict_json_schema,
    validate_optional_number,
    validate_optional_timeout,
)
from gnode.reliability import CancellationToken

SUBMIT_TOOL_NAME = "submit"
MAX_TOOL_LOOP_STEPS = 32
_TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class ToolInvocationError(ValueError):
    """A tool refused its arguments; the message is fed back to the model."""


class ToolLoopExhausted(ValueError):
    """The episode spent its budget without an admitted ``submit``.

    One episode is one provider operation whether or not it submits, so a host's
    spend ledger reads ``attempts`` off this error the way it does off a result.
    """

    attempts = 1


@dataclass(frozen=True, slots=True)
class ToolLoopReference:
    url: str
    provenance_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValueError("tool-loop reference url must be non-empty")
        if not REFERENCE_URL_RE.match(self.url):
            raise ValueError("tool-loop references must be HTTP(S) URLs or base64 image data URLs")


@dataclass(frozen=True, slots=True)
class ToolResult:
    """What a tool hands back to the model: text, and optionally images to look at."""

    text: str
    images: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("tool result text must be non-empty")
        for image in self.images:
            if not REFERENCE_URL_RE.match(image):
                raise ValueError("tool result images must be HTTP(S) URLs or image data URLs")


type ToolHandler = Callable[[Mapping[str, object]], Awaitable[ToolResult] | ToolResult]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """The model-facing declaration of one tool."""

    name: str
    description: str
    parameters: Mapping[str, object]

    def __post_init__(self) -> None:
        if not _TOOL_NAME_RE.match(self.name):
            raise ValueError("tool name must be lower_snake_case, at most 64 characters")
        if not self.description.strip():
            raise ValueError(f"tool {self.name} must carry a description")
        if not isinstance(self.parameters, Mapping):
            raise ValueError(f"tool {self.name} parameters must be a JSON Schema object")
        object.__setattr__(self, "parameters", canonicalize_strict_json_schema(self.parameters))


@dataclass(frozen=True, slots=True)
class Tool(ToolSpec):
    """A declared tool bound to the caller's handler."""

    handler: ToolHandler = field(kw_only=True)

    def __post_init__(self) -> None:
        ToolSpec.__post_init__(self)
        if self.name == SUBMIT_TOOL_NAME:
            raise ValueError(f"{SUBMIT_TOOL_NAME} is reserved for the episode's final answer")
        if not callable(self.handler):
            raise ValueError(f"tool {self.name} handler must be callable")


@dataclass(frozen=True, slots=True)
class ToolCall:
    call_id: str
    name: str
    arguments: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ToolLoopMessage:
    """One provider-neutral transcript entry; adapters map it to their wire shape."""

    role: Literal["system", "user", "assistant", "tool"]
    text: str
    images: tuple[str, ...] = ()
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None

    def __post_init__(self) -> None:
        if self.images and self.role != "user":
            raise ValueError("only user messages carry images")
        if self.tool_calls and self.role != "assistant":
            raise ValueError("only assistant messages carry tool calls")
        if (self.tool_call_id is None) == (self.role == "tool"):
            raise ValueError("exactly the tool messages carry a tool_call_id")


@dataclass(frozen=True, slots=True)
class ToolLoopStepRequest:
    """One model turn: the transcript so far and the tools it may call."""

    messages: tuple[ToolLoopMessage, ...]
    tools: tuple[ToolSpec, ...]
    temperature: float | None = None
    max_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ProviderToolLoopStep:
    text: str
    tool_calls: tuple[ToolCall, ...]
    response_metadata: ProviderResponseMetadata


class ToolLoopModelV1(Protocol):
    """The v1 tool-loop model spec: one turn per call, injected credentials."""

    spec_version: ClassVar[Literal[1]]
    provider: str
    model: str
    secrets: tuple[str, ...]

    async def step(self, request: ToolLoopStepRequest) -> ProviderToolLoopStep: ...

    async def aclose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ToolLoopRequest[T]:
    instructions: str
    artifact_path: str | Path
    tools: tuple[Tool, ...]
    submit_schema: Mapping[str, object]
    parse: Callable[[object], T]
    submit_description: str = "Submit the final answer. This ends the episode."
    system: str | None = None
    references: tuple[ToolLoopReference, ...] = ()
    max_steps: int = 8
    max_total_tokens: int | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    timeout_seconds: float | None = None
    cancellation: CancellationToken | None = None
    artifact_value: Callable[[T], object] | None = None
    validate: Callable[[T], Mapping[str, object] | None] | None = None
    provenance_schema_version: Literal[2] = 2

    def __post_init__(self) -> None:
        if not self.instructions.strip():
            raise ValueError("tool-loop instructions must be non-empty")
        if not str(self.artifact_path).strip():
            raise ValueError("artifact_path must be non-empty")
        if not self.tools:
            raise ValueError("a tool loop needs at least one tool besides submit")
        names = [tool.name for tool in self.tools]
        if len(set(names)) != len(names):
            raise ValueError("tool names must be unique")
        if not isinstance(self.submit_schema, Mapping):
            raise ValueError("submit_schema must be a JSON Schema object")
        object.__setattr__(
            self, "submit_schema", canonicalize_strict_json_schema(self.submit_schema)
        )
        if not self.submit_description.strip():
            raise ValueError("submit_description must be non-empty")
        if not callable(self.parse):
            raise ValueError("parse must be callable")
        if self.artifact_value is not None and not callable(self.artifact_value):
            raise ValueError("artifact_value must be callable")
        if self.validate is not None and not callable(self.validate):
            raise ValueError("validate must be callable")
        if (
            isinstance(self.max_steps, bool)
            or not isinstance(self.max_steps, int)
            or not 1 <= self.max_steps <= MAX_TOOL_LOOP_STEPS
        ):
            raise ValueError(f"max_steps must be an integer from 1 to {MAX_TOOL_LOOP_STEPS}")
        if self.max_total_tokens is not None and (
            isinstance(self.max_total_tokens, bool)
            or not isinstance(self.max_total_tokens, int)
            or self.max_total_tokens < 1
        ):
            raise ValueError("max_total_tokens must be a positive integer")
        validate_optional_number(
            self.temperature,
            "temperature",
            minimum=0,
            maximum=2,
            message="temperature must be between 0 and 2",
        )
        if self.max_tokens is not None and (
            isinstance(self.max_tokens, bool)
            or not isinstance(self.max_tokens, int)
            or self.max_tokens < 1
        ):
            raise ValueError("max_tokens must be a positive integer")
        validate_optional_timeout(self.timeout_seconds)
        if self.provenance_schema_version != 2:
            raise ValueError("provenance_schema_version must be 2")

    @property
    def submit_tool(self) -> ToolSpec:
        return ToolSpec(SUBMIT_TOOL_NAME, self.submit_description, self.submit_schema)

    @property
    def tool_specs(self) -> tuple[ToolSpec, ...]:
        return (
            *(ToolSpec(tool.name, tool.description, tool.parameters) for tool in self.tools),
            self.submit_tool,
        )


@dataclass(frozen=True, slots=True)
class ToolLoopTraceEntry:
    """One tool call the episode made, with its outcome; images are not kept."""

    step: int
    call_id: str
    tool: str
    arguments: Mapping[str, object]
    outcome: Literal["ok", "error", "accepted", "rejected"]
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {
            "step": self.step,
            "call_id": self.call_id,
            "tool": self.tool,
            "arguments": dict(self.arguments),
            "outcome": self.outcome,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class ToolLoopResult[T]:
    value: T
    steps: int
    provider: str
    model: str
    provenance_path: str
    trace: tuple[ToolLoopTraceEntry, ...]
    total_tokens: int | None
    # One episode is one provider operation; the loop is work, not retry.
    attempts: int = 1
