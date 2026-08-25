from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from PIL import Image, ImageDraw

import stage_gen.recipes.scrolling_preview.executor as executor_module
import stage_gen.recipes.scrolling_preview.manifest as manifest_module
from stage_gen.components import (
    BackgroundRemovalRequest,
    BackgroundRemovalResult,
    BackgroundRemovalService,
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageGenerationService,
    StructuredGenerationRequest,
    StructuredGenerationService,
)
from stage_gen.components._types import ProviderResponseMetadata
from stage_gen.components.background_removal import (
    BackgroundRemovalBackend,
    ProviderBackgroundRemoval,
)
from stage_gen.components.image_generation import (
    ImageGenerationBackend,
    ProviderImage,
    StyleModeSelection,
    canonical_style_anchor_digest,
)
from stage_gen.components.structured_generation import ProviderStructuredOutput
from stage_gen.config import StageGenConfig, TransparencyMode
from stage_gen.contracts import BinaryArtifact, ProvenanceInput
from stage_gen.image_prompting import (
    IMAGE_STYLE_SELECTION_SCHEMA,
    load_image_style_resources,
    materialize_style_anchor,
)
from stage_gen.media import CHROMA_MATTE_VERSION
from stage_gen.recipes.base import StageContext
from stage_gen.recipes.scrolling_preview.executor import (
    _STATES,
    ScrollingPreviewExecutor,
    _exact_image,
    _ImageSpec,
    _valid_transparency_cache,
)
from stage_gen.recipes.scrolling_preview.manifest import write_scrolling_preview_manifest
from stage_gen.recipes.scrolling_preview.models import WorldLayer, WorldSpec
from stage_gen.recipes.scrolling_preview.raster_contracts import (
    GRID_EMPTY_CELL_ERROR_CODE,
    GRID_ISOLATION_ERROR_CODE,
    GRID_UNIFORM_SOURCE_ERROR_CODE,
    ISOLATED_ALPHA_CLEANUP_VERSION,
    ISOLATED_SUBJECT_FIT_VERSION,
    GridSourceLayoutError,
    contract_for_stage,
    grid_semantic_contract,
    normalize_canonical_grid,
    side_view_symmetry_ceiling,
    validate_canonical_grid,
)
from stage_gen.recipes.scrolling_preview.tileset_materials import (
    CAP_FILL_GLOBAL_GAMUT_VERSION,
    CAP_FILL_LIGHTNESS_VERSION,
)
from stage_gen.recipes.scrolling_preview.village import (
    VILLAGE_NPC_COUNT,
    VILLAGE_SPEC_SCHEMA_NAME,
    VillageSpec,
    npc_turnaround_subject,
)
from stage_gen.reliability import (
    RetryExhaustedError,
    RetryFailureRecord,
    RetryPolicy,
    sha256_hex,
    write_artifact_with_provenance,
)
from stage_gen.theme import (
    THEME_COMPILER_VERSION,
    CompiledThemePlan,
    ThemeHandles,
    canonical_theme_json,
    load_theme_compiler_skill,
    raw_theme_control_leaks,
)


def _png(*, alpha: bool) -> bytes:
    image = Image.new("RGBA" if alpha else "RGB", (2, 2), (20, 40, 60, 255))
    if alpha:
        image.putpixel((0, 0), (20, 40, 60, 0))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _image_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _alpha_png(values: tuple[int, int, int, int]) -> bytes:
    image = Image.new("RGBA", (2, 2))
    image.putdata([(20, 40, 60, value) for value in values])
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
    sidecar: dict[str, Any] = {
        "artifact": {"sha256": sha256_hex(canonical_data)},
        "params": {
            "transparency": {
                "mode": "chroma",
                "retained_raw_path": raw_path.name,
                "raw_sha256": sha256_hex(raw),
                "output_sha256": sha256_hex(canonical_data),
                "matte_version": CHROMA_MATTE_VERSION,
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


def test_grid_transparency_cache_requires_bound_normalization_evidence(tmp_path: Path) -> None:
    contract = contract_for_stage("items")
    assert contract is not None
    raw_path = tmp_path / "items.raw.png"
    raw = _grid_source()
    raw_path.write_bytes(raw)
    canonical_path = tmp_path / "items.png"
    canonical_data, geometry = normalize_canonical_grid(_grid_alpha(), contract)
    canonical_path.write_bytes(canonical_data)
    normalization_input = cast(dict[str, Any], geometry["grid_normalization"])
    normalization = {
        **normalization_input,
        "normalization_input_sha256": normalization_input["input_sha256"],
        "normalization_input_bytes": normalization_input["input_bytes"],
        "input_sha256": sha256_hex(raw),
        "input_bytes": len(raw),
        "input_role": "retained-raw-artifact",
    }
    geometry = {**geometry, "grid_normalization": normalization}
    sidecar: dict[str, Any] = {
        "artifact": {"sha256": sha256_hex(canonical_data)},
        "params": {
            "transparency": {
                "mode": "chroma",
                "retained_raw_path": raw_path.name,
                "raw_sha256": sha256_hex(raw),
                "output_sha256": sha256_hex(canonical_data),
                "matte_version": CHROMA_MATTE_VERSION,
                "processor": {
                    "kind": "chroma-key+grid-cell-normalization",
                    "version": "per-cell-isolation-v2",
                },
                "grid_normalization": normalization,
            },
            "metadata": {"grid_contract": contract.as_dict(160, 80)},
        },
        "validation": {
            "alpha_nontrivial": True,
            "dimensions_preserved": True,
            "output_width": 160,
            "output_height": 80,
            "transparent_pixels": 1,
            "nontransparent_pixels": 1,
            **geometry,
        },
    }

    assert _valid_transparency_cache(
        canonical_path,
        sidecar,
        raw_path=raw_path,
        mode=TransparencyMode.CHROMA,
        width=160,
        height=80,
        contract=contract,
    )

    forged_input = cast(dict[str, Any], json.loads(json.dumps(sidecar)))
    forged_input["validation"]["grid_normalization"]["input_sha256"] = "0" * 64
    forged_input["params"]["transparency"]["grid_normalization"]["input_sha256"] = "0" * 64
    assert not _valid_transparency_cache(
        canonical_path,
        forged_input,
        raw_path=raw_path,
        mode=TransparencyMode.CHROMA,
        width=160,
        height=80,
        contract=contract,
    )

    forged_role = cast(dict[str, Any], json.loads(json.dumps(sidecar)))
    forged_role["validation"]["grid_normalization"]["transforms"][0]["semantic_role"] = (
        "forged-role"
    )
    forged_role["params"]["transparency"]["grid_normalization"]["transforms"][0][
        "semantic_role"
    ] = "forged-role"
    assert not _valid_transparency_cache(
        canonical_path,
        forged_role,
        raw_path=raw_path,
        mode=TransparencyMode.CHROMA,
        width=160,
        height=80,
        contract=contract,
    )

    forged_layout = cast(dict[str, Any], json.loads(json.dumps(sidecar)))
    for container in (
        forged_layout["validation"],
        forged_layout["params"]["transparency"],
    ):
        semantic_contract = container["grid_normalization"]["semantic_contract"]
        semantic_contract["roles"][0]["semantic_role"] = "forged-role"
        semantic_contract["sha256"] = "0" * 64
    assert not _valid_transparency_cache(
        canonical_path,
        forged_layout,
        raw_path=raw_path,
        mode=TransparencyMode.CHROMA,
        width=160,
        height=80,
        contract=contract,
    )

    del sidecar["validation"]["grid_normalization"]
    assert not _valid_transparency_cache(
        canonical_path,
        sidecar,
        raw_path=raw_path,
        mode=TransparencyMode.CHROMA,
        width=160,
        height=80,
        contract=contract,
    )


class _FakeImageService:
    def __init__(self) -> None:
        self.requests: list[ImageGenerationRequest] = []

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        self.requests.append(request)
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
    def __init__(self) -> None:
        self.requests: list[BackgroundRemovalRequest] = []

    async def remove(self, request: BackgroundRemovalRequest) -> BackgroundRemovalResult:
        self.requests.append(request)
        artifact_path = Path(request.artifact_path)
        data = _png(alpha=True)
        provenance_path = write_artifact_with_provenance(
            artifact_path,
            BinaryArtifact(data=data, media_type="image/png"),
            ProvenanceInput(
                provider="fake-remover",
                model="removal-model",
                prompt="remove background",
                params={
                    "output_mask": request.output_mask,
                    "validated": request.validate is not None,
                },
                validation={"mask_received": False, "caller": request.validate is not None},
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


def _compiled_plan() -> dict[str, str]:
    return {
        "concept": (
            "Polished ink-lined gothic anime art of clearly adult masked investigators in a "
            "moonlit rooftop garden, sharing warm eye contact while a spectral gate glows."
        ),
        "world_spec": (
            "Plan clearly adult characters, tense confrontations, intact bodies, festive drink "
            "vessels, and an ominous but coherent world."
        ),
        "environment": (
            "Use broken cover, tense silhouettes, deep violet shadows, and clearly readable "
            "scenery with generous negative space."
        ),
        "characters": (
            "Show clearly adult characters in dynamic confrontation, with mutual warmth, elegant "
            "opaque eveningwear, and intact skin."
        ),
        "items": (
            "Use readable fantasy props, festive drink vessels, weathered gear, and ominous relics "
            "arranged with clean silhouettes."
        ),
        "portals": (
            "Make transition landmarks ominous and forceful, with supernatural pressure and "
            "controlled signs of conflict."
        ),
        "hard_exclusions": (
            "Every figure has mature adult facial proportions, tailored securely arranged "
            "clothing, intact bodies, outward-directed gestures, original designs, and a clean "
            "unlettered presentation."
        ),
    }


def _world_payload() -> dict[str, object]:
    body_plans = (
        "humanoid biped",
        "quadruped wolf",
        "winged avian",
        "serpentine snake",
        "insectoid mantis",
        "crablike crustacean",
        "spectral wraith",
        "amorphous ooze",
    )
    return {
        "world": {
            "name": "Moonlit Court",
            "one_liner": "A tense rooftop crossing.",
            "narrative": "Investigators cross a haunted garden.",
        },
        "mobs": [
            {
                "tier_label": f"foe-{index}",
                "body_plan": body_plan,
                "name": f"Foe {index}",
                "brief": "A distinct supernatural opponent.",
            }
            for index, body_plan in enumerate(body_plans)
        ],
        "obstacles": [
            {
                "sheet_theme": f"courtyard set {sheet}",
                "props": [
                    {"name": f"Prop {sheet}-{index}", "brief": "Readable broken cover."}
                    for index in range(8)
                ],
            }
            for sheet in range(3)
        ],
        "items": [
            {"kind": kind, "name": kind.title(), "brief": "A distinct collectible."}
            for kind in ("key", "lantern", "map", "feather", "bell", "mask", "crystal", "compass")
        ],
        "layers": [
            {
                "id": "backdrop",
                "title": "Backdrop",
                "z_index": 0,
                "parallax": 0.0,
                "opaque": True,
                "paint_region": "full frame",
                "description": "Moonlit rooftop architecture.",
            },
            {
                "id": "near_foreground",
                "title": "Near Foreground",
                "z_index": 1,
                "parallax": 1.8,
                "opaque": False,
                "paint_region": "screen edges",
                "description": "Sparse garden silhouettes.",
            },
        ],
    }


def _village_payload() -> dict[str, object]:
    """A roster a provider could plausibly return, satisfying every distinguishability rule.

    The four body plans are deliberately different anatomies rather than four aprons on one
    human: the schema refuses a plan that names no anatomy and refuses two consecutive plans that
    match, so a payload built any other way would test the validator instead of the stage.
    """

    residents = (
        ("Provisioner", "Bela Ash", "stocky humanoid"),
        ("Toolwright", "Oro Kem", "tall bipedal"),
        ("Archivist", "Sable Wren", "winged avian"),
        ("Ferrier", "Tomas Reed", "reptilian lizard"),
    )
    fixtures = (
        "Awning stall",
        "Stone well",
        "Notice post",
        "Hand cart",
        "Drying rack",
        "Rope winch",
        "Grain bin",
        "Lamp post",
    )
    return {
        "name": "Kettlebrook",
        "one_liner": "A quiet crossing where nothing is hunted.",
        "narrative": "Four trades share one square between the ridges.",
        "fixtures_theme": "riverside market furniture",
        "npcs": [
            {
                "role_label": role_label,
                "name": name,
                "body_plan": body_plan,
                "brief": f"Original townsfolk direction for {name}.",
                "greeting": f"{name} greets you.",
                "remark": f"{name} mentions the weather.",
                "farewell": f"{name} says goodbye.",
            }
            for role_label, name, body_plan in residents
        ],
        "fixtures": [
            {"name": name, "brief": f"A readable isolated {name.lower()}."} for name in fixtures
        ],
    }


class _RecordingStructuredBackend:
    provider = "fake-structured"
    model = "text-model"
    secrets: tuple[str, ...] = ()

    def __init__(
        self,
        *,
        fail_first_theme: bool = False,
        world_payload: dict[str, object] | None = None,
        village_payload: dict[str, object] | None = None,
        style_mode: str = "cel_shaded_anime_2d",
    ) -> None:
        self.fail_first_theme = fail_first_theme
        self.world_payload = world_payload
        self.village_payload = village_payload
        self.style_mode = style_mode
        self.theme_calls = 0
        self.style_calls = 0
        self.village_calls = 0
        self.requests: list[StructuredGenerationRequest[object]] = []

    async def generate_once(
        self, request: StructuredGenerationRequest[object]
    ) -> ProviderStructuredOutput:
        self.requests.append(request)
        if request.schema.name.startswith("stage_gen_theme_plan_v"):
            self.theme_calls += 1
            decoded: object = _compiled_plan()
            if self.fail_first_theme and self.theme_calls == 1:
                decoded = {**_compiled_plan(), "concept": "Use level 4 treatment."}
        elif request.schema.name == IMAGE_STYLE_SELECTION_SCHEMA:
            self.style_calls += 1
            decoded = {
                "schema_version": 1,
                "kind": "image_style_selection_v1",
                "style_mode": self.style_mode,
            }
        elif request.schema.name == VILLAGE_SPEC_SCHEMA_NAME:
            # Answered here rather than through a second fake backend so a village run exercises
            # the identical transport, decoding and retry owner the world bible does. The two
            # bibles are different schemas, never different providers.
            self.village_calls += 1
            decoded = json.loads(json.dumps(self.village_payload or _village_payload()))
        else:
            decoded = json.loads(json.dumps(self.world_payload or _world_payload()))
        return ProviderStructuredOutput(
            decoded=decoded,
            raw_text=json.dumps(decoded),
            response_metadata=ProviderResponseMetadata(
                request_id=f"structured-{len(self.requests)}"
            ),
        )

    async def aclose(self) -> None:
        return None


class _SequencedBackgroundBackend:
    provider = "fake-remover"
    model = "removal-model"
    secrets: tuple[str, ...] = ()

    def __init__(self, outputs: tuple[bytes, ...]) -> None:
        if not outputs:
            raise ValueError("outputs must be non-empty")
        self.outputs = outputs
        self.calls = 0
        self.requests: list[BackgroundRemovalRequest] = []

    async def remove_once(self, request: BackgroundRemovalRequest) -> ProviderBackgroundRemoval:
        self.requests.append(request)
        data = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        return ProviderBackgroundRemoval(
            data=data,
            media_type="image/png",
            source_url="https://example.invalid/removed.png",
            source_kind="test",
            response_metadata=ProviderResponseMetadata(request_id=f"remove-{self.calls}"),
            width=2,
            height=2,
        )

    async def aclose(self) -> None:
        return None


class _SequencedImageBackend:
    provider = "fake-image"
    model = "image-model"
    secrets: tuple[str, ...] = ()

    def __init__(self, outputs: tuple[bytes, ...]) -> None:
        self.outputs = outputs
        self.calls = 0
        self.requests: list[ImageGenerationRequest] = []

    async def generate_once(self, request: ImageGenerationRequest) -> ProviderImage:
        self.requests.append(request)
        data = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        return ProviderImage(
            data=data,
            media_type="image/png",
            response_metadata=ProviderResponseMetadata(request_id=f"image-{self.calls}"),
        )

    async def aclose(self) -> None:
        return None


class _TilesetFallbackImageBackend:
    provider = "fake-image"
    model = "image-model"
    secrets: tuple[str, ...] = ()

    def __init__(
        self,
        *,
        invalid_material_role: str | None = None,
        cap_needs_lightness_recovery: bool = False,
        cap_needs_global_gamut_recovery: bool = False,
    ) -> None:
        self.invalid_material_role = invalid_material_role
        self.cap_needs_lightness_recovery = cap_needs_lightness_recovery
        self.cap_needs_global_gamut_recovery = cap_needs_global_gamut_recovery
        self.calls = 0
        self.requests: list[ImageGenerationRequest] = []

    async def generate_once(self, request: ImageGenerationRequest) -> ProviderImage:
        self.requests.append(request)
        self.calls += 1
        stage = str(request.metadata.get("stage"))
        if stage == "tileset":
            data = _tileset_cross_seam_source()
        elif stage.startswith("tileset-material-"):
            role = stage.removeprefix("tileset-material-")
            if role == self.invalid_material_role:
                data = _flat_material_source()
            elif self.cap_needs_global_gamut_recovery:
                data = _tileset_material_source(f"global-recoverable-{role}")
            elif role == "cap" and self.cap_needs_lightness_recovery:
                # This is an otherwise-valid linked material with sub-contract
                # CAP/FILL luminance separation, matching the live retry shape.
                data = _tileset_material_source("recoverable-cap")
            else:
                data = _tileset_material_source(role)
        else:
            raise AssertionError(f"unexpected image stage: {stage}")
        return ProviderImage(
            data=data,
            media_type="image/png",
            response_metadata=ProviderResponseMetadata(request_id=f"image-{self.calls}"),
        )

    async def aclose(self) -> None:
        return None


class _PerCellOversizeImageBackend:
    provider = "fake-image"
    model = "image-model"
    secrets: tuple[str, ...] = ()

    def __init__(
        self,
        *,
        parent_stage: str = "items",
        oversize_index: int = 5,
        border_noise_index: int | None = None,
        parent_width: int = 160,
        parent_height: int = 80,
    ) -> None:
        self.parent_stage = parent_stage
        self.adapter = "items-v1" if parent_stage == "items" else "obstacles-v1"
        self.oversize_index = oversize_index
        self.border_noise_index = border_noise_index
        self.parent_width = parent_width
        self.parent_height = parent_height
        self.calls = 0
        self.requests: list[ImageGenerationRequest] = []

    async def generate_once(self, request: ImageGenerationRequest) -> ProviderImage:
        self.requests.append(request)
        self.calls += 1
        stage = str(request.metadata.get("stage"))
        if stage == self.parent_stage:
            data = _grid_source(
                cross_seam=True,
                width=self.parent_width,
                height=self.parent_height,
            )
        elif stage == f"per-cell-{self.adapter}-{self.oversize_index}":
            data = _isolated_cell_source(
                width=600,
                height=400,
                height_fraction=0.8 if self.border_noise_index is not None else 0.755,
                border_noise=self.border_noise_index == self.oversize_index,
            )
        elif stage.startswith(f"per-cell-{self.adapter}-"):
            data = _isolated_cell_source(width=600, height=400)
        else:
            raise AssertionError(f"unexpected image stage: {stage}")
        return ProviderImage(
            data=data,
            media_type="image/png",
            response_metadata=ProviderResponseMetadata(request_id=f"image-{self.calls}"),
        )

    async def aclose(self) -> None:
        return None


class _PerCellAlphaBackgroundBackend:
    provider = "fake-remover"
    model = "removal-model"
    secrets: tuple[str, ...] = ()

    def __init__(self, *, parent_stage: str = "items") -> None:
        self.parent_stage = parent_stage
        self.calls = 0
        self.requests: list[BackgroundRemovalRequest] = []

    async def remove_once(self, request: BackgroundRemovalRequest) -> ProviderBackgroundRemoval:
        self.requests.append(request)
        self.calls += 1
        stage = str(request.metadata.get("stage"))
        fraction = 0.755 if stage.endswith("-5") else 0.55
        data = _isolated_alpha(
            width=40,
            height=40,
            height_fraction=fraction,
            bottom_anchor=self.parent_stage.startswith("obstacles-"),
        )
        return ProviderBackgroundRemoval(
            data=data,
            media_type="image/png",
            source_url="https://example.invalid/removed.png",
            source_kind="test",
            response_metadata=ProviderResponseMetadata(request_id=f"remove-{self.calls}"),
            width=40,
            height=40,
        )

    async def aclose(self) -> None:
        return None


def _retrying_background(
    outputs: tuple[bytes, ...],
) -> tuple[BackgroundRemovalService, _SequencedBackgroundBackend]:
    backend = _SequencedBackgroundBackend(outputs)
    service = BackgroundRemovalService(
        cast(BackgroundRemovalBackend, backend),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    return service, backend


def _grid_source(
    *,
    missing_last: bool = False,
    gutter_contact: bool = False,
    cross_seam: bool = False,
    width: int = 160,
    height: int = 80,
) -> bytes:
    image = Image.new("RGB", (width, height), (128, 128, 128))
    draw = ImageDraw.Draw(image)
    cell_width = width // 4
    cell_height = height // 2
    for row in range(2):
        for column in range(4):
            if missing_last and (row, column) == (1, 3):
                continue
            draw.rectangle(
                (
                    column * cell_width + cell_width // 4,
                    row * cell_height + cell_height // 4,
                    column * cell_width + cell_width * 3 // 4 - 1,
                    row * cell_height + cell_height * 3 // 4 - 1,
                ),
                fill=(20 + column * 20, 30 + row * 20, 230),
            )
    if gutter_contact:
        image.putpixel((cell_width, cell_height // 4), (220, 40, 20))
    if cross_seam:
        image.putpixel((cell_width - 1, cell_height // 4), (220, 40, 20))
        image.putpixel((cell_width, cell_height // 4), (220, 40, 20))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _continuous_grid_source(*, width: int = 160, height: int = 80) -> bytes:
    image = Image.new("RGB", (width, height), (128, 128, 128))
    ImageDraw.Draw(image).rectangle(
        (0, height // 4, width - 1, height * 3 // 4),
        fill=(20, 90, 220),
    )
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@lru_cache(maxsize=1)
def _tileset_cross_seam_source() -> bytes:
    image = Image.new("RGB", (2400, 800), (128, 128, 128))
    draw = ImageDraw.Draw(image)
    for row in range(4):
        for column in range(12):
            left = column * 200
            top = row * 200
            draw.rectangle(
                (left + 20, top + 20, left + 179, top + 179),
                fill=(20 + column * 3, 60 + row * 5, 220),
            )
    draw.rectangle((179, 96, 220, 104), fill=(20, 60, 220))
    return _image_bytes(image)


@lru_cache(maxsize=3)
def _tileset_material_source(role: str) -> bytes:
    palettes = {
        "fill": (
            (142, 99, 54),
            (126, 84, 46),
            (156, 112, 66),
            (112, 76, 50),
        ),
        "cap": (
            (180, 190, 76),
            (156, 170, 62),
            (204, 205, 102),
            (139, 153, 66),
        ),
        "recoverable-cap": (
            (135, 130, 52),
            (117, 116, 43),
            (151, 141, 66),
            (101, 105, 43),
        ),
        "global-recoverable-cap": (
            (54, 111, 252),
            (67, 101, 227),
            (65, 137, 255),
            (69, 88, 207),
        ),
        "global-recoverable-fill": (
            (39, 113, 236),
            (52, 100, 210),
            (52, 146, 254),
            (54, 85, 190),
        ),
        "global-recoverable-edge": (
            (20, 75, 165),
            (30, 65, 145),
            (38, 100, 190),
            (32, 50, 115),
        ),
        "edge": (
            (20, 35, 30),
            (30, 50, 40),
            (70, 90, 65),
            (45, 65, 50),
        ),
    }
    palette = palettes[role]
    image = Image.new("RGB", (1024, 1024))
    pixels = image.load()
    assert pixels is not None
    for y in range(1024):
        for x in range(1024):
            pixels[x, y] = palette[((x // 64) + (y // 64) * 3 + (x // 256)) % len(palette)]
    return _image_bytes(image)


@lru_cache(maxsize=1)
def _flat_material_source() -> bytes:
    return _image_bytes(Image.new("RGB", (1024, 1024), (120, 90, 60)))


def _turnaround_source(*, cross_seam: bool = False, missing_last: bool = False) -> bytes:
    image = Image.new("RGB", (240, 80), (128, 128, 128))
    draw = ImageDraw.Draw(image)
    for column in range(3):
        if missing_last and column == 2:
            continue
        draw.rectangle(
            (column * 80 + 20, 12, column * 80 + 59, 67),
            fill=(40 + column * 30, 90, 180),
        )
    if cross_seam:
        image.putpixel((79, 40), (220, 40, 20))
        image.putpixel((80, 40), (220, 40, 20))
    return _image_bytes(image)


def _isolated_view_source(
    *,
    edge_contact: bool = False,
    border_noise: bool = False,
) -> bytes:
    image = Image.new("RGB", (80, 80), (255, 0, 255))
    bounds = (0, 8, 50, 71) if edge_contact else (24, 8, 55, 71)
    ImageDraw.Draw(image).rectangle(bounds, fill=(30, 110, 210))
    if border_noise:
        # Opaque-source validation treats these as background. Chroma-keying exposes the same
        # two isolated corner pixels seen in the live run. The deviation is blue-only so it
        # stays near the key in luminance while clearing the matte's minimum-coverage floor,
        # which absorbs fainter speckle before the cleanup stage ever sees it.
        image.putpixel((0, 79), (255, 0, 200))
        image.putpixel((79, 79), (255, 0, 200))
    return _image_bytes(image)


def _isolated_cell_source(
    *,
    width: int = 40,
    height: int = 40,
    height_fraction: float = 0.55,
    edge_contact: bool = False,
    border_noise: bool = False,
) -> bytes:
    image = Image.new("RGB", (width, height), (255, 0, 255))
    left = 0 if edge_contact else width * 3 // 10
    right = width - left - 1
    subject_height = round(height * height_fraction)
    top = (height - subject_height) // 2
    bottom = top + subject_height - 1
    ImageDraw.Draw(image).rectangle((left, top, right, bottom), fill=(30, 110, 210))
    if border_noise:
        # The opaque-source luminance threshold ignores this subtle blue-only deviation, while
        # chroma distance correctly exposes one alpha pixel. Blue carries the least luminance
        # weight, so this stays nearer the key in luminance than a red-only deviation while
        # clearing the matte's minimum-coverage floor and reaching the cleanup stage.
        image.putpixel((0, height - 1), (255, 0, 200))
    return _image_bytes(image)


def _isolated_alpha(
    *,
    width: int,
    height: int,
    height_fraction: float,
    bottom_anchor: bool,
) -> bytes:
    image = Image.new("RGBA", (width, height), (30, 110, 210, 0))
    subject_height = round(height * height_fraction)
    bottom = height - 4 if bottom_anchor else (height + subject_height) // 2
    top = bottom - subject_height
    ImageDraw.Draw(image).rectangle(
        (width * 3 // 10, top, width * 7 // 10 - 1, bottom - 1),
        fill=(30, 110, 210, 255),
    )
    return _image_bytes(image)


def _per_cell_fallback_spec(
    tmp_path: Path,
    *,
    stage: str = "items",
    width: int = 160,
    height: int = 80,
) -> _ImageSpec:
    tag = "offline"
    world = _minimal_world()
    (tmp_path / f"world_spec_{tag}.json").write_text(json.dumps(world), encoding="utf-8")
    concept = tmp_path / f"concept_{tag}.png"
    concept.write_bytes(_isolated_view_source())
    concept_data = concept.read_bytes()
    concept_binding = {
        "role": "world-concept-style-reference",
        "path": concept.name,
        "sha256": sha256_hex(concept_data),
        "bytes": len(concept_data),
    }
    prompt = f"Eight declared assets for {stage}."
    references: tuple[Path, ...]
    if stage == "items":
        sources = cast(list[dict[str, object]], world["items"])
        references = (concept,)
        bindings: tuple[Mapping[str, object], ...] = (concept_binding,)
        identity_policy = "independent-distinct-items"
        sheet_theme = None
        output = tmp_path / f"items_{tag}.png"
    else:
        prior = tmp_path / "obstacle_template.png"
        prior.write_bytes(_grid_source())
        prior_data = prior.read_bytes()
        prior_binding = {
            "role": "obstacle-layout-prior",
            "path": prior.name,
            "sha256": sha256_hex(prior_data),
            "bytes": len(prior_data),
        }
        obstacle = cast(list[dict[str, object]], world["obstacles"])[0]
        sources = cast(list[dict[str, object]], obstacle["props"])
        references = (prior, concept)
        bindings = (prior_binding, concept_binding)
        identity_policy = "cell-0-scale-style-anchor"
        sheet_theme = str(obstacle["sheet_theme"])
        output = tmp_path / f"obstacles_{tag}_0.png"
    parent_contract = executor_module._per_cell_parent_contract(
        stage=stage,
        prompt=prompt,
        source_specs=sources,
        reference_bindings=bindings,
        identity_policy=identity_policy,
        sheet_theme=sheet_theme,
    )
    return _ImageSpec(
        stage,
        prompt,
        output,
        width,
        height,
        references=references,
        metadata={
            **({"sheet_theme": sheet_theme, "slot": 0} if sheet_theme is not None else {}),
            "per_cell_generation_contract": parent_contract,
        },
    )


def _typed_per_cell_failure_history() -> list[dict[str, object]]:
    failures = (
        (GRID_ISOLATION_ERROR_CODE, None, None),
        (GRID_EMPTY_CELL_ERROR_CODE, 0, 1),
        (GRID_UNIFORM_SOURCE_ERROR_CODE, None, None),
        (GRID_ISOLATION_ERROR_CODE, None, None),
        (GRID_EMPTY_CELL_ERROR_CODE, 1, 3),
        (GRID_UNIFORM_SOURCE_ERROR_CODE, None, None),
    )
    history: list[dict[str, object]] = []
    for attempt, (code, row, column) in enumerate(failures, start=1):
        failure: dict[str, object] = {
            "attempt": attempt,
            "code": code,
            "message": f"{code}: layout failure on attempt {attempt}",
        }
        if row is not None and column is not None:
            failure.update({"row": row, "column": column})
        history.append(failure)
    return history


def _typed_tileset_failure_history() -> list[dict[str, object]]:
    return [
        {
            "attempt": attempt,
            "code": GRID_ISOLATION_ERROR_CODE,
            "message": (
                f"{GRID_ISOLATION_ERROR_CODE}: grid source has a connected foreground "
                f"component spanning declared cells: vertical seam {attempt}"
            ),
        }
        for attempt in range(1, 7)
    ]


def _concept_fallback_spec(
    tmp_path: Path,
    reference: Path,
    *,
    stage: str = "mob-concept-0",
) -> _ImageSpec:
    prompt = executor_module._turnaround_prompt("Creature guardian")
    reference_data = reference.read_bytes()
    binding = {
        "role": "world-concept-style-reference",
        "path": reference.name,
        "sha256": sha256_hex(reference_data),
        "bytes": len(reference_data),
    }
    return _ImageSpec(
        stage,
        prompt,
        tmp_path / "mob_concept_offline_0.png",
        240,
        80,
        references=(reference,),
        metadata={
            "turnaround_prompt_reference_contract": (
                executor_module._turnaround_prompt_reference_contract(
                    prompt,
                    reference_bindings=(binding,),
                )
            )
        },
    )


def _wrong_role_tileset_source() -> bytes:
    contract = contract_for_stage("tileset")
    assert contract is not None
    canonical, _facts = normalize_canonical_grid(
        _image_bytes(Image.new("RGBA", (240, 80), (40, 120, 180, 255))),
        contract,
    )
    with Image.open(BytesIO(canonical)) as opened:
        template = opened.convert("RGBA")
    source = Image.new("RGB", template.size, (128, 128, 128))
    source.paste(template.convert("RGB"), mask=template.getchannel("A"))
    draw = ImageDraw.Draw(source)
    draw.rectangle((0, 40, 19, 59), fill=(128, 128, 128))
    draw.rectangle((2, 42, 17, 57), fill=(40, 120, 180))
    return _image_bytes(source)


def _write_raw_pair(raw_path: Path) -> bytes:
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
    return raw


def _write_grid_raw_pair(raw_path: Path) -> bytes:
    raw = _grid_source()
    write_artifact_with_provenance(
        raw_path,
        BinaryArtifact(data=raw, media_type="image/png"),
        ProvenanceInput(
            provider="fake-image",
            model="image-model",
            prompt="grid prompt",
            params={"metadata": {"stage": "items", "transparency_mode": "ai"}},
            validation={
                "exact_contract_dimensions": True,
                "output_width": 160,
                "output_height": 80,
            },
            attempts=1,
        ),
    )
    return raw


def _grid_alpha(*, missing_last: bool = False) -> bytes:
    image = Image.new("RGBA", (160, 80), (20, 30, 230, 0))
    draw = ImageDraw.Draw(image)
    for row in range(2):
        for column in range(4):
            if missing_last and (row, column) == (1, 3):
                continue
            draw.rectangle(
                (column * 40 + 10, row * 40 + 10, column * 40 + 29, row * 40 + 29),
                fill=(20, 30, 230, 255),
            )
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _executor(
    *, background: _FakeBackgroundService | BackgroundRemovalService | None = None
) -> ScrollingPreviewExecutor:
    return ScrollingPreviewExecutor(
        image_service=cast(ImageGenerationService, _FakeImageService()),
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
        background_service=(
            cast(BackgroundRemovalService, background) if background is not None else None
        ),
    )


@pytest.mark.parametrize(
    ("canvas", "expected"),
    [
        ((100, 100), "1:1"),
        ((300, 200), "3:2"),
        ((200, 300), "2:3"),
        ((400, 300), "4:3"),
        ((300, 400), "3:4"),
        ((1600, 900), "16:9"),
        ((900, 1600), "9:16"),
        ((2100, 900), "21:9"),
        ((2400, 800), "21:9"),
        ((2048, 1024), "16:9"),
        ((256, 1024), "9:16"),
    ],
)
def test_provider_aspect_ratio_uses_verified_values(canvas: tuple[int, int], expected: str) -> None:
    assert executor_module._provider_aspect_ratio(*canvas) == expected


def test_provider_aspect_ratio_rejects_unverified_ratio() -> None:
    with pytest.raises(ValueError, match="has no verified provider aspect ratio"):
        executor_module._provider_aspect_ratio(5, 2)


def test_transparent_parallax_prompt_requires_sparse_uniform_background() -> None:
    layer = WorldLayer(
        id="foreground_canopy_floral",
        title="Foreground Canopy Floral",
        z_index=4,
        parallax=1.4,
        opaque=False,
        paint_region="screen edges and near foreground",
        description="Deep foliage, tree limbs, flowers, and mushrooms framing the scene.",
    )

    prompt = executor_module._prompt_for_transparency(
        executor_module._parallax_layer_prompt(layer), TransparencyMode.AI
    )

    assert layer.description in prompt
    assert f"Paint region: {layer.paint_region}." in prompt
    assert "sparse, isolated foreground framing elements" in prompt
    assert "perfectly uniform neutral-grey background" in prompt
    assert "large connected background areas and generous negative space" in prompt
    assert "Do not fill the full frame or create an edge-to-edge scene" in prompt
    assert "#FF00FF" not in prompt


@pytest.mark.parametrize(
    ("layer_id", "z_index", "parallax", "required", "forbidden"),
    [
        (
            "middle_vale",
            2,
            0.65,
            "gentle rolling silhouettes and small distributed foliage",
            "houses, bridges, castles, large trees",
        ),
        (
            "near_foreground",
            4,
            1.8,
            "small foliage silhouettes, short stems, and small leaves",
            "large flowers, rocks, trunks, arches",
        ),
    ],
)
def test_scrolling_repeat_layers_shape_low_salience_source_inputs(
    layer_id: str,
    z_index: int,
    parallax: float,
    required: str,
    forbidden: str,
) -> None:
    layer = WorldLayer(
        id=layer_id,
        title=layer_id.replace("_", " ").title(),
        z_index=z_index,
        parallax=parallax,
        opaque=False,
        paint_region="lower band",
        description="A moving scene layer.",
    )

    prompt = executor_module._parallax_layer_prompt(layer)

    assert "INPUT SHAPE FOR HORIZONTAL REPEAT" in prompt
    assert "both horizontal end bands quiet and similarly sparse" in prompt
    assert required in prompt
    assert forbidden in prompt


async def test_theme_compile_retries_resumes_and_binds_exact_request_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _RecordingStructuredBackend(fail_first_theme=True)
    structured = StructuredGenerationService[object](
        backend,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    executor = ScrollingPreviewExecutor(
        image_service=cast(ImageGenerationService, _FakeImageService()),
        structured_service=structured,
    )
    context = StageContext(
        input={"prompt": "moonlit gothic court", "theme": {"hostile_action": 4}},
        tag="themed-chroma",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.CHROMA),
    )

    first = await executor.run_scrolling_preview_stage("theme-compile", context)
    assert backend.theme_calls == 2
    assert Path(first[0]).name == "theme_plan_themed-chroma.json"
    await executor.run_scrolling_preview_stage("theme-compile", context)
    assert backend.theme_calls == 2

    sidecar_path = Path(first[1])
    sidecar = json.loads(await asyncio.to_thread(sidecar_path.read_text, encoding="utf-8"))
    assert sidecar["attempts"] == 2
    assert sidecar["params"]["metadata"]["theme_compiler_version"] == THEME_COMPILER_VERSION
    skill = load_theme_compiler_skill()
    assert sidecar["params"]["metadata"]["theme_skill_name"] == skill.name
    assert sidecar["params"]["metadata"]["theme_skill_sha256"] == skill.sha256
    assert sidecar["params"]["metadata"]["canonical_theme_json"] == canonical_theme_json(
        ThemeHandles(hostile_action=4)
    )

    sidecar["prompt"] = "stale compiler prompt"
    await asyncio.to_thread(sidecar_path.write_text, json.dumps(sidecar), encoding="utf-8")
    await executor.run_scrolling_preview_stage("theme-compile", context)
    assert backend.theme_calls == 3

    sidecar = json.loads(await asyncio.to_thread(sidecar_path.read_text, encoding="utf-8"))
    sidecar["params"]["schema_name"] = "stale_schema"
    await asyncio.to_thread(sidecar_path.write_text, json.dumps(sidecar), encoding="utf-8")
    await executor.run_scrolling_preview_stage("theme-compile", context)
    assert backend.theme_calls == 4

    sidecar = json.loads(await asyncio.to_thread(sidecar_path.read_text, encoding="utf-8"))
    sidecar["params"]["metadata"]["theme_skill_sha256"] = "0" * 64
    await asyncio.to_thread(sidecar_path.write_text, json.dumps(sidecar), encoding="utf-8")
    await executor.run_scrolling_preview_stage("theme-compile", context)
    assert backend.theme_calls == 5

    sidecar = json.loads(await asyncio.to_thread(sidecar_path.read_text, encoding="utf-8"))
    sidecar["params"]["metadata"]["theme_compiler_version"] = -1
    await asyncio.to_thread(sidecar_path.write_text, json.dumps(sidecar), encoding="utf-8")
    await executor.run_scrolling_preview_stage("theme-compile", context)
    assert backend.theme_calls == 6

    monkeypatch.setenv("STAGE_GEN_FORCE", "1")
    await executor.run_scrolling_preview_stage("theme-compile", context)
    assert backend.theme_calls == 7

    monkeypatch.delenv("STAGE_GEN_FORCE")
    await asyncio.to_thread(sidecar_path.unlink)
    await executor.run_scrolling_preview_stage("theme-compile", context)
    assert backend.theme_calls == 8


@pytest.mark.parametrize(
    "style_mode",
    [
        "cel_shaded_anime_2d",
        "gouache_illustration_2d",
        "photorealistic_natural",
    ],
)
async def test_style_select_materializes_only_approved_modes_and_resumes(
    tmp_path: Path,
    style_mode: str,
) -> None:
    backend = _RecordingStructuredBackend(style_mode=style_mode)
    executor = ScrollingPreviewExecutor(
        image_service=cast(ImageGenerationService, _FakeImageService()),
        structured_service=StructuredGenerationService[object](backend),
    )
    context = StageContext(
        input={
            "prompt": "original lantern forest",
            "style_anchor": {
                "schema_version": 1,
                "kind": "automatic_style_anchor_v1",
            },
        },
        tag="styled-v1",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.CHROMA),
    )

    first = await executor.run_scrolling_preview_stage("style-select", context)
    await executor.run_scrolling_preview_stage("style-select", context)

    assert backend.style_calls == 1
    anchor = json.loads(await asyncio.to_thread(Path(first[0]).read_text, encoding="utf-8"))
    assert anchor["style_mode"] == style_mode
    sidecar_path = Path(first[1])
    sidecar = json.loads(await asyncio.to_thread(sidecar_path.read_text, encoding="utf-8"))
    assert sidecar["params"]["metadata"]["resource_sha256"] == anchor["resource_sha256"]
    sidecar["params"]["metadata"]["resource_sha256"] = "0" * 64
    await asyncio.to_thread(sidecar_path.write_text, json.dumps(sidecar), encoding="utf-8")
    await executor.run_scrolling_preview_stage("style-select", context)
    assert backend.style_calls == 2


async def test_enabled_style_anchor_reaches_every_scrolling_image_asset_family_once(
    tmp_path: Path,
) -> None:
    backend = _RecordingStructuredBackend(style_mode="gouache_illustration_2d")
    images = _FakeImageService()
    executor = ScrollingPreviewExecutor(
        image_service=cast(ImageGenerationService, images),
        structured_service=StructuredGenerationService[object](backend),
    )
    context = StageContext(
        input={
            "prompt": "original lantern forest",
            "style_anchor": {
                "schema_version": 1,
                "kind": "automatic_style_anchor_v1",
            },
        },
        tag="styled-v1",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.CHROMA),
    )
    await executor.run_scrolling_preview_stage("style-select", context)
    representatives = {
        "concept": "concept_art",
        "layer-backdrop": "environment_background",
        "character-attack": "character_sprite",
        "free-illustration": "illustration",
        "ladder": "asset_sheet",
        "tileset-material-probe": "tileable_texture",
        "inventory": "interface_art",
        "portal": "effect_sheet",
    }
    for stage in representatives:
        await executor._generate_image_asset(
            context,
            _ImageSpec(
                stage,
                f"Prompt for {stage}.",
                tmp_path / f"{stage}.png",
                240,
                80,
                transparent=False,
            ),
        )

    assert [request.asset_kind for request in images.requests] == list(representatives.values())
    assert all(request.style_anchor is not None for request in images.requests)
    assert all("Canonical style anchor" not in request.prompt for request in images.requests)
    assert all(
        cast(Mapping[str, object], request.metadata["style_anchor"])["style_mode"]
        == "gouache_illustration_2d"
        for request in images.requests
    )


async def test_style_selection_sees_compiled_prose_without_raw_theme_controls(
    tmp_path: Path,
) -> None:
    backend = _RecordingStructuredBackend()
    executor = ScrollingPreviewExecutor(
        image_service=cast(ImageGenerationService, _FakeImageService()),
        structured_service=StructuredGenerationService[object](backend),
    )
    context = StageContext(
        input={
            "prompt": "original moonlit court",
            "theme": {"hostile_action": 4},
            "style_anchor": {
                "schema_version": 1,
                "kind": "automatic_style_anchor_v1",
            },
        },
        tag="themed-styled-v1",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.CHROMA),
    )
    await executor.run_scrolling_preview_stage("theme-compile", context)
    await executor.run_scrolling_preview_stage("style-select", context)
    request = next(
        request
        for request in backend.requests
        if request.schema.name == IMAGE_STYLE_SELECTION_SCHEMA
    )
    assert _compiled_plan()["concept"] in request.prompt
    assert raw_theme_control_leaks(request.prompt) == ()
    assert "hostile_action" not in request.prompt


async def test_style_select_rejects_unknown_model_selection(tmp_path: Path) -> None:
    backend = _RecordingStructuredBackend(style_mode="invented_mode")
    executor = ScrollingPreviewExecutor(
        image_service=cast(ImageGenerationService, _FakeImageService()),
        structured_service=StructuredGenerationService[object](
            backend,
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ),
    )
    context = StageContext(
        input={
            "prompt": "original lantern forest",
            "style_anchor": {
                "schema_version": 1,
                "kind": "automatic_style_anchor_v1",
            },
        },
        tag="styled-v1",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.CHROMA),
    )

    with pytest.raises(RetryExhaustedError):
        await executor.run_scrolling_preview_stage("style-select", context)
    assert backend.style_calls == 6


async def test_compiled_theme_prose_reaches_planner_and_image_stages_without_raw_controls(
    tmp_path: Path,
) -> None:
    backend = _RecordingStructuredBackend()
    structured = StructuredGenerationService[object](
        backend,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    images = _FakeImageService()
    executor = ScrollingPreviewExecutor(
        image_service=cast(ImageGenerationService, images),
        structured_service=structured,
    )
    handles = ThemeHandles(
        sexual_content=3,
        nudity_exposure=2,
        hostile_action=4,
        injury_detail=3,
        substance_depiction=2,
        threat_disturbance=4,
    )
    skill = load_theme_compiler_skill()
    raw_marker = "RAW_USER_MARKER_7C91D2"
    context = StageContext(
        input={
            "prompt": f"{raw_marker} moonlit gothic court",
            "theme": handles.model_dump(mode="json"),
        },
        tag="themed-chroma",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.CHROMA),
    )
    plan = CompiledThemePlan.model_validate(_compiled_plan())

    await executor.run_scrolling_preview_stage("theme-compile", context)
    compiler_request = next(
        request
        for request in backend.requests
        if request.schema.name.startswith("stage_gen_theme_plan_v")
    )
    assert raw_marker in compiler_request.prompt
    compiler_sidecar = json.loads(
        await asyncio.to_thread(
            Path(f"{executor_module._theme_plan_path(context)}.meta.json").read_text,
            encoding="utf-8",
        )
    )
    assert raw_marker in compiler_sidecar["prompt"]

    await executor.run_scrolling_preview_stage("concept", context)
    concept_request = images.requests[-1]
    assert concept_request.prompt.startswith(plan.concept)
    assert "Recipe composition:" in concept_request.prompt
    assert "Visible content direction:" not in concept_request.prompt
    assert "Binding visual constraints:" in concept_request.prompt
    assert "Binding exclusions:" not in concept_request.prompt
    assert "user_prompt" not in concept_request.metadata
    concept_sidecar_text = await asyncio.to_thread(
        (tmp_path / f"concept_{context.tag}.png.meta.json").read_text,
        encoding="utf-8",
    )
    assert raw_marker not in concept_sidecar_text
    assert plan.concept in concept_sidecar_text

    cases = {
        "layer-backdrop": plan.environment,
        "character-attack": plan.characters,
        "items": plan.items,
        "portal": plan.portals,
    }
    for stage, directive in cases.items():
        output = (
            tmp_path / f"concept_{context.tag}.png"
            if stage == "concept"
            else tmp_path / f"{stage}.png"
        )
        await executor._generate_image_asset(
            context,
            _ImageSpec(stage, f"Base prompt for {stage}.", output, 72, 36, transparent=False),
        )
        request = images.requests[-1]
        assert directive in request.prompt
        assert plan.hard_exclusions in request.prompt
        assert raw_theme_control_leaks(request.prompt) == ()
        rendered_request = json.dumps(
            {"prompt": request.prompt, "metadata": request.metadata}, ensure_ascii=False
        )
        assert canonical_theme_json(handles) not in rendered_request
        assert all(name not in rendered_request for name in ThemeHandles.model_fields)
        image_request_identity = request.metadata["theme_compilation"]
        assert isinstance(image_request_identity, Mapping)
        assert image_request_identity["compiler_version"] == THEME_COMPILER_VERSION
        assert image_request_identity["theme_skill_name"] == skill.name
        assert image_request_identity["theme_skill_sha256"] == skill.sha256

    assert all(
        raw_marker not in request.prompt
        and raw_marker not in json.dumps(request.metadata, ensure_ascii=False)
        for request in images.requests
    )

    await executor.run_scrolling_preview_stage("world-spec", context)
    world_request = next(
        request
        for request in backend.requests
        if request.schema.name == "scrolling_preview_world_spec"
    )
    assert plan.world_spec in world_request.prompt
    assert plan.hard_exclusions in world_request.prompt
    assert canonical_theme_json(handles) not in world_request.prompt
    world_identity = world_request.metadata["theme_compilation"]
    assert isinstance(world_identity, Mapping)
    assert str(world_identity["artifact_ref"]).startswith("sha256:")
    assert len(str(world_identity["artifact_sha256"])) == 64
    await executor.run_scrolling_preview_stage("world-spec", context)
    assert (
        sum(request.schema.name == "scrolling_preview_world_spec" for request in backend.requests)
        == 1
    )

    image_sidecar = json.loads(
        await asyncio.to_thread(
            (tmp_path / "items.png.meta.json").read_text,
            encoding="utf-8",
        )
    )
    assert (
        image_sidecar["params"]["metadata"]["theme_compilation"]
        == (images.requests[3].metadata["theme_compilation"])
    )
    assert "canonical_theme_json" not in json.dumps(image_sidecar)
    assert raw_marker not in json.dumps(image_sidecar)
    image_identity = image_sidecar["params"]["metadata"]["theme_compilation"]
    assert any(
        item["ref"] == image_identity["artifact_ref"]
        and item["sha256"] == image_identity["artifact_sha256"]
        and item["media_type"] == "application/json"
        for item in image_sidecar["inputs"]
    )
    assert executor_module._theme_identity_matches(image_sidecar, image_identity)
    assert not executor_module._theme_identity_matches(
        image_sidecar,
        {**image_identity, "artifact_sha256": "0" * 64},
    )


async def test_world_spec_canonicalizes_foreground_and_rejects_stale_cache(
    tmp_path: Path,
) -> None:
    payload = _world_payload()
    layers = payload["layers"]
    assert isinstance(layers, list)
    near = layers[-1]
    assert isinstance(near, dict)
    near["parallax"] = 1.2
    backend = _RecordingStructuredBackend(world_payload=payload)
    structured = StructuredGenerationService[object](
        backend,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    executor = ScrollingPreviewExecutor(
        image_service=cast(ImageGenerationService, object()),
        structured_service=structured,
    )
    context = StageContext(
        input={"prompt": "storybook"},
        tag="normalized-chroma",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.CHROMA),
    )
    concept = tmp_path / f"concept_{context.tag}.png"
    await asyncio.to_thread(concept.write_bytes, b"synthetic concept reference")

    await executor.run_scrolling_preview_stage("world-spec", context)

    output = tmp_path / f"world_spec_{context.tag}.json"
    sidecar_path = Path(f"{output}.meta.json")
    artifact = json.loads(await asyncio.to_thread(output.read_text, encoding="utf-8"))
    sidecar = json.loads(await asyncio.to_thread(sidecar_path.read_text, encoding="utf-8"))
    assert artifact["layers"][-1]["parallax"] == 1.8
    assert sidecar["validation"]["world_spec_normalization"] == {
        "version": "near-foreground-parallax-v1",
        "target_layer_id": "near_foreground",
        "target_z_index": 1,
        "input_parallax": 1.2,
        "output_parallax": 1.8,
        "changed": True,
        "changed_fields": ["layers[1].parallax"],
        "layer_ids": ["backdrop", "near_foreground"],
        "unchanged_layer_ids": ["backdrop"],
        "layer_order_preserved": True,
        "unrelated_layers_unchanged": True,
    }
    assert sidecar["validation"]["world_spec_final_validation"] is True
    assert len(backend.requests) == 1

    del sidecar["validation"]["world_spec_normalization"]
    await asyncio.to_thread(
        sidecar_path.write_text,
        json.dumps(sidecar),
        encoding="utf-8",
    )
    await executor.run_scrolling_preview_stage("world-spec", context)

    assert len(backend.requests) == 2


async def test_unset_theme_preserves_legacy_image_prompt_and_makes_no_structured_call(
    tmp_path: Path,
) -> None:
    images = _FakeImageService()
    executor = ScrollingPreviewExecutor(
        image_service=cast(ImageGenerationService, images),
        structured_service=cast(StructuredGenerationService[object], object()),
    )
    context = StageContext(
        input={"prompt": "offline"},
        tag="offline",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.CHROMA),
    )
    original_prompt = "  Original legacy prompt.  "

    await executor._generate_image_asset(
        context,
        _ImageSpec("opaque", original_prompt, tmp_path / "legacy.png", 2, 2, transparent=False),
    )

    assert images.requests[0].prompt == executor_module._prompt_for_transparency(
        original_prompt, None
    )
    assert "theme_compilation" not in images.requests[0].metadata
    assert "style_anchor" not in images.requests[0].metadata
    assert images.requests[0].style_anchor is None
    assert images.requests[0].asset_kind is None


async def test_unset_theme_preserves_legacy_concept_prompt_and_metadata(tmp_path: Path) -> None:
    images = _FakeImageService()
    executor = ScrollingPreviewExecutor(
        image_service=cast(ImageGenerationService, images),
        structured_service=cast(StructuredGenerationService[object], object()),
    )
    user_prompt = "Original legacy moonlit ruins"
    context = StageContext(
        input={"prompt": user_prompt},
        tag="legacy-concept",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.CHROMA),
    )

    await executor.run_scrolling_preview_stage("concept", context)

    assert images.requests[0].prompt == (
        "2D scrolling-game scene concept art, wide cinematic landscape view.\n"
        f"Theme: {user_prompt}.\n"
        "Compose clear distant, middle, and foreground depth. Hand-painted, fully opaque, "
        "without text or labels."
    )
    assert images.requests[0].metadata["user_prompt"] == user_prompt
    assert "theme_compilation" not in images.requests[0].metadata


async def test_final_theme_boundary_allows_ordinary_level_tier_and_rating_language(
    tmp_path: Path,
) -> None:
    backend = _RecordingStructuredBackend()
    structured = StructuredGenerationService[object](
        backend,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    images = _FakeImageService()
    executor = ScrollingPreviewExecutor(
        image_service=cast(ImageGenerationService, images),
        structured_service=structured,
    )
    context = StageContext(
        input={
            "prompt": "Level 4 dungeon beneath a five-star rating sign",
            "theme": {"hostile_action": 1},
        },
        tag="ordinary-themed",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.CHROMA),
    )
    await executor.run_scrolling_preview_stage("theme-compile", context)
    await executor.run_scrolling_preview_stage("concept", context)

    await executor._generate_image_asset(
        context,
        _ImageSpec(
            "mob-concept-0",
            "A Tier 1 guardian patrols the Level 4 dungeon; rating stars mark the doorway.",
            tmp_path / "ordinary.png",
            72,
            36,
            transparent=False,
            metadata={"tier_label": "Tier 1", "world_note": "Level 4 dungeon"},
        ),
    )

    assert len(images.requests) == 2
    concept_request, world_request = images.requests
    assert "Level 4 dungeon beneath a five-star rating sign" not in concept_request.prompt
    assert "user_prompt" not in concept_request.metadata
    assert _compiled_plan()["concept"] in concept_request.prompt
    assert "Binding visual constraints:" in concept_request.prompt
    assert raw_theme_control_leaks(concept_request.prompt) == ()
    assert "Tier 1 guardian" in world_request.prompt
    assert "Level 4 dungeon" in world_request.prompt
    assert raw_theme_control_leaks(world_request.prompt) == ()
    assert world_request.metadata["tier_label"] == "Tier 1"


@pytest.mark.parametrize(
    ("prompt", "metadata"),
    [
        ("sexual_content=4", None),
        ("Safe descriptive prompt.", {"hostile_action": 4}),
        ("Safe descriptive prompt.", {"violence": 4}),
        ("Safe descriptive prompt.", {"theme": {"threat_disturbance": 4}}),
    ],
)
async def test_final_theme_boundary_rejects_raw_controls_before_image_call(
    tmp_path: Path,
    prompt: str,
    metadata: dict[str, object] | None,
) -> None:
    backend = _RecordingStructuredBackend()
    structured = StructuredGenerationService[object](
        backend,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    images = _FakeImageService()
    executor = ScrollingPreviewExecutor(
        image_service=cast(ImageGenerationService, images),
        structured_service=structured,
    )
    context = StageContext(
        input={"prompt": "moonlit ruins", "theme": {"hostile_action": 2}},
        tag="raw-control",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.CHROMA),
    )
    await executor.run_scrolling_preview_stage("theme-compile", context)

    with pytest.raises(ValueError, match="image-bound prompt leaks raw theme controls"):
        await executor._generate_image_asset(
            context,
            _ImageSpec(
                "concept",
                prompt,
                tmp_path / "rejected.png",
                72,
                36,
                transparent=False,
                metadata=metadata,
            ),
        )

    assert images.requests == []


@pytest.mark.parametrize(
    ("stage", "field"),
    [
        ("concept", "concept"),
        ("layer-backdrop", "environment"),
        ("tileset", "environment"),
        ("obstacles-0", "items"),
        ("ladder", "items"),
        ("character-concept", "characters"),
        ("character-master-strip-idle", "characters"),
        ("character-attack", "characters"),
        ("character-climb", "characters"),
        ("mob-concept-0", "characters"),
        ("mob-idle-0", "characters"),
        ("mob-hurt-0", "characters"),
        ("items", "items"),
        ("inventory", "items"),
        ("portal", "portals"),
    ],
)
def test_every_image_stage_class_selects_its_compiled_directive(stage: str, field: str) -> None:
    plan = CompiledThemePlan.model_validate(_compiled_plan())

    assert executor_module._directive_for_image_stage(plan, stage) == getattr(plan, field)


@pytest.mark.parametrize(
    ("canvas", "provider_ratio"),
    [((2400, 800), "21:9"), ((2048, 1024), "16:9")],
)
async def test_provider_ratio_mapping_preserves_exact_normalized_canvas(
    tmp_path: Path, canvas: tuple[int, int], provider_ratio: str
) -> None:
    image_service = _FakeImageService()
    executor = ScrollingPreviewExecutor(
        image_service=cast(ImageGenerationService, image_service),
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    output = tmp_path / f"mapped-{canvas[0]}x{canvas[1]}.png"

    await executor._generate_image_asset(
        StageContext(
            input={"prompt": "offline"},
            tag="offline",
            run_dir=tmp_path,
            config=StageGenConfig(out_dir=tmp_path),
        ),
        _ImageSpec("mapped", "offline prompt", output, *canvas, transparent=False),
    )

    assert len(image_service.requests) == 1
    request = image_service.requests[0]
    assert request.aspect_ratio == provider_ratio
    assert request.metadata["requested_width"] == canvas[0]
    assert request.metadata["requested_height"] == canvas[1]
    with Image.open(output) as image:
        assert image.size == canvas
    sidecar = json.loads(await asyncio.to_thread(Path(f"{output}.meta.json").read_text))
    assert sidecar["validation"]["output_width"] == canvas[0]
    assert sidecar["validation"]["output_height"] == canvas[1]


async def test_turnaround_prompt_reference_contract_invalidates_only_concept_cache(
    tmp_path: Path,
) -> None:
    backend = _SequencedImageBackend((_turnaround_source(),))
    image_service = ImageGenerationService(
        cast(ImageGenerationBackend, backend),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    executor = ScrollingPreviewExecutor(
        image_service=image_service,
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    context = StageContext(
        input={"prompt": "offline"},
        tag="offline",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path),
    )
    reference = b"world concept reference"
    binding = {
        "role": "world-concept-style-reference",
        "path": "concept_offline.png",
        "sha256": sha256_hex(reference),
        "bytes": len(reference),
    }
    prompt = executor_module._turnaround_prompt("Creature guardian")

    def spec_for(value: str, *, reference_binding: Mapping[str, object] = binding) -> _ImageSpec:
        return _ImageSpec(
            "mob-concept-0",
            value,
            tmp_path / "mob_concept_offline_0.png",
            240,
            80,
            transparent=False,
            metadata={
                "turnaround_prompt_reference_contract": (
                    executor_module._turnaround_prompt_reference_contract(
                        value,
                        reference_bindings=(reference_binding,),
                    )
                )
            },
        )

    await executor._generate_image_asset(context, spec_for(prompt))
    await executor._generate_image_asset(context, spec_for(prompt))
    assert backend.calls == 1

    changed = f"{prompt}\nIdentity detail: chipped left horn."
    await executor._generate_image_asset(context, spec_for(changed))
    assert backend.calls == 2

    changed_reference = {
        **binding,
        "sha256": sha256_hex(b"updated world concept reference"),
        "bytes": len(b"updated world concept reference"),
    }
    await executor._generate_image_asset(
        context,
        spec_for(changed, reference_binding=changed_reference),
    )
    assert backend.calls == 3

    unrelated = _ImageSpec(
        "unrelated-opaque",
        "Unrelated opaque reference.",
        tmp_path / "unrelated.png",
        240,
        80,
        transparent=False,
    )
    await executor._generate_image_asset(context, unrelated)
    await executor._generate_image_asset(context, unrelated)
    assert backend.calls == 4


def test_per_cell_failure_history_accepts_six_typed_layout_failures() -> None:
    assert executor_module._valid_per_cell_failure_history(_typed_per_cell_failure_history())


def test_per_cell_failure_history_rejects_forged_or_incomplete_records() -> None:
    valid = _typed_per_cell_failure_history()

    def cloned() -> list[dict[str, object]]:
        return [dict(failure) for failure in valid]

    missing_code = cloned()
    missing_code[0].pop("code")
    missing_message = cloned()
    missing_message[0].pop("message")
    forged_message = cloned()
    forged_message[0]["message"] = f"{GRID_UNIFORM_SOURCE_ERROR_CODE}: forged diagnostic prefix"
    wrong_code = cloned()
    wrong_code[0].update(
        {
            "code": "scrolling-grid-unknown-v1",
            "message": "scrolling-grid-unknown-v1: unsupported layout failure",
        }
    )
    missing_empty_coordinate = cloned()
    missing_empty_coordinate[1].pop("column")
    invalid_empty_coordinate = cloned()
    invalid_empty_coordinate[1]["row"] = 2
    boolean_empty_coordinate = cloned()
    boolean_empty_coordinate[1]["column"] = False
    forged_cross_coordinates = cloned()
    forged_cross_coordinates[0].update({"row": 0, "column": 0})

    invalid_histories: dict[str, object] = {
        "missing-code": missing_code,
        "missing-message": missing_message,
        "forged-message": forged_message,
        "wrong-count": valid[:-1],
        "wrong-order": [valid[1], valid[0], *valid[2:]],
        "wrong-code": wrong_code,
        "missing-empty-coordinate": missing_empty_coordinate,
        "invalid-empty-coordinate": invalid_empty_coordinate,
        "boolean-empty-coordinate": boolean_empty_coordinate,
        "forged-cross-coordinates": forged_cross_coordinates,
        "non-mapping-record": [*valid[:5], "not-a-typed-failure"],
    }
    for label, history in invalid_histories.items():
        assert not executor_module._valid_per_cell_failure_history(history), label


def test_tileset_material_failure_history_requires_six_typed_cross_seam_failures() -> None:
    valid = _typed_tileset_failure_history()
    assert executor_module._valid_tileset_material_failure_history(valid)

    # A sibling grid-source code is a legitimate exhaustion reason and still hands off to
    # material synthesis, provided each record keeps its own raise site's coordinate shape.
    mixed = [dict(value) for value in valid]
    mixed[2] = {
        "attempt": 3,
        "code": GRID_EMPTY_CELL_ERROR_CODE,
        "message": f"{GRID_EMPTY_CELL_ERROR_CODE}: grid cell (0,2) is empty",
        "row": 0,
        "column": 2,
    }
    alternate_diagnostic = [dict(value) for value in valid]
    alternate_diagnostic[0]["message"] = f"{GRID_ISOLATION_ERROR_CODE}: alternate typed diagnostic"
    forged = [dict(value) for value in valid]
    forged[0]["message"] = "arbitrary failure without typed prefix"
    # Cross-cell isolation describes the whole sheet, so a record claiming it while naming a
    # cell is fabricated evidence.
    with_coordinates = [dict(value) for value in valid]
    with_coordinates[0]["row"] = 0
    # An empty-cell record always names its cell at the raise site, so one without coordinates
    # is fabricated in the other direction.
    empty_cell_without_coordinates = [dict(value) for value in valid]
    empty_cell_without_coordinates[2] = {
        "attempt": 3,
        "code": GRID_EMPTY_CELL_ERROR_CODE,
        "message": f"{GRID_EMPTY_CELL_ERROR_CODE}: grid cell (0,2) is empty",
    }
    unknown_code = [dict(value) for value in valid]
    unknown_code[0] = {
        "attempt": 1,
        "code": "some-other-contract-v1",
        "message": "some-other-contract-v1: unrelated failure",
    }

    assert not executor_module._valid_tileset_material_failure_history(valid[:-1])
    assert executor_module._valid_tileset_material_failure_history(mixed)
    assert executor_module._valid_tileset_material_failure_history(alternate_diagnostic)
    assert not executor_module._valid_tileset_material_failure_history(forged)
    assert not executor_module._valid_tileset_material_failure_history(with_coordinates)
    assert not executor_module._valid_tileset_material_failure_history(
        empty_cell_without_coordinates
    )
    assert not executor_module._valid_tileset_material_failure_history(unknown_code)


def test_tileset_material_fallback_requires_exact_production_contract(tmp_path: Path) -> None:
    contract = contract_for_stage("tileset")
    assert contract is not None
    error = RetryExhaustedError(
        "fake image generation",
        Exception(GRID_ISOLATION_ERROR_CODE),
        6,
    )
    spec = _ImageSpec(
        "tileset",
        "production tileset",
        tmp_path / "tileset_offline.png",
        2400,
        800,
    )
    failures = _typed_tileset_failure_history()

    assert executor_module._eligible_tileset_material_fallback(spec, contract, error, failures)
    assert executor_module._eligible_tileset_material_fallback(
        spec,
        contract,
        RetryExhaustedError("fake", Exception("redacted terminal cause"), 6),
        failures,
    )
    assert not executor_module._eligible_tileset_material_fallback(
        _ImageSpec(
            "tileset",
            spec.prompt,
            tmp_path / "opaque.png",
            2400,
            800,
            transparent=False,
        ),
        contract,
        error,
        failures,
    )
    assert not executor_module._eligible_tileset_material_fallback(
        _ImageSpec("tileset", spec.prompt, tmp_path / "small.png", 240, 80),
        contract,
        error,
        failures,
    )
    assert not executor_module._eligible_tileset_material_fallback(
        spec,
        contract,
        RetryExhaustedError("fake", Exception(GRID_ISOLATION_ERROR_CODE), 5),
        failures,
    )


def test_tileset_material_fallback_recovers_six_typed_retry_owner_failures(
    tmp_path: Path,
) -> None:
    contract = contract_for_stage("tileset")
    assert contract is not None
    spec = _ImageSpec(
        "tileset",
        "production tileset",
        tmp_path / "tileset_live_shape.png",
        2400,
        800,
    )
    error_type = f"{GridSourceLayoutError.__module__}.{GridSourceLayoutError.__qualname__}"
    history = tuple(
        RetryFailureRecord(
            attempt=attempt,
            error_type=error_type,
            code=GRID_ISOLATION_ERROR_CODE,
            message=(
                f"{GRID_ISOLATION_ERROR_CODE}: grid source has a connected foreground "
                f"component spanning declared cells: vertical:{attempt}:1:0"
            ),
        )
        for attempt in range(1, 7)
    )
    error = RetryExhaustedError(
        "openrouter image generation",
        Exception(history[-1].message),
        6,
        history,
    )

    resolved = executor_module._resolved_grid_failure_history(error)

    assert [failure["attempt"] for failure in resolved] == list(range(1, 7))
    assert executor_module._eligible_tileset_material_fallback(
        spec,
        contract,
        error,
        resolved,
    )


def test_grid_failure_history_requires_current_retry_owner_records() -> None:
    error = RetryExhaustedError(
        "image generation",
        GridSourceLayoutError(GRID_ISOLATION_ERROR_CODE, "invalid grid"),
        6,
    )

    assert executor_module._resolved_grid_failure_history(error) == []


def test_tileset_material_fallback_rejects_mixed_retry_owner_history(tmp_path: Path) -> None:
    contract = contract_for_stage("tileset")
    assert contract is not None
    spec = _ImageSpec(
        "tileset",
        "production tileset",
        tmp_path / "tileset_mixed.png",
        2400,
        800,
    )
    grid_error_type = f"{GridSourceLayoutError.__module__}.{GridSourceLayoutError.__qualname__}"
    history = tuple(
        [
            RetryFailureRecord(
                attempt=attempt,
                error_type="builtins.TimeoutError",
                message="provider timeout",
            )
            for attempt in range(1, 6)
        ]
        + [
            RetryFailureRecord(
                attempt=6,
                error_type=grid_error_type,
                code=GRID_ISOLATION_ERROR_CODE,
                message=(
                    f"{GRID_ISOLATION_ERROR_CODE}: grid source has a connected foreground "
                    "component spanning declared cells: vertical:0:1:0"
                ),
            )
        ]
    )
    error = RetryExhaustedError(
        "openrouter image generation",
        Exception(history[-1].message),
        6,
        history,
    )

    resolved = executor_module._resolved_grid_failure_history(error)

    assert resolved == []
    assert not executor_module._eligible_tileset_material_fallback(
        spec,
        contract,
        error,
        resolved,
    )


def test_per_cell_stage_eligibility_requires_supported_transparent_parent_contract(
    tmp_path: Path,
) -> None:
    prompt = "Eight isolated inventory assets."
    contract = executor_module._per_cell_parent_contract(
        stage="items",
        prompt=prompt,
        source_specs=tuple({"kind": f"item-{index}"} for index in range(8)),
        reference_bindings=(),
        identity_policy="independent-distinct-items",
    )
    metadata: dict[str, object] = {"per_cell_generation_contract": contract}
    valid = _ImageSpec(
        "items",
        prompt,
        tmp_path / "items.png",
        160,
        80,
        metadata=metadata,
    )

    assert executor_module._eligible_per_cell_stage(valid)
    assert not executor_module._eligible_per_cell_stage(
        _ImageSpec(
            "items",
            prompt,
            tmp_path / "opaque-items.png",
            160,
            80,
            transparent=False,
            metadata=metadata,
        )
    )
    assert not executor_module._eligible_per_cell_stage(
        _ImageSpec(
            "portal",
            prompt,
            tmp_path / "portal.png",
            160,
            80,
            metadata=metadata,
        )
    )


async def test_grid_source_validation_retries_inside_image_generation_boundary(
    tmp_path: Path,
) -> None:
    backend = _SequencedImageBackend((_grid_source(missing_last=True), _grid_source()))
    image_service = ImageGenerationService(
        cast(ImageGenerationBackend, backend),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    executor = ScrollingPreviewExecutor(
        image_service=image_service,
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    output = tmp_path / "items_offline.png"

    await executor._generate_image_asset(
        StageContext(
            input={"prompt": "offline"},
            tag="offline",
            run_dir=tmp_path,
            config=StageGenConfig(out_dir=tmp_path),
        ),
        _ImageSpec(
            "items",
            "eight isolated items",
            output,
            160,
            80,
            transparent=False,
        ),
    )

    assert backend.calls == 2
    sidecar_text = await asyncio.to_thread(Path(f"{output}.meta.json").read_text, encoding="utf-8")
    sidecar = json.loads(sidecar_text)
    assert sidecar["attempts"] == 2
    assert sidecar["validation"]["source_cells_nonempty"] == 8
    assert sidecar["validation"]["source_cells_recoverable"] is True
    assert sidecar["validation"]["source_boundaries_isolated"] is True


async def test_fixable_grid_gutter_contact_does_not_consume_provider_retry(
    tmp_path: Path,
) -> None:
    backend = _SequencedImageBackend((_grid_source(gutter_contact=True),))
    image_service = ImageGenerationService(
        cast(ImageGenerationBackend, backend),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    executor = ScrollingPreviewExecutor(
        image_service=image_service,
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    output = tmp_path / "items_recoverable.png"

    await executor._generate_image_asset(
        StageContext(
            input={"prompt": "offline"},
            tag="offline",
            run_dir=tmp_path,
            config=StageGenConfig(out_dir=tmp_path),
        ),
        _ImageSpec("items", "eight isolated items", output, 160, 80, transparent=False),
    )

    assert backend.calls == 1
    sidecar = json.loads(
        await asyncio.to_thread(Path(f"{output}.meta.json").read_text, encoding="utf-8")
    )
    assert sidecar["validation"]["source_cells_recoverable"] is True
    assert sidecar["validation"]["source_boundaries_isolated"] is False
    assert sidecar["validation"]["source_gutter_pixels_painted"] == 1


@pytest.mark.parametrize(
    ("stage", "canvas", "invalid"),
    [
        ("items", (160, 80), _grid_source(missing_last=True)),
        ("items", (160, 80), _grid_source(cross_seam=True)),
        ("tileset", (240, 80), _continuous_grid_source(width=240, height=80)),
        ("tileset", (240, 80), _wrong_role_tileset_source()),
    ],
)
async def test_unrecoverable_grid_source_exhausts_all_six_provider_attempts(
    tmp_path: Path,
    stage: str,
    canvas: tuple[int, int],
    invalid: bytes,
) -> None:
    backend = _SequencedImageBackend((invalid,))
    image_service = ImageGenerationService(
        cast(ImageGenerationBackend, backend),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    executor = ScrollingPreviewExecutor(
        image_service=image_service,
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    output = tmp_path / f"{stage}_invalid.png"

    with pytest.raises(RetryExhaustedError):
        await executor._generate_image_asset(
            StageContext(
                input={"prompt": "offline"},
                tag="offline",
                run_dir=tmp_path,
                config=StageGenConfig(out_dir=tmp_path),
            ),
            _ImageSpec(stage, "declared cell atlas", output, *canvas, transparent=False),
        )

    assert backend.calls == 6
    assert not await asyncio.to_thread(output.exists)


async def test_tileset_cross_seam_exhaustion_uses_three_linked_material_swatches(
    tmp_path: Path,
) -> None:
    backend = _TilesetFallbackImageBackend()
    image_service = ImageGenerationService(
        cast(ImageGenerationBackend, backend),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    executor = ScrollingPreviewExecutor(
        image_service=image_service,
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    context = _tileset_fallback_context(tmp_path)
    spec = executor._tileset_spec(context)

    await executor._generate_image_asset(context, spec)

    assert backend.calls == 9
    stages = [str(request.metadata.get("stage")) for request in backend.requests]
    assert stages[:6] == ["tileset"] * 6
    assert stages[6] == "tileset-material-fill"
    assert set(stages[7:]) == {"tileset-material-cap", "tileset-material-edge"}
    fill_request = backend.requests[6]
    assert len(fill_request.input_references) == 1
    for request in backend.requests[7:]:
        assert len(request.input_references) == 2
        assert request.input_references[1].provenance_ref == (
            f".{spec.output.stem}.material-fill.png"
        )
        assert all(
            "wireframe" not in str(reference.provenance_ref)
            for reference in request.input_references
        )

    contract = contract_for_stage("tileset")
    assert contract is not None
    validate_canonical_grid(await asyncio.to_thread(spec.output.read_bytes), contract)
    sidecar = json.loads(
        await asyncio.to_thread(Path(f"{spec.output}.meta.json").read_text, encoding="utf-8")
    )
    fallback = sidecar["params"]["transparency"]["tileset_material_synthesis"]
    assert fallback["version"] == "tileset-material-synthesis-v1"
    assert fallback["role_order"] == ["fill", "cap", "edge"]
    assert fallback["failed_sheet_pixels_used"] is False
    assert fallback["independent_role_cell_calls"] == 0
    assert [failure["attempt"] for failure in fallback["sheet_failures"]] == list(range(1, 7))
    assert all(
        failure["code"] == GRID_ISOLATION_ERROR_CODE for failure in fallback["sheet_failures"]
    )
    for role in ("fill", "cap", "edge"):
        canonical = tmp_path / f".{spec.output.stem}.material-{role}.png"
        raw = canonical.with_name(f"{canonical.stem}.raw.png")
        assert await asyncio.to_thread(canonical.is_file)
        assert await asyncio.to_thread(raw.is_file)
        assert await asyncio.to_thread(Path(f"{canonical}.meta.json").is_file)
        assert await asyncio.to_thread(Path(f"{raw}.meta.json").is_file)

    await executor._generate_image_asset(context, spec)
    assert backend.calls == 9

    cap = tmp_path / f".{spec.output.stem}.material-cap.png"
    cap.write_bytes(b"tampered-cap")
    await executor._generate_image_asset(context, spec)
    assert backend.calls == 10
    assert backend.requests[-1].metadata["stage"] == "tileset-material-cap"

    fill = tmp_path / f".{spec.output.stem}.material-fill.png"
    fill.write_bytes(b"tampered-fill")
    await executor._generate_image_asset(context, spec)
    assert backend.calls == 13
    assert backend.requests[-3].metadata["stage"] == "tileset-material-fill"
    assert {request.metadata["stage"] for request in backend.requests[-2:]} == {
        "tileset-material-cap",
        "tileset-material-edge",
    }


@pytest.mark.parametrize("global_gamut", [False, True], ids=["lightness", "global-gamut"])
async def test_live_cap_separation_is_recovered_and_evidence_tamper_regenerates_only_cap(
    tmp_path: Path,
    global_gamut: bool,
) -> None:
    backend = _TilesetFallbackImageBackend(
        cap_needs_lightness_recovery=not global_gamut,
        cap_needs_global_gamut_recovery=global_gamut,
    )
    executor = ScrollingPreviewExecutor(
        image_service=ImageGenerationService(
            cast(ImageGenerationBackend, backend),
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ),
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    context = _tileset_fallback_context(tmp_path)
    spec = executor._tileset_spec(context)

    await executor._generate_image_asset(context, spec)

    assert backend.calls == 9
    assert (
        sum(request.metadata.get("stage") == "tileset-material-cap" for request in backend.requests)
        == 1
    )
    cap = tmp_path / f".{spec.output.stem}.material-cap.png"
    cap_raw = cap.with_name(f"{cap.stem}.raw.png")
    cap_sidecar = Path(f"{cap}.meta.json")
    cap_raw_sidecar = Path(f"{cap_raw}.meta.json")
    record = json.loads(await asyncio.to_thread(cap_sidecar.read_text, encoding="utf-8"))
    raw_record = json.loads(await asyncio.to_thread(cap_raw_sidecar.read_text, encoding="utf-8"))
    canonicalization = record["params"]["tileset_material_canonicalization"]
    assert canonicalization == record["validation"]["tileset_material_canonicalization"]
    assert canonicalization == raw_record["validation"]["tileset_material_raw_canonicalization"]
    recovery = canonicalization["cap_fill_lightness_recovery"]
    assert recovery["version"] == CAP_FILL_LIGHTNESS_VERSION
    if global_gamut:
        assert recovery["global_gamut_version"] == CAP_FILL_GLOBAL_GAMUT_VERSION
        assert recovery["global_chroma_factor"] == 0.65
        assert recovery["gamut"]["maximum_hue_drift_degrees"] <= 2.0
    else:
        assert "global_gamut_version" not in recovery
    assert recovery["input_sha256"] != recovery["output_sha256"]
    fill = tmp_path / f".{spec.output.stem}.material-fill.png"
    fill_bytes = await asyncio.to_thread(fill.read_bytes)
    assert recovery["fill_anchor_sha256"] == sha256_hex(fill_bytes)
    relationship = recovery["output_relationship"]
    assert 0.12 <= abs(relationship["luminance_delta"]) <= 0.16
    assert relationship["delta_e00"] >= 10.0

    fill_sidecar = Path(f"{tmp_path / f'.{spec.output.stem}.material-fill.png'}.meta.json")
    edge_sidecar = Path(f"{tmp_path / f'.{spec.output.stem}.material-edge.png'}.meta.json")
    fill_before, edge_before = await asyncio.gather(
        asyncio.to_thread(fill_sidecar.read_bytes),
        asyncio.to_thread(edge_sidecar.read_bytes),
    )
    forged_recovery = dict(recovery)
    forged_recovery["direction"] = "forged"
    recovery_payload = {key: value for key, value in forged_recovery.items() if key != "sha256"}
    forged_recovery["sha256"] = sha256_hex(
        json.dumps(recovery_payload, sort_keys=True, separators=(",", ":")).encode()
    )
    for location in (
        record["params"]["tileset_material_canonicalization"],
        record["validation"]["tileset_material_canonicalization"],
    ):
        location["cap_fill_lightness_recovery"] = dict(forged_recovery)
    await asyncio.to_thread(cap_sidecar.write_text, json.dumps(record), encoding="utf-8")

    await executor._generate_image_asset(context, spec)

    assert backend.calls == 10
    assert backend.requests[-1].metadata["stage"] == "tileset-material-cap"
    assert await asyncio.to_thread(fill_sidecar.read_bytes) == fill_before
    assert await asyncio.to_thread(edge_sidecar.read_bytes) == edge_before
    repaired = json.loads(await asyncio.to_thread(cap_sidecar.read_text, encoding="utf-8"))
    repaired_recovery = repaired["params"]["tileset_material_canonicalization"][
        "cap_fill_lightness_recovery"
    ]
    assert repaired_recovery["direction"] != "forged"
    assert (
        repaired_recovery
        == repaired["validation"]["tileset_material_canonicalization"][
            "cap_fill_lightness_recovery"
        ]
    )
    await executor._generate_image_asset(context, spec)
    assert backend.calls == 10


async def test_tileset_material_style_anchor_is_bound_once_and_cache_resumes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    style = _tileset_style_context()

    async def read_style(_context: StageContext) -> executor_module._StyleAnchorContext:
        return style

    monkeypatch.setattr(executor_module, "_read_style_anchor", read_style)
    backend = _TilesetFallbackImageBackend()
    executor = ScrollingPreviewExecutor(
        image_service=ImageGenerationService(
            cast(ImageGenerationBackend, backend),
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ),
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    context = _tileset_fallback_context(tmp_path)
    spec = executor._tileset_spec(context)

    await executor._generate_image_asset(context, spec)
    assert backend.calls == 9
    for request in backend.requests[6:]:
        assert request.style_anchor == style.anchor
        assert request.asset_kind == "tileable_texture"
        assert request.prompt.count("Canonical style anchor — ") == 1

    await executor._generate_image_asset(context, spec)
    assert backend.calls == 9
    parent = json.loads(
        await asyncio.to_thread(
            Path(f"{spec.output}.meta.json").read_text,
            encoding="utf-8",
        )
    )
    fallback = parent["params"]["transparency"]["tileset_material_synthesis"]
    assert fallback["parent_contract"]["style_anchor"] == style.identity
    assert all(
        component["component_contract"]["style_anchor"] == style.identity
        for component in fallback["components"]
    )


async def test_tileset_material_failure_never_publishes_parent_bundle(tmp_path: Path) -> None:
    backend = _TilesetFallbackImageBackend(invalid_material_role="fill")
    image_service = ImageGenerationService(
        cast(ImageGenerationBackend, backend),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    executor = ScrollingPreviewExecutor(
        image_service=image_service,
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    context = _tileset_fallback_context(tmp_path)
    spec = executor._tileset_spec(context)

    with pytest.raises(RuntimeError, match="tileset material fill failed"):
        await executor._generate_image_asset(context, spec)

    assert backend.calls == 12
    assert not await asyncio.to_thread(spec.output.exists)
    retained_raw = spec.output.with_name(f"{spec.output.stem}.raw.png")
    assert not await asyncio.to_thread(retained_raw.exists)


@pytest.mark.parametrize("invalid_role", ["cap", "edge"])
async def test_tileset_dependent_material_owns_six_retries_and_parent_is_atomic(
    tmp_path: Path,
    invalid_role: str,
) -> None:
    backend = _TilesetFallbackImageBackend(invalid_material_role=invalid_role)
    executor = ScrollingPreviewExecutor(
        image_service=ImageGenerationService(
            cast(ImageGenerationBackend, backend),
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ),
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    context = _tileset_fallback_context(tmp_path)
    spec = executor._tileset_spec(context)

    with pytest.raises(RuntimeError, match="tileset material swatch failed"):
        await executor._generate_image_asset(context, spec)

    assert (
        sum(
            request.metadata.get("stage") == f"tileset-material-{invalid_role}"
            for request in backend.requests
        )
        == 6
    )
    assert not await asyncio.to_thread(spec.output.exists)
    retained_raw = spec.output.with_name(f"{spec.output.stem}.raw.png")
    assert not await asyncio.to_thread(retained_raw.exists)


async def test_tileset_material_cache_rejects_sidecar_conflicts_and_tamper(
    tmp_path: Path,
) -> None:
    backend = _TilesetFallbackImageBackend()
    executor = ScrollingPreviewExecutor(
        image_service=ImageGenerationService(
            cast(ImageGenerationBackend, backend),
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ),
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    context = _tileset_fallback_context(tmp_path)
    spec = executor._tileset_spec(context)
    await executor._generate_image_asset(context, spec)
    assert backend.calls == 9

    parent_sidecar = Path(f"{spec.output}.meta.json")
    parent_record = json.loads(await asyncio.to_thread(parent_sidecar.read_text, encoding="utf-8"))
    parent_record["params"]["metadata"]["tileset_material_synthesis"] = {
        "version": "forged-conflicting-copy"
    }
    await asyncio.to_thread(
        parent_sidecar.write_text,
        json.dumps(parent_record),
        encoding="utf-8",
    )
    await executor._generate_image_asset(context, spec)
    assert backend.calls == 9
    repaired = json.loads(await asyncio.to_thread(parent_sidecar.read_text, encoding="utf-8"))
    assert (
        repaired["params"]["metadata"]["tileset_material_synthesis"]
        == repaired["params"]["transparency"]["tileset_material_synthesis"]
    )

    cap_raw = tmp_path / f".{spec.output.stem}.material-cap.raw.png"
    cap_raw_sidecar = Path(f"{cap_raw}.meta.json")
    cap_record = json.loads(await asyncio.to_thread(cap_raw_sidecar.read_text, encoding="utf-8"))
    cap_record["provider"] = "forged-provider"
    await asyncio.to_thread(
        cap_raw_sidecar.write_text,
        json.dumps(cap_record),
        encoding="utf-8",
    )
    await executor._generate_image_asset(context, spec)
    assert backend.calls == 10
    assert backend.requests[-1].metadata["stage"] == "tileset-material-cap"

    edge = tmp_path / f".{spec.output.stem}.material-edge.png"
    edge_sidecar = Path(f"{edge}.meta.json")
    edge_record = json.loads(await asyncio.to_thread(edge_sidecar.read_text, encoding="utf-8"))
    edge_record["inputs"][0]["sha256"] = "0" * 64
    await asyncio.to_thread(
        edge_sidecar.write_text,
        json.dumps(edge_record),
        encoding="utf-8",
    )
    await executor._generate_image_asset(context, spec)
    assert backend.calls == 11
    assert str(backend.requests[-1].metadata["stage"]) == "tileset-material-edge"


async def test_tileset_material_resume_uses_surviving_child_parent_contract(
    tmp_path: Path,
) -> None:
    backend = _TilesetFallbackImageBackend()
    executor = ScrollingPreviewExecutor(
        image_service=ImageGenerationService(
            cast(ImageGenerationBackend, backend),
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ),
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    context = _tileset_fallback_context(tmp_path)
    spec = executor._tileset_spec(context)
    await executor._generate_image_asset(context, spec)
    assert backend.calls == 9

    parent_raw = spec.output.with_name(f"{spec.output.stem}.raw.png")
    fill = tmp_path / f".{spec.output.stem}.material-fill.png"
    fill_raw = fill.with_name(f"{fill.stem}.raw.png")
    for path in (parent_raw, spec.output, fill_raw, fill):
        await asyncio.to_thread(path.unlink)
        await asyncio.to_thread(Path(f"{path}.meta.json").unlink)

    await executor._generate_image_asset(context, spec)
    assert backend.calls == 12
    assert backend.requests[-3].metadata["stage"] == "tileset-material-fill"
    assert {request.metadata["stage"] for request in backend.requests[-2:]} == {
        "tileset-material-cap",
        "tileset-material-edge",
    }


async def test_tileset_semantic_failure_never_enters_material_fallback(tmp_path: Path) -> None:
    backend = _SequencedImageBackend((_wrong_role_tileset_source(),))
    image_service = ImageGenerationService(
        cast(ImageGenerationBackend, backend),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    executor = ScrollingPreviewExecutor(
        image_service=image_service,
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    output = tmp_path / "tileset_semantic_failure.png"

    with pytest.raises(RetryExhaustedError):
        await executor._generate_image_asset(
            StageContext(
                input={"prompt": "offline"},
                tag="offline",
                run_dir=tmp_path,
                config=StageGenConfig(out_dir=tmp_path),
            ),
            _ImageSpec("tileset", "declared terrain roles", output, 2400, 800),
        )

    assert backend.calls == 6
    assert all(request.metadata["stage"] == "tileset" for request in backend.requests)
    assert not await asyncio.to_thread(output.exists)


async def test_concept_cross_seam_exhaustion_uses_linked_isolated_view_fallback(
    tmp_path: Path,
) -> None:
    reference = tmp_path / "concept_offline.png"
    reference.write_bytes(_isolated_view_source())
    backend = _SequencedImageBackend(
        (_turnaround_source(cross_seam=True),) * 6 + (_isolated_view_source(),) * 3
    )
    image_service = ImageGenerationService(
        cast(ImageGenerationBackend, backend),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    structured_backend = _RecordingStructuredBackend()
    structured_service = StructuredGenerationService[object](
        structured_backend,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    executor = ScrollingPreviewExecutor(
        image_service=image_service,
        structured_service=structured_service,
    )
    context = StageContext(
        input={"prompt": "offline", "theme": {"hostile_action": 1}},
        tag="offline",
        run_dir=tmp_path,
        config=StageGenConfig(
            out_dir=tmp_path,
            transparency_mode=TransparencyMode.CHROMA,
        ),
    )
    spec = _concept_fallback_spec(tmp_path, reference)

    await executor.run_scrolling_preview_stage("theme-compile", context)
    await executor._generate_image_asset(context, spec)

    assert backend.calls == 9
    contract = contract_for_stage(spec.stage)
    assert contract is not None
    validate_canonical_grid(await asyncio.to_thread(spec.output.read_bytes), contract)
    sidecar = json.loads(
        await asyncio.to_thread(
            Path(f"{spec.output}.meta.json").read_text,
            encoding="utf-8",
        )
    )
    fallback = sidecar["params"]["transparency"]["isolated_view_fallback"]
    assert sidecar["params"]["metadata"]["theme_compilation"]["compiler_version"] == (
        THEME_COMPILER_VERSION
    )
    assert fallback["version"] == "isolated-view-fallback-v1"
    assert fallback["sheet_exhaustion"]["attempts"] == 6
    assert fallback["sheet_exhaustion"]["retries"] == 5
    assert fallback["view_roles"] == ["front", "side", "back"]
    assert [component["generation"]["attempts"] for component in fallback["components"]] == [
        1,
        1,
        1,
    ]
    for index in range(3):
        canonical = spec.output.with_name(f".{spec.output.stem}.view-{index}.png")
        raw = canonical.with_name(f"{canonical.stem}.raw.png")
        assert await asyncio.to_thread(canonical.is_file)
        assert await asyncio.to_thread(raw.is_file)
        assert await asyncio.to_thread(Path(f"{canonical}.meta.json").is_file)
        assert await asyncio.to_thread(Path(f"{raw}.meta.json").is_file)
    world_ref = str(reference)
    anchor_ref = str(spec.output.with_name(f".{spec.output.stem}.view-0.png"))
    assert [ref.provenance_ref for ref in backend.requests[6].input_references] == [world_ref]
    assert [ref.provenance_ref for ref in backend.requests[7].input_references] == [
        world_ref,
        anchor_ref,
    ]
    assert [ref.provenance_ref for ref in backend.requests[8].input_references] == [
        world_ref,
        anchor_ref,
    ]
    for request, role in zip(backend.requests[6:], ("front", "side", "back"), strict=True):
        assert f"one {role}-view full-body identity study" in request.prompt
        assert "one complete centered subject only" in request.prompt
        assert "No ground plane" in request.prompt

    raw_path = spec.output.with_name(f"{spec.output.stem}.raw.png")
    raw_sidecar = json.loads(
        await asyncio.to_thread(
            Path(f"{raw_path}.meta.json").read_text,
            encoding="utf-8",
        )
    )
    assert executor_module._valid_raw_asset_cache(
        raw_path,
        raw_sidecar,
        spec=spec,
        contract=contract,
    )
    await executor._generate_image_asset(context, spec)
    assert backend.calls == 9

    component_raw = spec.output.with_name(f".{spec.output.stem}.view-0.raw.png")
    await asyncio.to_thread(component_raw.write_bytes, b"tampered")
    await executor._generate_image_asset(context, spec)
    assert backend.calls == 16
    assert await asyncio.to_thread(component_raw.read_bytes) != b"tampered"
    await executor._generate_image_asset(context, spec)
    assert backend.calls == 16


async def test_live_concept_border_noise_is_cleaned_and_cache_tamper_repairs_view(
    tmp_path: Path,
) -> None:
    reference = tmp_path / "concept_offline.png"
    reference.write_bytes(_isolated_view_source())
    sheet_failure = _turnaround_source(cross_seam=True)
    backend = _SequencedImageBackend(
        (sheet_failure,) * 6
        + (_isolated_view_source(border_noise=True),)
        + (_isolated_view_source(),) * 2
        + (sheet_failure,) * 6
    )
    executor = ScrollingPreviewExecutor(
        image_service=ImageGenerationService(
            cast(ImageGenerationBackend, backend),
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ),
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    context = StageContext(
        input={"prompt": "offline"},
        tag="offline",
        run_dir=tmp_path,
        config=StageGenConfig(
            out_dir=tmp_path,
            transparency_mode=TransparencyMode.CHROMA,
        ),
    )
    spec = _concept_fallback_spec(tmp_path, reference, stage="mob-concept-4")

    await executor._generate_image_asset(context, spec)

    assert backend.calls == 9
    component = spec.output.with_name(f".{spec.output.stem}.view-0.png")
    sidecar_path = Path(f"{component}.meta.json")
    untouched_sidecar = Path(
        f"{spec.output.with_name(f'.{spec.output.stem}.view-1.png')}.meta.json"
    )
    untouched_before = await asyncio.to_thread(untouched_sidecar.read_bytes)
    sidecar = json.loads(await asyncio.to_thread(sidecar_path.read_text, encoding="utf-8"))
    transparency = sidecar["params"]["transparency"]
    cleanup = transparency["isolated_view_alpha_cleanup"]
    assert cleanup == sidecar["validation"]["isolated_view_alpha_cleanup"]
    assert cleanup["version"] == ISOLATED_ALPHA_CLEANUP_VERSION
    assert cleanup["removed_pixels"] == 2
    assert cleanup["removed_coordinates"] == [[0, 79], [79, 79]]
    assert "isolated_view_subject_fit" not in transparency
    assert transparency["processor"] == {
        "kind": f"chroma-key+{ISOLATED_ALPHA_CLEANUP_VERSION}",
        "version": ISOLATED_ALPHA_CLEANUP_VERSION,
    }

    forged_cleanup = dict(cleanup)
    forged_cleanup["removed_coordinates"] = [[0, 78], [79, 79]]
    cleanup_payload = {key: value for key, value in forged_cleanup.items() if key != "sha256"}
    forged_cleanup["sha256"] = sha256_hex(
        json.dumps(cleanup_payload, sort_keys=True, separators=(",", ":")).encode()
    )
    transparency["isolated_view_alpha_cleanup"] = forged_cleanup
    sidecar["validation"]["isolated_view_alpha_cleanup"] = dict(forged_cleanup)
    await asyncio.to_thread(sidecar_path.write_text, json.dumps(sidecar), encoding="utf-8")

    await executor._generate_image_asset(context, spec)

    assert backend.calls == 15
    assert all(request.metadata["stage"] == "mob-concept-4" for request in backend.requests[9:])
    assert await asyncio.to_thread(untouched_sidecar.read_bytes) == untouched_before
    repaired = json.loads(await asyncio.to_thread(sidecar_path.read_text, encoding="utf-8"))
    repaired_cleanup = repaired["params"]["transparency"]["isolated_view_alpha_cleanup"]
    assert repaired_cleanup["removed_coordinates"] == [[0, 79], [79, 79]]
    assert repaired_cleanup == repaired["validation"]["isolated_view_alpha_cleanup"]
    await executor._generate_image_asset(context, spec)
    assert backend.calls == 15


async def test_items_sheet_exhaustion_uses_per_cell_generation_and_cache(
    tmp_path: Path,
) -> None:
    backend = _SequencedImageBackend(
        (_grid_source(cross_seam=True),) * 6 + (_isolated_cell_source(),) * 8
    )
    image_service = ImageGenerationService(
        cast(ImageGenerationBackend, backend),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    executor = ScrollingPreviewExecutor(
        image_service=image_service,
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    context = StageContext(
        input={"prompt": "offline"},
        tag="offline",
        run_dir=tmp_path,
        config=StageGenConfig(
            out_dir=tmp_path,
            transparency_mode=TransparencyMode.CHROMA,
        ),
    )
    spec = _per_cell_fallback_spec(tmp_path)

    await executor._generate_image_asset(context, spec)

    assert backend.calls == 14
    assert len({request.prompt for request in backend.requests[6:]}) == 8
    assert all(
        [reference.provenance_ref for reference in request.input_references]
        == [f"concept_{context.tag}.png"]
        for request in backend.requests[6:]
    )
    contract = contract_for_stage("items")
    assert contract is not None
    validate_canonical_grid(spec.output.read_bytes(), contract)
    sidecar = json.loads(
        await asyncio.to_thread(
            Path(f"{spec.output}.meta.json").read_text,
            encoding="utf-8",
        )
    )
    fallback = sidecar["params"]["transparency"]["per_cell_generation"]
    assert fallback["version"] == "per-cell-generation-v1"
    assert fallback["role_order"] == [f"item-{index}" for index in range(8)]
    assert [failure["attempt"] for failure in fallback["sheet_failures"]] == list(range(1, 7))
    assert fallback["identity_dag"] == [
        {"cell_index": index, "depends_on": [], "usage": "independent"} for index in range(8)
    ]
    for row in range(2):
        for column in range(4):
            component = spec.output.with_name(f".{spec.output.stem}.cell-{row}-{column}.png")
            assert component.is_file()
            assert component.with_name(f"{component.stem}.raw.png").is_file()

    await executor._generate_image_asset(context, spec)
    assert backend.calls == 14


async def test_items_live_oversize_cell_is_fitted_locally_and_cache_tamper_repairs_selectively(
    tmp_path: Path,
) -> None:
    backend = _PerCellOversizeImageBackend()
    image_service = ImageGenerationService(
        cast(ImageGenerationBackend, backend),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    executor = ScrollingPreviewExecutor(
        image_service=image_service,
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    context = StageContext(
        input={"prompt": "offline"},
        tag="offline",
        run_dir=tmp_path,
        config=StageGenConfig(
            out_dir=tmp_path,
            transparency_mode=TransparencyMode.CHROMA,
        ),
    )
    spec = _per_cell_fallback_spec(tmp_path)

    await executor._generate_image_asset(context, spec)

    assert backend.calls == 14
    assert (
        sum(request.metadata.get("stage") == "per-cell-items-v1-5" for request in backend.requests)
        == 1
    )
    component = spec.output.with_name(f".{spec.output.stem}.cell-1-1.png")
    sidecar_path = Path(f"{component}.meta.json")
    sidecar = json.loads(await asyncio.to_thread(sidecar_path.read_text, encoding="utf-8"))
    fit = sidecar["params"]["transparency"]["per_cell_subject_fit"]
    assert fit == sidecar["validation"]["per_cell_subject_fit"]
    assert fit["version"] == ISOLATED_SUBJECT_FIT_VERSION
    assert fit["source_height_fraction"] > 0.70
    assert fit["target_height_fraction"] <= 0.70
    assert fit["output_sha256"] == sha256_hex(await asyncio.to_thread(component.read_bytes))
    assert (
        fit["component_contract_sha256"]
        == sidecar["params"]["metadata"]["per_cell_generation"]["sha256"]
    )

    sidecar["params"]["transparency"]["per_cell_subject_fit"]["output_sha256"] = "0" * 64
    await asyncio.to_thread(sidecar_path.write_text, json.dumps(sidecar), encoding="utf-8")
    await executor._generate_image_asset(context, spec)

    assert backend.calls == 14
    repaired = json.loads(await asyncio.to_thread(sidecar_path.read_text, encoding="utf-8"))
    repaired_fit = repaired["params"]["transparency"]["per_cell_subject_fit"]
    assert repaired_fit["output_sha256"] == sha256_hex(
        await asyncio.to_thread(component.read_bytes)
    )
    await executor._generate_image_asset(context, spec)
    assert backend.calls == 14


async def test_ai_oversize_item_fit_binds_removal_and_repairs_only_tampered_component(
    tmp_path: Path,
) -> None:
    image_backend = _PerCellOversizeImageBackend()
    removal_backend = _PerCellAlphaBackgroundBackend()
    executor = ScrollingPreviewExecutor(
        image_service=ImageGenerationService(
            cast(ImageGenerationBackend, image_backend),
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ),
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
        background_service=BackgroundRemovalService(
            cast(BackgroundRemovalBackend, removal_backend),
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ),
    )
    context = StageContext(
        input={"prompt": "offline"},
        tag="offline",
        run_dir=tmp_path,
        config=StageGenConfig(
            out_dir=tmp_path,
            transparency_mode=TransparencyMode.AI,
        ),
    )
    spec = _per_cell_fallback_spec(tmp_path)

    await executor._generate_image_asset(context, spec)

    assert image_backend.calls == 14
    assert removal_backend.calls == 8
    component = spec.output.with_name(f".{spec.output.stem}.cell-1-1.png")
    raw_component = component.with_name(f"{component.stem}.raw.png")
    sidecar_path = Path(f"{component}.meta.json")
    sidecar = json.loads(await asyncio.to_thread(sidecar_path.read_text, encoding="utf-8"))
    fit = sidecar["params"]["transparency"]["per_cell_subject_fit"]
    removal = sidecar["params"]["transparency"]["removal"]["provenance"]
    assert fit["source_processor"] == "ai-background-removal"
    assert fit["removal_provenance_sha256"] == executor_module._canonical_mapping_sha256(removal)
    assert removal["validation"]["per_cell_fit_input_sha256"] == fit["input_sha256"]
    assert removal["validation"]["isolated_view_alpha_bbox"] == fit["source_bbox"]

    sidecar["params"]["transparency"]["removal"]["provenance"]["validation"][
        "per_cell_fit_input_sha256"
    ] = "0" * 64
    await asyncio.to_thread(sidecar_path.write_text, json.dumps(sidecar), encoding="utf-8")
    await executor._generate_image_asset(context, spec)

    assert image_backend.calls == 14
    assert removal_backend.calls == 9
    repaired = json.loads(await asyncio.to_thread(sidecar_path.read_text, encoding="utf-8"))
    repaired_fit = repaired["params"]["transparency"]["per_cell_subject_fit"]
    repaired_removal = repaired["params"]["transparency"]["removal"]["provenance"]
    assert (
        repaired_removal["validation"]["per_cell_fit_input_sha256"] == repaired_fit["input_sha256"]
    )
    raw_bytes = await asyncio.to_thread(raw_component.read_bytes)
    canonical_bytes = await asyncio.to_thread(component.read_bytes)
    assert executor_module._valid_per_cell_transparency_evidence(
        raw=raw_bytes,
        canonical=canonical_bytes,
        canonical_sidecar=repaired,
        mode=TransparencyMode.AI,
        contract=repaired["params"]["metadata"]["per_cell_generation"],
        width=40,
        height=40,
    )
    for key, invalid in (
        ("source_bbox", [12, 6, 28, 35]),
        ("placement", [13, 7]),
        ("scale_factor", 0.94),
    ):
        forged = cast(dict[str, Any], json.loads(json.dumps(repaired)))
        forged_fit = forged["params"]["transparency"]["per_cell_subject_fit"]
        forged_fit[key] = invalid
        payload = {name: value for name, value in forged_fit.items() if name != "sha256"}
        forged_fit["sha256"] = sha256_hex(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        )
        forged["validation"]["per_cell_subject_fit"] = dict(forged_fit)
        assert not executor_module._valid_per_cell_transparency_evidence(
            raw=raw_bytes,
            canonical=canonical_bytes,
            canonical_sidecar=forged,
            mode=TransparencyMode.AI,
            contract=forged["params"]["metadata"]["per_cell_generation"],
            width=40,
            height=40,
        )
    await executor._generate_image_asset(context, spec)
    assert image_backend.calls == 14
    assert removal_backend.calls == 9


async def test_live_one_pixel_border_noise_is_cleaned_fitted_and_cache_tamper_repairs_locally(
    tmp_path: Path,
) -> None:
    backend = _PerCellOversizeImageBackend(
        oversize_index=3,
        border_noise_index=3,
        parent_width=2400,
        parent_height=800,
    )
    executor = ScrollingPreviewExecutor(
        image_service=ImageGenerationService(
            cast(ImageGenerationBackend, backend),
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ),
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    context = StageContext(
        input={"prompt": "offline"},
        tag="offline",
        run_dir=tmp_path,
        config=StageGenConfig(
            out_dir=tmp_path,
            transparency_mode=TransparencyMode.CHROMA,
        ),
    )
    spec = _per_cell_fallback_spec(tmp_path, width=2400, height=800)

    await executor._generate_image_asset(context, spec)

    assert backend.calls == 14
    component = spec.output.with_name(f".{spec.output.stem}.cell-0-3.png")
    sidecar_path = Path(f"{component}.meta.json")
    untouched_sidecar = Path(
        f"{spec.output.with_name(f'.{spec.output.stem}.cell-0-2.png')}.meta.json"
    )
    untouched_before = await asyncio.to_thread(untouched_sidecar.read_bytes)
    sidecar = json.loads(await asyncio.to_thread(sidecar_path.read_text, encoding="utf-8"))
    transparency = sidecar["params"]["transparency"]
    cleanup = transparency["per_cell_alpha_cleanup"]
    fit = transparency["per_cell_subject_fit"]
    assert cleanup == sidecar["validation"]["per_cell_alpha_cleanup"]
    assert cleanup["version"] == ISOLATED_ALPHA_CLEANUP_VERSION
    assert cleanup["removed_pixels"] == 1
    assert cleanup["removed_coordinates"] == [[0, 399]]
    assert fit["version"] == ISOLATED_SUBJECT_FIT_VERSION
    assert fit["cleanup"] == cleanup
    assert fit["source_height_fraction"] == 0.8
    assert fit["target_height_fraction"] <= 0.70

    forged_cleanup = dict(cleanup)
    forged_cleanup["removed_coordinates"] = [[0, 398]]
    cleanup_payload = {key: value for key, value in forged_cleanup.items() if key != "sha256"}
    forged_cleanup["sha256"] = sha256_hex(
        json.dumps(cleanup_payload, sort_keys=True, separators=(",", ":")).encode()
    )
    forged_fit = dict(fit)
    forged_fit["cleanup"] = forged_cleanup
    fit_payload = {key: value for key, value in forged_fit.items() if key != "sha256"}
    forged_fit["sha256"] = sha256_hex(
        json.dumps(fit_payload, sort_keys=True, separators=(",", ":")).encode()
    )
    transparency["per_cell_alpha_cleanup"] = forged_cleanup
    transparency["per_cell_subject_fit"] = forged_fit
    sidecar["validation"]["per_cell_alpha_cleanup"] = dict(forged_cleanup)
    sidecar["validation"]["per_cell_subject_fit"] = dict(forged_fit)
    await asyncio.to_thread(sidecar_path.write_text, json.dumps(sidecar), encoding="utf-8")

    await executor._generate_image_asset(context, spec)

    assert backend.calls == 14
    assert await asyncio.to_thread(untouched_sidecar.read_bytes) == untouched_before
    repaired = json.loads(await asyncio.to_thread(sidecar_path.read_text, encoding="utf-8"))
    repaired_cleanup = repaired["params"]["transparency"]["per_cell_alpha_cleanup"]
    assert repaired_cleanup["removed_coordinates"] == [[0, 399]]
    assert repaired_cleanup == repaired["validation"]["per_cell_alpha_cleanup"]
    await executor._generate_image_asset(context, spec)
    assert backend.calls == 14


async def test_obstacle_oversize_fit_preserves_bottom_anchor_and_repairs_locally(
    tmp_path: Path,
) -> None:
    backend = _PerCellOversizeImageBackend(parent_stage="obstacles-0")
    executor = ScrollingPreviewExecutor(
        image_service=ImageGenerationService(
            cast(ImageGenerationBackend, backend),
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ),
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    context = StageContext(
        input={"prompt": "offline"},
        tag="offline",
        run_dir=tmp_path,
        config=StageGenConfig(
            out_dir=tmp_path,
            transparency_mode=TransparencyMode.CHROMA,
        ),
    )
    spec = _per_cell_fallback_spec(tmp_path, stage="obstacles-0")

    await executor._generate_image_asset(context, spec)

    assert backend.calls == 14
    component = spec.output.with_name(f".{spec.output.stem}.cell-1-1.png")
    sidecar_path = Path(f"{component}.meta.json")
    sidecar = json.loads(await asyncio.to_thread(sidecar_path.read_text, encoding="utf-8"))
    fit = sidecar["params"]["transparency"]["per_cell_subject_fit"]
    assert fit["anchor"] == "bottom"
    assert fit["placement"][1] + fit["target_size"][1] == fit["anchor_coordinate"]
    sidecar["params"]["transparency"]["per_cell_subject_fit"]["output_sha256"] = "0" * 64
    await asyncio.to_thread(sidecar_path.write_text, json.dumps(sidecar), encoding="utf-8")

    await executor._generate_image_asset(context, spec)

    assert backend.calls == 14
    repaired = json.loads(await asyncio.to_thread(sidecar_path.read_text, encoding="utf-8"))
    assert repaired["params"]["transparency"]["per_cell_subject_fit"]["output_sha256"] == (
        sha256_hex(await asyncio.to_thread(component.read_bytes))
    )
    await executor._generate_image_asset(context, spec)
    assert backend.calls == 14


async def test_obstacle_per_cell_generation_links_style_scale_anchor(
    tmp_path: Path,
) -> None:
    backend = _SequencedImageBackend(
        (_grid_source(cross_seam=True),) * 6 + (_isolated_cell_source(),) * 8
    )
    image_service = ImageGenerationService(
        cast(ImageGenerationBackend, backend),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    executor = ScrollingPreviewExecutor(
        image_service=image_service,
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    context = StageContext(
        input={"prompt": "offline"},
        tag="offline",
        run_dir=tmp_path,
        config=StageGenConfig(
            out_dir=tmp_path,
            transparency_mode=TransparencyMode.CHROMA,
        ),
    )
    spec = _per_cell_fallback_spec(tmp_path, stage="obstacles-0")

    await executor._generate_image_asset(context, spec)

    assert backend.calls == 14
    first_refs = [ref.provenance_ref for ref in backend.requests[6].input_references]
    assert first_refs == ["concept_offline.png", ".obstacles_offline_0.cell-0-0.prior.png"]
    anchor_path = ".obstacles_offline_0.cell-0-0.png"
    for request in backend.requests[7:]:
        assert [ref.provenance_ref for ref in request.input_references] == [
            "concept_offline.png",
            anchor_path,
            request.input_references[2].provenance_ref,
        ]
        assert "style and relative scale" in request.prompt
        assert "do not copy its identity" in request.prompt
    sidecar = json.loads(
        await asyncio.to_thread(
            Path(f"{spec.output}.meta.json").read_text,
            encoding="utf-8",
        )
    )
    fallback = sidecar["params"]["transparency"]["per_cell_generation"]
    assert fallback["identity_anchor"] == {
        "path": anchor_path,
        "sha256": sha256_hex(spec.output.with_name(anchor_path).read_bytes()),
        "bytes": len(spec.output.with_name(anchor_path).read_bytes()),
        "source_cell": 0,
        "usage": "style-and-scale-only",
    }
    assert fallback["identity_dag"][1] == {
        "cell_index": 1,
        "depends_on": [0],
        "usage": "style-and-scale-only",
    }
    contract = contract_for_stage("obstacles-0")
    assert contract is not None and contract.anchor == "bottom"
    validate_canonical_grid(spec.output.read_bytes(), contract)


async def test_per_cell_component_keeps_its_own_six_attempt_retry_boundary(
    tmp_path: Path,
) -> None:
    backend = _SequencedImageBackend(
        (_grid_source(cross_seam=True),) * 6
        + (_isolated_cell_source(edge_contact=True),)
        + (_isolated_cell_source(),) * 8
    )
    image_service = ImageGenerationService(
        cast(ImageGenerationBackend, backend),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    executor = ScrollingPreviewExecutor(
        image_service=image_service,
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    context = StageContext(
        input={"prompt": "offline"},
        tag="offline",
        run_dir=tmp_path,
        config=StageGenConfig(
            out_dir=tmp_path,
            transparency_mode=TransparencyMode.CHROMA,
        ),
    )
    spec = _per_cell_fallback_spec(tmp_path)

    await executor._generate_image_asset(context, spec)

    assert backend.calls == 15
    sidecar = json.loads(
        await asyncio.to_thread(
            Path(f"{spec.output}.meta.json").read_text,
            encoding="utf-8",
        )
    )
    attempts = [
        component["generation"]["attempts"]
        for component in sidecar["params"]["transparency"]["per_cell_generation"]["components"]
    ]
    assert sorted(attempts) == [1, 1, 1, 1, 1, 1, 1, 2]


async def test_per_cell_failure_publishes_no_parent_composite(tmp_path: Path) -> None:
    backend = _SequencedImageBackend(
        (_grid_source(cross_seam=True),) * 6 + (_isolated_cell_source(edge_contact=True),)
    )
    image_service = ImageGenerationService(
        cast(ImageGenerationBackend, backend),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    executor = ScrollingPreviewExecutor(
        image_service=image_service,
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    context = StageContext(
        input={"prompt": "offline"},
        tag="offline",
        run_dir=tmp_path,
        config=StageGenConfig(
            out_dir=tmp_path,
            transparency_mode=TransparencyMode.CHROMA,
        ),
    )
    spec = _per_cell_fallback_spec(tmp_path)

    with pytest.raises(RuntimeError, match="per-cell item-"):
        await executor._generate_image_asset(context, spec)

    assert backend.calls >= 12
    assert not await asyncio.to_thread(spec.output.exists)
    assert not await asyncio.to_thread(Path(f"{spec.output}.meta.json").exists)
    raw = spec.output.with_name(f"{spec.output.stem}.raw.png")
    assert not await asyncio.to_thread(raw.exists)
    assert not await asyncio.to_thread(Path(f"{raw}.meta.json").exists)


async def test_provider_failure_does_not_enter_per_cell_fallback(tmp_path: Path) -> None:
    backend = _SequencedImageBackend((b"not-a-png",))
    image_service = ImageGenerationService(
        cast(ImageGenerationBackend, backend),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    executor = ScrollingPreviewExecutor(
        image_service=image_service,
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    context = StageContext(
        input={"prompt": "offline"},
        tag="offline",
        run_dir=tmp_path,
        config=StageGenConfig(
            out_dir=tmp_path,
            transparency_mode=TransparencyMode.CHROMA,
        ),
    )
    spec = _per_cell_fallback_spec(tmp_path)

    with pytest.raises(RetryExhaustedError):
        await executor._generate_image_asset(context, spec)

    assert backend.calls == 6
    assert not await asyncio.to_thread(lambda: list(tmp_path.glob(".*.cell-*.png")))


async def test_per_cell_cache_tamper_regenerates_only_that_component(
    tmp_path: Path,
) -> None:
    backend = _SequencedImageBackend(
        (_grid_source(cross_seam=True),) * 6 + (_isolated_cell_source(),) * 9
    )
    image_service = ImageGenerationService(
        cast(ImageGenerationBackend, backend),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    executor = ScrollingPreviewExecutor(
        image_service=image_service,
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    context = StageContext(
        input={"prompt": "offline"},
        tag="offline",
        run_dir=tmp_path,
        config=StageGenConfig(
            out_dir=tmp_path,
            transparency_mode=TransparencyMode.CHROMA,
        ),
    )
    spec = _per_cell_fallback_spec(tmp_path)
    await executor._generate_image_asset(context, spec)
    assert backend.calls == 14
    component = spec.output.with_name(f".{spec.output.stem}.cell-1-2.raw.png")
    await asyncio.to_thread(component.write_bytes, b"tampered")

    await executor._generate_image_asset(context, spec)

    assert backend.calls == 15
    assert await asyncio.to_thread(component.read_bytes) != b"tampered"
    await executor._generate_image_asset(context, spec)
    assert backend.calls == 15

    component_sidecar = Path(f"{component}.meta.json")
    sidecar = json.loads(await asyncio.to_thread(component_sidecar.read_text, encoding="utf-8"))
    sidecar["params"]["metadata"]["per_cell_generation"]["semantic_role"] = "forged"
    await asyncio.to_thread(
        component_sidecar.write_text,
        json.dumps(sidecar),
        encoding="utf-8",
    )
    await executor._generate_image_asset(context, spec)
    assert backend.calls == 16
    await executor._generate_image_asset(context, spec)
    assert backend.calls == 16


async def test_isolated_view_fallback_preserves_per_view_retry_contract(
    tmp_path: Path,
) -> None:
    reference = tmp_path / "concept_offline.png"
    reference.write_bytes(_isolated_view_source())
    backend = _SequencedImageBackend(
        (_turnaround_source(cross_seam=True),) * 6
        + (_isolated_view_source(edge_contact=True),)
        + (_isolated_view_source(),) * 3
    )
    image_service = ImageGenerationService(
        cast(ImageGenerationBackend, backend),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    executor = ScrollingPreviewExecutor(
        image_service=image_service,
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    context = StageContext(
        input={"prompt": "offline"},
        tag="offline",
        run_dir=tmp_path,
        config=StageGenConfig(
            out_dir=tmp_path,
            transparency_mode=TransparencyMode.CHROMA,
        ),
    )
    spec = _concept_fallback_spec(tmp_path, reference)

    await executor._generate_image_asset(context, spec)

    assert backend.calls == 10
    sidecar = json.loads(
        await asyncio.to_thread(
            Path(f"{spec.output}.meta.json").read_text,
            encoding="utf-8",
        )
    )
    components = sidecar["params"]["transparency"]["isolated_view_fallback"]["components"]
    assert [component["generation"]["attempts"] for component in components] == [2, 1, 1]


async def test_named_mob_concept_empty_cell_exhausts_without_fallback(
    tmp_path: Path,
) -> None:
    reference = tmp_path / "concept_offline.png"
    reference.write_bytes(_isolated_view_source())
    backend = _SequencedImageBackend((_turnaround_source(missing_last=True),))
    image_service = ImageGenerationService(
        cast(ImageGenerationBackend, backend),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    executor = ScrollingPreviewExecutor(
        image_service=image_service,
        structured_service=cast(StructuredGenerationService[WorldSpec], object()),
    )
    spec = _concept_fallback_spec(tmp_path, reference)

    with pytest.raises(
        RuntimeError,
        match=r"asset mob-concept-0 \(mob_concept_offline_0\.png\) failed:",
    ):
        await executor._fan_out(
            StageContext(
                input={"prompt": "offline"},
                tag="offline",
                run_dir=tmp_path,
                config=StageGenConfig(out_dir=tmp_path),
            ),
            (spec,),
        )

    assert backend.calls == 6
    assert not await asyncio.to_thread(spec.output.exists)
    assert not await asyncio.to_thread(lambda: list(tmp_path.glob(".*.view-*.png")))


async def test_wave_fan_out_surfaces_named_artifact_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = _executor()

    async def fail_named(
        _context: StageContext, spec: _ImageSpec, *, force: bool = False
    ) -> tuple[str, str]:
        del force
        if spec.stage == "tileset":
            raise ValueError("continuous source")
        return str(spec.output), f"{spec.output}.meta.json"

    monkeypatch.setattr(executor, "_generate_image_asset", fail_named)
    context = StageContext(
        input={"prompt": "offline"},
        tag="offline",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path),
    )
    specs = (
        _ImageSpec("items", "items", tmp_path / "items_named.png", 160, 80),
        _ImageSpec("tileset", "tiles", tmp_path / "tileset_named.png", 240, 80),
    )

    with pytest.raises(
        RuntimeError,
        match=r"asset tileset \(tileset_named\.png\) failed: continuous source",
    ):
        await executor._fan_out(context, specs)


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
        input={"prompt": "existing", "transparency_mode": "chroma"},
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


async def test_recipe_declares_ladder_climb_and_two_by_four_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tag = "offline"
    (tmp_path / f"world_spec_{tag}.json").write_text(json.dumps(_minimal_world()), encoding="utf-8")
    concept = tmp_path / f"concept_{tag}.png"
    concept_data = b"synthetic concept reference"
    concept.write_bytes(concept_data)
    captured: dict[str, _ImageSpec] = {}
    executor = _executor()

    async def capture(
        _context: StageContext, specs: tuple[_ImageSpec, ...] | list[_ImageSpec]
    ) -> tuple[str, ...]:
        captured.update((spec.stage, spec) for spec in specs)
        return ()

    async def no_master(_context: StageContext) -> tuple[str, ...]:
        return ()

    monkeypatch.setattr(executor, "_fan_out", capture)
    monkeypatch.setattr(executor, "_compose_character_master", no_master)
    context = StageContext(
        input={"prompt": "offline"},
        tag=tag,
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path),
    )

    await executor._wave_a(context)
    await executor._wave_b(context)

    assert (captured["ladder"].width, captured["ladder"].height) == (256, 1024)
    assert (captured["character-climb"].width, captured["character-climb"].height) == (
        256,
        128,
    )
    assert "strict 2-row x 4-column grid" in captured["items"].prompt
    items_contract = contract_for_stage("items")
    assert items_contract is not None
    assert items_contract.as_dict(2400, 800)["rows"] == 2
    for stage in ("character-concept", "mob-concept-0"):
        concept_spec = captured[stage]
        assert concept_spec.references == (concept,)
        assert "exact 1-row x 3-column grid" in concept_spec.prompt
        assert "independent isolated subject" in concept_spec.prompt
        assert "centered wholly inside its exact third" in concept_spec.prompt
        assert "wide, uninterrupted clear separator bands" in concept_spec.prompt
        assert "uniform mode background" in concept_spec.prompt
        for forbidden in (
            "shared ground plane",
            "shared baseline",
            "cast or contact shadow",
            "vines",
            "flourishes",
            "labels",
            "arrows",
            "panels",
            "borders",
        ):
            assert forbidden in concept_spec.prompt
        assert concept_spec.metadata is not None
        binding = concept_spec.metadata["turnaround_prompt_reference_contract"]
        assert isinstance(binding, dict)
        assert binding["version"] == "isolated-turnaround-thirds-v1"
        assert binding["layout"] == {"rows": 1, "columns": 3, "gutter": 8}
        assert binding["layout_reference"] is None
        assert binding["reference_bindings"] == [
            {
                "role": "world-concept-style-reference",
                "path": concept.name,
                "sha256": sha256_hex(concept_data),
                "bytes": len(concept_data),
            }
        ]
        assert binding["prompt_sha256"] == sha256_hex(concept_spec.prompt.encode())
        assert isinstance(binding["sha256"], str) and len(binding["sha256"]) == 64
    assert "turnaround_prompt_reference_contract" not in (captured["items"].metadata or {})


async def test_profileless_scrolling_run_skips_character_profile_cache(tmp_path: Path) -> None:
    context = StageContext(
        input={"prompt": "Whimsical storybook fantasy"},
        tag="profileless",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path),
    )

    assert await executor_module._read_character_profile(context) is None
    assert not await asyncio.to_thread(lambda: list(tmp_path.iterdir()))


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
    _write_raw_pair(raw_path)
    background = _FakeBackgroundService()
    executor = _executor(background=background)
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
    assert len(background.requests) == 1
    assert background.requests[0].output_mask is False
    assert background.requests[0].validate is not None
    assert removal["provider"] == "fake-remover"
    assert removal["mask_used"] is False
    assert removal["provenance"]["params"]["validated"] is True
    assert removal["provenance"]["response"]["request_id"] == "remove-request"
    assert sidecar["response"]["transparency"]["removal_provenance"] == "inline"
    assert ".removed-" not in serialized
    assert not await asyncio.to_thread(lambda: list(tmp_path.glob(".*.removed-*.png")))


async def test_ai_transparency_retries_uniform_alpha_then_persists_valid_output(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "asset.raw.png"
    _write_raw_pair(raw_path)
    background, backend = _retrying_background(
        (
            _alpha_png((128, 128, 128, 128)),
            _alpha_png((0, 255, 255, 255)),
        )
    )
    output = tmp_path / "asset.png"

    await _executor(background=background)._derive_transparency(
        StageContext(
            input={"prompt": "offline"},
            tag="offline",
            run_dir=tmp_path,
            config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.AI),
        ),
        _ImageSpec("asset", "offline prompt", output, 2, 2),
        raw_path,
    )

    assert backend.calls == 2
    assert all(request.output_mask is False for request in backend.requests)
    assert all(request.validate is not None for request in backend.requests)
    sidecar = json.loads(await asyncio.to_thread(Path(f"{output}.meta.json").read_text))
    assert sidecar["attempts"] == 2
    assert sidecar["validation"]["transparent_pixels"] == 1
    assert sidecar["validation"]["nontransparent_pixels"] == 3
    removal = sidecar["params"]["transparency"]["removal"]
    assert removal["provenance"]["validation"]["caller"] is True
    assert removal["provenance"]["validation"]["alpha_nontrivial"] is True
    assert output.exists()
    assert not await asyncio.to_thread(lambda: list(tmp_path.glob(".*.removed-*.png")))


async def test_grid_cell_validation_retries_inside_background_removal_boundary(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "items.raw.png"
    _write_grid_raw_pair(raw_path)
    background, backend = _retrying_background((_grid_alpha(missing_last=True), _grid_alpha()))
    output = tmp_path / "items.png"

    await _executor(background=background)._derive_transparency(
        StageContext(
            input={"prompt": "offline"},
            tag="offline",
            run_dir=tmp_path,
            config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.AI),
        ),
        _ImageSpec("items", "eight isolated items", output, 160, 80),
        raw_path,
    )

    assert backend.calls == 2
    sidecar_text = await asyncio.to_thread(Path(f"{output}.meta.json").read_text, encoding="utf-8")
    sidecar = json.loads(sidecar_text)
    assert sidecar["validation"]["cells_nonempty"] == 8
    assert sidecar["validation"]["boundaries_isolated"] is True
    assert sidecar["validation"]["cross_cell_contamination"] is False
    normalization = sidecar["validation"]["grid_normalization"]
    raw = await asyncio.to_thread(raw_path.read_bytes)
    assert normalization["version"] == "per-cell-isolation-v2"
    assert normalization["transform_count"] == 8
    assert normalization["input_sha256"] == sha256_hex(raw)
    assert normalization["input_bytes"] == len(raw)
    assert normalization["input_role"] == "retained-raw-artifact"
    items_contract = contract_for_stage("items")
    assert items_contract is not None
    assert normalization["semantic_contract"] == grid_semantic_contract(items_contract, 160, 80)
    assert normalization["output_sha256"] == sha256_hex(await asyncio.to_thread(output.read_bytes))
    assert sidecar["params"]["transparency"]["grid_normalization"] == normalization
    assert sidecar["params"]["transparency"]["processor"] == {
        "kind": "ai-background-removal+grid-cell-normalization",
        "version": "per-cell-isolation-v2",
    }


async def test_ai_transparency_exhausts_six_invalid_outputs_without_canonical_pair(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "asset.raw.png"
    _write_raw_pair(raw_path)
    background, backend = _retrying_background(
        (
            _alpha_png((0, 0, 0, 0)),
            _alpha_png((128, 128, 128, 128)),
            _alpha_png((255, 255, 255, 255)),
            b"",
            b"malformed",
            _alpha_png((128, 128, 128, 128)),
        )
    )
    output = tmp_path / "asset.png"

    with pytest.raises(RetryExhaustedError) as captured:
        await _executor(background=background)._derive_transparency(
            StageContext(
                input={"prompt": "offline"},
                tag="offline",
                run_dir=tmp_path,
                config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.AI),
            ),
            _ImageSpec("asset", "offline prompt", output, 2, 2),
            raw_path,
        )

    assert captured.value.attempts == backend.calls == 6
    raw_exists, raw_meta_exists, output_exists, output_meta_exists = await asyncio.to_thread(
        lambda: (
            raw_path.exists(),
            Path(f"{raw_path}.meta.json").exists(),
            output.exists(),
            Path(f"{output}.meta.json").exists(),
        )
    )
    assert raw_exists
    assert raw_meta_exists
    assert not output_exists
    assert not output_meta_exists
    assert not await asyncio.to_thread(lambda: list(tmp_path.glob(".*.removed-*.png")))


async def test_ai_mode_opaque_asset_bypasses_background_removal(tmp_path: Path) -> None:
    background, backend = _retrying_background((_png(alpha=True),))
    output = tmp_path / "opaque.png"

    await _executor(background=background)._generate_image_asset(
        StageContext(
            input={"prompt": "offline"},
            tag="offline",
            run_dir=tmp_path,
            config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.AI),
        ),
        _ImageSpec("opaque", "offline prompt", output, 2, 2, transparent=False),
    )

    assert backend.calls == 0
    with Image.open(output) as image:
        assert image.size == (2, 2)
        assert image.mode == "RGB"


async def test_executor_composite_sidecar_flows_into_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        manifest_module,
        "_collect_runtime_assets",
        lambda _run_dir, manifest_tag, *_args: (
            [],
            {
                "path": f"world_spec_{manifest_tag}.json",
                "provenancePath": f"world_spec_{manifest_tag}.json.meta.json",
            },
        ),
    )
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
                        "matte_version": CHROMA_MATTE_VERSION,
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
    master = next(
        entry for entry in manifest["canonical_artifacts"] if entry["path"] == master_name
    )
    assert master["transparency"]["lineage"]["source_paths"] == [
        f"character_{tag}_combined_strip_{state}.png" for state in _STATES
    ]


async def test_executor_manifest_projects_the_current_game_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def read_current_game(_context: StageContext) -> Any:
        return SimpleNamespace(
            contract=SimpleNamespace(schema_version=3),
            resident=SimpleNamespace(is_still=False),
        )

    async def write_manifest(**kwargs: object) -> Any:
        captured.update(kwargs)
        return SimpleNamespace(artifacts=("manifest.json", "manifest.json.meta.json"))

    monkeypatch.setattr(executor_module, "_read_game_contract", read_current_game)
    monkeypatch.setattr(executor_module, "write_scrolling_preview_manifest", write_manifest)
    context = StageContext(
        input={
            "prompt": "offline",
            "game": {
                "schema_version": 1,
                "kind": "game-contract-binding-v1",
                "ref": "library/games/test-game/game.toml",
                "source_sha256": "a" * 64,
            },
        },
        tag="current-game",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.CHROMA),
    )

    artifacts = await _executor().run_scrolling_preview_stage("manifest", context)

    assert artifacts == ("manifest.json", "manifest.json.meta.json")
    assert captured["game_contract"] is True


def _village_context(tmp_path: Path, *, tag: str = "kettle-chroma") -> StageContext:
    return StageContext(
        input={
            "prompt": "original ridge crossing",
            "village": {"schema_version": 1, "kind": "village_hub_v1"},
        },
        tag=tag,
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.CHROMA),
    )


async def test_village_spec_is_designed_from_the_concept_and_resumes_from_a_content_bound_cache(
    tmp_path: Path,
) -> None:
    backend = _RecordingStructuredBackend()
    executor = ScrollingPreviewExecutor(
        image_service=cast(ImageGenerationService, object()),
        structured_service=StructuredGenerationService[object](
            backend,
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ),
    )
    context = _village_context(tmp_path)
    concept = tmp_path / f"concept_{context.tag}.png"
    await asyncio.to_thread(concept.write_bytes, b"synthetic concept reference")

    paths = await executor.run_scrolling_preview_stage("village-spec", context)

    output = tmp_path / f"village_spec_{context.tag}.json"
    assert tuple(paths) == (str(output), f"{output}.meta.json")
    spec = VillageSpec.model_validate_json(await asyncio.to_thread(output.read_text))
    assert len(spec.npcs) == VILLAGE_NPC_COUNT

    request = backend.requests[0]
    assert request.schema.name == VILLAGE_SPEC_SCHEMA_NAME
    assert request.schema.strict is True
    # The component sanitizes provider-unsupported keywords out of the schema it sends, so the
    # comparable part is the shape: the bible's own fields, and `$defs` still carrying the
    # external-standard vocabulary the recipe is required to preserve verbatim.
    declared = VillageSpec.model_json_schema()
    sent = request.schema.json_schema
    assert cast(Mapping[str, object], sent["properties"]).keys() == (
        cast(Mapping[str, object], declared["properties"]).keys()
    )
    assert sent["required"] == declared["required"]
    assert set(cast(Mapping[str, object], sent["$defs"])) == {"VillageNpc", "VillageFixture"}
    assert sent["additionalProperties"] is False
    # The concept is the run's style root: a settlement designed without seeing it reads as a
    # different world's town dropped into this one.
    assert [reference.provenance_ref for reference in request.references] == [str(concept)]
    assert request.metadata == {
        "stage": "village-spec",
        "user_prompt": "original ridge crossing",
    }
    assert f"{VILLAGE_NPC_COUNT} residents" in request.prompt
    assert "exactly 8 village fixtures" in request.prompt
    assert "not monsters" in request.prompt
    assert "not the player character" in request.prompt

    sidecar = json.loads(await asyncio.to_thread(Path(paths[1]).read_text, encoding="utf-8"))
    # The roster the accepted bible actually carries, recorded so the cache can re-derive it from
    # the artifact later. Body plans are included because the turnaround prompts are built from
    # them, so a changed plan means changed artwork.
    roster = {
        "village_schema_name": VILLAGE_SPEC_SCHEMA_NAME,
        "village_npc_names": [npc.name for npc in spec.npcs],
        "village_npc_role_labels": [npc.role_label for npc in spec.npcs],
        "village_npc_body_plans": [npc.body_plan for npc in spec.npcs],
        "village_fixture_names": [fixture.name for fixture in spec.fixtures],
        "village_final_validation": True,
    }
    assert {key: sidecar["validation"][key] for key in roster} == roster
    # Purely additive: the bible is a new artifact beside the concept, and `world_spec_<tag>.json`
    # is neither read nor written, so every artifact an existing run holds stays cache-valid.
    written = await asyncio.to_thread(lambda: sorted(path.name for path in tmp_path.iterdir()))
    assert written == [concept.name, output.name, f"{output.name}.meta.json"]

    await executor.run_scrolling_preview_stage("village-spec", context)
    assert backend.village_calls == 1

    # Existence is never the test: a bible that no longer re-derives the roster its own sidecar
    # recorded is designed afresh rather than left to mis-design nine image stages.
    await asyncio.to_thread(output.write_text, json.dumps(_minimal_world()), encoding="utf-8")
    await executor.run_scrolling_preview_stage("village-spec", context)
    assert backend.village_calls == 2
    assert VillageSpec.model_validate_json(await asyncio.to_thread(output.read_text)) == spec

    # And the pairing runs the other way too: a sidecar whose recorded roster was removed or
    # rewritten no longer describes the artifact beside it, which is exactly the state a replaced
    # or hand-edited bible leaves behind.
    sidecar_path = Path(paths[1])
    stale = json.loads(await asyncio.to_thread(sidecar_path.read_text, encoding="utf-8"))
    stale["validation"]["village_npc_names"] = ["Someone Else"] * VILLAGE_NPC_COUNT
    await asyncio.to_thread(sidecar_path.write_text, json.dumps(stale), encoding="utf-8")
    await executor.run_scrolling_preview_stage("village-spec", context)
    assert backend.village_calls == 3


async def test_village_spec_refuses_to_run_without_the_versioned_opt_in(tmp_path: Path) -> None:
    executor = ScrollingPreviewExecutor(
        image_service=cast(ImageGenerationService, object()),
        structured_service=cast(StructuredGenerationService[object], object()),
    )
    context = StageContext(
        input={"prompt": "original ridge crossing"},
        tag="kettle-chroma",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.CHROMA),
    )

    with pytest.raises(ValueError, match="requires the versioned village opt-in"):
        await executor.run_scrolling_preview_stage("village-spec", context)


async def test_village_concepts_reuse_the_turnaround_and_obstacle_sheet_spec_shapes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = _executor()
    context = _village_context(tmp_path)
    spec = VillageSpec.model_validate(_village_payload())
    await asyncio.to_thread(
        (tmp_path / f"village_spec_{context.tag}.json").write_text,
        spec.model_dump_json(),
        encoding="utf-8",
    )
    concept = tmp_path / f"concept_{context.tag}.png"
    await asyncio.to_thread(concept.write_bytes, b"synthetic concept reference")
    captured: list[_ImageSpec] = []

    async def capture(_context: StageContext, specs: Sequence[_ImageSpec]) -> tuple[str, ...]:
        captured.extend(specs)
        return ()

    monkeypatch.setattr(executor, "_fan_out", capture)
    await executor.run_scrolling_preview_stage("village-concepts", context)

    assert [item.stage for item in captured] == [
        *(f"village-npc-concept-{slot}" for slot in range(VILLAGE_NPC_COUNT)),
        "village-fixtures",
    ]
    # Nine image calls total for a whole village: four turnarounds and four strips per resident
    # pair, plus this one fixture sheet.
    assert len(captured) == VILLAGE_NPC_COUNT + 1
    assert all(item.width == 2400 and item.height == 800 for item in captured)
    assert all(item.transparent for item in captured)

    template = executor_module._template_root() / "obstacle_template.png"
    for slot, item in enumerate(captured[:VILLAGE_NPC_COUNT]):
        # Built from the shared turnaround builder rather than a village wording, so a resident
        # sheet is validated by, and rescued by, the identical machinery a mob sheet is.
        assert item.prompt == executor_module._turnaround_prompt(
            npc_turnaround_subject(spec.npcs[slot])
        )
        assert item.output == tmp_path / f"npc_concept_{context.tag}_{slot}.png"
        assert item.references == (concept,)
        metadata = item.metadata or {}
        assert metadata["slot"] == slot
        assert metadata["role_label"] == spec.npcs[slot].role_label
        contract = metadata["turnaround_prompt_reference_contract"]
        assert isinstance(contract, dict)
        assert contract["layout"] == {"rows": 1, "columns": 3, "gutter": 8}
        assert [binding["path"] for binding in contract["reference_bindings"]] == [concept.name]
        assert executor_module._asset_kind_for_image_stage(item.stage) == "concept_art"

    fixtures = captured[-1]
    assert fixtures.output == tmp_path / f"village_fixtures_{context.tag}.png"
    assert fixtures.references == (template, concept)
    fixtures_metadata = fixtures.metadata or {}
    assert fixtures_metadata["sheet_theme"] == spec.fixtures_theme
    assert fixtures.prompt == executor_module._village_fixtures_prompt(spec)
    # The per-cell fallback is the reason the fixture sheet is built as an obstacle sheet: an
    # exhausted sheet degrades into eight separately generated cells instead of failing the run.
    assert executor_module._eligible_per_cell_stage(fixtures) is True
    assert executor_module._asset_kind_for_image_stage(fixtures.stage) == "asset_sheet"


async def test_village_strips_bind_each_resident_to_its_own_turnaround_and_fail_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = _executor()
    context = _village_context(tmp_path)
    spec = VillageSpec.model_validate(_village_payload())
    await asyncio.to_thread(
        (tmp_path / f"village_spec_{context.tag}.json").write_text,
        spec.model_dump_json(),
        encoding="utf-8",
    )
    turnaround = _turnaround_source()
    for slot in range(VILLAGE_NPC_COUNT - 1):
        await asyncio.to_thread(
            (tmp_path / f"npc_concept_{context.tag}_{slot}.png").write_bytes, turnaround
        )
    captured: list[_ImageSpec] = []

    async def capture(_context: StageContext, specs: Sequence[_ImageSpec]) -> tuple[str, ...]:
        captured.extend(specs)
        return ()

    monkeypatch.setattr(executor, "_fan_out", capture)
    await executor.run_scrolling_preview_stage("village-strips", context)

    template = executor_module._template_root() / "character_template.png"
    assert [item.stage for item in captured] == [
        f"village-npc-{slot}-idle" for slot in range(VILLAGE_NPC_COUNT)
    ]
    for slot, item in enumerate(captured):
        assert item.output == tmp_path / f"npc_{context.tag}_{slot}_idle.png"
        assert item.references == (
            tmp_path / f"npc_concept_{context.tag}_{slot}.png",
            template,
        )
        assert (item.width, item.height) == (2400, 800)
        assert executor_module._asset_kind_for_image_stage(item.stage) == "character_sprite"
        assert item.prompt == executor_module._npc_idle_strip_prompt(spec.npcs[slot])

    # The head-on check reads a silhouette and cannot tell one resident's side view from their
    # front, so the ceiling comes from that resident's own turnaround.
    expected = side_view_symmetry_ceiling(turnaround)
    assert [(item.metadata or {}).get("maximum_frame_symmetry") for item in captured] == [
        expected,
        expected,
        expected,
        # The last resident's turnaround is missing: the ceiling falls back to the default rather
        # than failing a stage that does not own the measurement.
        None,
    ]
    assert captured[-1].metadata is None


def test_a_resident_idle_prompt_is_the_mob_strip_directives_with_a_settled_motion() -> None:
    """Every clause outside the motion phrase is called, not restated.

    The facing and containment wordings were arrived at against measured failures - half a run's
    strips arriving mirrored, and `character-attack` failing cell isolation once the containment
    clause was demoted to a sub-clause - so a paraphrase here would quietly opt the village out
    of both corrections while looking equivalent.
    """

    npc = VillageSpec.model_validate(_village_payload()).npcs[0]
    prompt = executor_module._npc_idle_strip_prompt(npc)

    assert executor_module._side_view_facing_directive() in prompt
    assert (
        executor_module._cell_containment_directive(
            grid="4x1",
            subject="frame",
            appendages="tools, aprons, cloaks, and carried goods",
        )
        in prompt
    )
    assert (
        "four visibly distinct phases of a settled standing idle - weight shift, breath, and a "
        "small gesture; the feet stay planted" in prompt
    )
    assert "CLEAN PLATE: do not render template lines, labels, borders, or shadows." in prompt
    assert npc.name in prompt and npc.role_label in prompt


def test_the_fixture_prompt_states_the_obstacle_sheet_grid_and_names_every_cell() -> None:
    spec = VillageSpec.model_validate(_village_payload())
    prompt = executor_module._village_fixtures_prompt(spec)

    assert spec.fixtures_theme in prompt
    assert (
        executor_module._cell_containment_directive(
            grid="2-row x 4-column",
            subject="fixture",
            appendages="awnings, poles, ropes, and hanging goods",
        )
        in prompt
    )
    assert "CLEAN PLATE: do not render template lines, labels, borders, or shadows." in prompt
    for index, fixture in enumerate(spec.fixtures):
        assert f"cell {index + 1} {fixture.name}: {fixture.brief}" in prompt


def _minimal_world() -> dict[str, object]:
    return {
        "world": {"name": "Vale", "one_liner": "Quiet.", "narrative": "Rain."},
        "mobs": [
            {
                "tier_label": "scout",
                "body_plan": "winged avian",
                "name": "Mote",
                "brief": "A pale bird.",
            }
        ],
        "obstacles": [
            {
                "sheet_theme": "ruins",
                "props": [{"name": f"prop {index}", "brief": "weathered"} for index in range(8)],
            }
        ],
        "items": [
            {"kind": kind, "name": f"item {index}", "brief": "small"}
            for index, kind in enumerate(
                (
                    "coin",
                    "vial",
                    "shard",
                    "key",
                    "charm",
                    "map",
                    "tool",
                    "blade",
                )
            )
        ],
        "layers": [
            {
                "id": "sky",
                "title": "Sky",
                "z_index": 0,
                "parallax": 0.0,
                "opaque": True,
                "paint_region": "all",
                "description": "Clouds",
            },
            {
                "id": "foreground",
                "title": "Foreground",
                "z_index": 1,
                "parallax": 1.8,
                "opaque": False,
                "paint_region": "edges",
                "description": "Leaves",
            },
        ],
    }


def _tileset_fallback_context(tmp_path: Path) -> StageContext:
    tag = "offline"
    world_path = tmp_path / f"world_spec_{tag}.json"
    world_data = json.dumps(_minimal_world()).encode()
    write_artifact_with_provenance(
        world_path,
        BinaryArtifact(data=world_data, media_type="application/json"),
        ProvenanceInput(
            provider="local",
            model="world-spec-fixture",
            prompt="Canonical fixture world spec",
            attempts=1,
        ),
    )
    concept = Image.new("RGB", (64, 64), (120, 170, 210))
    ImageDraw.Draw(concept).ellipse((8, 8, 55, 55), fill=(175, 135, 70))
    concept_path = tmp_path / f"concept_{tag}.png"
    write_artifact_with_provenance(
        concept_path,
        BinaryArtifact(data=_image_bytes(concept), media_type="image/png"),
        ProvenanceInput(
            provider="fake-image",
            model="concept-fixture",
            prompt="Canonical fixture world concept",
            attempts=1,
        ),
    )
    return StageContext(
        input={"prompt": "Whimsical storybook fantasy"},
        tag=tag,
        run_dir=tmp_path,
        config=StageGenConfig(
            out_dir=tmp_path,
            transparency_mode=TransparencyMode.CHROMA,
        ),
    )


def _tileset_style_context() -> executor_module._StyleAnchorContext:
    resources = load_image_style_resources()
    anchor = materialize_style_anchor(
        StyleModeSelection(
            schema_version=1,
            kind="image_style_selection_v1",
            style_mode="gouache_illustration_2d",
        ),
        resources,
    )
    raw = json.dumps(
        anchor.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    artifact_sha256 = sha256_hex(raw)
    return executor_module._StyleAnchorContext(
        anchor=anchor,
        identity={
            "schema_version": anchor.schema_version,
            "kind": anchor.kind,
            "anchor_sha256": canonical_style_anchor_digest(anchor),
            "style_mode": anchor.style_mode,
            "compiler_version": anchor.compiler_version,
            "compiler_sha256": anchor.compiler_sha256,
            "resource_sha256": anchor.resource_sha256,
            "skill_sha256": anchor.skill_sha256,
            "vocabulary_sha256": anchor.vocabulary_sha256,
            "artifact_ref": f"sha256:{artifact_sha256}",
            "artifact_sha256": artifact_sha256,
            "artifact_bytes": len(raw),
        },
        artifact_bytes=len(raw),
    )
