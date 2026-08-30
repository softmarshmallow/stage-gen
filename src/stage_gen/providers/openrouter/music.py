from __future__ import annotations

import json
import re
from typing import Any, ClassVar, Literal

import httpx

from gnode import (
    JsonObject,
    MusicGenerationRequest,
    ProviderMusic,
    assert_audio_signature,
    decode_base64_strict,
    normalize_audio_media_type,
)
from stage_gen.providers._http import (
    assert_success,
    normalized_base_url,
    response_metadata,
)

OPENROUTER_MUSIC_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MUSIC_MODEL = "google/lyria-3-pro-preview"
_DATA_URI = re.compile(r"^data:([^;,]+);base64,(.+)$", re.IGNORECASE | re.DOTALL)


class OpenRouterMusicBackend:
    spec_version: ClassVar[Literal[1]] = 1
    provider = "openrouter"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = OPENROUTER_MUSIC_MODEL,
        base_url: str = OPENROUTER_MUSIC_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenRouter api_key must be non-empty")
        if not model.strip():
            raise ValueError("OpenRouter music model must be non-empty")
        self._api_key = api_key
        self.secrets: tuple[str, ...] = (api_key,)
        self.model = model.strip()
        self._base_url = normalized_base_url(base_url, "OpenRouter base_url")
        self._client = client or httpx.AsyncClient(timeout=None)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def generate_once(self, request: MusicGenerationRequest) -> ProviderMusic:
        content: object = request.prompt
        if request.references:
            content = [
                {"type": "text", "text": request.prompt},
                *[
                    {"type": "image_url", "image_url": {"url": reference.url}}
                    for reference in request.references
                ],
            ]
        body: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "modalities": ["text", "audio"],
            "audio": {"format": request.output_format},
            "stream": True,
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.top_p is not None:
            body["top_p"] = request.top_p
        if request.seed is not None:
            body["seed"] = request.seed
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
        assert_success(response, "OpenRouter music generation")
        text = response.text
        if not text.strip():
            raise ValueError("OpenRouter music generation returned an empty response")
        content_type = response.headers.get("content-type", "").lower()
        if "text/event-stream" in content_type or re.search(r"^\s*data:", text, re.MULTILINE):
            return _parse_sse(response, text, request.output_format)
        try:
            payload: Any = response.json()
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("OpenRouter music generation returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("OpenRouter music generation returned a non-object JSON response")
        return _parse_buffered(response, payload, request.output_format)


def _parse_sse(response: httpx.Response, text: str, requested_format: str) -> ProviderMusic:
    audio_chunks: list[str] = []
    media_types: list[str] = []
    text_chunks: list[str] = []
    usage: JsonObject | None = None
    event_count = 0
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            event: Any = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValueError("OpenRouter music stream contained invalid JSON") from exc
        if not isinstance(event, dict):
            raise ValueError("OpenRouter music stream contained a non-object event")
        if event.get("type") == "error" or isinstance(event.get("error"), dict):
            raise ValueError("OpenRouter music stream reported an error")
        event_count += 1
        _collect_audio(event, audio_chunks, media_types, text_chunks)
        if isinstance(event.get("usage"), dict):
            usage = dict(event["usage"])
    if event_count == 0:
        raise ValueError("OpenRouter music stream contained no events")
    return _finalize(
        response,
        audio_chunks,
        media_types,
        text_chunks,
        requested_format,
        "sse",
        usage,
    )


def _parse_buffered(
    response: httpx.Response, payload: JsonObject, requested_format: str
) -> ProviderMusic:
    audio_chunks: list[str] = []
    media_types: list[str] = []
    text_chunks: list[str] = []
    _collect_audio(payload, audio_chunks, media_types, text_chunks)
    usage = dict(payload["usage"]) if isinstance(payload.get("usage"), dict) else None
    return _finalize(
        response,
        audio_chunks,
        media_types,
        text_chunks,
        requested_format,
        "json",
        usage,
    )


def _collect_audio(
    payload: JsonObject,
    audio_chunks: list[str],
    media_types: list[str],
    text_chunks: list[str],
) -> None:
    choices = payload.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            for holder_name in ("delta", "message"):
                holder = choice.get(holder_name)
                if not isinstance(holder, dict):
                    continue
                content = holder.get("content")
                if isinstance(content, str) and content:
                    text_chunks.append(content)
                elif isinstance(content, list):
                    _collect_content_blocks(content, audio_chunks, media_types, text_chunks)
                if isinstance(holder.get("audio"), dict):
                    _collect_audio_object(holder["audio"], audio_chunks, media_types, text_chunks)
    steps = payload.get("steps")
    if isinstance(steps, list):
        for step in steps:
            if (
                isinstance(step, dict)
                and step.get("type") == "model_output"
                and isinstance(step.get("content"), list)
            ):
                _collect_content_blocks(step["content"], audio_chunks, media_types, text_chunks)
    outputs = payload.get("output")
    if isinstance(outputs, list):
        for output in outputs:
            if isinstance(output, dict) and isinstance(output.get("content"), list):
                _collect_content_blocks(output["content"], audio_chunks, media_types, text_chunks)
    if isinstance(payload.get("output_audio"), dict):
        _collect_audio_object(payload["output_audio"], audio_chunks, media_types, text_chunks)


def _collect_content_blocks(
    blocks: list[object],
    audio_chunks: list[str],
    media_types: list[str],
    text_chunks: list[str],
) -> None:
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") in {"text", "output_text"}:
            if isinstance(block.get("text"), str) and block["text"]:
                text_chunks.append(block["text"])
        elif block.get("type") in {"audio", "output_audio", "input_audio"}:
            nested = block.get("audio")
            value: dict[str, object] = nested if isinstance(nested, dict) else block
            _collect_audio_object(value, audio_chunks, media_types, text_chunks)


def _collect_audio_object(
    audio: dict[str, object],
    audio_chunks: list[str],
    media_types: list[str],
    text_chunks: list[str],
) -> None:
    data = audio.get("data")
    if isinstance(data, str) and data:
        match = _DATA_URI.match(data)
        if match:
            media_types.append(normalize_audio_media_type(match.group(1)))
            audio_chunks.append(match.group(2))
        else:
            audio_chunks.append(data)
    for key in ("media_type", "mime_type", "content_type", "format"):
        value = audio.get(key)
        if isinstance(value, str) and value:
            media_types.append(normalize_audio_media_type(value))
    transcript = audio.get("transcript")
    if isinstance(transcript, str) and transcript:
        text_chunks.append(transcript)


def _finalize(
    response: httpx.Response,
    audio_chunks: list[str],
    media_types: list[str],
    text_chunks: list[str],
    requested_format: str,
    source_shape: str,
    usage: JsonObject | None,
) -> ProviderMusic:
    if not audio_chunks:
        raise ValueError("OpenRouter music generation returned no audio data")
    media_type = _resolve_media_type(media_types, requested_format)
    data = decode_base64_strict("".join(audio_chunks), "OpenRouter music audio data")
    assert_audio_signature(data, media_type)
    text = "".join(text_chunks).strip() or None
    metadata_payload: JsonObject = {"usage": usage} if usage is not None else {}
    return ProviderMusic(
        data=data,
        media_type=media_type,
        text=text,
        source_shape=source_shape,
        response_metadata=response_metadata(response, metadata_payload),
    )


def _resolve_media_type(candidates: list[str], requested_format: str) -> str:
    fallback = "audio/mpeg" if requested_format == "mp3" else "audio/wav"
    unique = list(dict.fromkeys(normalize_audio_media_type(value) for value in candidates))
    if len(unique) > 1:
        raise ValueError(
            "OpenRouter music response declared conflicting media types: " + ", ".join(unique)
        )
    media_type = unique[0] if unique else fallback
    expected = fallback
    if media_type != expected:
        raise ValueError(f"requested {requested_format} but received {media_type}")
    return media_type
