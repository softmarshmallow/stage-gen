from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from gnode import (
    ArtifactProvenance,
    ImageGenerationRequest,
    ImageGenerationResult,
    ProviderResponseMetadata,
)
from stage_gen.concept_studio.image import generate_concept_image
from stage_gen.concept_studio.profiles import GROK_IMAGINE_IMAGE_2
from stage_gen.concept_studio.workspace import create_workspace
from stage_gen.config import StageGenConfig
from stage_gen.media import inspect_image


def _jpeg() -> bytes:
    output = BytesIO()
    Image.new("RGB", (7, 5), (17, 61, 103)).save(output, format="JPEG", quality=90)
    return output.getvalue()


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (3, 2), (203, 109, 41)).save(output, format="PNG")
    return output.getvalue()


class _FakeJpegService:
    def __init__(
        self,
        data: bytes,
        *,
        on_generate: Callable[[ImageGenerationRequest], None] | None = None,
    ) -> None:
        self.data = data
        self.on_generate = on_generate
        self.requests: list[ImageGenerationRequest] = []
        self.closed = False

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        self.requests.append(request)
        if self.on_generate is not None:
            self.on_generate(request)
        return ImageGenerationResult(
            data=self.data,
            media_type="image/jpeg",
            provider="openrouter",
            model=GROK_IMAGINE_IMAGE_2,
            attempts=2,
            provenance_path="/private/provider/original.jpeg.meta.json",
            response_metadata=ProviderResponseMetadata(
                request_id="request-123",
                usage={"images": 1},
            ),
        )

    async def aclose(self) -> None:
        self.closed = True


async def test_generate_jpeg_normalizes_to_portable_png_provenance_without_leaks(
    concept_repository: Path,
) -> None:
    created = create_workspace(
        concept_repository,
        concept_id="jpeg-normalization",
        title="JPEG Normalization",
        brief="Explore a rain-soaked rooftop courier game.",
    )
    workspace = Path(str(created["workspace"]))
    reference_path = workspace / "private-reference.png"
    reference_path.write_bytes(_png())
    service = _FakeJpegService(_jpeg())
    secret = "offline-super-secret"

    result = await generate_concept_image(
        repository_root=concept_repository,
        concept_id="jpeg-normalization",
        image_name="candidate-01",
        prompt="A courier crossing flooded rooftops at blue hour",
        model="grok",
        quality=None,
        resolution=None,
        aspect_ratio="16:9",
        reference_paths=(reference_path,),
        service=service,
        config=StageGenConfig(open_router_api_key=secret),
    )

    artifact_path = Path(str(result["artifact_path"]))
    provenance_path = Path(str(result["provenance_path"]))
    provenance_bytes = await asyncio.to_thread(provenance_path.read_bytes)
    serialized = await asyncio.to_thread(provenance_path.read_text)
    artifact_bytes = await asyncio.to_thread(artifact_path.read_bytes)
    record = ArtifactProvenance.model_validate_json(provenance_bytes)

    assert inspect_image(artifact_bytes, expected_media_type="image/png").format == "PNG"
    assert (result["source_media_type"], result["media_type"]) == ("image/jpeg", "image/png")
    assert (result["width"], result["height"]) == (7, 5)
    assert record.model == GROK_IMAGINE_IMAGE_2
    assert record.attempts == 2
    assert record.rights is not None and record.rights.status == "unreviewed"
    assert record.params["quality"] == "low"
    assert record.params["resolution"] == "1K"
    assert record.params["normalization"]["operation"] == "image-to-png"
    assert record.validation["source_media_type"] == "image/jpeg"
    assert len(record.inputs) == 2
    assert all(item.ref.startswith("sha256:") for item in record.inputs)
    assert service.requests[0].quality == "low"
    assert service.requests[0].resolution == "1K"
    assert len(service.requests[0].input_references) == 1
    assert workspace not in Path(service.requests[0].artifact_path).parents
    assert not service.closed
    for private_value in (
        secret,
        str(concept_repository),
        str(reference_path),
        reference_path.name,
        "/private/provider/original.jpeg.meta.json",
        "data:image",
    ):
        assert private_value not in serialized


async def test_generate_rolls_back_when_a_racing_sidecar_claims_the_candidate(
    concept_repository: Path,
) -> None:
    created = create_workspace(
        concept_repository,
        concept_id="candidate-race",
        title="Candidate Race",
        brief="Preserve a candidate created while the provider is running.",
    )
    workspace = Path(str(created["workspace"]))
    artifact = workspace / "images/candidate-01.png"
    sidecar = Path(f"{artifact}.meta.json")
    competing_sidecar = b"concurrent provenance"

    def publish_competing_candidate(_request: ImageGenerationRequest) -> None:
        sidecar.write_bytes(competing_sidecar)

    service = _FakeJpegService(_jpeg(), on_generate=publish_competing_candidate)

    with pytest.raises(ValueError, match="concept image already exists: candidate-01"):
        await generate_concept_image(
            repository_root=concept_repository,
            concept_id="candidate-race",
            image_name="candidate-01",
            prompt="A race-safe concept image",
            model="grok",
            quality=None,
            resolution=None,
            aspect_ratio="16:9",
            service=service,
            config=StageGenConfig(open_router_api_key="offline-secret"),
        )

    assert not await asyncio.to_thread(artifact.exists)
    assert await asyncio.to_thread(sidecar.read_bytes) == competing_sidecar


async def test_generate_replace_publishes_one_consistent_artifact_pair(
    concept_repository: Path,
) -> None:
    created = create_workspace(
        concept_repository,
        concept_id="candidate-replace",
        title="Candidate Replace",
        brief="Replace an existing pair as one rollback-safe publication.",
    )
    workspace = Path(str(created["workspace"]))
    artifact = workspace / "images/candidate-01.png"
    sidecar = Path(f"{artifact}.meta.json")
    await asyncio.to_thread(artifact.write_bytes, b"old candidate")
    await asyncio.to_thread(sidecar.write_bytes, b"old provenance")

    result = await generate_concept_image(
        repository_root=concept_repository,
        concept_id="candidate-replace",
        image_name="candidate-01",
        prompt="A replacement concept image",
        model="grok",
        quality=None,
        resolution=None,
        aspect_ratio="16:9",
        replace=True,
        service=_FakeJpegService(_jpeg()),
        config=StageGenConfig(open_router_api_key="offline-secret"),
    )

    artifact_bytes = await asyncio.to_thread(artifact.read_bytes)
    sidecar_bytes = await asyncio.to_thread(sidecar.read_bytes)
    record = ArtifactProvenance.model_validate_json(sidecar_bytes)
    assert result["sha256"] == hashlib.sha256(artifact_bytes).hexdigest()
    assert record.artifact is not None
    assert record.artifact.sha256 == result["sha256"]
    assert record.artifact.bytes == len(artifact_bytes)


async def test_generate_replace_restores_the_old_pair_when_second_install_fails(
    concept_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = create_workspace(
        concept_repository,
        concept_id="candidate-rollback",
        title="Candidate Rollback",
        brief="Restore both prior files if replacement cannot finish.",
    )
    workspace = Path(str(created["workspace"]))
    artifact = workspace / "images/candidate-01.png"
    sidecar = Path(f"{artifact}.meta.json")
    old_artifact = b"old candidate"
    old_sidecar = b"old provenance"
    await asyncio.to_thread(artifact.write_bytes, old_artifact)
    await asyncio.to_thread(sidecar.write_bytes, old_sidecar)
    original_replace = os.replace

    def fail_second_install(source: Any, destination: Any, **kwargs: Any) -> None:
        if ".tmp" in os.fspath(source) and os.fspath(destination) == sidecar.name:
            raise OSError("injected second install failure")
        original_replace(source, destination, **kwargs)

    monkeypatch.setattr(os, "replace", fail_second_install)

    with pytest.raises(OSError, match="injected second install failure"):
        await generate_concept_image(
            repository_root=concept_repository,
            concept_id="candidate-rollback",
            image_name="candidate-01",
            prompt="A rollback-safe replacement",
            model="grok",
            quality=None,
            resolution=None,
            aspect_ratio="16:9",
            replace=True,
            service=_FakeJpegService(_jpeg()),
            config=StageGenConfig(open_router_api_key="offline-secret"),
        )

    assert await asyncio.to_thread(artifact.read_bytes) == old_artifact
    assert await asyncio.to_thread(sidecar.read_bytes) == old_sidecar


async def test_generate_rejects_a_workspace_symlink_swap_without_writing_outside(
    concept_repository: Path,
) -> None:
    created = create_workspace(
        concept_repository,
        concept_id="workspace-swap",
        title="Workspace Swap",
        brief="Keep final publication confined to the opened workspace.",
    )
    workspace = Path(str(created["workspace"]))
    moved_workspace = workspace.with_name("workspace-swap-original")
    outside = concept_repository / "outside-workspace"
    outside.mkdir()

    def swap_workspace(_request: ImageGenerationRequest) -> None:
        workspace.rename(moved_workspace)
        workspace.symlink_to(outside, target_is_directory=True)

    service = _FakeJpegService(_jpeg(), on_generate=swap_workspace)

    with pytest.raises(ValueError, match="concept workspace changed while in use"):
        await generate_concept_image(
            repository_root=concept_repository,
            concept_id="workspace-swap",
            image_name="candidate-01",
            prompt="A confined concept image",
            model="grok",
            quality=None,
            resolution=None,
            aspect_ratio="16:9",
            service=service,
            config=StageGenConfig(open_router_api_key="offline-secret"),
        )

    assert not (outside / "images/candidate-01.png").exists()
    assert not (moved_workspace / "images/candidate-01.png").exists()
