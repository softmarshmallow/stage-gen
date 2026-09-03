from __future__ import annotations

from typing import ClassVar, Literal

import httpx

from gnode.modalities._types import JsonObject
from gnode.modalities.signatures import assert_audio_signature, normalize_audio_media_type
from gnode.modalities.speech import ProviderSpeech, SpeechGenerationRequest
from gnode.providers._http import assert_success, normalized_base_url, response_metadata

from .sound_effect import ELEVENLABS_BASE_URL

#: The v3 model is the one that reads bracketed delivery annotations; the v2
#: family ignores them or speaks them aloud.
ELEVENLABS_SPEECH_MODEL = "eleven_v3"
#: The one container every reviewed clip used; the route's raw PCM formats are
#: headerless and would fail the audio-signature floor.
_OUTPUT_FORMATS: dict[str, str] = {"mp3": "mp3_44100_192"}
_MEDIA_TYPES: dict[str, str] = {"mp3": "audio/mpeg"}


class ElevenLabsSpeechBackend:
    """One attempt against the ElevenLabs text-to-speech route.

    ``voice_settings`` carries ``stability`` alone. The v3 model reports
    ``can_use_style`` and ``can_use_speaker_boost`` false, so nothing else is
    sent, and a seed is never sent: measured, it pins the length of a read and
    not its waveform, which is not reproducibility and must not be recorded as
    such.
    """

    spec_version: ClassVar[Literal[1]] = 1
    provider = "elevenlabs"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = ELEVENLABS_SPEECH_MODEL,
        base_url: str = ELEVENLABS_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("ElevenLabs api_key must be non-empty")
        if not model.strip():
            raise ValueError("ElevenLabs speech model must be non-empty")
        self._api_key = api_key
        self.secrets: tuple[str, ...] = (api_key,)
        self.model = model.strip()
        self._base_url = normalized_base_url(base_url, "ElevenLabs base_url")
        self._client = client or httpx.AsyncClient(timeout=None)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def generate_once(self, request: SpeechGenerationRequest) -> ProviderSpeech:
        body: JsonObject = {"text": request.text, "model_id": self.model}
        if request.stability is not None:
            body["voice_settings"] = {"stability": request.stability}
        if request.language_code is not None:
            body["language_code"] = request.language_code
        response = await self._client.post(
            f"{self._base_url}/text-to-speech/{request.voice}",
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
            "ElevenLabs speech generation",
            include_safe_error_detail=True,
            redactions=self.secrets,
        )
        data = response.content
        if not data:
            raise ValueError("ElevenLabs speech generation returned no audio data")
        expected = _MEDIA_TYPES[request.output_format]
        declared = response.headers.get("content-type")
        media_type = expected if declared is None else normalize_audio_media_type(declared)
        if media_type != expected:
            raise ValueError(f"requested {request.output_format} but received {media_type}")
        assert_audio_signature(data, media_type)
        usage = _usage(response)
        return ProviderSpeech(
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
