from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import ClassVar, Literal

import httpx

from gnode.modalities.structured import (
    ProviderStructuredOutput,
    StructuredGenerationRequest,
)
from gnode.providers._http import (
    assert_success,
    json_object,
    normalized_base_url,
    response_metadata,
)

OPENROUTER_STRUCTURED_BASE_URL = "https://openrouter.ai/api/v1"
_PROVIDER_SLUG = re.compile(r"[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*")
_REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
_IMAGE_DETAILS = ("auto", "low", "high", "original")


@dataclass(frozen=True, slots=True)
class OpenRouterProviderRouting:
    """Explicit provider preferences; omitted restrictions preserve gateway defaults."""

    only: tuple[str, ...] | None = None
    allow_fallbacks: bool | None = None
    require_parameters: Literal[True] = True

    def __post_init__(self) -> None:
        if self.require_parameters is not True:
            raise ValueError("Structured generation requires OpenRouter require_parameters=True")
        if self.allow_fallbacks is not None and not isinstance(self.allow_fallbacks, bool):
            raise ValueError("OpenRouter allow_fallbacks must be a boolean or None")
        if self.only is not None:
            if not isinstance(self.only, tuple) or not self.only:
                raise ValueError("OpenRouter only must be a non-empty tuple of provider slugs")
            if any(
                not isinstance(slug, str) or _PROVIDER_SLUG.fullmatch(slug) is None
                for slug in self.only
            ):
                raise ValueError("OpenRouter only contains an invalid provider slug")
            if len(set(self.only)) != len(self.only):
                raise ValueError("OpenRouter only must not repeat provider slugs")

    def snapshot(self) -> dict[str, object]:
        """Return a detached JSON-safe routing object without credentials or content."""

        result: dict[str, object] = {"require_parameters": self.require_parameters}
        if self.only is not None:
            result["only"] = list(self.only)
        if self.allow_fallbacks is not None:
            result["allow_fallbacks"] = self.allow_fallbacks
        return result


@dataclass(frozen=True, slots=True)
class OpenRouterStructuredRequestPolicy:
    """Immutable generic request settings, separate from a selected model's capabilities.

    Planning must still check that the selected model/provider supports each
    requested setting. In particular, the gateway can downgrade original image
    detail to high; this policy does not promise original-resolution processing.
    """

    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"] | None = (
        None
    )
    image_detail: Literal["auto", "low", "high", "original"] | None = None
    provider: OpenRouterProviderRouting = field(default_factory=OpenRouterProviderRouting)

    def __post_init__(self) -> None:
        if self.reasoning_effort is not None and self.reasoning_effort not in _REASONING_EFFORTS:
            raise ValueError("Unsupported OpenRouter reasoning effort")
        if self.image_detail is not None and self.image_detail not in _IMAGE_DETAILS:
            raise ValueError("Unsupported OpenRouter image detail")
        if not isinstance(self.provider, OpenRouterProviderRouting):
            raise ValueError("OpenRouter provider policy must be typed routing preferences")

    def snapshot(self) -> dict[str, object]:
        """Return settings suitable for provenance; image detail applies per reference."""

        result: dict[str, object] = {"provider": self.provider.snapshot()}
        if self.reasoning_effort is not None:
            result["reasoning"] = {"effort": self.reasoning_effort}
        if self.image_detail is not None:
            result["image_detail"] = self.image_detail
        return result


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
        request_policy: OpenRouterStructuredRequestPolicy | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenRouter api_key must be non-empty")
        if not model.strip():
            raise ValueError("OpenRouter structured model must be non-empty")
        if request_policy is not None and not isinstance(
            request_policy, OpenRouterStructuredRequestPolicy
        ):
            raise ValueError("OpenRouter request_policy must be typed structured preferences")
        self._api_key = api_key
        self.secrets: tuple[str, ...] = (api_key,)
        self.model = model.strip()
        self._base_url = normalized_base_url(base_url, "OpenRouter base_url")
        self._client = client or httpx.AsyncClient(timeout=None)
        self._owns_client = client is None
        self._request_policy = request_policy or OpenRouterStructuredRequestPolicy()

    @property
    def request_policy(self) -> OpenRouterStructuredRequestPolicy:
        return self._request_policy

    def policy_snapshot(self) -> dict[str, object]:
        """Expose detached request settings for the composition root's provenance."""

        return self._request_policy.snapshot()

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
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": reference.url,
                            **(
                                {"detail": self._request_policy.image_detail}
                                if self._request_policy.image_detail is not None
                                else {}
                            ),
                        },
                    }
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
            "provider": self._request_policy.provider.snapshot(),
        }
        if self._request_policy.reasoning_effort is not None:
            body["reasoning"] = {"effort": self._request_policy.reasoning_effort}
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
