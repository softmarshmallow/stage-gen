from __future__ import annotations

import asyncio
import hashlib
import json
import re
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from pydantic import ValidationError

import stage_gen.recipes.scrolling_preview.manifest as manifest_module
from stage_gen.config import TransparencyMode
from stage_gen.contracts import BinaryArtifact, ProvenanceInput
from stage_gen.recipes.scrolling_preview.cache import valid_artifact_pair
from stage_gen.recipes.scrolling_preview.manifest import write_scrolling_preview_manifest
from stage_gen.recipes.scrolling_preview.models import (
    NEAR_FOREGROUND_PARALLAX,
    WORLD_SPEC_NORMALIZATION_VERSION,
    WorldSpec,
    canonicalize_generated_world_spec,
)
from stage_gen.recipes.scrolling_preview.raster_contracts import (
    contract_for_runtime_role,
    normalize_canonical_grid,
    validate_canonical_grid,
)
from stage_gen.recipes.scrolling_preview.scale_reference import (
    evaluate_actor_scale_reference,
    parse_actor_scale_reference,
    scale_reference_frame,
)
from stage_gen.recipes.scrolling_preview.village import (
    VillageSpec,
    village_manifest_block,
)
from stage_gen.reliability import sha256_hex, write_artifact_with_provenance


def valid_world() -> dict[str, object]:
    kinds = [
        "sun-coin",
        "spore-vial",
        "rune-shard",
        "gate-key",
        "bone-charm",
        "signal-map",
        "flint-tool",
        "thorn-blade",
    ]
    return {
        "world": {"name": "Vale", "one_liner": "A quiet ruin.", "narrative": "Rain falls."},
        "mobs": [
            {
                "tier_label": "scout",
                "body_plan": "winged avian",
                "name": "Mote",
                "brief": "A pale bird.",
            },
            {
                "tier_label": "apex",
                "body_plan": "four-legged quadruped",
                "name": "Maw",
                "brief": "A stone beast.",
            },
        ],
        "obstacles": [
            {
                "sheet_theme": "mossy ruins",
                "props": [{"name": f"prop {index}", "brief": "weathered"} for index in range(8)],
            }
        ],
        "items": [
            {"kind": kind, "name": f"item {index}", "brief": "small"}
            for index, kind in enumerate(kinds)
        ],
        "layers": [
            {
                "id": "deep_sky",
                "title": "Deep sky",
                "z_index": 0,
                "parallax": 0.0,
                "opaque": True,
                "paint_region": "all canvas",
                "description": "Clouds",
            },
            {
                "id": "near_ruins",
                "title": "Near ruins",
                "z_index": 1,
                "parallax": 1.8,
                "opaque": False,
                "paint_region": "lower half",
                "description": "Arches",
            },
        ],
    }


def test_world_schema_enforces_cross_asset_invariants() -> None:
    parsed = WorldSpec.model_validate(valid_world())
    assert len(parsed.items) == 8
    duplicate = valid_world()
    duplicate["mobs"][1]["body_plan"] = "winged avian"  # type: ignore[index]
    with pytest.raises(ValidationError, match="must differ"):
        WorldSpec.model_validate(duplicate)


def test_world_schema_requires_one_canonical_near_foreground() -> None:
    stale = valid_world()
    stale["layers"][1]["parallax"] = 1.0  # type: ignore[index]
    with pytest.raises(ValidationError, match=r"near foreground at parallax=1\.8"):
        WorldSpec.model_validate(stale)

    extra_near = valid_world()
    layers = extra_near["layers"]
    assert isinstance(layers, list)
    layers.insert(
        1,
        {
            "id": "middle_ruins",
            "title": "Middle ruins",
            "z_index": 1,
            "parallax": 1.2,
            "opaque": False,
            "paint_region": "middle",
            "description": "Arches",
        },
    )
    extra_near["layers"][2]["z_index"] = 2  # type: ignore[index]
    with pytest.raises(ValidationError, match="only the front-most"):
        WorldSpec.model_validate(extra_near)


@pytest.mark.parametrize("input_parallax", [1.0, 1.2])
def test_generated_world_canonicalizes_only_frontmost_parallax(
    input_parallax: float,
) -> None:
    payload = valid_world()
    layers = payload["layers"]
    assert isinstance(layers, list)
    layers.insert(
        1,
        {
            "id": "middle_ruins",
            "title": "Middle ruins",
            "z_index": 1,
            "parallax": 0.6,
            "opaque": False,
            "paint_region": "middle",
            "description": "Arches",
        },
    )
    near = layers[2]
    assert isinstance(near, dict)
    near["z_index"] = 2
    near["parallax"] = input_parallax
    source_layers = json.loads(json.dumps(layers))

    result = canonicalize_generated_world_spec(payload)

    assert [layer.id for layer in result.spec.layers] == [
        "deep_sky",
        "middle_ruins",
        "near_ruins",
    ]
    assert result.spec.layers[0].parallax == 0
    assert result.spec.layers[1].parallax == 0.6
    assert result.spec.layers[2].parallax == NEAR_FOREGROUND_PARALLAX
    assert payload["layers"] == source_layers
    record = result.validation["world_spec_normalization"]
    assert isinstance(record, dict)
    assert record == {
        "version": WORLD_SPEC_NORMALIZATION_VERSION,
        "target_layer_id": "near_ruins",
        "target_z_index": 2,
        "input_parallax": input_parallax,
        "output_parallax": NEAR_FOREGROUND_PARALLAX,
        "changed": True,
        "changed_fields": ["layers[2].parallax"],
        "layer_ids": ["deep_sky", "middle_ruins", "near_ruins"],
        "unchanged_layer_ids": ["deep_sky", "middle_ruins"],
        "layer_order_preserved": True,
        "unrelated_layers_unchanged": True,
    }


def test_generated_world_preserves_already_canonical_foreground() -> None:
    result = canonicalize_generated_world_spec(valid_world())
    record = result.validation["world_spec_normalization"]

    assert isinstance(record, dict)
    assert result.spec.layers[-1].parallax == NEAR_FOREGROUND_PARALLAX
    assert record["input_parallax"] == NEAR_FOREGROUND_PARALLAX
    assert record["changed"] is False
    assert record["changed_fields"] == []


def test_generated_world_rejects_missing_or_ambiguous_foreground() -> None:
    missing = valid_world()
    layers = missing["layers"]
    assert isinstance(layers, list)
    missing["layers"] = layers[:1]
    with pytest.raises(ValidationError, match="at least one transparent"):
        canonicalize_generated_world_spec(missing)

    ambiguous = valid_world()
    layers = ambiguous["layers"]
    assert isinstance(layers, list)
    layers.append(
        {
            "id": "near_branches",
            "title": "Near branches",
            "z_index": 1,
            "parallax": 1.0,
            "opaque": False,
            "paint_region": "edges",
            "description": "Branches",
        }
    )
    with pytest.raises(ValidationError, match="exactly one front-most transparent"):
        canonicalize_generated_world_spec(ambiguous)


def test_runtime_requirements_include_exact_ladder_climb_items_and_layers() -> None:
    world = WorldSpec.model_validate(valid_world())
    requirements = {
        requirement.role: requirement
        for requirement in manifest_module._runtime_requirements("storybook-ai", world)
    }

    assert (requirements["concept"].width, requirements["concept"].height) == (1536, 1024)
    assert requirements["concept"].alpha == "opaque"
    assert (
        requirements["character-concept"].width,
        requirements["character-concept"].height,
    ) == (2400, 800)
    assert requirements["character-concept"].alpha == "transparent"
    assert {role for role in requirements if role.startswith("mob-concept-")} == {
        f"mob-concept-{index}" for index in range(len(world.mobs))
    }
    assert (requirements["ladder"].width, requirements["ladder"].height) == (256, 1024)
    assert (
        requirements["character-climb"].width,
        requirements["character-climb"].height,
    ) == (256, 128)
    assert (requirements["items"].width, requirements["items"].height) == (2400, 800)
    assert requirements["layer-near_ruins"].metadata == {
        "zIndex": 1,
        "parallax": 1.8,
        "opaque": False,
    }


def test_runtime_manifest_contract_rejects_missing_world_and_required_roles(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="world spec artifact pair is missing"):
        manifest_module._collect_runtime_assets(tmp_path, "missing", set(), [])

    tag = "incomplete-ai"
    world_path = tmp_path / f"world_spec_{tag}.json"
    world_data = (json.dumps(valid_world()) + "\n").encode()
    world_meta = write_artifact_with_provenance(
        world_path,
        BinaryArtifact(data=world_data, media_type="application/json"),
        ProvenanceInput(
            provider="local",
            model="offline",
            prompt="create world spec",
            params={"metadata": {"stage": "world-spec"}},
            attempts=1,
        ),
    )
    names = {world_path.name, Path(world_meta).name}
    with pytest.raises(ValueError, match="runtime-required role concept is missing"):
        manifest_module._collect_runtime_assets(tmp_path, tag, names, [])


async def test_runtime_publication_rejects_each_missing_concept_role(tmp_path: Path) -> None:
    tag = "missing-concepts"
    world = WorldSpec.model_validate(valid_world())
    world_path = tmp_path / f"world_spec_{tag}.json"
    world_data = (world.model_dump_json(indent=2) + "\n").encode()
    write_artifact_with_provenance(
        world_path,
        BinaryArtifact(data=world_data, media_type="application/json"),
        ProvenanceInput(
            provider="local",
            model="offline",
            prompt="create complete world",
            params={"metadata": {"stage": "world-spec"}},
            attempts=1,
        ),
    )
    requirements = manifest_module._runtime_requirements(tag, world)
    for requirement in requirements:
        _write_runtime_pair(tmp_path, requirement, mode="chroma")

    concept_requirements = [
        requirement
        for requirement in requirements
        if requirement.role in {"concept", "character-concept"}
        or requirement.role.startswith("mob-concept-")
    ]
    assert len(concept_requirements) == len(world.mobs) + 2
    for missing in concept_requirements:
        artifact = tmp_path / missing.path
        await asyncio.to_thread(artifact.unlink)
        await asyncio.to_thread(Path(f"{artifact}.meta.json").unlink)
        with pytest.raises(
            ValueError,
            match=rf"runtime-required role {re.escape(missing.role)} is missing",
        ):
            await write_scrolling_preview_manifest(
                run_dir=tmp_path,
                tag=tag,
                transparency_mode=TransparencyMode.CHROMA,
            )
        _write_runtime_pair(tmp_path, missing, mode="chroma")


@pytest.mark.parametrize(
    ("processor", "kind"),
    [
        ("ai-background-removal", "ai-background-removal"),
        ("chroma-key", "chroma-key"),
        ("imagegen/remove_chroma_key.py", "chroma-key"),
        ("tileset-topology-mask", "tileset-topology-mask"),
        (
            "ai-background-removal+grid-cell-normalization",
            "ai-background-removal+grid-cell-normalization",
        ),
        (
            "isolated-view-fallback-v1+grid-cell-normalization",
            "isolated-view-fallback-v1",
        ),
        (
            "per-cell-generation-v1+grid-cell-normalization",
            "per-cell-generation-v1",
        ),
        (
            "tileset-material-synthesis-v1+tileset-topology-mask",
            "tileset-material-synthesis-v1",
        ),
    ],
)
def test_manifest_derivation_uses_actual_processor(processor: str, kind: str) -> None:
    assert manifest_module._generated_derivation_kind(processor, "asset.png") == kind


def test_canonical_scan_excludes_unprovenanced_gameplay_evidence(tmp_path: Path) -> None:
    evidence = tmp_path / "gameplay-verification.png"
    evidence.write_bytes(b"not-a-publishable-artifact")

    assert (
        manifest_module._collect_canonical_images(
            tmp_path,
            {evidence.name},
            TransparencyMode.AI,
        )
        == []
    )


def test_canonical_scan_excludes_hidden_fallback_components_and_priors(
    tmp_path: Path,
) -> None:
    names = {
        ".mob_concept_storybook_0.view-0.png",
        ".mob_concept_storybook_0.view-0.png.meta.json",
        ".mob_concept_storybook_0.view-0.raw.png",
        ".mob_concept_storybook_0.view-0.raw.png.meta.json",
        ".items_storybook.cell-0-0.png",
        ".items_storybook.cell-0-0.png.meta.json",
        ".items_storybook.cell-0-0.raw.png",
        ".items_storybook.cell-0-0.raw.png.meta.json",
        ".obstacles_storybook_0.cell-1-3.png",
        ".obstacles_storybook_0.cell-1-3.png.meta.json",
        ".obstacles_storybook_0.cell-1-3.raw.png",
        ".obstacles_storybook_0.cell-1-3.raw.png.meta.json",
        ".obstacles_storybook_0.cell-1-3.prior.png",
        ".obstacles_storybook_0.cell-1-3.prior.png.meta.json",
        ".tileset_storybook.material-fill.raw.png",
        ".tileset_storybook.material-fill.raw.png.meta.json",
        ".tileset_storybook.material-fill.png",
        ".tileset_storybook.material-fill.png.meta.json",
        ".tileset_storybook.material-cap.raw.png",
        ".tileset_storybook.material-cap.raw.png.meta.json",
        ".tileset_storybook.material-cap.png",
        ".tileset_storybook.material-cap.png.meta.json",
        ".tileset_storybook.material-edge.raw.png",
        ".tileset_storybook.material-edge.raw.png.meta.json",
        ".tileset_storybook.material-edge.png",
        ".tileset_storybook.material-edge.png.meta.json",
    }

    assert (
        manifest_module._collect_canonical_images(
            tmp_path,
            names,
            TransparencyMode.CHROMA,
        )
        == []
    )


async def test_manifest_publishes_complete_pixel_validated_runtime_bindings(
    tmp_path: Path,
) -> None:
    tag = "complete-chroma"
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    world = WorldSpec.model_validate(valid_world())
    world_data = (world.model_dump_json(indent=2) + "\n").encode()
    write_artifact_with_provenance(
        run_dir / f"world_spec_{tag}.json",
        BinaryArtifact(data=world_data, media_type="application/json"),
        ProvenanceInput(
            provider="local",
            model="offline",
            prompt="create complete world",
            params={"metadata": {"stage": "world-spec"}},
            attempts=1,
        ),
    )
    for requirement in manifest_module._runtime_requirements(tag, world):
        _write_runtime_pair(
            run_dir,
            requirement,
            mode="chroma",
            processor_override=(
                "tileset-material-synthesis-v1+tileset-topology-mask"
                if requirement.role == "tileset"
                else None
            ),
        )
    (run_dir / "gameplay-verification.png").write_bytes(b"review-only")
    hidden_material_names = (
        f".tileset_{tag}.material-fill.raw.png",
        f".tileset_{tag}.material-fill.raw.png.meta.json",
        f".tileset_{tag}.material-fill.png",
        f".tileset_{tag}.material-fill.png.meta.json",
        f".tileset_{tag}.material-cap.raw.png",
        f".tileset_{tag}.material-cap.raw.png.meta.json",
        f".tileset_{tag}.material-cap.png",
        f".tileset_{tag}.material-cap.png.meta.json",
        f".tileset_{tag}.material-edge.raw.png",
        f".tileset_{tag}.material-edge.raw.png.meta.json",
        f".tileset_{tag}.material-edge.png",
        f".tileset_{tag}.material-edge.png.meta.json",
    )
    for name in hidden_material_names:
        (run_dir / name).write_bytes(b"private-resume-state")

    result = await write_scrolling_preview_manifest(
        run_dir=run_dir,
        tag=tag,
        transparency_mode=TransparencyMode.CHROMA,
    )

    manifest_text = await asyncio.to_thread(Path(result.manifest_path).read_text, encoding="utf-8")
    manifest = json.loads(manifest_text)
    runtime = {entry["id"]: entry for entry in manifest["runtime_assets"]}
    tileset_entry = next(
        entry for entry in manifest["canonical_artifacts"] if entry["path"] == f"tileset_{tag}.png"
    )
    assert tileset_entry["transparency"]["derivation"]["kind"] == ("tileset-material-synthesis-v1")
    assert runtime["tileset"]["layout"] == {
        "topology": "tileset",
        "rows": 4,
        "columns": 12,
        "cell_width": 200,
        "cell_height": 200,
        "gutter": 2,
    }
    assert runtime["tileset"]["geometry_validation"]["canonical_fill_opaque"] is True
    assert runtime["concept"]["layout"]["columns"] == 1
    assert runtime["character-concept"]["layout"]["columns"] == 3
    assert all(
        runtime[f"mob-concept-{index}"]["layout"]["columns"] == 3
        for index in range(len(world.mobs))
    )
    assert runtime["items"]["layout"]["rows"] == 2
    assert runtime["items"]["layout"]["columns"] == 4
    assert runtime["ladder"]["layout"]["cell_height"] == 1024
    assert runtime["character-climb"]["layout"]["cell_width"] == 64
    assert runtime["layer-near_ruins"]["binding"]["parallax"] == 1.8
    assert {role for role, entry in runtime.items() if "scale_reference" in entry} == {
        requirement.role
        for requirement in manifest_module._runtime_requirements(tag, world)
        if manifest_module._scale_reference_owner_stage(requirement) is not None
    }
    assert "gameplay-verification.png" not in manifest["artifacts"]
    assert all(name not in manifest["artifacts"] for name in hidden_material_names)
    assert [entry["id"] for entry in manifest["runtime_assets"]].count("tileset") == 1


async def test_current_manifest_copies_only_approved_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_music_only_manifest(monkeypatch)
    fallback = tmp_path / "fallback.mp3"
    fallback.write_bytes(b"offline-music")
    sha = hashlib.sha256(fallback.read_bytes()).hexdigest()
    sidecar = {
        "schema_version": 2,
        "artifact": {"sha256": sha, "bytes": fallback.stat().st_size, "media_type": "audio/mpeg"},
        "references": [],
        "refs": [],
        "inputs": [
            {
                "ref": f"sha256:{sha}",
                "sha256": sha,
                "source": "content",
                "bytes": fallback.stat().st_size,
                "media_type": "audio/mpeg",
            }
        ],
        "rights": {
            "status": "redistribution-approved",
            "attribution": [],
            "basis": [f"sha256:{sha}"],
            "reviewed_at": "2026-08-14T00:00:00Z",
        },
    }
    await asyncio.to_thread(
        Path(f"{fallback}.meta.json").write_text,
        json.dumps(sidecar),
        encoding="utf-8",
    )
    run_dir = tmp_path / "out" / "tag-ai"
    result = await write_scrolling_preview_manifest(
        run_dir=run_dir,
        tag="tag-ai",
        transparency_mode=TransparencyMode.AI,
        fallback_music_path=fallback,
    )
    manifest_text = await asyncio.to_thread(Path(result.manifest_path).read_text)
    manifest = json.loads(manifest_text)
    assert manifest["schema_version"] == 7
    assert manifest["transparency_mode"] == "ai"
    assert "music" not in manifest
    assert result.music_source == "generated-fallback"
    assert result.music_rights_status == "redistribution-approved"
    assert ".raw.png" not in "".join(manifest["artifacts"])
    assert await asyncio.to_thread(Path(result.manifest_provenance_path).is_file)
    manifest_provenance = json.loads(
        await asyncio.to_thread(
            Path(result.manifest_provenance_path).read_text,
            encoding="utf-8",
        )
    )
    assert manifest_provenance["schema_version"] == 2


def test_scrolling_cache_requires_current_provenance_v2(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    write_artifact_with_provenance(
        artifact,
        BinaryArtifact(data=b"{}\n", media_type="application/json"),
        ProvenanceInput(provider="local", model="test", prompt="test", attempts=1),
    )
    assert valid_artifact_pair(artifact, force=False)

    sidecar = Path(f"{artifact}.meta.json")
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    payload["schema_version"] = 1
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    assert not valid_artifact_pair(artifact, force=False)


async def test_manifest_uses_real_bundled_fallback_without_live_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_music_only_manifest(monkeypatch)
    result = await write_scrolling_preview_manifest(
        run_dir=tmp_path / "run",
        tag="bundled-ai",
        transparency_mode=TransparencyMode.AI,
    )
    manifest_text = await asyncio.to_thread(Path(result.manifest_path).read_text, encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert result.music_source == "generated-fallback"
    assert result.music_rights_status == "redistribution-approved"
    assert await asyncio.to_thread(Path(result.music_path).read_bytes)
    assert "music" not in manifest


@pytest.mark.parametrize(
    "reference",
    [".hidden/source.bin", "source.bin?query=1", r"folder\source.bin", "/tmp/source.bin"],
)
async def test_manifest_rejects_nonportable_fallback_references(
    tmp_path: Path, reference: str
) -> None:
    fallback = tmp_path / "fallback.mp3"
    fallback.write_bytes(b"offline-music")
    sha = hashlib.sha256(fallback.read_bytes()).hexdigest()
    sidecar = {
        "schema_version": 2,
        "artifact": {"sha256": sha, "bytes": len(fallback.read_bytes())},
        "references": [reference],
        "refs": [reference],
        "inputs": [],
        "rights": {
            "status": "redistribution-approved",
            "attribution": [],
            "basis": [f"sha256:{sha}"],
            "reviewed_at": "2026-08-14T00:00:00Z",
        },
    }
    await asyncio.to_thread(
        Path(f"{fallback}.meta.json").write_text,
        json.dumps(sidecar),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="stable non-temporary reference"):
        await write_scrolling_preview_manifest(
            run_dir=tmp_path / "out",
            tag="unsafe-ai",
            transparency_mode=TransparencyMode.AI,
            fallback_music_path=fallback,
        )


@pytest.mark.parametrize("status", ["unreviewed", "restricted"])
async def test_manifest_rejects_unapproved_repository_fallback(tmp_path: Path, status: str) -> None:
    fallback = _fallback_fixture(tmp_path, status=status)
    run_dir = tmp_path / "run"
    with pytest.raises(ValueError, match="not publication-approved"):
        await write_scrolling_preview_manifest(
            run_dir=run_dir,
            tag=f"{status}-ai",
            transparency_mode=TransparencyMode.AI,
            fallback_music_path=fallback,
        )
    assert not (run_dir / f"music_{status}-ai.mp3").exists()


async def test_manifest_rejects_fallback_digest_mismatch(tmp_path: Path) -> None:
    fallback = _fallback_fixture(tmp_path, digest="0" * 64)
    with pytest.raises(ValueError, match="artifact digest does not match"):
        await write_scrolling_preview_manifest(
            run_dir=tmp_path / "run",
            tag="bad-digest-ai",
            transparency_mode=TransparencyMode.AI,
            fallback_music_path=fallback,
        )


async def test_manifest_rejects_legacy_v1_fallback_provenance(tmp_path: Path) -> None:
    fallback = _fallback_fixture(tmp_path, schema_version=1)
    with pytest.raises(ValueError, match="bundled fallback provenance is invalid"):
        await write_scrolling_preview_manifest(
            run_dir=tmp_path / "run",
            tag="legacy-fallback-ai",
            transparency_mode=TransparencyMode.AI,
            fallback_music_path=fallback,
        )


async def test_manifest_reports_missing_per_run_and_fallback_music(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="generate-music capability"):
        await write_scrolling_preview_manifest(
            run_dir=tmp_path / "run",
            tag="missing-music-ai",
            transparency_mode=TransparencyMode.AI,
            fallback_music_path=tmp_path / "missing.mp3",
        )


async def test_manifest_preserves_existing_unreviewed_per_run_music(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_music_only_manifest(monkeypatch)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    music = run_dir / "music_custom-ai.mp3"
    await asyncio.to_thread(music.write_bytes, b"per-run")
    sidecar = Path(f"{music}.meta.json")
    await asyncio.to_thread(
        sidecar.write_text,
        json.dumps(
            {
                "rights": {
                    "status": "unreviewed",
                    "attribution": [],
                    "basis": [],
                    "reviewed_at": None,
                }
            },
        ),
        encoding="utf-8",
    )

    result = await write_scrolling_preview_manifest(
        run_dir=run_dir,
        tag="custom-ai",
        transparency_mode=TransparencyMode.AI,
        fallback_music_path=tmp_path / "missing.mp3",
    )

    assert result.music_source == "per-run"
    assert result.music_rights_status == "unreviewed"
    assert await asyncio.to_thread(music.read_bytes) == b"per-run"
    assert await asyncio.to_thread(sidecar.is_file)


async def test_manifest_accepts_executor_shaped_lineage_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_music_only_manifest(monkeypatch)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    tag = "executor-chroma"

    def pair(
        name: str,
        data: bytes,
        *,
        params: dict[str, object],
        validation: dict[str, object],
        refs: list[str] | None = None,
    ) -> Path:
        path = run_dir / name
        write_artifact_with_provenance(
            path,
            BinaryArtifact(data=data, media_type="image/png"),
            ProvenanceInput(
                provider="local",
                model="offline",
                prompt=f"create {name}",
                refs=refs or [],
                params=params,
                validation=validation,
                attempts=1,
            ),
        )
        return path

    pair(
        f"concept_{tag}.png",
        b"opaque",
        params={"metadata": {"stage": "concept"}},
        validation={},
    )
    raw_name = f"character_{tag}_combined_strip_idle.raw.png"
    raw_data = b"raw-strip"
    pair(
        raw_name,
        raw_data,
        params={"metadata": {"transparency_mode": "chroma"}},
        validation={
            "exact_contract_dimensions": True,
            "output_width": 2400,
            "output_height": 800,
        },
    )
    strip_name = f"character_{tag}_combined_strip_idle.png"
    strip_data = b"canonical-strip"
    pair(
        strip_name,
        strip_data,
        params={
            "transparency": {
                "mode": "chroma",
                "retained_raw_path": raw_name,
                "raw_sha256": sha256_hex(raw_data),
                "output_sha256": sha256_hex(strip_data),
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
        refs=[raw_name],
    )
    master_name = f"character_{tag}_combined.png"
    master_data = b"master"
    pair(
        master_name,
        master_data,
        params={
            "transparency": {
                "mode": "chroma",
                "source_paths": {"idle": strip_name},
                "source_hashes": [{"path": strip_name, "sha256": sha256_hex(strip_data)}],
                "output_sha256": sha256_hex(master_data),
                "processor": "deterministic-alpha-composite",
            }
        },
        validation={
            "alpha_nontrivial": True,
            "transparent_pixels": 1,
            "nontransparent_pixels": 1,
            "dimensions_preserved": True,
            "output_width": 2400,
            "output_height": 3440,
        },
        refs=[strip_name],
    )
    slice_name = f"character_{tag}-fromcombined_idle.png"
    slice_data = b"slice"
    pair(
        slice_name,
        slice_data,
        params={
            "transparency": {
                "mode": "chroma",
                "source_path": master_name,
                "source_sha256": sha256_hex(master_data),
                "output_sha256": sha256_hex(slice_data),
                "processor": "master-sheet-slice",
            }
        },
        validation={
            "alpha_nontrivial": True,
            "transparent_pixels": 1,
            "nontransparent_pixels": 1,
            "dimensions_preserved": True,
            "output_width": 2400,
            "output_height": 688,
        },
        refs=[master_name],
    )

    first = await write_scrolling_preview_manifest(
        run_dir=run_dir,
        tag=tag,
        transparency_mode=TransparencyMode.CHROMA,
    )
    first_manifest_bytes = await asyncio.to_thread(Path(first.manifest_path).read_bytes)
    first_provenance_bytes = await asyncio.to_thread(
        Path(first.manifest_provenance_path).read_bytes
    )
    second = await write_scrolling_preview_manifest(
        run_dir=run_dir,
        tag=tag,
        transparency_mode=TransparencyMode.CHROMA,
    )
    manifest_text = await asyncio.to_thread(Path(second.manifest_path).read_text, encoding="utf-8")
    manifest = json.loads(manifest_text)
    entries = {entry["path"]: entry for entry in manifest["canonical_artifacts"]}
    assert entries[master_name]["transparency"]["lineage"]["source_paths"] == [strip_name]
    assert entries[slice_name]["transparency"]["lineage"]["source_paths"] == [master_name]
    assert Path(first.manifest_provenance_path).name not in manifest["artifacts"]
    assert second.music_source == first.music_source == "generated-fallback"
    assert second.music_rights_status == first.music_rights_status
    assert await asyncio.to_thread(Path(second.manifest_path).read_bytes) == first_manifest_bytes
    assert (
        await asyncio.to_thread(Path(second.manifest_provenance_path).read_bytes)
        == first_provenance_bytes
    )


def valid_village() -> dict[str, object]:
    """A village bible whose residents are four different anatomies rather than four aprons."""

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


def _write_village_run(run_dir: Path, tag: str, *, village: VillageSpec | None) -> None:
    """A complete run directory, optionally including the nine village sheets and the bible."""

    world = WorldSpec.model_validate(valid_world())
    write_artifact_with_provenance(
        run_dir / f"world_spec_{tag}.json",
        BinaryArtifact(
            data=(world.model_dump_json(indent=2) + "\n").encode(),
            media_type="application/json",
        ),
        ProvenanceInput(
            provider="local",
            model="offline",
            prompt="create complete world",
            params={"metadata": {"stage": "world-spec"}},
            attempts=1,
        ),
    )
    for requirement in manifest_module._runtime_requirements(tag, world, village):
        _write_runtime_pair(run_dir, requirement, mode="chroma")
    if village is not None:
        write_artifact_with_provenance(
            run_dir / f"village_spec_{tag}.json",
            BinaryArtifact(
                data=(village.model_dump_json(indent=2) + "\n").encode(),
                media_type="application/json",
            ),
            ProvenanceInput(
                provider="local",
                model="offline",
                prompt="design the village hub",
                params={"metadata": {"stage": "village-spec"}},
                attempts=1,
            ),
        )


async def test_a_village_less_run_omits_the_optional_village_block(
    tmp_path: Path,
) -> None:
    """An undeclared village remains optional and does not require a bible or resident assets."""

    tag = "village-less-chroma"
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_village_run(run_dir, tag, village=None)

    without = await write_scrolling_preview_manifest(
        run_dir=run_dir, tag=tag, transparency_mode=TransparencyMode.CHROMA
    )
    village_less_bytes = await asyncio.to_thread(Path(without.manifest_path).read_bytes)

    manifest = json.loads(village_less_bytes.decode("utf-8"))
    assert "village" not in manifest
    world = WorldSpec.model_validate(valid_world())
    assert [entry["id"] for entry in manifest["runtime_assets"]] == [
        requirement.role for requirement in manifest_module._runtime_requirements(tag, world)
    ]
    assert not any(name.startswith("village") for name in manifest["artifacts"])


async def test_a_village_publishes_its_block_and_the_nine_sheets_the_block_describes(
    tmp_path: Path,
) -> None:
    tag = "village-chroma"
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    village = VillageSpec.model_validate(valid_village())
    _write_village_run(run_dir, tag, village=village)

    result = await write_scrolling_preview_manifest(
        run_dir=run_dir, tag=tag, transparency_mode=TransparencyMode.CHROMA, village=True
    )
    manifest = json.loads(
        await asyncio.to_thread(Path(result.manifest_path).read_text, encoding="utf-8")
    )

    assert manifest["village"] == village_manifest_block(village)
    assert manifest["schema_version"] == 7
    runtime = {entry["id"]: entry for entry in manifest["runtime_assets"]}
    village_roles = [role for role in runtime if role.startswith("village-")]
    assert village_roles == [
        *(
            role
            for slot in range(4)
            for role in (f"village-npc-concept-{slot}", f"village-npc-{slot}-idle")
        ),
        "village-fixtures",
    ]
    assert len(village_roles) == 9
    for slot in range(4):
        concept = runtime[f"village-npc-concept-{slot}"]
        assert concept["path"] == f"npc_concept_{tag}_{slot}.png"
        assert concept["layout"]["columns"] == 3
        assert concept["binding"] == {"slot": slot}
        idle = runtime[f"village-npc-{slot}-idle"]
        assert idle["path"] == f"npc_{tag}_{slot}_idle.png"
        assert idle["layout"]["columns"] == 4
        assert idle["binding"] == {"slot": slot, "state": "idle"}
        assert idle["alpha_expectation"] == "transparent"
    fixtures = runtime["village-fixtures"]
    assert fixtures["path"] == f"village_fixtures_{tag}.png"
    assert (fixtures["layout"]["rows"], fixtures["layout"]["columns"]) == (2, 4)
    # One sheet for the whole settlement, so it carries no positional binding of its own.
    assert "binding" not in fixtures

    provenance = Path(result.manifest_provenance_path)
    sidecar = json.loads(await asyncio.to_thread(provenance.read_text, encoding="utf-8"))
    # The published block is copied out of the bible, so the bible is a genuine input to these
    # bytes rather than merely another file in the run.
    assert f"village_spec_{tag}.json" in sidecar["refs"]


async def test_the_village_block_survives_current_key_normalization_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The current envelope snake-cases every producer-owned key.

    The village block is already `lower_snake_case` at the source, which is the reason it needs no
    aliasing at this boundary - but "needs none" is a claim about a normalizer that walks the whole
    document, renames keys and raises on a collision. Enabling both opt-ins at once is the only
    arrangement that exercises it, and a run that had both would otherwise be the first to find out.
    """

    tag = "village-profile-chroma"
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    village = VillageSpec.model_validate(valid_village())
    _write_village_run(run_dir, tag, village=village)
    monkeypatch.setattr(
        manifest_module,
        "_collect_character_profile_binding",
        lambda _run_dir, tag, _names: {
            "profile_id": "mira-vale-cartographer",
            "source_sha256": "a" * 64,
            "canonical_sha256": "b" * 64,
            "path": f"character_profile_{tag}.json",
            "provenance_path": f"character_profile_{tag}.json.meta.json",
        },
    )

    result = await write_scrolling_preview_manifest(
        run_dir=run_dir,
        tag=tag,
        transparency_mode=TransparencyMode.CHROMA,
        character_profile=True,
        village=True,
    )
    manifest = json.loads(
        await asyncio.to_thread(Path(result.manifest_path).read_text, encoding="utf-8")
    )

    assert manifest["schema_version"] == 7
    assert manifest["village"] == village_manifest_block(village)
    village_roles = [
        entry["id"] for entry in manifest["runtime_assets"] if entry["id"].startswith("village-")
    ]
    assert len(village_roles) == 9


async def test_a_declared_unreadable_village_bible_is_rejected(
    tmp_path: Path,
) -> None:
    tag = "village-broken-chroma"
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_village_run(run_dir, tag, village=VillageSpec.model_validate(valid_village()))
    spec_path = run_dir / f"village_spec_{tag}.json"
    await asyncio.to_thread(spec_path.write_text, "{ not a bible", encoding="utf-8")

    with pytest.raises(ValueError, match="declared village specification is invalid"):
        await write_scrolling_preview_manifest(
            run_dir=run_dir, tag=tag, transparency_mode=TransparencyMode.CHROMA, village=True
        )


def test_scale_reference_ownership_matches_the_current_runtime_closure() -> None:
    world = WorldSpec.model_validate(valid_world())
    village = VillageSpec.model_validate(valid_village())
    requirements = manifest_module._runtime_requirements("closure", world, village)

    owners = {
        requirement.role: manifest_module._scale_reference_owner_stage(requirement)
        for requirement in requirements
        if manifest_module._scale_reference_owner_stage(requirement) is not None
    }

    assert owners == {
        "character-idle": "character-idle",
        "character-walk": "character-walk",
        "character-run": "character-run",
        "character-jump": "character-jump",
        "character-crawl": "character-crawl",
        "character-attack": "character-attack",
        "character-climb": "character-climb",
        "mob-0-idle": "mob-idle-0",
        "mob-0-hurt": "mob-hurt-0",
        "mob-1-idle": "mob-idle-1",
        "mob-1-hurt": "mob-hurt-1",
        "village-npc-0-idle": "village-npc-0-idle",
        "village-npc-1-idle": "village-npc-1-idle",
        "village-npc-2-idle": "village-npc-2-idle",
        "village-npc-3-idle": "village-npc-3-idle",
    }


async def test_manifest_rejects_a_missing_required_scale_reference(tmp_path: Path) -> None:
    tag = "missing-scale-reference"
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_village_run(run_dir, tag, village=None)
    reference = run_dir / f"character_{tag}_attack.scale-reference.json"
    await asyncio.to_thread(reference.unlink)
    await asyncio.to_thread(Path(f"{reference}.meta.json").unlink)

    with pytest.raises(
        ValueError,
        match="runtime-required role character-attack scale reference is missing",
    ):
        await write_scrolling_preview_manifest(
            run_dir=run_dir,
            tag=tag,
            transparency_mode=TransparencyMode.CHROMA,
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("extent_pixels", 999.0),
        ("frame_index", 0),
        ("cell_width", 1),
    ],
)
async def test_manifest_rejects_malformed_required_scale_reference(
    tmp_path: Path,
    field: str,
    replacement: object,
) -> None:
    tag = f"malformed-scale-{field}"
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_village_run(run_dir, tag, village=None)
    reference = run_dir / f"character_{tag}_attack.scale-reference.json"
    payload = json.loads(await asyncio.to_thread(reference.read_text, encoding="utf-8"))
    payload[field] = replacement
    measured_bytes = await asyncio.to_thread((run_dir / f"character_{tag}_attack.png").read_bytes)
    write_artifact_with_provenance(
        reference,
        BinaryArtifact(
            data=(json.dumps(payload, indent=2) + "\n").encode(),
            media_type="application/json",
        ),
        ProvenanceInput(
            provider="local",
            model="offline",
            prompt="measure actor scale",
            params={
                "metadata": {
                    "stage": "character-attack-scale-reference",
                    "measured_sha256": sha256_hex(measured_bytes),
                }
            },
            attempts=1,
        ),
    )

    with pytest.raises(
        ValueError,
        match="runtime-required role character-attack scale reference is invalid",
    ):
        await write_scrolling_preview_manifest(
            run_dir=run_dir,
            tag=tag,
            transparency_mode=TransparencyMode.CHROMA,
        )


async def test_manifest_rejects_a_stale_scale_reference_digest(
    tmp_path: Path,
) -> None:
    tag = "stale-scale-reference"
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_village_run(run_dir, tag, village=None)
    reference = run_dir / f"character_{tag}_attack.scale-reference.json"
    sidecar = Path(f"{reference}.meta.json")
    provenance = json.loads(await asyncio.to_thread(sidecar.read_text, encoding="utf-8"))
    provenance["params"]["metadata"]["measured_sha256"] = "0" * 64
    await asyncio.to_thread(sidecar.write_text, json.dumps(provenance), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="runtime-required role character-attack scale reference is stale",
    ):
        await write_scrolling_preview_manifest(
            run_dir=run_dir,
            tag=tag,
            transparency_mode=TransparencyMode.CHROMA,
        )


def _write_runtime_pair(
    run_dir: Path,
    requirement: manifest_module._RuntimeRequirement,
    *,
    mode: str,
    processor_override: str | None = None,
) -> None:
    canonical_data, geometry = _runtime_png(requirement)
    canonical_path = run_dir / requirement.path
    if requirement.alpha == "opaque":
        write_artifact_with_provenance(
            canonical_path,
            BinaryArtifact(data=canonical_data, media_type="image/png"),
            ProvenanceInput(
                provider="local",
                model="offline",
                prompt=f"create {requirement.role}",
                params={"metadata": {"stage": requirement.role, "opaque": True}},
                validation={"exact_contract_dimensions": True},
                attempts=1,
            ),
        )
        return

    raw_path = canonical_path.with_name(f"{canonical_path.stem}.raw.png")
    raw_data = _solid_png(requirement.width, requirement.height, alpha=False)
    write_artifact_with_provenance(
        raw_path,
        BinaryArtifact(data=raw_data, media_type="image/png"),
        ProvenanceInput(
            provider="local",
            model="offline",
            prompt=f"create raw {requirement.role}",
            params={"metadata": {"stage": requirement.role, "transparency_mode": mode}},
            validation={
                "exact_contract_dimensions": True,
                "output_width": requirement.width,
                "output_height": requirement.height,
            },
            attempts=1,
        ),
    )
    with Image.open(BytesIO(canonical_data)) as opened:
        alpha = opened.convert("RGBA").getchannel("A").tobytes()
    transparent = sum(value < 255 for value in alpha)
    nontransparent = sum(value > 0 for value in alpha)
    contract = contract_for_runtime_role(requirement.role)
    processor = processor_override or (
        "tileset-topology-mask"
        if contract is not None and contract.topology == "tileset"
        else "chroma-key+grid-cell-normalization"
        if contract is not None
        else "chroma-key"
    )
    write_artifact_with_provenance(
        canonical_path,
        BinaryArtifact(data=canonical_data, media_type="image/png"),
        ProvenanceInput(
            provider="local",
            model=processor,
            prompt=f"normalize {requirement.role}",
            refs=[raw_path.name],
            params={
                "transparency": {
                    "mode": mode,
                    "retained_raw_path": raw_path.name,
                    "raw_sha256": sha256_hex(raw_data),
                    "output_sha256": sha256_hex(canonical_data),
                    "processor": {"kind": processor, "version": "1"},
                },
                "metadata": {"stage": requirement.role},
            },
            validation={
                "alpha_nontrivial": True,
                "transparent_pixels": transparent,
                "nontransparent_pixels": nontransparent,
                "dimensions_preserved": True,
                "output_width": requirement.width,
                "output_height": requirement.height,
                **geometry,
            },
            attempts=1,
        ),
    )
    _write_required_scale_reference(run_dir, requirement)


def _write_required_scale_reference(
    run_dir: Path,
    requirement: manifest_module._RuntimeRequirement,
) -> None:
    stage = manifest_module._scale_reference_owner_stage(requirement)
    if stage is None:
        return
    contract = contract_for_runtime_role(requirement.role)
    assert contract is not None
    cell_width, cell_height = contract.cell_size(requirement.width, requirement.height)
    measured = parse_actor_scale_reference(
        {
            "part": "head",
            "top": 0.1,
            "bottom": 0.2,
            "left": 0.1,
            "right": 0.2,
            "confident": True,
            "evidence": "head bounded inside the selected frame",
        }
    )
    payload = {
        **evaluate_actor_scale_reference(
            measured,
            frame_width=cell_width,
            frame_height=cell_height,
        ),
        "frame_index": scale_reference_frame(stage),
        "cell_width": cell_width,
        "cell_height": cell_height,
    }
    artifact = run_dir / requirement.path
    reference = artifact.with_name(f"{artifact.stem}.scale-reference.json")
    write_artifact_with_provenance(
        reference,
        BinaryArtifact(
            data=(json.dumps(payload, indent=2) + "\n").encode(),
            media_type="application/json",
        ),
        ProvenanceInput(
            provider="local",
            model="offline",
            prompt="measure actor scale",
            params={
                "metadata": {
                    "stage": f"{stage}-scale-reference",
                    "measured_sha256": sha256_hex(artifact.read_bytes()),
                }
            },
            attempts=1,
        ),
    )


def _runtime_png(
    requirement: manifest_module._RuntimeRequirement,
) -> tuple[bytes, dict[str, object]]:
    if requirement.alpha == "opaque":
        return _solid_png(requirement.width, requirement.height, alpha=False), {}
    contract = contract_for_runtime_role(requirement.role)
    if contract is not None and contract.topology == "tileset":
        return normalize_canonical_grid(
            _solid_png(requirement.width, requirement.height, alpha=True), contract
        )
    image = Image.new("RGBA", (requirement.width, requirement.height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if contract is None:
        draw.rectangle(
            (
                requirement.width // 4,
                requirement.height // 4,
                requirement.width * 3 // 4,
                requirement.height * 3 // 4,
            ),
            fill=(70, 120, 180, 255),
        )
        return _png_bytes(image), {}
    cell_width, cell_height = contract.cell_size(requirement.width, requirement.height)
    for row in range(contract.rows):
        for column in range(contract.columns):
            left = column * cell_width + contract.gutter
            top = row * cell_height + contract.gutter
            draw.rectangle(
                (
                    left,
                    top,
                    (column + 1) * cell_width - contract.gutter - 1,
                    (row + 1) * cell_height - contract.gutter - 1,
                ),
                fill=(70 + column * 10, 100 + row * 20, 180, 255),
            )
    data = _png_bytes(image)
    return data, validate_canonical_grid(data, contract)


def _solid_png(width: int, height: int, *, alpha: bool) -> bytes:
    mode = "RGBA" if alpha else "RGB"
    colour = (80, 120, 60, 255) if alpha else (80, 120, 60)
    return _png_bytes(Image.new(mode, (width, height), colour))


def _png_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _fallback_fixture(
    root: Path,
    *,
    status: str = "redistribution-approved",
    digest: str | None = None,
    schema_version: int = 2,
) -> Path:
    fallback = root / "fallback.mp3"
    data = b"offline-fallback-fixture"
    fallback.write_bytes(data)
    actual_digest = hashlib.sha256(data).hexdigest()
    rights: dict[str, object]
    if status == "unreviewed":
        rights = {
            "status": status,
            "attribution": [],
            "basis": [],
            "reviewed_at": None,
        }
    else:
        rights = {
            "status": status,
            "attribution": [],
            "basis": [f"sha256:{actual_digest}"],
            "reviewed_at": "2026-08-14T00:00:00.000Z",
        }
    sidecar = {
        "schema_version": schema_version,
        "artifact": {
            "sha256": digest or actual_digest,
            "bytes": len(data),
            "media_type": "audio/mpeg",
        },
        "references": [],
        "refs": [],
        "inputs": [
            {
                "ref": f"sha256:{actual_digest}",
                "sha256": actual_digest,
                "source": "content",
                "bytes": len(data),
                "media_type": "audio/mpeg",
            }
        ],
        "rights": rights,
    }
    Path(f"{fallback}.meta.json").write_text(json.dumps(sidecar), encoding="utf-8")
    return fallback


def _allow_music_only_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        manifest_module,
        "_collect_runtime_assets",
        lambda _run_dir, tag, *_args: (
            [],
            {
                "path": f"world_spec_{tag}.json",
                "provenancePath": f"world_spec_{tag}.json.meta.json",
            },
        ),
    )
