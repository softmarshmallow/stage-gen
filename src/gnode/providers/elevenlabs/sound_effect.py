from __future__ import annotations

from typing import ClassVar, Literal

import httpx

from gnode.modalities._types import JsonObject
from gnode.modalities.signatures import assert_audio_signature, normalize_audio_media_type
from gnode.modalities.sound_effect import ProviderSoundEffect, SoundEffectGenerationRequest
from gnode.providers._http import assert_success, normalized_base_url, response_metadata

ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"
ELEVENLABS_SOUND_EFFECT_MODEL = "eleven_text_to_sound_v2"
#: The one container every reviewed clip used. The route's raw PCM formats are
#: headerless and would fail the audio-signature floor, and wrapping them is
#: post-processing, so mp3 is the only format this adapter requests.
_OUTPUT_FORMATS: dict[str, str] = {"mp3": "mp3_44100_192"}
_MEDIA_TYPES: dict[str, str] = {"mp3": "audio/mpeg"}


class ElevenLabsSoundEffectBackend:
    """One attempt against the ElevenLabs text-to-sound-effect route."""

    spec_version: ClassVar[Literal[1]] = 1
    provider = "elevenlabs"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = ELEVENLABS_SOUND_EFFECT_MODEL,
        base_url: str = ELEVENLABS_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("ElevenLabs api_key must be non-empty")
        if not model.strip():
            raise ValueError("ElevenLabs sound effect model must be non-empty")
        self._api_key = api_key
        self.secrets: tuple[str, ...] = (api_key,)
        self.model = model.strip()
        self._base_url = normalized_base_url(base_url, "ElevenLabs base_url")
        self._client = client or httpx.AsyncClient(timeout=None)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def generate_once(self, request: SoundEffectGenerationRequest) -> ProviderSoundEffect:
        body: JsonObject = {
            "text": request.prompt,
            "model_id": self.model,
            "loop": request.loop,
        }
        if request.duration_seconds is not None:
            body["duration_seconds"] = request.duration_seconds
        if request.prompt_influence is not None:
            body["prompt_influence"] = request.prompt_influence
        response = await self._client.post(
            f"{self._base_url}/sound-generation",
            params={"output_format": _OUTPUT_FORMATS[request.output_format]},
            headers={
                "xi-api-key": self._api_key,
                "content-type": "application/json",
                "accept": "audio/mpeg",
            },
            json=body,
            timeout=request.timeout_seconds,
        )
        assert_success(
            response,
            "ElevenLabs sound generation",
            include_safe_error_detail=True,
            redactions=self.secrets,
        )
        data = response.content
        if not data:
            raise ValueError("ElevenLabs sound generation returned no audio data")
        expected = _MEDIA_TYPES[request.output_format]
        declared = response.headers.get("content-type")
        media_type = expected if declared is None else normalize_audio_media_type(declared)
        if media_type != expected:
            raise ValueError(f"requested {request.output_format} but received {media_type}")
        assert_audio_signature(data, media_type)
        usage = _usage(response)
        return ProviderSoundEffect(
            data=data,
            media_type=media_type,
            source_shape="binary",
            response_metadata=response_metadata(
                response, {"usage": usage} if usage is not None else None
            ),
        )


def _usage(response: httpx.Response) -> JsonObject | None:
    """The route bills in characters and reports the charge as a header."""

    raw = response.headers.get("character-cost")
    if raw is None:
        return None
    try:
        return {"character_cost": int(raw)}
    except ValueError:
        return None
