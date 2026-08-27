from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

import stage_gen.recipes.scrolling_preview.manifest as manifest_module
from stage_gen.components.character_profile import resolve_character_profile_binding
from stage_gen.config import StageGenConfig, TransparencyMode
from stage_gen.recipes.base import StageContext, resolve_force_stage_plan
from stage_gen.recipes.scrolling_preview.executor import (
    ScrollingPreviewExecutor,
    _character_profile_identity_matches,
    _ImageSpec,
    _is_player_asset_stage,
)
from stage_gen.recipes.scrolling_preview.profile import (
    character_profile_tag_suffix,
)
from stage_gen.recipes.scrolling_preview.recipe import (
    parse_scrolling_preview_input,
    scrolling_preview_recipe,
    scrolling_preview_tag,
)

PROFILE_TOML = """\
schema_version = 1
kind = "character-profile-v1"
profile_id = "mira-vale-cartographer"
revision = 1
display_name = "Mira Vale"
age_years = 29
description = "Original adult cartographer"
visual_identity = "Warm brown skin, gray-green eyes, and a black undercut"
wardrobe = "Teal field jacket and charcoal work trousers"
invariants = ["Gray-green eyes", "Teal field jacket"]

[rights]
status = "unreviewed"
basis = ["Original test text"]
"""


def _binding(root: Path, *, contents: str = PROFILE_TOML) -> dict[str, object]:
    source = root / "library/characters/mira-vale-cartographer/profile.toml"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(contents, encoding="utf-8")
    return {
        "schema_version": 1,
        "kind": "character-profile-binding-v1",
        "ref": "library/characters/mira-vale-cartographer/profile.toml",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }


def _context(tmp_path: Path, binding: dict[str, object]) -> StageContext:
    return StageContext(
        input={"prompt": "original coast", "character_profile": binding},
        tag="coast-profile-v1-test-chroma",
        run_dir=tmp_path / "run",
        config=StageGenConfig(
            out_dir=str(tmp_path),
            character_library_root=tmp_path,
            open_router_api_key="offline",
            transparency_mode="chroma",
        ),
    )


def test_profile_binding_is_exact_strict_and_unbound_path_is_identical(tmp_path: Path) -> None:
    unbound = parse_scrolling_preview_input({"prompt": "original coast"})
    assert unbound == {"prompt": "original coast"}
    assert scrolling_preview_recipe.stages_for(unbound) is scrolling_preview_recipe.stages

    binding = _binding(tmp_path)
    parsed = parse_scrolling_preview_input(
        {"prompt": "original coast", "character_profile": binding}
    )
    assert parsed["character_profile"] == binding
    stages = scrolling_preview_recipe.stages_for(parsed)
    assert [stage.name for stage in stages] == [
        "profile-resolve",
        "concept",
        "world-spec",
        "wave-a",
        "wave-b",
        "post-split",
        "manifest",
    ]
    by_name = {stage.name: stage for stage in stages}
    assert by_name["profile-resolve"].depends_on == ()
    assert by_name["world-spec"].depends_on == ("concept",)
    assert by_name["wave-a"].depends_on == ("world-spec", "profile-resolve")
    force = resolve_force_stage_plan(stages, ("profile-resolve",))
    assert force.affected == {
        "profile-resolve",
        "wave-a",
        "wave-b",
        "post-split",
        "manifest",
    }
    assert scrolling_preview_tag(parsed).endswith(character_profile_tag_suffix(binding))

    revised_binding = {**binding, "source_sha256": "f" * 64}
    assert character_profile_tag_suffix(revised_binding) == character_profile_tag_suffix(binding)

    for invalid in (
        {**binding, "sourceSha256": binding["source_sha256"]},
        {**binding, "unknown": True},
        {**binding, "ref": "/tmp/profile.toml"},
        {**binding, "ref": "../profile.toml"},
    ):
        with pytest.raises(ValueError):
            parse_scrolling_preview_input(
                {"prompt": "original coast", "character_profile": invalid}
            )


async def test_profile_stage_requires_explicit_character_library_root(tmp_path: Path) -> None:
    binding = _binding(tmp_path)
    context = _context(tmp_path, binding)
    context = StageContext(
        input=context.input,
        tag=context.tag,
        run_dir=context.run_dir,
        config=context.config.model_copy(update={"character_library_root": None}),
    )
    executor = ScrollingPreviewExecutor(
        image_service=cast(Any, None),
        structured_service=cast(Any, None),
    )
    with pytest.raises(ValueError, match="requires character_library_root"):
        await executor.run_scrolling_preview_stage("profile-resolve", context)


def test_resolver_binds_source_and_canonical_digests_and_rejects_tamper(
    tmp_path: Path,
) -> None:
    binding = _binding(tmp_path)
    resolved = resolve_character_profile_binding(binding, character_library_root=tmp_path)
    assert resolved.source_sha256 == binding["source_sha256"]
    assert hashlib.sha256(resolved.canonical_bytes).hexdigest() == resolved.canonical_sha256
    assert resolved.identity()["profile_id"] == "mira-vale-cartographer"

    source = tmp_path / str(binding["ref"])
    source.write_text(PROFILE_TOML.replace("revision = 1", "revision = 2"), encoding="utf-8")
    with pytest.raises(ValueError, match="source_sha256 mismatch"):
        resolve_character_profile_binding(binding, character_library_root=tmp_path)


def test_resolver_confines_exact_library_path_and_rejects_symlink_components(
    tmp_path: Path,
) -> None:
    binding = _binding(tmp_path)
    with pytest.raises(ValueError, match="must equal library/characters"):
        resolve_character_profile_binding(
            {**binding, "ref": "profiles/mira-vale-cartographer/profile.toml"},
            character_library_root=tmp_path,
        )
    wrong = tmp_path / "library/characters/wrong-id/profile.toml"
    wrong.parent.mkdir(parents=True)
    wrong.write_text(PROFILE_TOML, encoding="utf-8")
    with pytest.raises(ValueError, match="profile_id must match"):
        resolve_character_profile_binding(
            {
                **binding,
                "ref": "library/characters/wrong-id/profile.toml",
                "source_sha256": hashlib.sha256(wrong.read_bytes()).hexdigest(),
            },
            character_library_root=tmp_path,
        )
    linked_root = tmp_path / "linked"
    linked_root.mkdir()
    (linked_root / "library").symlink_to(tmp_path / "library", target_is_directory=True)
    with pytest.raises(ValueError, match="must not traverse a symlink"):
        resolve_character_profile_binding(binding, character_library_root=linked_root)


async def test_profile_resolve_persists_validated_canonical_pair_and_repairs_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binding = _binding(tmp_path)
    monkeypatch.chdir(tmp_path)
    context = _context(tmp_path, binding)
    await asyncio.to_thread(context.run_dir.mkdir, parents=True)
    executor = ScrollingPreviewExecutor(
        image_service=cast(Any, None),
        structured_service=cast(Any, None),
    )

    paths = await executor.run_scrolling_preview_stage("profile-resolve", context)
    artifact = Path(paths[0])
    sidecar = json.loads(await asyncio.to_thread(Path(paths[1]).read_text, encoding="utf-8"))
    identity = sidecar["params"]["character_profile"]
    artifact_bytes = await asyncio.to_thread(artifact.read_bytes)
    assert (
        artifact_bytes
        == resolve_character_profile_binding(
            binding, character_library_root=tmp_path
        ).canonical_bytes
    )
    assert identity["source_sha256"] == binding["source_sha256"]
    assert identity["canonical_sha256"] == hashlib.sha256(artifact_bytes).hexdigest()
    assert sidecar["inputs"][0]["sha256"] == binding["source_sha256"]

    original_sidecar = await asyncio.to_thread(Path(paths[1]).read_bytes)
    await executor.run_scrolling_preview_stage("profile-resolve", context)
    assert await asyncio.to_thread(Path(paths[1]).read_bytes) == original_sidecar
    await asyncio.to_thread(artifact.write_bytes, b"tampered")
    await executor.run_scrolling_preview_stage("profile-resolve", context)
    assert (
        await asyncio.to_thread(artifact.read_bytes)
        == resolve_character_profile_binding(
            binding, character_library_root=tmp_path
        ).canonical_bytes
    )


async def test_only_player_concept_prompt_consumes_profile_prose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binding = _binding(tmp_path)
    monkeypatch.chdir(tmp_path)
    context = _context(tmp_path, binding)
    await asyncio.to_thread(context.run_dir.mkdir, parents=True)
    concept = context.run_dir / f"concept_{context.tag}.png"
    await asyncio.to_thread(concept.write_bytes, b"opaque world concept")
    executor = ScrollingPreviewExecutor(
        image_service=cast(Any, None),
        structured_service=cast(Any, None),
    )
    await executor.run_scrolling_preview_stage("profile-resolve", context)

    class Item:
        def __init__(self, index: int) -> None:
            self.name = f"item {index}"
            self.brief = "original collectible"
            self.index = index

        def model_dump(self, *, mode: str) -> dict[str, object]:
            assert mode == "json"
            return {"kind": f"kind-{self.index}", "name": self.name, "brief": self.brief}

    world = cast(
        Any,
        type(
            "World",
            (),
            {
                "layers": (),
                "items": tuple(Item(index) for index in range(8)),
                "mobs": (),
                "obstacles": (),
            },
        )(),
    )

    async def read_world(_context: StageContext) -> Any:
        return world

    captured: list[_ImageSpec] = []

    async def capture(_context: StageContext, specs: list[_ImageSpec]) -> tuple[str, ...]:
        captured.extend(specs)
        return ()

    monkeypatch.setattr("stage_gen.recipes.scrolling_preview.executor._read_world_spec", read_world)
    monkeypatch.setattr(executor, "_fan_out", capture)
    await executor.run_scrolling_preview_stage("wave-a", context)

    by_stage = {spec.stage: spec.prompt for spec in captured}
    assert "Display name: Mira Vale." in by_stage["character-concept"]
    assert "Gray-green eyes" in by_stage["character-concept"]
    assert all(
        "Durable player character profile" not in prompt
        for stage, prompt in by_stage.items()
        if stage != "character-concept"
    )


def test_profile_change_invalidates_only_allowlisted_player_asset_metadata() -> None:
    old = {"canonical_sha256": "a" * 64}
    changed = {"canonical_sha256": "b" * 64}
    player_sidecar = {"params": {"metadata": {"character_profile": old}}}
    world_sidecar = {"params": {"metadata": {"stage": "world-spec"}}}

    assert not _character_profile_identity_matches(player_sidecar, changed)
    assert _character_profile_identity_matches(world_sidecar, None)
    assert all(
        _is_player_asset_stage(stage)
        for stage in (
            "character-concept",
            "character-master-strip-idle",
            "character-attack",
            "character-climb",
            "character-isolated-view-0",
        )
    )
    assert not any(
        _is_player_asset_stage(stage)
        for stage in ("concept", "world-spec", "layer-sky", "items", "mob-concept-0")
    )


async def test_opt_in_manifest_is_v7_and_rejects_profile_lineage_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binding = _binding(tmp_path)
    monkeypatch.chdir(tmp_path)
    context = _context(tmp_path, binding)
    await asyncio.to_thread(context.run_dir.mkdir, parents=True)
    executor = ScrollingPreviewExecutor(
        image_service=cast(Any, None),
        structured_service=cast(Any, None),
    )
    await executor.run_scrolling_preview_stage("profile-resolve", context)

    monkeypatch.setattr(manifest_module, "_collect_canonical_images", lambda *_args: [])
    monkeypatch.setattr(manifest_module, "_collect_image_repeat", lambda *_args: [])
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
    result = await manifest_module.write_scrolling_preview_manifest(
        run_dir=context.run_dir,
        tag=context.tag,
        transparency_mode=TransparencyMode.CHROMA,
        character_profile=True,
    )
    manifest = json.loads(
        await asyncio.to_thread(Path(result.manifest_path).read_text, encoding="utf-8")
    )
    assert manifest["schema_version"] == 7

    def assert_snake(value: object) -> None:
        if isinstance(value, dict):
            assert all(
                key == key.lower() and not any(char.isupper() for char in key) for key in value
            )
            for item in value.values():
                assert_snake(item)
        elif isinstance(value, list):
            for item in value:
                assert_snake(item)

    assert_snake(manifest)
    assert manifest["character_profile"]["binding"] == binding
    profile_artifact = context.run_dir / manifest["character_profile"]["path"]
    profile_artifact_bytes = await asyncio.to_thread(profile_artifact.read_bytes)
    assert (
        manifest["character_profile"]["canonical_sha256"]
        == hashlib.sha256(profile_artifact_bytes).hexdigest()
    )
    manifest_sidecar = json.loads(
        await asyncio.to_thread(
            Path(f"{result.manifest_path}.meta.json").read_text,
            encoding="utf-8",
        )
    )
    assert manifest_sidecar["params"]["character_profile_source_sha256"] == binding["source_sha256"]
    assert (
        manifest_sidecar["params"]["character_profile_canonical_sha256"]
        == manifest["character_profile"]["canonical_sha256"]
    )
    assert manifest["character_profile"]["path"] in manifest_sidecar["refs"]
    assert manifest["character_profile"]["provenance_path"] in manifest_sidecar["refs"]

    profile_sidecar = context.run_dir / f"character_profile_{context.tag}.json.meta.json"
    tampered = json.loads(await asyncio.to_thread(profile_sidecar.read_text, encoding="utf-8"))
    tampered["params"]["character_profile"]["source_sha256"] = "0" * 64
    await asyncio.to_thread(profile_sidecar.write_text, json.dumps(tampered), encoding="utf-8")
    run_names = await asyncio.to_thread(lambda: {path.name for path in context.run_dir.iterdir()})
    with pytest.raises(ValueError, match="lineage mismatch"):
        manifest_module._collect_character_profile_binding(
            context.run_dir,
            context.tag,
            run_names,
        )
