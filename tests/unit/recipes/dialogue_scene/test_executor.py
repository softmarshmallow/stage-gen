from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from stage_gen.components import (
    BackgroundRemovalRequest,
    BackgroundRemovalService,
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageGenerationService,
    StructuredGenerationRequest,
    StructuredGenerationResult,
    StructuredGenerationService,
    append_style_anchor_once,
    canonical_style_anchor_digest,
    render_style_anchor,
)
from stage_gen.components._types import ProviderResponseMetadata
from stage_gen.components.background_removal.models import ProviderBackgroundRemoval
from stage_gen.components.image_generation.models import ProviderImage
from stage_gen.components.structured_generation import ProviderStructuredOutput
from stage_gen.config import StageGenConfig
from stage_gen.contracts import BinaryArtifact, ProvenanceInput
from stage_gen.image_prompting import load_image_style_resources
from stage_gen.recipes.base import StageContext
from stage_gen.recipes.dialogue_scene import executor as executor_module
from stage_gen.recipes.dialogue_scene.executor import (
    DialogueExecutorContext,
    DialogueSceneExecutor,
)
from stage_gen.recipes.dialogue_scene.identity import canonical_sha256, content_sha256
from stage_gen.recipes.dialogue_scene.models import DialogueBundleV3
from stage_gen.recipes.dialogue_scene.prompts import TEMPLATE_DIGEST
from stage_gen.recipes.dialogue_scene.schema import dialogue_plan_json_schema
from stage_gen.reliability import RetryExhaustedError, RetryPolicy, write_artifact_with_provenance

from .test_contracts import profile_request_value, request_value


def _png() -> bytes:
    output = BytesIO()
    image = Image.new("RGB", (1024, 1536), (255, 0, 255))
    image.paste((20, 30, 80), (256, 256, 768, 1280))
    image.save(output, format="PNG")
    return output.getvalue()


def _sized_png(width: int, height: int) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), (20, 30, 80)).save(output, format="PNG")
    return output.getvalue()


def _flat_png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (1024, 1536), (255, 0, 255)).save(output, format="PNG")
    return output.getvalue()


def _removed_png() -> bytes:
    output = BytesIO()
    image = Image.new("RGBA", (1024, 1536), (20, 30, 80, 255))
    image.paste((20, 30, 80, 0), (0, 0, 512, 1536))
    image.save(output, format="PNG")
    return output.getvalue()


class SequencedImageBackend:
    provider = "fake"
    model = "fake-image"
    secrets: tuple[str, ...] = ()

    def __init__(self, outputs: list[bytes]) -> None:
        self.outputs = outputs
        self.calls = 0

    async def generate_once(self, _request: ImageGenerationRequest) -> ProviderImage:
        index = min(self.calls, len(self.outputs) - 1)
        self.calls += 1
        return ProviderImage(
            data=self.outputs[index],
            media_type="image/png",
            response_metadata=ProviderResponseMetadata(),
        )

    async def aclose(self) -> None:
        pass


class SequencedBackgroundBackend:
    provider = "fake"
    model = "fake-removal"
    secrets: tuple[str, ...] = ()

    def __init__(self, outputs: list[bytes]) -> None:
        self.outputs = outputs
        self.calls = 0

    async def remove_once(self, _request: BackgroundRemovalRequest) -> ProviderBackgroundRemoval:
        index = min(self.calls, len(self.outputs) - 1)
        self.calls += 1
        return ProviderBackgroundRemoval(
            data=self.outputs[index],
            media_type="image/png",
            source_url="data:image/png;base64,stable",
            source_kind="inline",
            width=1024,
            height=1536,
            response_metadata=ProviderResponseMetadata(),
        )

    async def aclose(self) -> None:
        pass


class FakeImages:
    def __init__(
        self,
        *,
        attempts: int = 1,
        exhausted: bool = False,
        vary_forced_concept: bool = False,
    ) -> None:
        self.attempts = attempts
        self.exhausted = exhausted
        self.vary_forced_concept = vary_forced_concept
        self.concept_calls = 0
        self.requests: list[ImageGenerationRequest] = []

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        self.requests.append(request)
        if self.exhausted:
            raise RetryExhaustedError("fake image", ValueError("bad media"), 6)
        role = request.metadata.get("role")
        if role == "concept":
            self.concept_calls += 1
        data = (
            _sized_png(1024, 1536)
            if role == "concept" and self.vary_forced_concept and self.concept_calls > 1
            else _png()
            if role != "background"
            else _sized_png(1672, 941)
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


class FakeStructured:
    def __init__(
        self,
        request: dict[str, object],
        *,
        plan_shared_locks: dict[str, str] | None = None,
    ) -> None:
        self.request = request
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


class InvalidStyleBackend:
    provider = "fake"
    model = "fake-invalid-style"
    secrets: tuple[str, ...] = ()

    def __init__(self) -> None:
        self.calls = 0

    async def generate_once(
        self, _request: StructuredGenerationRequest[object]
    ) -> ProviderStructuredOutput:
        self.calls += 1
        value = {
            "schema_version": 1,
            "kind": "image_style_selection_v1",
            "style_mode": "invented_semi_realistic_mode",
        }
        return ProviderStructuredOutput(
            decoded=value,
            raw_text=json.dumps(value),
            response_metadata=ProviderResponseMetadata(),
        )

    async def aclose(self) -> None:
        pass


def _context(
    tmp_path: Path,
    request: dict[str, object],
    *,
    character_library_root: Path | None = None,
) -> StageContext:
    return StageContext(
        input=request,
        tag="dialogue-test-chroma",
        run_dir=tmp_path,
        config=StageGenConfig(
            out_dir=tmp_path,
            character_library_root=character_library_root,
            transparency_mode="chroma",
        ),
    )


def _profile_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repository = Path(__file__).resolve().parents[4]
    source = repository / "library/characters/mira-vale-cartographer/profile.toml"
    root = tmp_path / "authored-library"
    target = root / "library/characters/mira-vale-cartographer/profile.toml"
    target.parent.mkdir(parents=True)
    target.write_bytes(source.read_bytes())
    return target


@pytest.mark.asyncio
async def test_profile_v3_requires_explicit_character_library_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _profile_source(tmp_path, monkeypatch)
    request = profile_request_value(content_sha256(source.read_bytes()))
    executor = DialogueSceneExecutor(
        DialogueExecutorContext(
            structured=FakeStructured(request),
            images=FakeImages(),
        )
    )
    with pytest.raises(ValueError, match="requires character_library_root"):
        await executor.run_stage("profile-resolve", _context(tmp_path / "run", request))


@pytest.mark.asyncio
async def test_profile_v3_resolves_binds_and_overrides_provider_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _profile_source(tmp_path, monkeypatch)
    request = profile_request_value(content_sha256(source.read_bytes()))
    images = FakeImages()
    structured = FakeStructured(
        request,
        plan_shared_locks={
            "identity": "provider invented identity",
            "wardrobe": "provider invented wardrobe",
            "pose": "fixed conversational pose",
            "lighting": "soft evening light",
            "style": "provider style draft",
        },
    )
    executor = DialogueSceneExecutor(DialogueExecutorContext(structured=structured, images=images))
    context = _context(
        tmp_path / "run",
        request,
        character_library_root=source.parents[3],
    )
    for stage in (
        "prepare",
        "profile-resolve",
        "style-selection",
        "appearance-concept",
        "scene-plan",
        "neutral",
    ):
        await executor.run_stage(stage, context)

    profile_bytes = (context.run_dir / "character-profile.json").read_bytes()
    assert not profile_bytes.endswith(b"\n")
    profile = json.loads(profile_bytes)
    assert profile["profile_id"] == "mira-vale-cartographer"
    profile_meta = json.loads(
        (context.run_dir / "character-profile.json.meta.json").read_text(encoding="utf-8")
    )
    assert (
        profile_meta["params"]["character_profile_source_sha256"]
        == (
            request["character_profile"]["source_sha256"]  # type: ignore[index]
        )
    )
    assert profile_meta["params"]["character_profile_sha256"] == content_sha256(profile_bytes)
    assert profile_meta["inputs"] == [
        {
            "ref": request["character_profile"]["ref"],  # type: ignore[index]
            "sha256": request["character_profile"]["source_sha256"],  # type: ignore[index]
            "source": "content",
            "bytes": len(source.read_bytes()),
            "media_type": "application/toml",
        }
    ]
    plan = json.loads((context.run_dir / "plan.json").read_text(encoding="utf-8"))
    assert (plan["schema_version"], plan["kind"], plan["recipe_version"]) == (
        3,
        "dialogue-scene-plan-v3",
        "dialogue-scene-v4",
    )
    assert "Mira Vale" in plan["shared_locks"]["identity"]
    assert "provider invented identity" not in plan["shared_locks"]["identity"]
    assert "Weathered teal field jacket" in plan["shared_locks"]["wardrobe"]
    assert "provider invented wardrobe" not in plan["shared_locks"]["wardrobe"]
    assert all(
        item.metadata["character_profile_sha256"] == content_sha256(profile_bytes)
        for item in images.requests
    )
    assert "Required durable acceptance invariants" in images.requests[0].prompt
    assert structured.calls[-1].metadata["character_profile_sha256"] == content_sha256(
        profile_bytes
    )

    call_counts = (len(images.requests), len(structured.calls))
    for stage in (
        "profile-resolve",
        "style-selection",
        "appearance-concept",
        "scene-plan",
        "neutral",
    ):
        await executor.run_stage(stage, context)
    assert (len(images.requests), len(structured.calls)) == call_counts

    for stage in ("background", "expressions", "canonicalize", "bundle"):
        await executor.run_stage(stage, context)
    bundle = DialogueBundleV3.model_validate_json((context.run_dir / "bundle.json").read_bytes())
    assert bundle.character_profile_binding.source_sha256 == content_sha256(source.read_bytes())
    assert bundle.character_profile.sha256 == bundle.character_profile_sha256
    assert bundle.scene_data.appearance.label == "Mira Vale"
    assert bundle.scene_data.appearance.visual_identity == profile["visual_identity"]
    bundle_meta = json.loads(
        (context.run_dir / "bundle.json.meta.json").read_text(encoding="utf-8")
    )
    assert bundle_meta["params"]["character_profile_sha256"] == bundle.character_profile_sha256

    source.write_text(source.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source_sha256 mismatch"):
        await executor.run_stage("profile-resolve", context)


def test_background_validation_records_the_selected_recipe_version() -> None:
    validation = executor_module._background_validator(
        source=_png(),
        width=1024,
        height=1536,
        recipe_contract="dialogue-scene-v4",
    )(BinaryArtifact(data=_removed_png(), media_type="image/png"), None)

    assert validation["recipe_contract"] == "dialogue-scene-v4"


@pytest.mark.asyncio
async def test_prompt_reference_attempt_and_resume_flow(tmp_path: Path) -> None:
    request = request_value()
    images = FakeImages(attempts=3)
    structured = FakeStructured(request)
    executor = DialogueSceneExecutor(DialogueExecutorContext(structured=structured, images=images))
    context = _context(tmp_path, request)

    await executor.run_stage("prepare", context)
    request_sidecar = json.loads((tmp_path / "request.json.meta.json").read_text(encoding="utf-8"))
    assert request_sidecar["schema_version"] == 2
    await executor.run_stage("style-selection", context)
    await executor.run_stage("appearance-concept", context)
    await executor.run_stage("scene-plan", context)
    await executor.run_stage("neutral", context)

    assert len(images.requests) == 2
    assert images.requests[0].input_references == ()
    assert len(images.requests[1].input_references) == 1
    provenance_ref = images.requests[1].input_references[0].provenance_ref
    assert provenance_ref is not None
    assert provenance_ref.startswith("assets/concept.png#sha256=")
    assert structured.calls[0].schema.name == "image_style_selection_v1"
    assert structured.calls[0].references == ()
    concept_direction = "Original clean Japanese anime visual-novel character direction"
    assert concept_direction in structured.calls[0].prompt
    assert len(structured.calls[1].references) == 1
    assert structured.calls[1].schema.json_schema == dialogue_plan_json_schema()
    anchor = images.requests[0].style_anchor
    assert anchor is not None
    assert anchor.style_mode == "cel_shaded_anime_2d"
    assert anchor.medium_keyword == "clean 2D Japanese anime illustration"
    assert "semi-realistic rendering" in anchor.exclusions
    assert [item.asset_kind for item in images.requests] == ["concept_art", "character_sprite"]
    assert all("Canonical style anchor" not in item.prompt for item in images.requests)
    assert images.requests[0].prompt.count(concept_direction) == 1
    assert images.requests[0].prompt.count("Adult woman in a navy cardigan") == 1
    assert "Occupation or role context only: Graduate researcher" in images.requests[0].prompt
    assert "occupation-associated attire" in images.requests[0].prompt
    assert "visual novel character sprite" in render_style_anchor(anchor, "character_sprite")
    plan_metadata = structured.calls[1].metadata
    assert plan_metadata["style_anchor_sha256"] == canonical_style_anchor_digest(anchor)
    assert plan_metadata["style_anchor_path"] == "style-anchor.json"
    assert plan_metadata["style_anchor_artifact_sha256"] == content_sha256(
        (tmp_path / "style-anchor.json").read_bytes()
    )
    assert plan_metadata["style_anchor_provenance_path"] == "style-anchor.json.meta.json"
    assert plan_metadata["style_anchor_provenance_sha256"] == content_sha256(
        (tmp_path / "style-anchor.json.meta.json").read_bytes()
    )
    assert plan_metadata["style_resource_sha256"] == anchor.resource_sha256
    assert plan_metadata["style_compiler_sha256"] == anchor.compiler_sha256
    plan = json.loads((tmp_path / "plan.json").read_text(encoding="utf-8"))
    assert plan["request_sha256"] == canonical_sha256(request)
    assert plan["appearance_id"] == "mio-researcher"
    assert [state["id"] for state in plan["states"]] == [
        "neutral",
        "delighted",
        "flustered",
        "concerned",
    ]
    assert plan["prompt_templates"] == [
        {"id": "neutral-v5", "sha256": TEMPLATE_DIGEST},
        {"id": "expression-edit-v5", "sha256": TEMPLATE_DIGEST},
    ]
    assert "Adult woman in a navy cardigan" in plan["shared_locks"]["identity"]
    assert "Adult woman in a navy cardigan" in plan["shared_locks"]["wardrobe"]
    assert "occupation-associated attire" in plan["shared_locks"]["wardrobe"]
    assert "Adult woman in a navy cardigan" in images.requests[1].prompt
    ledger = json.loads((tmp_path / "attempts.json").read_text(encoding="utf-8"))
    concept = [entry for entry in ledger["attempts"] if entry["role"] == "concept"]
    assert [entry["outcome"] for entry in concept] == ["rejected", "rejected", "selected"]

    await executor.run_stage("appearance-concept", context)
    assert len(images.requests) == 2


@pytest.mark.asyncio
async def test_public_force_env_rebuilds_stage_and_downstream_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = request_value()
    images = FakeImages()
    structured = FakeStructured(request)
    executor = DialogueSceneExecutor(DialogueExecutorContext(structured=structured, images=images))
    context = _context(tmp_path, request)
    for stage in ("prepare", "style-selection", "appearance-concept", "scene-plan", "neutral"):
        await executor.run_stage(stage, context)
    assert (len(images.requests), len(structured.calls)) == (2, 2)

    monkeypatch.setenv("STAGE_GEN_FORCE", "1")
    for stage in ("style-selection", "appearance-concept", "scene-plan", "neutral"):
        await executor.run_stage(stage, context)
    assert (len(images.requests), len(structured.calls)) == (4, 4)

    monkeypatch.delenv("STAGE_GEN_FORCE")
    for stage in ("style-selection", "appearance-concept", "scene-plan", "neutral"):
        await executor.run_stage(stage, context)
    assert (len(images.requests), len(structured.calls)) == (4, 4)


@pytest.mark.asyncio
async def test_targeted_force_rebuilds_root_and_rechecks_descendant_cache(tmp_path: Path) -> None:
    request = request_value()
    images = FakeImages()
    structured = FakeStructured(request)
    context = _context(tmp_path, request)
    initial = DialogueSceneExecutor(DialogueExecutorContext(structured=structured, images=images))
    for stage in ("prepare", "style-selection", "appearance-concept", "scene-plan", "neutral"):
        await initial.run_stage(stage, context)
    assert (len(images.requests), len(structured.calls)) == (2, 2)

    forced = DialogueSceneExecutor(
        DialogueExecutorContext(
            structured=structured,
            images=images,
            force_stages=frozenset({"appearance-concept"}),
        )
    )
    for stage in ("style-selection", "appearance-concept", "scene-plan", "neutral"):
        await forced.run_stage(stage, context)
    assert (len(images.requests), len(structured.calls)) == (3, 2)


@pytest.mark.asyncio
async def test_public_targeted_force_preserves_byte_identical_background(tmp_path: Path) -> None:
    request = request_value()
    images = FakeImages()
    structured = FakeStructured(request)
    context = _context(tmp_path, request)
    executor = DialogueSceneExecutor(DialogueExecutorContext(structured=structured, images=images))
    stages = (
        "prepare",
        "style-selection",
        "appearance-concept",
        "scene-plan",
        "background",
        "neutral",
    )
    for stage in stages:
        await executor.run_stage(stage, context)
    assert (len(images.requests), len(structured.calls)) == (3, 2)

    forced_context = replace(
        context,
        force_stages=frozenset({"appearance-concept"}),
        affected_stages=frozenset(
            {
                "appearance-concept",
                "scene-plan",
                "background",
                "neutral",
                "expressions",
                "canonicalize",
                "bundle",
            }
        ),
    )
    for stage in stages:
        await executor.run_stage(stage, forced_context)

    background_requests = [
        item for item in images.requests if item.metadata.get("role") == "background"
    ]
    assert (len(images.requests), len(structured.calls), len(background_requests)) == (4, 2, 1)


@pytest.mark.asyncio
async def test_public_targeted_force_regenerates_only_changed_dependency_branches(
    tmp_path: Path,
) -> None:
    request = request_value()
    images = FakeImages(vary_forced_concept=True)
    structured = FakeStructured(request)
    context = _context(tmp_path, request)
    executor = DialogueSceneExecutor(DialogueExecutorContext(structured=structured, images=images))
    stages = (
        "prepare",
        "style-selection",
        "appearance-concept",
        "scene-plan",
        "background",
        "neutral",
    )
    for stage in stages:
        await executor.run_stage(stage, context)

    forced_context = replace(
        context,
        force_stages=frozenset({"appearance-concept"}),
        affected_stages=frozenset(
            {
                "appearance-concept",
                "scene-plan",
                "background",
                "neutral",
                "expressions",
                "canonicalize",
                "bundle",
            }
        ),
    )
    for stage in stages:
        await executor.run_stage(stage, forced_context)

    roles = [item.metadata.get("role") for item in images.requests]
    assert roles.count("concept") == 2
    assert roles.count("background") == 1
    assert roles.count("neutral") == 2
    assert len(structured.calls) == 3
    ledger = json.loads((tmp_path / "attempts.json").read_text(encoding="utf-8"))
    selected_roles = [
        entry["role"] for entry in ledger["attempts"] if entry["outcome"] == "selected"
    ]
    assert selected_roles.count("concept") == 2
    assert selected_roles.count("background") == 1
    assert selected_roles.count("neutral") == 2


@pytest.mark.asyncio
async def test_chroma_contract_retries_inside_image_service_before_selection(
    tmp_path: Path,
) -> None:
    request = request_value()
    structured = FakeStructured(request)
    setup = DialogueSceneExecutor(
        DialogueExecutorContext(structured=structured, images=FakeImages())
    )
    context = _context(tmp_path, request)
    for stage in ("prepare", "style-selection", "appearance-concept", "scene-plan"):
        await setup.run_stage(stage, context)

    invalid, valid = _flat_png(), _png()
    backend = SequencedImageBackend([invalid, valid])
    service = ImageGenerationService(
        backend, retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0)
    )
    executor = DialogueSceneExecutor(DialogueExecutorContext(structured=structured, images=service))
    await executor.run_stage("neutral", context)

    output = tmp_path / "raw/expression-neutral.png"
    assert backend.calls == 2
    assert output.read_bytes() == valid
    assert output.read_bytes() != invalid
    sidecar_text = await asyncio.to_thread(Path(f"{output}.meta.json").read_text, encoding="utf-8")
    sidecar = json.loads(sidecar_text)
    assert sidecar["schema_version"] == 2
    assert sidecar["attempts"] == 2
    ledger = json.loads((tmp_path / "attempts.json").read_text(encoding="utf-8"))
    selected = [
        entry
        for entry in ledger["attempts"]
        if entry["role"] == "neutral" and entry["outcome"] == "selected"
    ]
    assert len(selected) == 1
    assert selected[0]["artifact_sha256"] != content_sha256(invalid)


@pytest.mark.asyncio
async def test_ai_removal_contract_retries_before_persistence_and_selection(
    tmp_path: Path,
) -> None:
    request = request_value(transparency_mode="ai")
    structured = FakeStructured(request)
    invalid, valid = _png(), _removed_png()
    backend = SequencedBackgroundBackend([invalid, valid])
    service = BackgroundRemovalService(
        backend, retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0)
    )
    executor = DialogueSceneExecutor(
        DialogueExecutorContext(
            structured=structured,
            images=FakeImages(),
            background=service,
        )
    )
    context = _context(tmp_path, request)
    await executor.run_stage("prepare", context)
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    for state in ("neutral", "delighted", "flustered", "concerned"):
        (raw_root / f"expression-{state}.png").write_bytes(_png())

    await executor.run_stage("canonicalize", context)

    removed = raw_root / "expression-neutral.removed.png"
    assert backend.calls == 5
    assert removed.read_bytes() == valid
    assert removed.read_bytes() != invalid
    sidecar_text = await asyncio.to_thread(Path(f"{removed}.meta.json").read_text, encoding="utf-8")
    sidecar = json.loads(sidecar_text)
    assert sidecar["schema_version"] == 2
    assert sidecar["attempts"] == 2
    ledger = json.loads((tmp_path / "attempts.json").read_text(encoding="utf-8"))
    selected = [
        entry
        for entry in ledger["attempts"]
        if entry["role"] == "neutral" and entry["stage"] == "canonicalize"
    ]
    assert [entry["outcome"] for entry in selected] == ["rejected", "selected"]
    assert selected[-1]["artifact_sha256"] != content_sha256(invalid)


@pytest.mark.asyncio
async def test_service_retry_exhaustion_is_surfaced_and_recorded(tmp_path: Path) -> None:
    request = request_value()
    images = FakeImages(exhausted=True)
    executor = DialogueSceneExecutor(
        DialogueExecutorContext(structured=FakeStructured(request), images=images)
    )
    context = _context(tmp_path, request)
    await executor.run_stage("prepare", context)
    await executor.run_stage("style-selection", context)
    with pytest.raises(RetryExhaustedError, match="6 attempts"):
        await executor.run_stage("appearance-concept", context)
    ledger = json.loads((tmp_path / "attempts.json").read_text(encoding="utf-8"))
    concept_attempts = [entry for entry in ledger["attempts"] if entry["role"] == "concept"]
    assert len(concept_attempts) == 6
    assert {entry["outcome"] for entry in concept_attempts} == {"rejected"}


@pytest.mark.asyncio
async def test_every_image_request_has_one_canonical_asset_aware_anchor(tmp_path: Path) -> None:
    request = request_value()
    images = FakeImages()
    structured = FakeStructured(request)
    executor = DialogueSceneExecutor(DialogueExecutorContext(structured=structured, images=images))
    context = _context(tmp_path, request)
    for stage in (
        "prepare",
        "style-selection",
        "appearance-concept",
        "scene-plan",
        "background",
        "neutral",
        "expressions",
    ):
        await executor.run_stage(stage, context)

    assert len(images.requests) == 6
    assert [item.asset_kind for item in images.requests] == [
        "concept_art",
        "environment_background",
        "character_sprite",
        "character_sprite",
        "character_sprite",
        "character_sprite",
    ]
    anchors = [item.style_anchor for item in images.requests]
    assert all(anchor is not None for anchor in anchors)
    assert len({anchor.model_dump_json() for anchor in anchors if anchor is not None}) == 1
    treatments = (
        "polished 2D character and world concept art",
        "visual novel background art with clear depth planes and focal staging",
        *("visual novel character sprite with a readable silhouette and expression",) * 4,
    )
    for item, treatment in zip(images.requests, treatments, strict=True):
        assert item.style_anchor is not None
        assert item.asset_kind is not None
        final_prompt = append_style_anchor_once(item.prompt, item.style_anchor, item.asset_kind)
        assert final_prompt.count("Canonical style anchor — ") == 1
        assert "medium: clean 2D Japanese anime illustration" in final_prompt
        assert treatment in final_prompt
        assert "semi-realistic rendering" in final_prompt
        assert "untrusted edge style that must not reach image prompts" not in final_prompt


@pytest.mark.asyncio
async def test_occupation_never_substitutes_workplace_attire_for_requested_outfit(
    tmp_path: Path,
) -> None:
    appearance = {
        "id": "saki-lighting-designer",
        "label": "Saki",
        "age": 24,
        "role": "Urban lighting designer",
        "description": (
            "Adult woman with a chestnut bob, gold-leaf hair ornament, deep-teal modern "
            "yukata with silver-wave motifs, and a coral obi"
        ),
        "concept": {
            "mode": "generate",
            "description": "Original clean Japanese anime visual-novel character direction",
        },
    }
    request = request_value(
        scene_brief="Summer-festival night at a lantern-lit urban riverside",
        appearance=appearance,
        background={
            "mode": "generate",
            "description": "Lanterns, fireworks, and festival stalls beside the river",
        },
    )
    images = FakeImages()
    structured = FakeStructured(
        request,
        plan_shared_locks={
            "identity": "office-suited businesswoman",
            "wardrobe": "navy office suit",
            "pose": "fixed conversational pose",
            "lighting": "summer festival night lighting",
            "style": "untrusted generated style",
        },
    )
    executor = DialogueSceneExecutor(DialogueExecutorContext(structured=structured, images=images))
    context = _context(tmp_path, request)
    for stage in (
        "prepare",
        "style-selection",
        "appearance-concept",
        "scene-plan",
        "neutral",
        "expressions",
    ):
        await executor.run_stage(stage, context)

    required = appearance["description"]
    assert isinstance(required, str)
    concept = images.requests[0]
    assert concept.prompt.count(required) == 1
    assert "Occupation or role context only: Urban lighting designer" in concept.prompt
    assert "Summer-festival night at a lantern-lit urban riverside" in concept.prompt
    assert "Lanterns, fireworks, and festival stalls beside the river" in concept.prompt
    assert "Polished character-and-world concept art" in concept.prompt
    assert "full or three-quarter adult character primary" in concept.prompt
    assert "visibly stage them in the requested world" in concept.prompt
    assert "Do not use a blank, white, neutral studio, seamless, or design-sheet field" in (
        concept.prompt
    )
    assert "Canonical style anchor" not in concept.prompt

    plan = json.loads((tmp_path / "plan.json").read_text(encoding="utf-8"))
    locks = plan["shared_locks"]
    assert required in locks["identity"]
    assert required in locks["wardrobe"]
    assert "office" not in locks["identity"].lower()
    assert "office" not in locks["wardrobe"].lower()
    assert "suit" not in locks["wardrobe"].lower()

    for image_request in images.requests[1:]:
        assert required in image_request.prompt
        assert "office" not in image_request.prompt.lower()
        assert "suit" not in image_request.prompt.lower()
        assert "Canonical style anchor" not in image_request.prompt
    neutral = images.requests[1]
    assert "isolated character" in neutral.prompt
    assert "separable edges" in neutral.prompt
    assert "cutout-friendly composition" in neutral.prompt
    assert "no environmental staging" in neutral.prompt


@pytest.mark.asyncio
async def test_unknown_style_selection_exhausts_service_retry_without_artifact(
    tmp_path: Path,
) -> None:
    request = request_value()
    backend = InvalidStyleBackend()
    structured = StructuredGenerationService[Any](
        backend,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    executor = DialogueSceneExecutor(
        DialogueExecutorContext(structured=structured, images=FakeImages())
    )
    context = _context(tmp_path, request)
    await executor.run_stage("prepare", context)
    with pytest.raises(RetryExhaustedError, match="6 attempts"):
        await executor.run_stage("style-selection", context)
    assert backend.calls == 6
    assert not (tmp_path / "style-anchor.json").exists()
    ledger = json.loads((tmp_path / "attempts.json").read_text(encoding="utf-8"))
    records = [entry for entry in ledger["attempts"] if entry["role"] == "style-anchor"]
    assert len(records) == 6
    assert {entry["outcome"] for entry in records} == {"rejected"}


@pytest.mark.asyncio
async def test_style_resource_change_invalidates_anchor_and_image_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = request_value()
    images = FakeImages()
    structured = FakeStructured(request)
    context = _context(tmp_path, request)
    first = DialogueSceneExecutor(DialogueExecutorContext(structured=structured, images=images))
    for stage in ("prepare", "style-selection", "appearance-concept"):
        await first.run_stage(stage, context)
    original = json.loads((tmp_path / "style-anchor.json").read_text(encoding="utf-8"))

    resources = load_image_style_resources()
    vocabulary = json.loads(resources.vocabulary_document)
    vocabulary["modes"][0]["observable_traits"][3] = "minimal controlled gradients"
    mutated_path = tmp_path / "mutated-style-vocabulary.json"
    mutated_path.write_text(json.dumps(vocabulary), encoding="utf-8")
    mutated = load_image_style_resources(vocabulary_path=mutated_path)
    monkeypatch.setattr(
        "stage_gen.recipes.dialogue_scene.executor.load_image_style_resources",
        lambda: mutated,
    )
    second = DialogueSceneExecutor(DialogueExecutorContext(structured=structured, images=images))
    for stage in ("style-selection", "appearance-concept"):
        await second.run_stage(stage, context)
    changed = json.loads((tmp_path / "style-anchor.json").read_text(encoding="utf-8"))

    assert len(structured.calls) == 2
    assert len(images.requests) == 2
    assert original["resource_sha256"] != changed["resource_sha256"]
    assert changed["resource_sha256"] == mutated.resource_sha256


def test_force_validation_rejects_unknown_stage() -> None:
    with pytest.raises(ValueError, match="unknown forced"):
        DialogueSceneExecutor(
            DialogueExecutorContext(
                structured=FakeStructured(request_value()),
                images=FakeImages(),
                force_stages=frozenset({"provider-retry"}),
            )
        )
