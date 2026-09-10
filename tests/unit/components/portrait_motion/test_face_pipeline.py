"""Provider-free integration of face location, the existing graph, and native output."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from scipy.ndimage import gaussian_filter

from gnode import (
    ArtifactProvenance,
    ArtifactRights,
    BinaryArtifact,
    ImageGenerationService,
    ProvenanceInput,
    ProviderResponseMetadata,
    ProviderStructuredOutput,
    RetryPolicy,
    StructuredGenerationRequest,
    StructuredGenerationService,
    write_artifact_with_provenance,
)
from stage_gen.components.portrait_motion import PortraitMotionSpec
from stage_gen.components.portrait_motion.processing import png_bytes
from stage_gen.components.portrait_motion.storage import COMPONENT
from stage_gen.config import ConfigError, StageGenConfig
from stage_gen.image_product import ImageProvider
from stage_gen.orchestration.portrait_face import KIND, REQUIRED_STAGES, load_face_plan
from stage_gen.orchestration.portrait_motion import (
    TOOL,
    RuntimeProfile,
    prepare_run,
    run_pipeline,
    verify_run,
)

from .test_pipeline import FEATURES, Case, ImageBackend, StructuredBackend, specification

SOURCE_SIZE = (768, 1152)
FACE_BOX = [200, 100, 800, 500]


class FaceStructuredBackend(StructuredBackend):
    """Add spatial location to the existing real-service integration backend."""

    def __init__(self, profile: RuntimeProfile, mode: str) -> None:
        super().__init__(profile, mode)
        self.locatable = mode != "no_face"
        self.locator_input: bytes | None = None

    async def generate_once(
        self, request: StructuredGenerationRequest[object]
    ) -> ProviderStructuredOutput:
        if request.schema.name != "portrait_face_location":
            return await super().generate_once(request)
        self.calls.append("face_location")
        assert len(request.references) == 1
        self.locator_input = base64.b64decode(request.references[0].url.partition(",")[2])
        value = {
            "status": "located" if self.locatable else "not_locatable",
            "bbox_xyxy": FACE_BOX if self.locatable else None,
            "reason": "Spatially located synthetic face." if self.locatable else "No face visible.",
        }
        return ProviderStructuredOutput(
            decoded=value,
            raw_text=json.dumps(value),
            response_metadata=ProviderResponseMetadata(
                request_id="offline-location", usage={"cost": 0}
            ),
        )


def prepare_face_case(
    tmp_path: Path,
    mode: str = "complete",
    *,
    config: StageGenConfig | None = None,
) -> Case:
    profile = RuntimeProfile()
    noise = gaussian_filter(
        np.random.default_rng(913).normal(size=(SOURCE_SIZE[1], SOURCE_SIZE[0])), 1.4
    )
    plane = np.clip(np.rint(128 + noise / noise.std() * 32), 0, 255).astype(np.uint8)
    pixels = np.empty((*plane.shape, 4), dtype=np.uint8)
    pixels[..., :3] = plane[..., None]
    pixels[..., 3] = 254
    pixels[:30, :30, 3] = 0
    pixels[230:240, 220:230, 3] = 128
    source = tmp_path / "source.png"
    write_artifact_with_provenance(
        source,
        BinaryArtifact(png_bytes(Image.fromarray(pixels)), "image/png"),
        ProvenanceInput(
            provider="local",
            model="synthetic-test",
            prompt="Original seeded full-canvas texture with partial alpha.",
            component=COMPONENT,
            tool=TOOL,
            attempts=1,
            rights=ArtifactRights(
                status="unreviewed",
                basis=["Original procedural test texture"],
                attribution=["Synthetic fixture author"],
                reviewed_at=None,
            ),
        ),
    )
    run = tmp_path / "run"
    prepare_run(source, run, specification(), profile, config=config, face_crop=True)
    _, _, graph = load_face_plan(run)
    route = graph.resolved_route_for("atlas")
    structured = FaceStructuredBackend(profile, mode)
    image = ImageBackend(route.provider, route.model, structured.eligible)
    retry = RetryPolicy(initial_delay_s=0, max_delay_s=0)
    return Case(
        run,
        image,
        structured,
        ImageGenerationService(image, component=COMPONENT, tool=TOOL, retry_policy=retry),
        StructuredGenerationService(structured, component=COMPONENT, tool=TOOL, retry_policy=retry),
    )


def test_face_prepare_preserves_original_and_seals_independent_working_canvas(
    tmp_path: Path,
) -> None:
    case = prepare_face_case(tmp_path)
    _, plan, graph = load_face_plan(case.run_dir)
    assert plan["kind"] == KIND
    assert plan["source"]["size"] == list(SOURCE_SIZE)
    assert (plan["spec"]["width"], plan["spec"]["height"]) == (1024, 1024)
    assert plan["image_jobs"] == 1 and plan["structured_jobs"] == 4
    assert graph.resolved_route_for("atlas").provider == "openai"
    original = (tmp_path / "source.png").read_bytes()
    assert (case.run_dir / "inputs/source.png").read_bytes() == original
    assert (case.run_dir / "locator/inputs/source.png").read_bytes() == original
    source_meta = ArtifactProvenance.model_validate_json(
        (tmp_path / "source.png.meta.json").read_bytes()
    )
    imported = ArtifactProvenance.model_validate_json(
        (case.run_dir / "inputs/source.png.meta.json").read_bytes()
    )
    assert imported.rights == source_meta.rights
    assert case.image_backend.calls == 0 and case.structured_backend.calls == []
    assert not (case.run_dir / "portrait").exists()
    assert not (case.run_dir / "crop").exists()


def test_nonsquare_card_layout_is_refused_before_creating_a_run(tmp_path: Path) -> None:
    case = prepare_face_case(tmp_path)
    value = specification().model_dump(mode="json")
    value.update(
        columns=2,
        rows=1,
        states=value["states"][:2],
        requested_features=["canvas_left_eye", "canvas_right_eye"],
        playback=[segment for segment in value["playback"] if segment["mouth"] == "rest"],
    )
    spec = PortraitMotionSpec.model_validate(value)
    run = tmp_path / "nonsquare-card-run"
    with pytest.raises(ValueError, match="square"):
        prepare_run(tmp_path / "source.png", run, spec, face_crop=True)
    assert not run.exists()
    assert case.image_backend.calls == 0 and case.structured_backend.calls == []


@pytest.mark.asyncio
async def test_face_pipeline_complete_native_rgba_and_offline_cache(tmp_path: Path) -> None:
    case = prepare_face_case(tmp_path)
    result = await case.run()
    assert result["status"] == "complete", result
    assert result["accepted_features"] == FEATURES
    assert result["verified_stages"] == REQUIRED_STAGES
    assert result["provider_operations_this_invocation"] == 5
    assert result["provider_operations_total"] == 5
    assert case.image_backend.calls == 1
    assert case.structured_backend.calls == ["face_location", "admission", "geometry", "quality"]
    assert isinstance(case.structured_backend, FaceStructuredBackend)
    assert case.structured_backend.locator_input == (tmp_path / "source.png").read_bytes()
    assert result["preview_ref"] == "render/animation.webp"
    assert result["manifest_ref"] == "render/manifest.json"
    assert result["temporal_review"] == "not_performed"
    manifest = json.loads((case.run_dir / result["manifest_ref"]).read_bytes())
    assert manifest["source_size"] == list(SOURCE_SIZE)
    assert manifest["feather_already_baked"] is True
    assert len(manifest["combinations"]) == 9 and len(manifest["patches"]) == 6
    source = np.asarray(Image.open(case.run_dir / "inputs/source.png").convert("RGBA"))
    closed = np.asarray(
        Image.open(case.run_dir / "render/states/eyes_closed--rest.png").convert("RGBA")
    )
    rest = np.asarray(Image.open(case.run_dir / "render/states/rest--rest.png").convert("RGBA"))
    np.testing.assert_array_equal(rest, source)
    np.testing.assert_array_equal(closed[..., 3], source[..., 3])
    assert np.any(closed[source[..., 3] == 254] != source[source[..., 3] == 254])
    np.testing.assert_array_equal(closed[source[..., 3] == 0], source[source[..., 3] == 0])
    with Image.open(case.run_dir / "crop/work.png") as work:
        assert work.size == (1024, 1024) and work.mode == "RGB"
    with Image.open(case.run_dir / result["preview_ref"]) as preview:
        assert preview.size == SOURCE_SIZE
        durations = []
        for index in range(getattr(preview, "n_frames", 1)):
            preview.seek(index)
            preview.load()
            durations.append(preview.info["duration"])
        assert sum(durations) == 420
    replay = await run_pipeline(case.run_dir)
    assert replay["status"] == "complete" and replay["provider_operations_this_invocation"] == 0
    assert replay["provider_operations_total"] == 5
    assert case.image_backend.calls == 1
    assert case.structured_backend.calls == ["face_location", "admission", "geometry", "quality"]
    assert verify_run(case.run_dir)["status"] == "complete"


@pytest.mark.asyncio
async def test_unlocatable_face_stops_before_crop_admission_or_image_jobs(tmp_path: Path) -> None:
    case = prepare_face_case(tmp_path, "no_face")
    result = await case.run()
    assert result["status"] == "refused" and result["accepted_features"] == []
    assert result["provider_operations_this_invocation"] == 1
    assert result["provider_operations_total"] == 1
    assert result["verified_stages"] == ["face_location"]
    assert result["preview_ref"] is None and result["portrait_run_ref"] is None
    assert case.image_backend.calls == 0
    assert case.structured_backend.calls == ["face_location"]
    assert not (case.run_dir / "crop").exists() and not (case.run_dir / "portrait").exists()
    replay = await run_pipeline(case.run_dir)
    assert replay["status"] == "refused" and replay["provider_operations_this_invocation"] == 0
    assert verify_run(case.run_dir)["status"] == "refused"


@pytest.mark.asyncio
async def test_partial_child_acceptance_remains_partial_after_native_reconstruction(
    tmp_path: Path,
) -> None:
    case = prepare_face_case(tmp_path, "one_eye")
    result = await case.run()
    assert result["status"] == "partial", result
    assert result["accepted_features"] == ["canvas_right_eye"]
    manifest = json.loads((case.run_dir / "render/manifest.json").read_bytes())
    assert manifest["features"] == ["canvas_right_eye"] and len(manifest["patches"]) == 2
    for eye in ("rest", "eyes_half", "eyes_closed"):
        rest = (case.run_dir / f"render/states/{eye}--rest.png").read_bytes()
        assert (case.run_dir / f"render/states/{eye}--mouth_a.png").read_bytes() == rest
        assert (case.run_dir / f"render/states/{eye}--mouth_smile.png").read_bytes() == rest
    assert verify_run(case.run_dir)["status"] == "partial"


@pytest.mark.asyncio
@pytest.mark.parametrize("modality", ["image", "structured"])
async def test_mismatched_injected_route_is_refused_before_face_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, modality: str
) -> None:
    case = prepare_face_case(tmp_path)
    backend = case.image_backend if modality == "image" else case.structured_backend
    monkeypatch.setattr(backend, "model", "unexpected")
    with pytest.raises(ValueError, match="service route must match the prepared binding"):
        await case.run()
    assert case.image_backend.calls == 0 and case.structured_backend.calls == []
    assert not list(case.run_dir.rglob("submission.json"))


@pytest.mark.asyncio
async def test_all_live_keys_are_required_before_locator_spend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = prepare_face_case(
        tmp_path, config=StageGenConfig(image_provider_override=ImageProvider.FAL)
    )
    monkeypatch.setenv("STAGE_GEN_RUN_LIVE", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "offline-unused-key")
    monkeypatch.delenv("FAL_KEY", raising=False)
    with pytest.raises(ConfigError) as caught:
        await run_pipeline(case.run_dir, live=True)
    assert caught.value.missing == ("FAL_KEY",)
    assert not list(case.run_dir.rglob("submission.json"))
    assert not (case.run_dir / "locator/budget.json").exists()


@pytest.mark.asyncio
async def test_source_crop_child_and_native_output_tampering_refuses_cache_reuse(
    tmp_path: Path,
) -> None:
    case = prepare_face_case(tmp_path)
    assert (await case.run())["status"] == "complete"
    calls = (case.image_backend.calls, list(case.structured_backend.calls))
    for ref in (
        "inputs/source.png",
        "crop/work.png",
        "crop/transform.json",
        "portrait/registration/eyes_closed-donor.png",
        "render/states/eyes_closed--rest.png",
        "render/animation.webp",
        "render/manifest.json",
    ):
        path = case.run_dir / ref
        original = path.read_bytes()
        path.write_bytes(original + b"tampered")
        try:
            with pytest.raises(ValueError):
                verify_run(case.run_dir)
            with pytest.raises(ValueError):
                await case.run()
        finally:
            path.write_bytes(original)
        assert (case.image_backend.calls, case.structured_backend.calls) == calls
    assert (await run_pipeline(case.run_dir))["provider_operations_this_invocation"] == 0


def test_original_import_rights_tampering_is_rejected_before_location(tmp_path: Path) -> None:
    case = prepare_face_case(tmp_path)
    path = case.run_dir / "inputs/source.png.meta.json"
    metadata = ArtifactProvenance.model_validate_json(path.read_bytes())
    changed = metadata.model_copy(
        update={
            "rights": ArtifactRights(
                status="unreviewed", basis=["Unrelated changed rights"], reviewed_at=None
            )
        }
    )
    path.write_text(changed.model_dump_json())
    with pytest.raises(ValueError, match="Prepared locator"):
        load_face_plan(case.run_dir)
    assert case.image_backend.calls == 0 and case.structured_backend.calls == []


def test_cli_face_crop_flag_prepares_the_same_public_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from stage_gen.interfaces import portrait_motion as cli

    prepare_face_case(tmp_path)
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(specification().model_dump_json())
    run = tmp_path / "cli-run"
    monkeypatch.setattr(cli, "load_config", StageGenConfig)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stage-gen-portrait-motion",
            "prepare",
            "--source",
            str(tmp_path / "source.png"),
            "--spec",
            str(spec_path),
            "--run",
            str(run),
            "--face-crop",
        ],
    )
    cli.entrypoint()
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "prepared" and result["source_size"] == list(SOURCE_SIZE)
    assert json.loads((run / "plan.json").read_bytes())["kind"] == KIND
