from __future__ import annotations

import json
from typing import ClassVar, Literal

import httpx

from gnode import ProviderStructuredOutput, StructuredGenerationRequest
from stage_gen.providers._http import (
    assert_success,
    json_object,
    normalized_base_url,
    response_metadata,
)

OPENROUTER_STRUCTURED_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterStructuredBackend:
    spec_version: ClassVar[Literal[1]] = 1
    provider = "openrouter"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = OPENROUTER_STRUCTURED_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenRouter api_key must be non-empty")
        if not model.strip():
            raise ValueError("OpenRouter structured model must be non-empty")
        self._api_key = api_key
        self.secrets: tuple[str, ...] = (api_key,)
        self.model = model.strip()
        self._base_url = normalized_base_url(base_url, "OpenRouter base_url")
        self._client = client or httpx.AsyncClient(timeout=None)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def generate_once(
        self, request: StructuredGenerationRequest[object]
    ) -> ProviderStructuredOutput:
        references = request.references
        user_content: object = request.prompt
        if references:
            user_content = [
                {"type": "text", "text": request.prompt},
                *[
                    {"type": "image_url", "image_url": {"url": reference.url}}
                    for reference in references
                ],
            ]
        messages: list[dict[str, object]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": user_content})
        schema = request.schema
        json_schema: dict[str, object] = {
            "name": schema.name,
            "strict": schema.strict,
            "schema": schema.json_schema,
        }
        if schema.description:
            json_schema["description"] = schema.description
        body: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_schema", "json_schema": json_schema},
            "provider": {"require_parameters": True},
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        if request.seed is not None:
            body["seed"] = request.seed
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
            "OpenRouter structured generation",
            include_safe_error_detail=True,
            redactions=(
                self._api_key,
                request.prompt,
                request.system or "",
                *(reference.url for reference in request.references),
            ),
        )
        payload = json_object(response, "OpenRouter structured generation")
        choices = payload.get("choices")
        first = choices[0] if isinstance(choices, list) and choices else None
        message = first.get("message") if isinstance(first, dict) else None
        if not isinstance(message, dict):
            raise ValueError("OpenRouter structured generation returned no message")
        parsed = message.get("parsed")
        if isinstance(parsed, dict):
            decoded: object = parsed
            try:
                raw_text = json.dumps(
                    parsed,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "OpenRouter structured generation returned non-standard JSON"
                ) from exc
        else:
            raw_text = _extract_text(message.get("content"))
            if not raw_text.strip():
                raise ValueError("OpenRouter structured generation returned empty content")
            try:
                decoded = json.loads(raw_text, parse_constant=_reject_json_constant)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(
                    "OpenRouter structured generation returned invalid JSON content"
                ) from exc
        return ProviderStructuredOutput(
            decoded=decoded,
            raw_text=raw_text,
            response_metadata=response_metadata(response, payload),
        )


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
