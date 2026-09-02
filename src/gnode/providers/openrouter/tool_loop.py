from __future__ import annotations

import json
from typing import ClassVar, Literal

import httpx

from gnode.modalities.tool_loop import (
    ProviderToolLoopStep,
    ToolCall,
    ToolLoopMessage,
    ToolLoopStepRequest,
)
from gnode.providers._http import (
    assert_success,
    json_object,
    normalized_base_url,
    response_metadata,
)

OPENROUTER_TOOL_LOOP_BASE_URL = "https://openrouter.ai/api/v1"
_LABEL = "OpenRouter tool loop"


class OpenRouterToolLoopBackend:
    """One chat turn with function tools over OpenRouter's chat completions."""

    spec_version: ClassVar[Literal[1]] = 1
    provider = "openrouter"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = OPENROUTER_TOOL_LOOP_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenRouter api_key must be non-empty")
        if not model.strip():
            raise ValueError("OpenRouter tool-loop model must be non-empty")
        self._api_key = api_key
        self.secrets: tuple[str, ...] = (api_key,)
        self.model = model.strip()
        self._base_url = normalized_base_url(base_url, "OpenRouter base_url")
        self._client = client or httpx.AsyncClient(timeout=None)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def step(self, request: ToolLoopStepRequest) -> ProviderToolLoopStep:
        body: dict[str, object] = {
            "model": self.model,
            "messages": [_wire_message(message) for message in request.messages],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": spec.parameters,
                        "strict": True,
                    },
                }
                for spec in request.tools
            ],
            "tool_choice": "required",
            "provider": {"require_parameters": True},
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        response = await self._client.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        assert_success(
            response,
            _LABEL,
            include_safe_error_detail=True,
            redactions=(
                self._api_key,
                *(message.text for message in request.messages),
                *(image for message in request.messages for image in message.images),
            ),
        )
        payload = json_object(response, _LABEL)
        choices = payload.get("choices")
        first = choices[0] if isinstance(choices, list) and choices else None
        message = first.get("message") if isinstance(first, dict) else None
        if not isinstance(message, dict):
            raise ValueError(f"{_LABEL} returned no message")
        return ProviderToolLoopStep(
            text=_extract_text(message.get("content")),
            tool_calls=_tool_calls(message.get("tool_calls")),
            response_metadata=response_metadata(response, payload),
        )


def _wire_message(message: ToolLoopMessage) -> dict[str, object]:
    if message.role == "system":
        return {"role": "system", "content": message.text}
    if message.role == "user":
        if not message.images:
            return {"role": "user", "content": message.text}
        return {
            "role": "user",
            "content": [
                {"type": "text", "text": message.text},
                *[{"type": "image_url", "image_url": {"url": image}} for image in message.images],
            ],
        }
    if message.role == "assistant":
        wire: dict[str, object] = {"role": "assistant", "content": message.text or None}
        if message.tool_calls:
            wire["tool_calls"] = [
                {
                    "id": call.call_id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(
                            dict(call.arguments), separators=(",", ":"), ensure_ascii=False
                        ),
                    },
                }
                for call in message.tool_calls
            ]
        return wire
    return {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.text}


def _tool_calls(value: object) -> tuple[ToolCall, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{_LABEL} returned malformed tool calls")
    calls: list[ToolCall] = []
    for entry in value:
        function = entry.get("function") if isinstance(entry, dict) else None
        call_id = entry.get("id") if isinstance(entry, dict) else None
        name = function.get("name") if isinstance(function, dict) else None
        raw_arguments = function.get("arguments") if isinstance(function, dict) else None
        if not isinstance(call_id, str) or not call_id or not isinstance(name, str) or not name:
            raise ValueError(f"{_LABEL} returned a tool call without an id or name")
        if isinstance(raw_arguments, dict):
            arguments: object = raw_arguments
        else:
            if not isinstance(raw_arguments, str):
                raise ValueError(f"{_LABEL} returned a tool call without arguments")
            try:
                arguments = json.loads(raw_arguments or "{}", parse_constant=_reject_json_constant)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"{_LABEL} returned invalid JSON tool arguments") from exc
        if not isinstance(arguments, dict):
            raise ValueError(f"{_LABEL} returned non-object tool arguments")
        calls.append(ToolCall(call_id=call_id, name=name, arguments=arguments))
    return tuple(calls)


def _extract_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "".join(
        part["text"]
        for part in content
        if isinstance(part, dict)
        and part.get("type") == "text"
        and isinstance(part.get("text"), str)
    )


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-standard JSON constant: {value}")
