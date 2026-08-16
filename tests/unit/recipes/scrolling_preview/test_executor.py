from __future__ import annotations

import asyncio
import json
from io import BytesIO
from pathlib import Path
from typing import cast

import pytest
from PIL import Image

import stage_gen.recipes.scrolling_preview.executor as executor_module
from stage_gen.components import (
    BackgroundRemovalRequest,
    BackgroundRemovalResult,
    BackgroundRemovalService,
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageGenerationService,
    StructuredGenerationService,
)
from stage_gen.components._types import ProviderResponseMetadata
from stage_gen.config import StageGenConfig, TransparencyMode
from stage_gen.contracts import BinaryArtifact, ProvenanceInput
from stage_gen.recipes.base import StageContext
from stage_gen.recipes.scrolling_preview.executor import (
    _STATES,
    ScrollingPreviewExecutor,
    _exact_image,
    _ImageSpec,
    _valid_transparency_cache,
)
from stage_gen.recipes.scrolling_preview.manifest import write_scrolling_preview_manifest
from stage_gen.recipes.scrolling_preview.models import WorldSpec
from stage_gen.reliability import sha256_hex, write_artifact_with_provenance


def _png(*, alpha: bool) -> bytes:
    image = Image.new("RGBA" if alpha else "RGB", (2, 2), (20, 40, 60, 255))
    if alpha:
        image.putpixel((0, 0), (20, 40, 60, 0))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_transparency_cache_binds_raw_hash_dimensions_mode_and_nontrivial_alpha(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "asset.raw.png"
    raw = _png(alpha=False)
    raw_path.write_bytes(raw)
    canonical = tmp_path / "asset.png"
    canonical_data = _png(alpha=True)
    canonical.write_bytes(canonical_data)
    sidecar = {
        "artifact": {"sha256": sha256_hex(canonical_data)},
        "params": {
            "transparency": {
                "mode": "chroma",
                "retained_raw_path": raw_path.name,
                "raw_sha256": sha256_hex(raw),
                "output_sha256": sha256_hex(canonical_data),
            }
        },
        "validation": {
            "alpha_nontrivial": True,
            "dimensions_preserved": True,
            "output_width": 2,
            "output_height": 2,
            "transparent_pixels": 1,
            "nontransparent_pixels": 3,
        },
    }
    assert _valid_transparency_cache(
        canonical,
        sidecar,
        raw_path=raw_path,
        mode=TransparencyMode.CHROMA,
        width=2,
        height=2,
    )
    raw_path.write_bytes(b"stale")
    assert not _valid_transparency_cache(
        canonical,
        sidecar,
        raw_path=raw_path,
        mode=TransparencyMode.CHROMA,
        width=2,
        height=2,
    )
    opaque = tmp_path / "opaque.png"
    opaque.write_bytes(_png(alpha=False))
    assert not _exact_image(opaque, 2, 2, alpha=True)


class _FakeImageService:
    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        artifact_path = Path(request.artifact_path)
        data = _png(alpha=False)
        provenance_path = write_artifact_with_provenance(
            artifact_path,
            BinaryArtifact(data=data, media_type="image/png"),
            ProvenanceInput(
                provider="fake-image",
                model="image-model",
                prompt=request.prompt,
                params={"upstream": {"quality": "high"}},
                validation={"provider_validated": True},
                attempts=3,
                response={"request_id": "image-request", "usage": {"images": 1}},
            ),
        )
        return ImageGenerationResult(
            data=data,
            media_type="image/png",
            provider="fake-image",
            model="image-model",
            attempts=3,
            provenance_path=str(provenance_path),
            response_metadata=ProviderResponseMetadata(request_id="image-request"),
        )


class _FakeBackgroundService:
    async def remove(self, request: BackgroundRemovalRequest) -> BackgroundRemovalResult:
        artifact_path = Path(request.artifact_path)
        data = _png(alpha=True)
        provenance_path = write_artifact_with_provenance(
            artifact_path,
            BinaryArtifact(data=data, media_type="image/png"),
            ProvenanceInput(
                provider="fake-remover",
                model="removal-model",
                prompt="remove background",
                params={"output_mask": True},
                validation={"mask_received": False},
                attempts=2,
                response={"request_id": "remove-request"},
            ),
        )
        return BackgroundRemovalResult(
            data=data,
            media_type="image/png",
            source_url="https://example.invalid/removed.png",
            provider="fake-remover",
            model="removal-model",
            attempts=2,
            provenance_path=str(provenance_path),
            response_metadata=ProviderResponseMetadata(request_id="remove-request"),
        )


def _executor(*, background: _FakeBackgroundService | None = None) -> ScrollingPreviewExecutor:
    return ScrollingPreviewExecutor(
        image_service=cast(ImageGenerationService, _FakeImageService()),
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
        background_service=(
            cast(BackgroundRemovalService, background) if background is not None else None
        ),
    )


async def test_tileset_maintenance_stage_reuses_production_spec_and_forces_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = _executor()
    observed: dict[str, object] = {}

    async def capture(
        context: StageContext, spec: _ImageSpec, *, force: bool = False
    ) -> tuple[str, str]:
        observed.update(context=context, spec=spec, force=force)
        return str(spec.output), f"{spec.output}.meta.json"

    monkeypatch.setattr(executor, "_generate_image_asset", capture)
    context = StageContext(
        input={"prompt": "existing", "transparencyMode": "chroma"},
        tag="existing-chroma",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.CHROMA),
    )
    result = await executor.run_scrolling_preview_stage("maintenance-regenerate-tileset", context)

    spec = cast(_ImageSpec, observed["spec"])
    assert observed["force"] is True
    assert spec.stage == "tileset"
    assert spec.output == tmp_path / "tileset_existing-chroma.png"
    assert (spec.width, spec.height) == (2400, 800)
    assert spec.references[1] == tmp_path / "concept_existing-chroma.png"
    assert result == (str(spec.output), f"{spec.output}.meta.json")


async def test_normalized_raw_embeds_upstream_provenance_before_temp_cleanup(
    tmp_path: Path,
) -> None:
    executor = _executor()
    context = StageContext(
        input={"prompt": "offline"},
        tag="offline",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.CHROMA),
    )
    output = tmp_path / "opaque.png"
    await executor._generate_image_asset(
        context,
        _ImageSpec("opaque", "offline prompt", output, 2, 2, transparent=False),
    )
    sidecar = json.loads(await asyncio.to_thread(Path(f"{output}.meta.json").read_text))
    serialized = json.dumps(sidecar)
    assert sidecar["provider"] == "fake-image"
    assert sidecar["attempts"] == 3
    assert sidecar["response"]["request_id"] == "image-request"
    assert sidecar["params"]["upstream_provenance"]["provider"] == "fake-image"
    assert ".provider-" not in serialized
    assert not await asyncio.to_thread(lambda: list(tmp_path.glob(".*.provider-*.png")))


async def test_ai_transparency_embeds_removal_provenance_without_dangling_temp_path(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "asset.raw.png"
    raw = _png(alpha=False)
    write_artifact_with_provenance(
        raw_path,
        BinaryArtifact(data=raw, media_type="image/png"),
        ProvenanceInput(
            provider="fake-image",
            model="image-model",
            prompt="raw prompt",
            params={"metadata": {"transparency_mode": "ai"}},
            validation={"exact_contract_dimensions": True},
            attempts=2,
            response={"request_id": "raw-request"},
        ),
    )
    executor = _executor(background=_FakeBackgroundService())
    context = StageContext(
        input={"prompt": "offline"},
        tag="offline",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.AI),
    )
    output = tmp_path / "asset.png"
    await executor._derive_transparency(
        context,
        _ImageSpec("asset", "offline prompt", output, 2, 2),
        raw_path,
    )
    sidecar = json.loads(await asyncio.to_thread(Path(f"{output}.meta.json").read_text))
    serialized = json.dumps(sidecar)
    removal = sidecar["params"]["transparency"]["removal"]
    assert sidecar["provider"] == "fake-remover"
    assert sidecar["attempts"] == 2
    assert removal["provider"] == "fake-remover"
    assert removal["provenance"]["response"]["request_id"] == "remove-request"
    assert sidecar["response"]["transparency"]["removal_provenance"] == "inline"
    assert ".removed-" not in serialized
    assert not await asyncio.to_thread(lambda: list(tmp_path.glob(".*.removed-*.png")))


async def test_executor_composite_sidecar_flows_into_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tag = "executor-chroma"
    for state in _STATES:
        raw_name = f"character_{tag}_combined_strip_{state}.raw.png"
        raw_data = f"raw-{state}".encode()
        write_artifact_with_provenance(
            tmp_path / raw_name,
            BinaryArtifact(data=raw_data, media_type="image/png"),
            ProvenanceInput(
                provider="fake-image",
                model="image-model",
                prompt=state,
                params={"metadata": {"transparency_mode": "chroma"}},
                validation={
                    "exact_contract_dimensions": True,
                    "output_width": 2400,
                    "output_height": 800,
                },
                attempts=1,
            ),
        )
        canonical_name = f"character_{tag}_combined_strip_{state}.png"
        canonical_data = f"canonical-{state}".encode()
        write_artifact_with_provenance(
            tmp_path / canonical_name,
            BinaryArtifact(data=canonical_data, media_type="image/png"),
            ProvenanceInput(
                provider="local",
                model="chroma-key",
                prompt=state,
                refs=[raw_name],
                params={
                    "transparency": {
                        "mode": "chroma",
                        "retained_raw_path": raw_name,
                        "raw_sha256": sha256_hex(raw_data),
                        "output_sha256": sha256_hex(canonical_data),
                        "processor": {"kind": "chroma-key", "version": "1"},
                    }
                },
                validation={
                    "alpha_nontrivial": True,
                    "transparent_pixels": 1,
                    "nontransparent_pixels": 1,
                    "dimensions_preserved": True,
                    "output_width": 2400,
                    "output_height": 800,
                },
                attempts=1,
            ),
        )

    composite_data = b"executor-composite"
    monkeypatch.setattr(
        executor_module,
        "_compose_master_rows",
        lambda _sources: (composite_data, 1, 1),
    )
    executor = _executor()
    context = StageContext(
        input={"prompt": "offline"},
        tag=tag,
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.CHROMA),
    )
    await executor._compose_character_master(context)
    result = await write_scrolling_preview_manifest(
        run_dir=tmp_path,
        tag=tag,
        transparency_mode=TransparencyMode.CHROMA,
    )
    manifest_text = await asyncio.to_thread(Path(result.manifest_path).read_text)
    manifest = json.loads(manifest_text)
    master_name = f"character_{tag}_combined.png"
    master = next(entry for entry in manifest["canonicalArtifacts"] if entry["path"] == master_name)
    assert master["transparency"]["lineage"]["sourcePaths"] == [
        f"character_{tag}_combined_strip_{state}.png" for state in _STATES
    ]
