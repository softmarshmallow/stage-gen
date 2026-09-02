"""Provider-free stand-ins for the services a dialogue-scene node calls."""

from __future__ import annotations

import asyncio
import json
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from gnode import (
    BinaryArtifact,
    ImageGenerationRequest,
    ImageGenerationResult,
    ProvenanceInput,
    ProviderResponseMetadata,
    RetryExhaustedError,
    SoftwareIdentity,
    StructuredGenerationRequest,
    StructuredGenerationResult,
    write_artifact_with_provenance,
)
from stage_gen.components.game_ui import ATLAS_ROLES
from tests.unit._ui_atlas_fixture import atlas_sheet


def chroma_png() -> bytes:
    output = BytesIO()
    image = Image.new("RGB", (1024, 1536), (255, 0, 255))
    image.paste((20, 30, 80), (256, 256, 768, 1280))
    image.save(output, format="PNG")
    return output.getvalue()


def sized_png(width: int, height: int) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), (20, 30, 80)).save(output, format="PNG")
    return output.getvalue()


def removed_png() -> bytes:
    output = BytesIO()
    image = Image.new("RGBA", (1024, 1536), (20, 30, 80, 255))
    image.paste((20, 30, 80, 0), (0, 0, 512, 1536))
    image.save(output, format="PNG")
    return output.getvalue()


class FakeImages:
    """Answer every image node with a deterministic PNG of the requested shape."""

    def __init__(self, *, attempts: int = 1, exhausted: bool = False) -> None:
        self.attempts = attempts
        self.exhausted = exhausted
        self.requests: list[ImageGenerationRequest] = []

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        self.requests.append(request)
        if self.exhausted:
            raise RetryExhaustedError("fake image", ValueError("bad media"), 6)
        role = request.metadata.get("role")
        data = (
            atlas_sheet(ATLAS_ROLES[str(role)])
            if role in ATLAS_ROLES
            else removed_png()
            if request.background == "transparent"
            else chroma_png()
            if role != "background"
            else sized_png(1680, 944)
            if request.size == "1680x944"
            else sized_png(1672, 941)
        )
        if request.validate is not None:
            request.validate(BinaryArtifact(data=data, media_type="image/png"))
        path = Path(request.artifact_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        provenance = await asyncio.to_thread(
            write_artifact_with_provenance,
            path,
            BinaryArtifact(data=data, media_type="image/png"),
            ProvenanceInput(
                component=SoftwareIdentity(name="@stage-gen/core", version="0.0.0"),
                tool=SoftwareIdentity(name="stage-gen", version="0.0.0"),
                schema_version=2,
                provider="fake",
                model="fake-image",
                prompt=request.prompt,
                attempts=1,
            ),
        )
        return ImageGenerationResult(
            data=data,
            media_type="image/png",
            provider="fake",
            model="fake-image",
            attempts=self.attempts,
            provenance_path=str(provenance),
            response_metadata=ProviderResponseMetadata(),
        )

    async def aclose(self) -> None:
        return None


class FakeStructured:
    """Answer the style-anchor and plan nodes with fixed, schema-valid documents."""

    def __init__(self, *, plan_shared_locks: dict[str, str] | None = None) -> None:
        self.plan_shared_locks = plan_shared_locks
        self.calls: list[StructuredGenerationRequest[Any]] = []

    async def generate(
        self, request: StructuredGenerationRequest[Any]
    ) -> StructuredGenerationResult[Any]:
        self.calls.append(request)
        value = (
            {
                "schema_version": 1,
                "kind": "image_style_selection_v1",
                "style_mode": "cel_shaded_anime_2d",
            }
            if request.schema.name == "image_style_selection_v1"
            else {
                "verdict": "accept",
                "confidence": 0.9,
                "checks": {"style_coherence": True, "text_free": True},
                "issues": [],
                "evidence": "fake atlas review",
            }
            if request.schema.name == "prepared_ui_atlas_review"
            else {
                "shared_locks": self.plan_shared_locks
                or {
                    "identity": "adult Mio identity",
                    "wardrobe": "navy cardigan",
                    "pose": "fixed conversational pose",
                    "lighting": "soft evening light",
                    "style": "untrusted edge style that must not reach image prompts",
                },
                "states": {
                    state: f"adult {state} expression"
                    for state in ("neutral", "delighted", "flustered", "concerned")
                },
            }
        )
        parsed = request.parse(value)
        persisted = request.artifact_value(parsed) if request.artifact_value else value
        path = Path(request.artifact_path)
        data = json.dumps(persisted).encode()
        provenance = await asyncio.to_thread(
            write_artifact_with_provenance,
            path,
            BinaryArtifact(data=data, media_type="application/json"),
            ProvenanceInput(
                component=SoftwareIdentity(name="@stage-gen/core", version="0.0.0"),
                tool=SoftwareIdentity(name="stage-gen", version="0.0.0"),
                schema_version=2,
                provider="fake",
                model="fake-structured",
                prompt=request.prompt,
                attempts=1,
            ),
        )
        return StructuredGenerationResult(
            value=parsed,
            raw_text=json.dumps(value),
            provider="fake",
            model="fake-structured",
            attempts=1,
            provenance_path=str(provenance),
            response_metadata=ProviderResponseMetadata(),
        )

    async def aclose(self) -> None:
        return None


def authored_profile_source(tmp_path: Path) -> Path:
    """Copy the tracked authored profile into a caller-owned library root."""

    repository = Path(__file__).resolve().parents[4]
    source = repository / "library/characters/mira-vale-cartographer/profile.toml"
    target = tmp_path / "authored-library/library/characters/mira-vale-cartographer/profile.toml"
    target.parent.mkdir(parents=True)
    target.write_bytes(source.read_bytes())
    return target
