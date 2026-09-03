"""Provider-free stand-ins for the services a point-and-click room node calls.

The image fake is **deliberately non-deterministic**: every instance stamps its
own nonce into the pixels it returns, exactly as an unseeded generator draws a
different picture every time it is asked. That is what makes a cache assertion
mean something here — if a re-run's backdrop still hashes to the first run's
bytes, the only way it could have is by reuse, because a second draw could not
have reproduced them.
"""

from __future__ import annotations

import asyncio
import json
import re
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
    SoftwareIdentity,
    StructuredGenerationRequest,
    StructuredGenerationResult,
    write_artifact_with_provenance,
)
from stage_gen.components.game_ui.nodes import UI_SHEET_ROLES
from tests.unit._ui_atlas_fixture import ui_sheet

_NARRATION_ID = re.compile(r'- id "([a-z0-9_-]+)"')


def _nonce_pixels(image: Image.Image, nonce: int) -> None:
    """Stamp the draw's identity into the top-left corner, one pixel per bit."""

    for bit in range(16):
        value = 255 if (nonce >> bit) & 1 else 0
        image.putpixel((bit, 0), (value, value, value, 255)[: len(image.getbands())])


def opaque_png(width: int, height: int, nonce: int) -> bytes:
    output = BytesIO()
    image = Image.new("RGB", (width, height), (20, 30, 80))
    _nonce_pixels(image, nonce)
    image.save(output, format="PNG")
    return output.getvalue()


def sprite_png(width: int, height: int, nonce: int) -> bytes:
    """One isolated opaque subject on transparent ground, as the gate demands."""

    output = BytesIO()
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    inset_x, inset_y = width // 4, height // 4
    image.paste((180, 140, 60, 255), (inset_x, inset_y, width - inset_x, height - inset_y))
    _nonce_pixels(image, nonce)
    image.save(output, format="PNG")
    return output.getvalue()


class FakeRoomImages:
    """Answer every room image node with a PNG of exactly the requested shape."""

    def __init__(self, *, nonce: int) -> None:
        self.nonce = nonce
        self.requests: list[ImageGenerationRequest] = []

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        self.requests.append(request)
        role = str(request.metadata.get("role"))
        if role in UI_SHEET_ROLES:
            # The interface sheets stay byte-stable: the atlas gate measures real
            # geometry on them, and this fake is not the thing under test.
            data = ui_sheet(role)
        else:
            width, height = (int(part) for part in str(request.size).split("x"))
            data = (
                sprite_png(width, height, self.nonce)
                if request.background == "transparent"
                else opaque_png(width, height, self.nonce)
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
            attempts=1,
            provenance_path=str(provenance),
            response_metadata=ProviderResponseMetadata(),
        )

    async def aclose(self) -> None:
        return None


class FakeRoomStructured:
    """Answer the style anchor, the narration gaps, and the atlas review."""

    def __init__(self) -> None:
        self.calls: list[StructuredGenerationRequest[Any]] = []

    async def generate(
        self, request: StructuredGenerationRequest[Any]
    ) -> StructuredGenerationResult[Any]:
        self.calls.append(request)
        name = request.schema.name
        if name == "image_style_selection_v1":
            value: object = {
                "schema_version": 1,
                "kind": "image_style_selection_v1",
                "style_mode": "cel_shaded_anime_2d",
            }
        elif name == "prepared_ui_atlas_review":
            value = {
                "verdict": "accept",
                "confidence": 0.9,
                "checks": {"style_coherence": True, "text_free": True},
                "issues": [],
                "evidence": "fake atlas review",
            }
        elif name == "pointclick_narration_v1":
            # The closed id set is stated in the prompt; answering exactly it is
            # what the handler checks, so read it back rather than inventing one.
            value = {
                "narrations": [
                    {"id": found, "text": f"A line for {found}."}
                    for found in _NARRATION_ID.findall(request.prompt)
                ]
            }
        else:
            raise AssertionError(f"unexpected structured schema: {name}")
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
