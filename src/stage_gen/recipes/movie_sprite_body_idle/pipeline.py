"""Generate or adopt sprite footage and finish it through the public asset harness."""

from __future__ import annotations

import asyncio
import io
import json
import re
import shutil
import tempfile
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Protocol

from PIL import Image

from gnode import (
    ArtifactProvenance,
    ArtifactRights,
    ArtifactValidator,
    BinaryArtifact,
    BindingTable,
    GraphBuilder,
    InputProvenance,
    Node,
    NodeExecutionError,
    NodeExecutionResult,
    NodeType,
    ProvenanceInput,
    RetryFailureRecord,
    SoftwareIdentity,
    VideoGenerationResult,
    ViewArchetype,
    build_artifact_provenance,
    is_portable_artifact_reference,
    sanitize_for_persistence,
    seal_graph,
)
from stage_gen.components.movie_sprite import (
    finish_video,
    inspect_source_video,
    validate_finish_config,
)
from stage_gen.pipeline import (
    InputFiles,
    NodeBinding,
    PipelineContext,
    PipelineDefinition,
    PipelineGraph,
    artifact_port,
    define,
    object_digest,
)

from .authoring import (
    SYSTEM_PROMPT,
    TEMPLATE_VERSION,
    Authoring,
    GenerationSettings,
    compile_prompt,
    digest,
    json_bytes,
    prepare_endpoint,
)


class VideoGenerator(Protocol):
    """Caller-owned, retry-owning endpoint service; the recipe chooses no provider."""

    @property
    def provider_operations(self) -> int: ...

    async def generate(
        self,
        prompt: str,
        endpoint: bytes,
        *,
        duration_seconds: int,
        resolution: str,
        aspect_ratio: str,
        artifact_path: Path,
        rights: ArtifactRights | None = None,
        endpoint_ref: str = "endpoint.png",
        validate: ArtifactValidator | None = None,
    ) -> VideoGenerationResult: ...


PREPARE = NodeType(
    "movie_sprite.prepare",
    "Prepare sprite endpoints",
    ViewArchetype.TRANSFORM,
    "local",
    "movie-sprite-prepare-v1",
)
GENERATE = NodeType(
    "movie_sprite.generate",
    "Generate body motion",
    ViewArchetype.VIDEO,
    "video_generation",
    "movie-sprite-generation-v1",
    features=("first_last_frame",),
)
ADOPT = NodeType(
    "movie_sprite.adopt",
    "Adopt supplied footage",
    ViewArchetype.TRANSFORM,
    "local",
    "movie-sprite-adopt-v1",
)
FINISH = NodeType(
    "movie_sprite.finish",
    "Finish transparent sprite loop",
    ViewArchetype.TRANSFORM,
    "local",
    "movie-sprite-finish-v1",
)
OUTPUTS = {
    "video": "body/loop.mkv",
    "canonical": "body/canonical.png",
    "preview": "body/loop-preview.mp4",
    "report": "body/processing-report.json",
    "manifest": "body/manifest.json",
    "contact_sheet": "body/contact-sheet.png",
}


def _local_origin(
    node: Node,
    context: PipelineContext,
    rights: ArtifactRights | None,
) -> ProvenanceInput:
    inputs = [
        InputProvenance(ref=ref, sha256=sha, source="content")
        for ref, sha in context.plan.input_digests.items()
        if sha in node.input_sha256
    ]
    inputs.extend(
        InputProvenance(ref=item.artifact_ref, sha256=item.sha256, source="content")
        for dependency, result in context.execution.dependency_results.items()
        if dependency not in node.barrier_only
        for item in result.artifacts
        if not item.artifact_ref.endswith(".meta.json")
    )
    identity = SoftwareIdentity(name=node.type_id, version="1")
    return ProvenanceInput(
        provider="local",
        model=node.type_id,
        prompt=node.description,
        refs=[item.ref for item in inputs],
        inputs=inputs,
        params={"node_cache_key": node.cache_key},
        validation={"structural_validation": True, "semantic_review": "not_granted"},
        component=identity,
        tool=SoftwareIdentity(name="stage-gen", version="0.0.0"),
        attempts=1,
        rights=rights,
    )


def _service_origin(saved: ArtifactProvenance) -> ProvenanceInput:
    return ProvenanceInput(
        provider=saved.provider,
        model=saved.model,
        seed=saved.seed,
        prompt=saved.prompt,
        refs=saved.refs,
        inputs=saved.inputs,
        params=saved.params,
        validation=saved.validation,
        component=saved.component,
        tool=saved.tool,
        timestamp=saved.ts,
        attempts=saved.attempts,
        response=saved.response,
        rights=saved.rights,
    )


def _source_record(raw: bytes, sidecar: bytes | None, ref: str) -> dict[str, Any]:
    record: dict[str, Any] = {"source_ref": ref, "source_sha256": digest(raw), "bytes": len(raw)}
    if sidecar is not None:
        saved = ArtifactProvenance.model_validate_json(sidecar)
        if saved.artifact is None or (
            saved.artifact.sha256 != digest(raw) or saved.artifact.bytes != len(raw)
        ):
            raise ValueError("supplied video does not match its recorded provenance")
        origin = saved.model_dump(mode="json")
        clean = build_artifact_provenance(
            BinaryArtifact(data=raw, media_type=saved.artifact.media_type),
            _service_origin(saved),
        ).model_dump(mode="json")
        if clean != origin or any(
            not is_portable_artifact_reference(item)
            for item in [*saved.refs, *(item.ref for item in saved.inputs)]
        ):
            raise ValueError("supplied provenance must contain only portable, sanitized metadata")
        _validate_imported_metadata(origin)
        record.update(
            {"provenance_sha256": digest(sidecar), "origin": saved.model_dump(mode="json")}
        )
    return record


def _validate_imported_metadata(value: object) -> None:
    """Reject private paths and credential-bearing references inside imported JSON too."""
    if isinstance(value, dict):
        for item in value.values():
            _validate_imported_metadata(item)
    elif isinstance(value, list):
        for item in value:
            _validate_imported_metadata(item)
    elif isinstance(value, str):
        references = re.findall(r"(?:https?://|file:|data:)[^\s\"<>]+", value)
        if any(not is_portable_artifact_reference(item) for item in references) or re.search(
            r"(?:^|[\s\"=])(?:/(?:Users|home|tmp|private|var|Volumes)/|[A-Za-z]:[\\/])",
            value,
        ):
            raise ValueError("supplied provenance must contain only portable metadata")


def _payloads(node: Node, values: tuple[bytes, ...]) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    index = 0
    for port in node.ports:
        result[port.port_id] = values[index]
        index += 2 if port.sidecar_ref is not None else 1
    if index != len(values):
        raise ValueError("unexpected artifact payload count")
    return result


def _media_signature(data: bytes) -> bool:
    return len(data) > 12 and (data[4:8] == b"ftyp" or data[:4] == b"\x1aE\xdf\xa3")


def create_pipeline(
    *,
    finish_ref: str,
    authoring_ref: str | None = None,
    settings: GenerationSettings | None = None,
    routes: BindingTable | None = None,
    generator: VideoGenerator | None = None,
    supplied_video_ref: str | None = None,
    supplied_provenance_ref: str | None = None,
    rights: ArtifactRights | None = None,
) -> PipelineDefinition:
    """Build body idle; optional facial repaint is a separate existing pipeline.

    Choose authored generation or supplied footage. Supplied footage preserves its
    original lineage and is never represented as a draw of the current template.
    The caller owns generator lifetime, explicit live admission and budget.
    """
    if (authoring_ref is None) == (supplied_video_ref is None):
        raise ValueError("supply exactly one of authoring_ref or supplied_video_ref")
    if supplied_provenance_ref is not None and supplied_video_ref is None:
        raise ValueError("supplied provenance requires supplied footage")
    generation = settings or GenerationSettings()
    profile = routes or BindingTable(())
    generation_type = replace(
        GENERATE,
        features=(
            "first_last_frame",
            f"resolution:{generation.resolution}",
            f"aspect_ratio:{generation.aspect_ratio}",
        ),
    )
    here = Path(__file__).parent
    authoring_identity = digest((here / "authoring.py").read_bytes())
    recipe_identity = digest(Path(__file__).read_bytes())
    import stage_gen.components.movie_sprite as component

    component_root = Path(component.__file__).parent
    processing_identity = object_digest(
        {item.name: digest(item.read_bytes()) for item in sorted(component_root.glob("*.py"))}
    )
    rights_identity = object_digest(rights.model_dump(mode="json") if rights else None)
    expected: dict[str, tuple[str, str]] = {}
    generated_requests: dict[str, dict[str, Any]] = {}
    source_ref = (
        "body/raw.mp4"
        if supplied_video_ref is None
        else "body/source" + Path(supplied_video_ref).suffix.lower()
    )

    def request_record(
        authoring: Authoring, image: bytes, transform: dict[str, Any]
    ) -> dict[str, Any]:
        prompt = compile_prompt(authoring, generation)
        return {
            "schema_version": 1,
            "kind": "movie-sprite-request-v1",
            "authoring": authoring.model_dump(mode="json"),
            "settings": generation.model_dump(mode="json"),
            "template_version": TEMPLATE_VERSION,
            "template_sha256": digest(SYSTEM_PROMPT.encode()),
            "prompt": prompt,
            "prompt_sha256": digest(prompt.encode()),
            "endpoint_sha256": digest(image),
            "start_frame": "body/endpoint.png",
            "end_frame": "body/endpoint.png",
            "preparation": transform,
            "semantic_review": "not_granted",
        }

    async def prepare(node: Node, context: PipelineContext) -> NodeExecutionResult:
        assert authoring_ref is not None
        authoring = Authoring.model_validate_json(context.read_input(authoring_ref))
        image, transform = prepare_endpoint(
            context.read_input(authoring.canonical_image), generation
        )
        record = request_record(authoring, image, transform)
        origin = _local_origin(node, context, rights)
        return await context.publish(
            node,
            {"image": image, "request": json_bytes(record)},
            provenance={"image": origin, "request": origin},
        )

    async def generate(node: Node, context: PipelineContext) -> NodeExecutionResult:
        if generator is None:
            raise RuntimeError("generation cache miss: no live video service was supplied")
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            raise RuntimeError("ffmpeg and ffprobe are required before video generation")
        request = json.loads(context.read_artifact("body/request.json"))
        image = context.read_artifact("body/endpoint.png")
        if digest(image) != request["endpoint_sha256"]:
            raise ValueError("prepared endpoint identity mismatch")
        before = generator.provider_operations
        cost_before = getattr(generator, "known_cost_usd", None)

        def reported_cost() -> float | None:
            total = getattr(generator, "known_cost_usd", None)
            return max(0.0, float(total) - float(cost_before or 0)) if total is not None else None

        async def validate_video(artifact: BinaryArtifact) -> dict[str, object]:
            facts = await asyncio.to_thread(inspect_source_video, artifact.data)
            short_side = {"360p": 360, "720p": 720, "1080p": 1080, "4k": 2160}[
                generation.resolution
            ]
            dimensions = (short_side, short_side * 16 // 9)
            if generation.aspect_ratio == "16:9":
                dimensions = dimensions[::-1]
            if (facts["width"], facts["height"]) != dimensions:
                raise ValueError("generated video dimensions differ from the admitted request")
            if (
                abs(facts["duration_seconds"] - generation.duration_seconds)
                > 1 / facts["fps"] + 0.01
            ):
                raise ValueError("generated video duration differs from the admitted request")
            return {"movie_sprite_source": facts}

        try:
            with tempfile.TemporaryDirectory(prefix="movie-sprite-service-") as scratch:
                result = await generator.generate(
                    request["prompt"],
                    image,
                    duration_seconds=generation.duration_seconds,
                    resolution=generation.resolution,
                    aspect_ratio=generation.aspect_ratio,
                    artifact_path=Path(scratch) / "body.mp4",
                    rights=rights,
                    endpoint_ref="body/endpoint.png",
                    validate=validate_video,
                )
                sidecar = await asyncio.to_thread(Path(result.provenance_path).read_bytes)
                saved = ArtifactProvenance.model_validate_json(sidecar)
                _source_record(result.data, sidecar, source_ref)
                validate_generated_origin(node, saved, request)
                return await context.publish(
                    node,
                    {"video": result.data},
                    provenance={"video": _service_origin(saved)},
                    attempts=result.attempts,
                    provider_operations=generator.provider_operations - before,
                    known_cost_usd=reported_cost(),
                )
        except Exception as error:
            if isinstance(error, NodeExecutionError):
                raise
            history = [
                item.as_dict()
                for item in getattr(error, "failure_history", ())
                if isinstance(item, RetryFailureRecord)
            ]
            message = str(error)
            if history:
                message += "\n" + json.dumps(sanitize_for_persistence({"failure_history": history}))
            raise NodeExecutionError(
                message,
                attempts=getattr(error, "attempts", max(1, generator.provider_operations - before)),
                provider_operations=generator.provider_operations - before,
                known_cost_usd=reported_cost(),
            ) from error

    def validate_generated_origin(
        node: Node, saved: ArtifactProvenance, request: dict[str, Any]
    ) -> None:
        if (
            saved.provider != node.provider
            or saved.model != node.model
            or saved.prompt != request["prompt"]
        ):
            raise ValueError(
                "generated video provenance differs from its admitted route and prompt"
            )
        if any(
            saved.params.get(key) != value
            for key, value in (
                ("duration_seconds", generation.duration_seconds),
                ("resolution", generation.resolution),
                ("aspect_ratio", generation.aspect_ratio),
            )
        ):
            raise ValueError("generated video provenance differs from its admitted settings")
        roles = [
            {"role": role, "ref": "body/endpoint.png"} for role in ("start_frame", "end_frame")
        ]
        if saved.params.get("reference_roles") != roles or saved.refs != ["body/endpoint.png"] * 2:
            raise ValueError("generated video provenance must preserve both endpoint roles")
        if len(saved.inputs) != 2 or any(
            item.ref != "body/endpoint.png" or item.sha256 != request["endpoint_sha256"]
            for item in saved.inputs
        ):
            raise ValueError("generated video endpoint digest differs from the prepared image")
        if not isinstance(saved.validation.get("movie_sprite_source"), dict):
            raise ValueError("generated video lacks structural decoding validation")

    async def adopt(node: Node, context: PipelineContext) -> NodeExecutionResult:
        assert supplied_video_ref is not None
        raw = context.read_input(supplied_video_ref)
        sidecar = context.read_input(supplied_provenance_ref) if supplied_provenance_ref else None
        record = _source_record(raw, sidecar, supplied_video_ref)
        record["media"] = await asyncio.to_thread(inspect_source_video, raw)
        adopted_rights = (
            ArtifactProvenance.model_validate_json(sidecar).rights if sidecar else rights
        )
        origin = _local_origin(node, context, adopted_rights)
        return await context.publish(
            node,
            {"video": raw, "source": json_bytes(record)},
            provenance={"video": origin, "source": origin},
            media_types={
                "video": "video/x-matroska" if source_ref.endswith(".mkv") else "video/mp4"
            },
        )

    async def finish(node: Node, context: PipelineContext) -> NodeExecutionResult:
        config = json.loads(context.read_input(finish_ref))
        output = await asyncio.to_thread(finish_video, context.read_artifact(source_ref), config)
        source = ArtifactProvenance.model_validate_json(
            context.read_artifact(source_ref + ".meta.json")
        )
        origin = _local_origin(node, context, source.rights)
        return await context.publish(
            node,
            output,
            provenance={key: origin for key in output},
            media_types={"video": "video/x-matroska"},
        )

    def admit_prepare(node: Node, values: tuple[bytes, ...]) -> bool:
        try:
            data = _payloads(node, values)
            return (digest(data["image"]), digest(data["request"])) == expected[node.cache_key]
        except (KeyError, ValueError, IndexError):
            return False

    def admit_source(node: Node, values: tuple[bytes, ...]) -> bool:
        try:
            data = _payloads(node, values)
            if not _media_signature(data["video"]):
                return False
            if "source" in data:
                record = json.loads(data["source"])
                return bool(
                    record["source_sha256"] == digest(data["video"])
                    and record["bytes"] == len(data["video"])
                    and record["media"]["source_sha256"] == record["source_sha256"]
                    and record["media"]["timestamps_constant_rate"] is True
                )
            saved = ArtifactProvenance.model_validate_json(values[1])
            validate_generated_origin(node, saved, generated_requests[node.cache_key])
            return True
        except (KeyError, ValueError, IndexError):
            return False

    def admit_finish(node: Node, values: tuple[bytes, ...]) -> bool:
        try:
            data = _payloads(node, values)
            report = json.loads(data["report"])
            manifest = json.loads(data["manifest"])
            with Image.open(io.BytesIO(data["canonical"])) as image:
                image.load()
                if image.mode != "RGBA":
                    return False
                size = image.size
                first_frame_digest = digest(image.tobytes())
            rows = report["frames"]
            if not isinstance(rows, list) or len(rows) != manifest["frame_count"] or not rows:
                return False
            if any(
                report[key] is not True
                for key in (
                    "all_native_frames_lossless_verified",
                    "canonical_first_frame_exact",
                    "loop_endpoints_exact",
                )
            ):
                return False
            return (
                _media_signature(data["video"])
                and _media_signature(data["preview"])
                and manifest["kind"] == "movie_sprite_body"
                and report["kind"] == "movie_sprite_body_processing"
                and manifest["canonical_sha256"] == digest(data["canonical"])
                and rows[0]["rgba_sha256"] == rows[-1]["rgba_sha256"] == first_frame_digest
                and size == (manifest["width"], manifest["height"])
                and all(
                    report[key] == manifest[key]
                    for key in (
                        "source_sha256",
                        "frame_count",
                        "width",
                        "height",
                        "playback_seconds",
                        "playback_fps",
                    )
                )
                and manifest["alpha_mode"] == "straight"
                and manifest["loop"] is True
                and manifest["audio"] is False
            )
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            return False

    def build(inputs: InputFiles) -> PipelineGraph:
        config = json.loads(inputs.read(finish_ref))
        validate_finish_config(config)
        builder = GraphBuilder(profile=profile)
        source_digests: list[str] = [recipe_identity, rights_identity]
        if supplied_video_ref is not None:
            if Path(supplied_video_ref).suffix.lower() not in {".mp4", ".mkv"}:
                raise ValueError("supplied footage must be MP4 or Matroska")
            raw = inputs.read(supplied_video_ref)
            if not _media_signature(raw):
                raise ValueError("supplied footage has no supported video signature")
            sidecar = inputs.read(supplied_provenance_ref) if supplied_provenance_ref else None
            _source_record(raw, sidecar, supplied_video_ref)
            source_digests.append(inputs.digest(supplied_video_ref))
            if supplied_provenance_ref:
                source_digests.append(inputs.digest(supplied_provenance_ref))
            source_node = "adopt"
            builder.add(
                ADOPT,
                source_node,
                domain="movie_sprite",
                description="Adopt caller-supplied footage and preserve its original source record",
                input_digests=tuple(source_digests),
                ports=(
                    artifact_port("video", source_ref, "movie-sprite-source-v1"),
                    artifact_port("source", "body/source.json", "movie-sprite-source-record-v1"),
                ),
            )
        else:
            assert authoring_ref is not None
            authoring = Authoring.model_validate_json(inputs.read(authoring_ref))
            route = profile.require(
                "video_generation",
                "first_last_frame",
                f"resolution:{generation.resolution}",
                f"aspect_ratio:{generation.aspect_ratio}",
            )
            route.within("clip_seconds_max", generation.duration_seconds, subject="movie_sprite")
            route.aligned("clip_seconds_step", generation.duration_seconds, subject="movie_sprite")
            minimum = route.limit("clip_seconds_min")
            if minimum is not None and generation.duration_seconds < minimum:
                raise ValueError("movie_sprite duration is below the selected route minimum")
            route.within(
                "prompt_chars_max",
                len(compile_prompt(authoring, generation)),
                subject="movie_sprite",
            )
            image, transform = prepare_endpoint(inputs.read(authoring.canonical_image), generation)
            record = request_record(authoring, image, transform)
            prepared = builder.add(
                PREPARE,
                "prepare",
                domain="movie_sprite",
                description="Prepare identical endpoints and one inspectable sprite motion prompt",
                input_digests=(
                    inputs.digest(authoring_ref),
                    inputs.digest(authoring.canonical_image),
                    object_digest(generation.model_dump(mode="json")),
                    authoring_identity,
                    recipe_identity,
                    rights_identity,
                ),
                ports=(
                    artifact_port("image", "body/endpoint.png", "movie-sprite-endpoint-v1"),
                    artifact_port("request", "body/request.json", "movie-sprite-request-v1"),
                ),
            )
            expected[prepared.cache_key] = (digest(image), digest(json_bytes(record)))
            source_node = "generate"
            generated = builder.add(
                generation_type,
                source_node,
                domain="movie_sprite",
                description="Generate sprite footage conditioned on identical explicit endpoints",
                depends_on=["prepare"],
                input_digests=(
                    recipe_identity,
                    object_digest({**asdict(route), "features": sorted(route.features)}),
                ),
                ports=(artifact_port("video", source_ref, "movie-sprite-source-v1"),),
            )
            generated_requests[generated.cache_key] = record
        output_refs = dict(OUTPUTS)
        if config.get("export_frames", False):
            output_refs["frames_zip"] = "body/frames.zip"
        builder.add(
            FINISH,
            "finish",
            domain="movie_sprite",
            description="Finish the transparent body loop and derive the facial canonical",
            depends_on=[source_node],
            input_digests=(
                inputs.digest(finish_ref),
                processing_identity,
                recipe_identity,
                rights_identity,
            ),
            ports=tuple(
                artifact_port(key, ref, "movie-sprite-loop-v1") for key, ref in output_refs.items()
            ),
        )
        return seal_graph(
            PipelineGraph,
            pipeline_id="movie_sprite_body_idle",
            title="Movie sprite body idle",
            nodes=builder.nodes,
            resources=builder.resources(),
            terminal_node_id="finish",
        )

    bindings = [NodeBinding(FINISH, finish, admit_finish)]
    if supplied_video_ref is not None:
        bindings.append(NodeBinding(ADOPT, adopt, admit_source))
    else:
        bindings.extend(
            (
                NodeBinding(PREPARE, prepare, admit_prepare),
                NodeBinding(generation_type, generate, admit_source),
            )
        )
    return define(
        "movie_sprite_body_idle", title="Movie sprite body idle", build=build, bindings=bindings
    )
