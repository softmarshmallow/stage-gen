from __future__ import annotations

import httpx
import pytest

from gnode import ImageGenerationRequest
from gnode.providers.openai import OpenAIImageBackend


def _backend(base_url: str, client: httpx.AsyncClient) -> OpenAIImageBackend:
    return OpenAIImageBackend(
        api_key="fixture-key",
        model="fixture-model",
        supports_native_alpha=True,
        base_url=base_url,
        client=client,
    )


@pytest.mark.parametrize(
    "value",
    [
        "http://provider.example.test/v1",
        "http://192.0.2.1:8080/v1",
    ],
)
@pytest.mark.asyncio
async def test_provider_base_url_refuses_cleartext_non_loopback_transport(value: str) -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError, match="must use HTTPS"):
            _backend(value, client)


@pytest.mark.parametrize(
    "value",
    [
        "http://localhost:8765/v1/",
        "http://127.0.0.1:8765/v1/",
        "http://[::1]:8765/v1/",
    ],
)
@pytest.mark.asyncio
async def test_provider_base_url_allows_cleartext_loopback_for_local_tests(value: str) -> None:
    async with httpx.AsyncClient() as client:
        backend = _backend(value, client)
        request = ImageGenerationRequest(prompt="fixture", artifact_path="unused.png")
        assert backend.endpoint_for(request) == f"{value.rstrip('/')}/images/generations"


@pytest.mark.parametrize(
    "value",
    [
        "https://user:password@provider.example.test/v1",
        "https://provider.example.test/v1?credential=secret",
        "https://provider.example.test/v1#secret",
    ],
)
@pytest.mark.asyncio
async def test_provider_base_url_refuses_embedded_credentials_or_suffixes(value: str) -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError, match="without credentials, query, or fragment"):
            _backend(value, client)


@pytest.mark.parametrize(
    "value",
    [
        "https://provider.example.test:bad/v1",
        "https://provider.example.test:99999/v1",
    ],
)
@pytest.mark.asyncio
async def test_provider_base_url_refuses_invalid_ports(value: str) -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError, match="valid network port"):
            _backend(value, client)
