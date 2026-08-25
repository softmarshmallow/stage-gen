from __future__ import annotations

import asyncio
import importlib.util
import json
import shutil
import sys
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
from PIL import Image

from stage_gen.config import StageGenConfig, TransparencyMode
from stage_gen.contracts import BinaryArtifact, InputProvenance, ProvenanceInput
from stage_gen.media import CHROMA_MATTE_VERSION
from stage_gen.reliability import sha256_hex, write_artifact_with_provenance


def _load_script() -> ModuleType:
    path = Path(__file__).parents[3] / "scripts/regenerate_repeat_candidate_layers.py"
    spec = importlib.util.spec_from_file_location("regenerate_repeat_candidate_layers", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()


def _png(mode: str, size: tuple[int, int], color: tuple[int, ...]) -> bytes:
    image = Image.new(mode, size, color)
    if mode == "RGBA":
        alpha = image.getchannel("A")
        alpha.paste(0, (0, 0, size[0] // 2, size[1]))
        image.putalpha(alpha)
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def _world() -> dict[str, object]:
    return {
        "world": {"name": "Vale", "one_liner": "Quiet hills.", "narrative": "Rain falls."},
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
                ("coin", "vial", "shard", "key", "charm", "map", "tool", "blade")
            )
        ],
        "layers": [
            {
                "id": "painted_sky_backdrop",
                "title": "Painted sky",
                "z_index": 0,
                "parallax": 0.0,
                "opaque": True,
                "paint_region": "full canvas",
                "description": "A quiet sky.",
            },
            {
                "id": "middle_country",
                "title": "Middle country",
                "z_index": 1,
                "parallax": 0.65,
                "opaque": False,
                "paint_region": "lower half",
                "description": "Rolling hills.",
            },
            {
                "id": "near_foreground",
                "title": "Near foreground",
                "z_index": 2,
                "parallax": 1.8,
                "opaque": False,
                "paint_region": "bottom edge",
                "description": "Small leaves.",
            },
        ],
    }


def _layer_metadata(layer: dict[str, object]) -> dict[str, object]:
    return {
        "stage": f"layer-{layer['id']}",
        "opaque": layer["opaque"],
        "z_index": layer["z_index"],
        "parallax": layer["parallax"],
    }


def _write_layer_pair(
    output: Path,
    *,
    prompt: str,
    metadata: dict[str, object],
    transparent: bool,
    color: int,
    transparency_mode: TransparencyMode = TransparencyMode.AI,
    references: tuple[Path, ...] = (),
    portable_references: bool = False,
) -> None:
    raw_path = output.with_name(f"{output.stem}.raw.png") if transparent else output
    raw = _png("RGB", (2400, 800), (color, color + 1, color + 2))
    raw_metadata = {
        "stage": metadata["stage"],
        "spec_prompt_sha256": sha256_hex(prompt.encode()),
        "requested_width": 2400,
        "requested_height": 800,
        **({"transparency_mode": str(transparency_mode)} if transparent else {}),
        **metadata,
    }
    write_artifact_with_provenance(
        raw_path,
        BinaryArtifact(data=raw, media_type="image/png"),
        ProvenanceInput(
            provider="fake-image",
            model="fake-model",
            prompt=prompt,
            refs=[path.name if portable_references else str(path) for path in references],
            inputs=[
                InputProvenance(
                    ref=path.name if portable_references else str(path),
                    sha256=sha256(path.read_bytes()).hexdigest(),
                    source="content",
                    bytes=path.stat().st_size,
                    media_type="image/png",
                )
                for path in references
            ],
            params={"metadata": raw_metadata},
            validation={
                "exact_contract_dimensions": True,
                "output_width": 2400,
                "output_height": 800,
            },
            attempts=1,
        ),
    )
    if not transparent:
        return
    canonical = _png("RGBA", (2400, 800), (color, color + 1, color + 2, 255))
    write_artifact_with_provenance(
        output,
        BinaryArtifact(data=canonical, media_type="image/png"),
        ProvenanceInput(
            provider="fake-remover",
            model="fake-removal-model",
            prompt="remove background",
            params={
                "metadata": metadata,
                "transparency": {
                    "mode": str(transparency_mode),
                    "retained_raw_path": raw_path.name,
                    "raw_sha256": sha256(raw).hexdigest(),
                    "output_sha256": sha256(canonical).hexdigest(),
                    "processor": {
                        "kind": (
                            "ai-background-removal"
                            if transparency_mode is TransparencyMode.AI
                            else "chroma-key"
                        ),
                        "version": "1",
                    },
                    **(
                        {"matte_version": CHROMA_MATTE_VERSION}
                        if transparency_mode is TransparencyMode.CHROMA
                        else {}
                    ),
                },
            },
            validation={
                "alpha_nontrivial": True,
                "dimensions_preserved": True,
                "output_width": 2400,
                "output_height": 800,
                "transparent_pixels": 960_000,
                "nontransparent_pixels": 960_000,
            },
            attempts=1,
        ),
    )


def _fixture_run(
    tmp_path: Path,
    *,
    transparency_mode: TransparencyMode = TransparencyMode.AI,
    stale_layer_prompt: bool = False,
    sky_layer_id: str = "painted_sky_backdrop",
) -> tuple[Path, Path, StageGenConfig]:
    run_dir = tmp_path / f"proof-run-{transparency_mode}"
    run_dir.mkdir(parents=True)
    backup_dir = tmp_path / "proof-backups"
    tag = run_dir.name
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "recipe": "scrolling-preview",
                "tag": tag,
                "runDir": str(run_dir),
                "input": {
                    "prompt": "A quiet original world",
                    "transparencyMode": str(transparency_mode),
                },
            }
        ),
        encoding="utf-8",
    )
    world_payload = _world()
    world_layers = cast(list[dict[str, object]], world_payload["layers"])
    world_layers[0]["id"] = sky_layer_id
    world_data = json.dumps(world_payload).encode()
    write_artifact_with_provenance(
        run_dir / f"world_spec_{tag}.json",
        BinaryArtifact(data=world_data, media_type="application/json"),
        ProvenanceInput(
            provider="fake-structured",
            model="fake-model",
            prompt="make a world",
            attempts=1,
        ),
    )
    concept = _png("RGB", (1536, 1024), (90, 120, 160))
    write_artifact_with_provenance(
        run_dir / f"concept_{tag}.png",
        BinaryArtifact(data=concept, media_type="image/png"),
        ProvenanceInput(
            provider="fake-image",
            model="fake-model",
            prompt="make a concept",
            attempts=1,
        ),
    )
    for index, raw_layer in enumerate(world_layers):
        layer = dict(raw_layer)
        name = str(layer["id"])
        world_layer = SCRIPT.WorldLayer.model_validate(layer)
        _write_layer_pair(
            run_dir / f"layer_{tag}_{name}.png",
            prompt=(
                f"Superseded prompt for {name}."
                if stale_layer_prompt
                else SCRIPT._parallax_layer_prompt(world_layer)
            ),
            metadata=_layer_metadata(layer),
            transparent=not bool(layer["opaque"]),
            color=30 + index * 20,
            transparency_mode=transparency_mode,
            references=(run_dir / f"concept_{tag}.png",),
        )
    config = StageGenConfig(
        out_dir=tmp_path,
        open_router_api_key="test-openrouter-key",
        fal_key=("test-fal-key" if transparency_mode is TransparencyMode.AI else None),
        transparency_mode=transparency_mode,
    )
    return run_dir, backup_dir, config


class _WritingExecutor:
    def __init__(
        self,
        *,
        fail: bool = False,
        transparency_mode: TransparencyMode = TransparencyMode.AI,
    ) -> None:
        self.fail = fail
        self.transparency_mode = transparency_mode
        self.calls: list[tuple[Any, Any, bool]] = []

    async def _generate_image_asset(
        self, context: Any, spec: Any, *, force: bool = False
    ) -> tuple[str, str]:
        self.calls.append((context, spec, force))
        if self.fail:
            raise RuntimeError("provider proof failed")
        _write_layer_pair(
            spec.output,
            prompt=spec.prompt,
            metadata=spec.metadata,
            transparent=spec.transparent,
            color=180,
            transparency_mode=self.transparency_mode,
            references=spec.references,
            portable_references=spec.portable_references,
        )
        return str(spec.output), f"{spec.output}.meta.json"


class _Closable:
    def __init__(self) -> None:
        self.closed = 0

    async def aclose(self) -> None:
        self.closed += 1


@pytest.mark.parametrize("transparency_mode", tuple(TransparencyMode))
def test_prepare_preserves_run_mode_and_builds_exact_production_specs(
    tmp_path: Path,
    transparency_mode: TransparencyMode,
) -> None:
    run_dir, backup_dir, config = _fixture_run(
        tmp_path,
        transparency_mode=transparency_mode,
    )
    plan = SCRIPT.prepare_regeneration(
        run_dir,
        ("painted_sky_backdrop", "middle_country", "near_foreground"),
        backup_dir,
        config,
    )

    assert plan.transparency_mode is transparency_mode
    assert plan.context.input["transparencyMode"] == transparency_mode
    assert plan.context.config.transparency_mode is transparency_mode
    assert [layer.transparent for layer in plan.layers] == [False, True, True]
    for layer in plan.layers:
        spec = layer.replacement_spec
        assert (spec.width, spec.height) == (2400, 800)
        assert spec.output == run_dir / f"layer_{plan.tag}_{layer.name}.png"
        assert spec.references == (run_dir / f"concept_{plan.tag}.png",)
        assert spec.stage == f"layer-{layer.name}"
        assert spec.portable_references is True
    assert "every x-axis column" in plan.layers[0].replacement_spec.prompt.lower()
    assert "no clouds" in plan.layers[0].replacement_spec.prompt.lower()
    assert "no hill peaks" in plan.layers[1].replacement_spec.prompt.lower()
    assert "houses, bridges, castles" in plan.layers[1].replacement_spec.prompt.lower()
    assert "no tall plants" in plan.layers[2].replacement_spec.prompt.lower()
    assert "large flowers, rocks" in plan.layers[2].replacement_spec.prompt.lower()


def test_prepare_accepts_canonical_backdrop_sky_alias(tmp_path: Path) -> None:
    run_dir, backup_dir, config = _fixture_run(
        tmp_path,
        sky_layer_id="backdrop_sky",
    )

    plan = SCRIPT.prepare_regeneration(
        run_dir,
        ("backdrop_sky",),
        backup_dir,
        config,
    )

    assert plan.layers[0].name == "backdrop_sky"
    assert plan.layers[0].transparent is False
    assert "every x-axis column" in plan.layers[0].replacement_spec.prompt.lower()
    assert "no clouds" in plan.layers[0].replacement_spec.prompt.lower()


def test_far_vale_replacement_is_transparent_and_low_salience(tmp_path: Path) -> None:
    run_dir, backup_dir, config = _fixture_run(tmp_path)
    world_path = run_dir / f"world_spec_{run_dir.name}.json"
    payload = json.loads(world_path.read_text())
    for existing in payload["layers"][1:]:
        existing["z_index"] += 1
    payload["layers"].insert(
        1,
        {
            "id": "far_vale",
            "title": "Far vale",
            "z_index": 1,
            "parallax": 0.22,
            "opaque": False,
            "paint_region": "lower quarter",
            "description": "A distant mist ribbon.",
        },
    )
    write_artifact_with_provenance(
        world_path,
        BinaryArtifact(data=json.dumps(payload).encode(), media_type="application/json"),
        ProvenanceInput(
            provider="fake-structured",
            model="fake-model",
            prompt="add a far vale",
            attempts=1,
        ),
    )
    layer = SCRIPT.WorldLayer.model_validate(payload["layers"][1])
    output = run_dir / f"layer_{run_dir.name}_far_vale.png"
    _write_layer_pair(
        output,
        prompt=SCRIPT._parallax_layer_prompt(layer),
        metadata=_layer_metadata(payload["layers"][1]),
        transparent=True,
        color=75,
        references=(run_dir / f"concept_{run_dir.name}.png",),
    )

    plan = SCRIPT.prepare_regeneration(
        run_dir,
        ("far_vale",),
        backup_dir,
        config,
    )

    assert plan.layers[0].transparent is True
    assert "visually interchangeable" in plan.layers[0].replacement_spec.prompt.lower()
    assert "perfectly straight" in plan.layers[0].replacement_spec.prompt.lower()
    assert "no hills" in plan.layers[0].replacement_spec.prompt.lower()


def test_dry_run_validates_but_does_not_move_or_create_backup(tmp_path: Path) -> None:
    run_dir, backup_dir, config = _fixture_run(tmp_path)
    source = run_dir / f"layer_{run_dir.name}_near_foreground.png"
    before = source.read_bytes()
    plan = SCRIPT.prepare_regeneration(run_dir, ("near_foreground",), backup_dir, config)

    report = SCRIPT.dry_run_report(plan)

    assert report["ok"] is True
    assert report["dry_run"] is True
    assert report["layers"][0]["status"] == "planned"
    assert source.read_bytes() == before
    assert not backup_dir.exists()


def test_execute_moves_exact_pairs_then_regenerates_canonical_paths(tmp_path: Path) -> None:
    run_dir, backup_dir, config = _fixture_run(tmp_path)
    plan = SCRIPT.prepare_regeneration(
        run_dir,
        ("middle_country", "near_foreground"),
        backup_dir,
        config,
    )
    original_digests = {
        move.source.name: sha256(move.source.read_bytes()).hexdigest()
        for layer in plan.layers
        for move in layer.moves
    }
    executor = _WritingExecutor()

    report = asyncio.run(SCRIPT.execute_regeneration(plan, executor))

    assert report["ok"] is True
    assert [record["status"] for record in report["layers"]] == [
        "regenerated",
        "regenerated",
    ]
    assert len(executor.calls) == 2
    assert all(force is False for _context, _spec, force in executor.calls)
    for layer in plan.layers:
        for move in layer.moves:
            assert not move.destination.is_symlink()
            assert (
                sha256(move.destination.read_bytes()).hexdigest()
                == original_digests[move.source.name]
            )
        assert layer.replacement_spec.output.is_file()
        assert Path(f"{layer.replacement_spec.output}.meta.json").is_file()
        assert SCRIPT._retained_raw_path(layer.replacement_spec).is_file()


@pytest.mark.parametrize("transparency_mode", tuple(TransparencyMode))
def test_prompt_drift_is_allowed_only_for_preflight_and_replacement_is_strict(
    tmp_path: Path,
    transparency_mode: TransparencyMode,
) -> None:
    run_dir, backup_dir, config = _fixture_run(
        tmp_path,
        transparency_mode=transparency_mode,
        stale_layer_prompt=True,
    )

    plan = SCRIPT.prepare_regeneration(
        run_dir,
        ("near_foreground",),
        backup_dir,
        config,
    )
    with pytest.raises(ValueError, match="regenerated raw artifact pair is invalid"):
        SCRIPT._require_existing_layer_cache(
            plan.layers[0].original_spec,
            transparency_mode,
        )

    report = asyncio.run(
        SCRIPT.execute_regeneration(
            plan,
            _WritingExecutor(transparency_mode=transparency_mode),
        )
    )

    assert report["ok"] is True
    assert report["transparency_mode"] == str(transparency_mode)
    SCRIPT._require_existing_layer_cache(
        plan.layers[0].replacement_spec,
        transparency_mode,
    )
    raw_path = SCRIPT._retained_raw_path(plan.layers[0].replacement_spec)
    raw_meta = json.loads(Path(f"{raw_path}.meta.json").read_text(encoding="utf-8"))
    assert raw_meta["refs"] == [f"concept_{plan.tag}.png"]
    assert raw_meta["inputs"][0]["ref"] == f"concept_{plan.tag}.png"

    next_plan = SCRIPT.prepare_regeneration(
        run_dir,
        ("near_foreground",),
        tmp_path / f"backup-{transparency_mode}-next",
        config,
    )
    assert next_plan.layers[0].replacement_spec.portable_references is True


def test_preflight_rejects_tamper_and_backup_collision_before_any_move(tmp_path: Path) -> None:
    run_dir, backup_dir, config = _fixture_run(tmp_path)
    source = run_dir / f"layer_{run_dir.name}_near_foreground.png"
    source.write_bytes(source.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="existing canonical transparency lineage is invalid"):
        SCRIPT.prepare_regeneration(run_dir, ("near_foreground",), backup_dir, config)
    assert source.is_file()
    assert not backup_dir.exists()

    run_dir, backup_dir, config = _fixture_run(tmp_path / "collision")
    (backup_dir / "near_foreground").mkdir(parents=True)
    with pytest.raises(ValueError, match="backup destination already exists"):
        SCRIPT.prepare_regeneration(run_dir, ("near_foreground",), backup_dir, config)
    assert (run_dir / f"layer_{run_dir.name}_near_foreground.png").is_file()


def test_preflight_rejects_run_mode_mismatch_before_any_move(tmp_path: Path) -> None:
    run_dir, backup_dir, config = _fixture_run(tmp_path)
    summary_path = run_dir / "run.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["input"]["transparencyMode"] = "chroma"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ValueError, match="existing raw artifact pair is invalid"):
        SCRIPT.prepare_regeneration(run_dir, ("near_foreground",), backup_dir, config)

    assert (run_dir / f"layer_{run_dir.name}_near_foreground.png").is_file()
    assert not backup_dir.exists()


def test_preflight_rejects_layer_bound_to_superseded_concept(tmp_path: Path) -> None:
    run_dir, backup_dir, config = _fixture_run(tmp_path)
    concept_path = run_dir / f"concept_{run_dir.name}.png"
    replacement = _png("RGB", (1536, 1024), (3, 4, 5))
    concept_path.write_bytes(replacement)
    concept_meta_path = Path(f"{concept_path}.meta.json")
    concept_meta = json.loads(concept_meta_path.read_text(encoding="utf-8"))
    concept_meta["artifact"]["sha256"] = sha256(replacement).hexdigest()
    concept_meta["artifact"]["bytes"] = len(replacement)
    concept_meta_path.write_text(json.dumps(concept_meta), encoding="utf-8")

    with pytest.raises(ValueError, match="existing raw artifact pair is invalid"):
        SCRIPT.prepare_regeneration(run_dir, ("near_foreground",), backup_dir, config)

    assert (run_dir / f"layer_{run_dir.name}_near_foreground.png").is_file()
    assert not backup_dir.exists()


def test_preflight_rejects_stale_raw_to_canonical_lineage(tmp_path: Path) -> None:
    run_dir, backup_dir, config = _fixture_run(tmp_path)
    raw_path = run_dir / f"layer_{run_dir.name}_near_foreground.raw.png"
    stale_raw = _png("RGB", (2400, 800), (7, 8, 9))
    raw_path.write_bytes(stale_raw)
    raw_meta_path = Path(f"{raw_path}.meta.json")
    raw_meta = json.loads(raw_meta_path.read_text(encoding="utf-8"))
    raw_meta["artifact"]["sha256"] = sha256(stale_raw).hexdigest()
    raw_meta["artifact"]["bytes"] = len(stale_raw)
    raw_meta_path.write_text(json.dumps(raw_meta), encoding="utf-8")

    with pytest.raises(ValueError, match="existing canonical transparency lineage is invalid"):
        SCRIPT.prepare_regeneration(run_dir, ("near_foreground",), backup_dir, config)

    assert raw_path.is_file()
    assert not backup_dir.exists()


def test_backup_move_rolls_back_all_artifacts_on_partial_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, backup_dir, config = _fixture_run(tmp_path)
    plan = SCRIPT.prepare_regeneration(run_dir, ("near_foreground",), backup_dir, config)
    originals = {move.source: move.source.read_bytes() for move in plan.layers[0].moves}
    real_move = shutil.move
    calls = 0

    def flaky_move(source: str, destination: str) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated backup failure")
        return str(real_move(source, destination))

    monkeypatch.setattr(SCRIPT.shutil, "move", flaky_move)

    with pytest.raises(OSError, match="simulated backup failure"):
        SCRIPT._move_all_to_backup(plan)
    assert all(path.read_bytes() == data for path, data in originals.items())


@pytest.mark.parametrize("transparency_mode", tuple(TransparencyMode))
def test_create_live_bundle_constructs_fal_only_for_ai(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    transparency_mode: TransparencyMode,
) -> None:
    _run_dir, _backup_dir, config = _fixture_run(
        tmp_path,
        transparency_mode=transparency_mode,
    )
    capabilities: list[tuple[Any, ...]] = []
    background_calls = 0

    monkeypatch.setattr(
        SCRIPT,
        "assert_capabilities",
        lambda _config, requested: capabilities.append(tuple(requested)),
    )
    monkeypatch.setattr(SCRIPT, "create_image_service", lambda **_kwargs: _Closable())
    monkeypatch.setattr(SCRIPT, "create_structured_service", lambda **_kwargs: _Closable())

    def background_service(**_kwargs: Any) -> _Closable:
        nonlocal background_calls
        background_calls += 1
        return _Closable()

    monkeypatch.setattr(SCRIPT, "create_background_removal_service", background_service)

    bundle = SCRIPT.create_live_bundle(
        config,
        transparency_mode=transparency_mode,
        needs_transparency=True,
    )

    expected_background = transparency_mode is TransparencyMode.AI
    assert background_calls == int(expected_background)
    assert len(bundle.resources) == (3 if expected_background else 2)
    assert (SCRIPT.CapabilityName.BACKGROUND_REMOVAL in capabilities[0]) is expected_background


@pytest.mark.parametrize("transparency_mode", tuple(TransparencyMode))
def test_run_live_closes_every_owned_service_when_generation_fails(
    tmp_path: Path,
    transparency_mode: TransparencyMode,
) -> None:
    run_dir, backup_dir, config = _fixture_run(
        tmp_path,
        transparency_mode=transparency_mode,
    )
    plan = SCRIPT.prepare_regeneration(run_dir, ("near_foreground",), backup_dir, config)
    originals = {move.source: move.source.read_bytes() for move in plan.layers[0].moves}
    resources = tuple(
        _Closable() for _index in range(3 if transparency_mode is TransparencyMode.AI else 2)
    )

    def factory(
        _config: Any,
        *,
        transparency_mode: TransparencyMode,
        needs_transparency: bool,
    ) -> Any:
        assert transparency_mode is plan.transparency_mode
        assert needs_transparency is True
        return SCRIPT.LiveBundle(
            executor=_WritingExecutor(
                fail=True,
                transparency_mode=transparency_mode,
            ),
            resources=resources,
        )

    with pytest.raises(RuntimeError, match="provider proof failed"):
        asyncio.run(SCRIPT.run_live(plan, factory))
    assert [resource.closed for resource in resources] == [1] * len(resources)
    assert all(path.read_bytes() == data for path, data in originals.items())
    assert all(not move.destination.exists() for move in plan.layers[0].moves)


def test_execute_preserves_partial_provider_outputs_before_restoring_source(
    tmp_path: Path,
) -> None:
    run_dir, backup_dir, config = _fixture_run(tmp_path)
    plan = SCRIPT.prepare_regeneration(run_dir, ("near_foreground",), backup_dir, config)
    originals = {move.source: move.source.read_bytes() for move in plan.layers[0].moves}

    class PartialExecutor:
        async def _generate_image_asset(
            self, _context: Any, spec: Any, *, force: bool = False
        ) -> tuple[str, str]:
            assert force is False
            await asyncio.to_thread(spec.output.write_bytes, b"partial-provider-output")
            await asyncio.to_thread(
                Path(f"{spec.output}.meta.json").write_bytes,
                b"partial-provider-sidecar",
            )
            raise RuntimeError("provider failed after a partial write")

    with pytest.raises(RuntimeError, match="partial write"):
        asyncio.run(SCRIPT.execute_regeneration(plan, PartialExecutor()))

    assert all(path.read_bytes() == data for path, data in originals.items())
    failed_dir = backup_dir / "_failed_generation" / "near_foreground"
    assert (failed_dir / plan.layers[0].replacement_spec.output.name).read_bytes() == (
        b"partial-provider-output"
    )
    assert Path(
        f"{failed_dir / plan.layers[0].replacement_spec.output.name}.meta.json"
    ).read_bytes() == (b"partial-provider-sidecar")


@pytest.mark.parametrize(
    "layers",
    [(), ("near_foreground", "near_foreground"), ("playfield",)],
)
def test_prepare_rejects_empty_duplicate_and_unsupported_selections(
    tmp_path: Path, layers: tuple[str, ...]
) -> None:
    run_dir, backup_dir, config = _fixture_run(tmp_path)
    with pytest.raises(ValueError):
        SCRIPT.prepare_regeneration(run_dir, layers, backup_dir, config)
