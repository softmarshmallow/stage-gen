"""Model-aware concept image generation with portable PNG lineage."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, cast

from stage_gen.components._types import ProviderResponseMetadata
from stage_gen.components.image_generation import (
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageGenerationService,
    ImageReference,
)
from stage_gen.config import CapabilityName, StageGenConfig, load_config
from stage_gen.contracts import (
    ArtifactRights,
    BinaryArtifact,
    InputProvenance,
    ProvenanceInput,
    SoftwareIdentity,
)
from stage_gen.media import ImageNormalizationRecord, inspect_image, normalize_image_to_png
from stage_gen.orchestration.runtime import create_image_service
from stage_gen.provider_env import load_provider_dotenv
from stage_gen.reliability import build_artifact_provenance, serialize_provenance

from .profiles import ConceptImageExecution, resolve_execution
from .workspace import (
    _assert_image_output_available,
    _open_workspace_handle,
    _publish_image_pair,
    read_regular_file_snapshot,
    validate_image_name,
)

CONCEPT_IMAGE_COMPONENT = SoftwareIdentity(
    name="@stage-gen/game-concept-image",
    version="0.0.0",
)
CONCEPT_IMAGE_TOOL = SoftwareIdentity(name="stage-gen-concept", version="0.0.0")


class ConceptImageService(Protocol):
    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult: ...

    async def aclose(self) -> None: ...


def load_concept_config(repository_root: str | Path, *, model: str) -> StageGenConfig:
    root = Path(repository_root)
    values: dict[str, str | None] = {}
    if os.environ.get("_STAGE_GEN_DISABLE_DOTENV") != "1":
        values.update(cast(dict[str, str | None], load_provider_dotenv(root / ".env")))
    values.update(os.environ)
    values["STAGE_GEN_IMAGE_MODEL"] = model
    return load_config(env=values, require=(CapabilityName.IMAGE_GENERATION,))


async def generate_concept_image(
    *,
    repository_root: str | Path,
    concept_id: str,
    image_name: str,
    prompt: str,
    model: str,
    quality: str | None,
    resolution: str | None,
    aspect_ratio: str,
    reference_paths: Sequence[str | Path] = (),
    replace: bool = False,
    service: ConceptImageService | None = None,
    config: StageGenConfig | None = None,
) -> dict[str, object]:
    clean_prompt = prompt.strip()
    if not clean_prompt:
        raise ValueError("concept image prompt must be non-empty")
    candidate_name = validate_image_name(image_name)
    execution = resolve_execution(
        model=model,
        quality=quality,
        resolution=resolution,
        aspect_ratio=aspect_ratio,
        reference_count=len(reference_paths),
    )
    references, reference_inputs = _read_references(reference_paths)
    active_config = config or load_concept_config(
        repository_root,
        model=execution.profile.model,
    )
    owned_service: ImageGenerationService | None = None
    if service is None:
        api_key = active_config.open_router_api_key
        if api_key is None:
            raise ValueError("missing required environment variable: OPENROUTER_API_KEY")
        owned_service = create_image_service(
            api_key=api_key,
            model=execution.profile.model,
            base_url=active_config.open_router_base_url or "https://openrouter.ai/api/v1",
        )
    active_service = service or owned_service
    assert active_service is not None
    try:
        with _open_workspace_handle(repository_root, concept_id) as workspace:
            output, _sidecar = _assert_image_output_available(
                workspace,
                candidate_name,
                replace=replace,
            )
            with tempfile.TemporaryDirectory(prefix="stage-gen-concept-image-") as temporary:
                provider_path = Path(temporary) / "provider-output"
                request = ImageGenerationRequest(
                    prompt=clean_prompt,
                    artifact_path=provider_path,
                    input_references=references,
                    aspect_ratio=execution.aspect_ratio,
                    resolution=execution.resolution,
                    quality=execution.quality,
                    metadata={
                        "contract": "game_concept_image_v1",
                        "concept_id": concept_id,
                        "candidate_name": candidate_name,
                    },
                    timeout_seconds=active_config.capability_timeout_s,
                    validate=_validate_provider_image,
                    provenance_schema_version=2,
                )
                generated = await active_service.generate(request)
                if generated.model != execution.profile.model:
                    raise ValueError("concept image provider returned an unexpected model identity")
                normalized, normalization = normalize_image_to_png(generated.data)
                output_facts = inspect_image(normalized, expected_media_type="image/png")
                source_facts = inspect_image(
                    generated.data, expected_media_type=generated.media_type
                )
                source_digest = hashlib.sha256(generated.data).hexdigest()
                source_ref = f"sha256:{source_digest}"
                source_input = InputProvenance(
                    ref=source_ref,
                    sha256=source_digest,
                    source="content",
                    bytes=len(generated.data),
                    media_type=generated.media_type,
                )
                provenance = ProvenanceInput(
                    schema_version=2,
                    provider=generated.provider,
                    model=generated.model,
                    prompt=clean_prompt,
                    refs=[source_ref, *(item.ref for item in reference_inputs)],
                    inputs=[source_input, *reference_inputs],
                    params=_provenance_params(
                        execution,
                        concept_id,
                        candidate_name,
                        normalization,
                    ),
                    validation={
                        "output_nonempty": True,
                        "media_type": "image/png",
                        "signature": "matched",
                        "width": output_facts.width,
                        "height": output_facts.height,
                        "source_media_type": source_facts.media_type,
                        "source_width": source_facts.width,
                        "source_height": source_facts.height,
                    },
                    component=CONCEPT_IMAGE_COMPONENT,
                    tool=CONCEPT_IMAGE_TOOL,
                    attempts=generated.attempts,
                    response=_response_record(generated.response_metadata, generated),
                    rights=_unreviewed_rights(),
                )
                artifact = BinaryArtifact(data=normalized, media_type="image/png")
                secrets = (
                    (active_config.open_router_api_key,)
                    if active_config.open_router_api_key
                    else ()
                )
                record = build_artifact_provenance(artifact, provenance, secrets=secrets)
                _artifact_path, provenance_path = await asyncio.to_thread(
                    _publish_image_pair,
                    workspace,
                    candidate_name,
                    normalized,
                    serialize_provenance(record),
                    replace=replace,
                )
    finally:
        if owned_service is not None:
            await owned_service.aclose()
    return {
        "schema_version": 1,
        "kind": "game_concept_image_result_v1",
        "concept_id": concept_id,
        "candidate_name": candidate_name,
        "artifact_path": str(output),
        "provenance_path": str(provenance_path),
        "provider": generated.provider,
        "model": generated.model,
        "attempts": generated.attempts,
        "media_type": "image/png",
        "source_media_type": generated.media_type,
        "width": output_facts.width,
        "height": output_facts.height,
        "bytes": len(normalized),
        "sha256": hashlib.sha256(normalized).hexdigest(),
    }


def _read_references(
    paths: Sequence[str | Path],
) -> tuple[tuple[ImageReference, ...], list[InputProvenance]]:
    references: list[ImageReference] = []
    inputs: list[InputProvenance] = []
    for raw_path in paths:
        data = read_regular_file_snapshot(
            raw_path,
            "concept image references",
        )
        facts = inspect_image(data)
        digest = hashlib.sha256(data).hexdigest()
        ref = f"sha256:{digest}"
        references.append(
            ImageReference(
                url=f"data:{facts.media_type};base64,{base64.b64encode(data).decode('ascii')}",
                provenance_ref=ref,
            )
        )
        inputs.append(
            InputProvenance(
                ref=ref,
                sha256=digest,
                source="reference",
                bytes=len(data),
                media_type=facts.media_type,
            )
        )
    return tuple(references), inputs


def _validate_provider_image(artifact: BinaryArtifact) -> dict[str, object]:
    facts = inspect_image(artifact.data, expected_media_type=artifact.media_type)
    return {
        "width": facts.width,
        "height": facts.height,
        "has_alpha": facts.has_alpha,
    }


def _provenance_params(
    execution: ConceptImageExecution,
    concept_id: str,
    candidate_name: str,
    normalization: ImageNormalizationRecord,
) -> dict[str, object]:
    params: dict[str, object] = {
        "n": 1,
        "aspect_ratio": execution.aspect_ratio,
        "quality": execution.quality,
        "concept_image": {
            "schema_version": 1,
            "concept_id": concept_id,
            "candidate_name": candidate_name,
        },
        "normalization": normalization.as_dict(),
    }
    if execution.resolution is not None:
        params["resolution"] = execution.resolution
    return params


def _response_record(
    metadata: ProviderResponseMetadata,
    generated: ImageGenerationResult,
) -> dict[str, object]:
    response: dict[str, object] = {
        "media_type": generated.media_type,
        "bytes": len(generated.data),
    }
    if metadata.request_id:
        response["request_id"] = metadata.request_id
    if metadata.created is not None:
        response["created"] = metadata.created
    if metadata.usage is not None:
        response["usage"] = metadata.usage
    return response


def _unreviewed_rights() -> ArtifactRights:
    return ArtifactRights(
        status="unreviewed",
        license_id=None,
        notice="No redistribution review has been recorded for this concept image.",
        attribution=[],
        basis=[],
        reviewed_at=None,
    )
