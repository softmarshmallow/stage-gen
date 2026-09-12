from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

MODEL_POLICY_SNAPSHOT_RESOURCE = "stage_gen/model_policy_snapshot.json"
MODEL_POLICY_SNAPSHOT_UNPACKED_LIMIT = 64_000
PORTRAIT_FACE_MODULES = {
    "stage_gen/components/portrait_motion/face_crop.py",
    "stage_gen/components/portrait_motion/face_location.py",
    "stage_gen/components/portrait_motion/face_patches.py",
    "stage_gen/components/portrait_motion/face_playback.py",
    "stage_gen/orchestration/portrait_face.py",
    "stage_gen/orchestration/portrait_face_location.py",
}

WHEEL_RESOURCES = {
    MODEL_POLICY_SNAPSHOT_RESOURCE,
    "stage_gen/resources/fixtures/image_gen_templates/inventory_template.png",
    "stage_gen/resources/fixtures/image_gen_templates/terrain_atlas_12x4_template.png",
    "stage_gen/resources/fixtures/image_gen_templates/terrain_atlas_godot_topology_reference.png",
    "stage_gen/resources/fixtures/prompts.txt",
    "stage_gen/resources/fixtures/styles.txt",
    "stage_gen/resources/prompting/image_style_vocabulary_v1.json",
    "stage_gen/resources/skills/anchor-image-style/SKILL.md",
    "stage_gen/resources/terrain/godot_3x3_minimal_lookup_v1.json",
}
SDIST_RESOURCES = {f"src/{name}" for name in WHEEL_RESOURCES}
EXPECTED_SDIST_FILES = {
    ".env.example",
    "LICENSE",
    "README.md",
    "VERIFICATION.md",
    "docs/README.md",
    "docs/testing.md",
    "examples/pipelines/local_media.py",
    "examples/pipelines/portrait_processing.py",
    "examples/pipelines/README.md",
    "pyproject.toml",
    "scripts/check.py",
    "src/stage_gen/__init__.py",
    "src/stage_gen/py.typed",
    "tests/contract/fixtures/tag-vectors.json",
    "tests/contract/test_packaged_resources.py",
    "scripts/build_hooks.py",
}
LEGACY_TOP_LEVEL = {"components", "fixtures", "stage-gen", "web"}
BANNED_SEGMENTS = {
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "qa-screenshots",
    "screenshots",
}
MEDIA_SUFFIXES = {
    ".aac",
    ".flac",
    ".gif",
    ".jpeg",
    ".jpg",
    ".m4a",
    ".mp3",
    ".mp4",
    ".ogg",
    ".otf",
    ".png",
    ".ttf",
    ".wav",
    ".webm",
    ".webp",
}
IMAGE_MEDIA_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".webp"}
#: A typeface is media, and until decision 0063 it was in no suffix set this gate
#: reads: two committed faces were outside both the aggregate ceiling and the
#: per-root location rules. They are counted here like every other binary.
FONT_MEDIA_SUFFIXES = {".otf", ".ttf"}
CONCEPT_GALLERY_PREFIX = ("concept-studio", "gallery")
CONCEPT_STYLE_DICTIONARY_PREFIX = ("concept-studio", "style-dictionary")
CONCEPT_MEDIA_PREFIXES = {
    CONCEPT_GALLERY_PREFIX,
    CONCEPT_STYLE_DICTIONARY_PREFIX,
}
STYLE_DICTIONARY_ROOT = PurePosixPath(*CONCEPT_STYLE_DICTIONARY_PREFIX)
STYLE_DICTIONARY_MANIFEST = STYLE_DICTIONARY_ROOT / "manifest.json"
STYLE_DICTIONARY_REVIEW = STYLE_DICTIONARY_ROOT / "images/style-dictionary.visual-review.md"
README_MARKETING_ROOT = PurePosixPath(".github/assets/readme")
DOCUMENTED_MEDIA_RECORD = PurePosixPath("docs/media/theme-art-direction-example.webp")
STYLE_DICTIONARY_REVIEWERS = {
    "mobile-live-service": ("mobile_exact_webp_reviewer_2026_08_26",),
    "indie-pc-console": (
        "indie_exact_webp_reviewer_a_2026_08_26",
        "indie_exact_webp_reviewer_b_2026_08_26",
    ),
    "western-card-casual": ("western_exact_webp_reviewer_2026_08_26",),
}
GIT_MEDIA_LIMITS = {
    "audio": 20 * 1024 * 1024,
    "font": 2 * 1024 * 1024,
    "image": 5 * 1024 * 1024,
    "video": 25 * 1024 * 1024,
}
GIT_MEDIA_TOTAL_LIMIT = 100 * 1024 * 1024
SECRET_SUFFIXES = {".key", ".p12", ".pem", ".pfx"}
GAME_MODULES = {
    "demo_game_tools",
    "demo_game_collection",
    "bellweather_pipeline",
    "iron_petal_unit_pipeline",
    "ember_hollow_pipeline",
    "the_grain_pipeline",
}
GAME_INPUT_ROOTS = tuple(
    map(
        PurePosixPath,
        (
            "godot/games/bellweather/inputs/default",
            "godot/games/bellweather/inputs/waves",
            "godot/games/iron_petal_unit/inputs",
            "godot/games/ember_hollow/inputs",
            "godot/games/the_grain/inputs",
        ),
    )
)


def test_built_distributions_are_small_clean_and_resource_complete(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    distribution_directory = tmp_path / "distributions"
    environment = os.environ.copy()
    environment.pop("OPENAI_API_KEY", None)
    environment.pop("OPENROUTER_API_KEY", None)
    environment.pop("FAL_KEY", None)
    environment.pop("ELEVENLABS_API_KEY", None)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--outdir",
            str(distribution_directory),
        ],
        cwd=repository,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = list(distribution_directory.glob("*.whl"))
    sdists = list(distribution_directory.glob("*.tar.gz"))
    assert len(wheels) == len(sdists) == 1
    assert wheels[0].stat().st_size < 1_500_000
    assert sdists[0].stat().st_size < 4_000_000

    installed = tmp_path / "installed"
    with zipfile.ZipFile(wheels[0]) as wheel:
        wheel_entries = {
            entry.filename: entry.file_size for entry in wheel.infolist() if not entry.is_dir()
        }
        _assert_archive_hygiene(wheel_entries, resource_prefix="stage_gen/resources/")
        # Budgets exclude the independently bounded route snapshot.
        model_policy_snapshot_size = wheel_entries[MODEL_POLICY_SNAPSHOT_RESOURCE]
        assert model_policy_snapshot_size < MODEL_POLICY_SNAPSHOT_UNPACKED_LIMIT
        # Character candidate final-m1-28 (2026-09-13): non-snapshot wheel slice
        # measured 3,727,974 B, of which the character capability is 967,681 B
        # across 85 Python/data files. No new media; the executable model snapshot
        # retains its separate unchanged cap. The compressed wheel (1,140,885 B),
        # the sdist (2,091,676 B) and the sdist slice (8,069,738 B) stay under
        # their incumbent limits. The raised cap leaves about 170 KB for growth.
        assert sum(wheel_entries.values()) - model_policy_snapshot_size < 3_900_000
        assert wheel_entries.keys() >= WHEEL_RESOURCES
        assert wheel_entries.keys() >= PORTRAIT_FACE_MODULES
        assert all(wheel_entries[name] > 0 for name in WHEEL_RESOURCES)
        assert {
            "gnode/__init__.py",
            "gnode/py.typed",
            "stage_gen/__init__.py",
            "stage_gen/py.typed",
            "stage_gen/resources/__init__.py",
        } <= wheel_entries.keys()
        assert any(name.endswith(".dist-info/METADATA") for name in wheel_entries)
        assert any(name.endswith(".dist-info/entry_points.txt") for name in wheel_entries)
        assert not any(
            name.startswith(
                (
                    "godot/",
                    "stage_gen_legacy/",
                    "concept_studio/",
                    *(f"{module}/" for module in GAME_MODULES),
                )
            )
            for name in wheel_entries
        )
        assert not any(name.startswith("tests/") for name in wheel_entries)
        assert not any("/universe/examples/lantern_ferry/" in name for name in wheel_entries)
        assert not any(name.startswith("library/") for name in wheel_entries)
        assert not any(name.startswith("concept-studio/") for name in wheel_entries)
        assert not any(_is_docs_media(name) for name in wheel_entries)
    installer_venv = tmp_path / "installer-venv"
    subprocess.run(
        [sys.executable, "-m", "venv", str(installer_venv)],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    installer_python = installer_venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run(
        [
            str(installer_python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--no-cache-dir",
            "--target",
            str(installed),
            str(wheels[0]),
        ],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    extracted_sdist_parent = tmp_path / "extracted-sdist"
    with tarfile.open(sdists[0], mode="r:gz") as sdist:
        members = sdist.getmembers()
        assert all(member.isfile() or member.isdir() for member in members)
        root, sdist_entries = _sdist_file_entries(members)
        _assert_archive_hygiene(sdist_entries, resource_prefix="src/stage_gen/resources/")
        # The size assertions below are what bound the archive. There is deliberately
        # no entry count: a count is a number that has to be re-pinned on every
        # honest addition, and the comment explaining each re-pin was a changelog
        # nobody reads. What a count was standing in for - a stray directory swept
        # into the sdist - is asserted directly: nothing Git ignores may ship.
        ignored = subprocess.run(
            ["git", "check-ignore", "--stdin", "--no-index"],
            cwd=Path(__file__).resolve().parents[2],
            input="\n".join(sorted(sdist_entries)),
            capture_output=True,
            text=True,
            check=False,
        )
        assert ignored.returncode in {0, 1}, ignored.stderr
        assert ignored.stdout.strip() == "", ignored.stdout
        sdist_snapshot_size = sdist_entries[f"src/{MODEL_POLICY_SNAPSHOT_RESOURCE}"]
        assert sdist_snapshot_size < MODEL_POLICY_SNAPSHOT_UNPACKED_LIMIT
        assert sum(sdist_entries.values()) - sdist_snapshot_size < 11_070_000
        assert not any(name.startswith("godot/") for name in sdist_entries)
        assert sdist_entries.keys() >= SDIST_RESOURCES | EXPECTED_SDIST_FILES
        assert sdist_entries.keys() >= {f"src/{name}" for name in PORTRAIT_FACE_MODULES}
        assert not any(name.startswith("library/") for name in sdist_entries)
        assert not any(name.startswith("concept-studio/") for name in sdist_entries)
        assert all(sdist_entries[name] > 0 for name in SDIST_RESOURCES)
        assert not any(_is_docs_media(name) for name in sdist_entries)
        env_handle = sdist.extractfile(f"{root}/.env.example")
        assert env_handle is not None
        env_example = env_handle.read().decode("utf-8")
        assert _env_value(env_example, "OPENAI_API_KEY") == ""
        assert _env_value(env_example, "OPENROUTER_API_KEY") == ""
        assert _env_value(env_example, "FAL_KEY") == ""
        assert _env_value(env_example, "ELEVENLABS_API_KEY") == ""
        sdist.extractall(extracted_sdist_parent, filter="data")

    extracted_sdist = extracted_sdist_parent / root
    packaged_metadata = tomllib.loads((extracted_sdist / "pyproject.toml").read_text())
    assert "uv" not in packaged_metadata["tool"]
    assert set(packaged_metadata["dependency-groups"]) == {"dev"}
    assert "uv.lock" not in sdist_entries
    rebuilt = tmp_path / "rebuilt"
    subprocess.run(
        [sys.executable, "-m", "build", "--no-isolation", "--wheel", "--outdir", str(rebuilt)],
        cwd=extracted_sdist,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    with zipfile.ZipFile(next(rebuilt.glob("*.whl"))) as rebuilt_wheel:
        assert set(rebuilt_wheel.namelist()) == set(wheel_entries)
    sdist_test_environment = environment | {"PYTHONPATH": str(extracted_sdist / "src")}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/unit/test_config.py",
        ],
        cwd=extracted_sdist,
        env=sdist_test_environment,
        check=True,
        capture_output=True,
        text=True,
    )

    probe = """
import importlib
import importlib.abc
import sys
from pathlib import Path

class NoConsumerImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {
            "stage_gen_legacy",
            "concept_studio",
            "demo_game_tools",
            "demo_game_collection",
            "bellweather_pipeline",
            "iron_petal_unit_pipeline",
            "ember_hollow_pipeline",
            "the_grain_pipeline",
        }:
            raise AssertionError(f"core installation imports consumer: {fullname}")
        return None

sys.meta_path.insert(0, NoConsumerImports())
from stage_gen.pipeline import define, inspect, plan, run
from stage_gen.recipes.looping_parallax import create_pipeline
from stage_gen.resources import (
    image_style_resource_digests,
    image_style_skill_path,
    image_style_vocabulary_path,
    image_template_dir,
    required_resource_paths,
    terrain_atlas_lookup_path,
    terrain_atlas_template_path,
    terrain_atlas_topology_reference_path,
)
from stage_gen.image_prompting import load_image_style_resources
from stage_gen.model_policy_maintenance import load_active_model_policy_snapshot

paths = required_resource_paths()
assert len(paths) == 8
assert all(path.is_file() and path.stat().st_size > 0 for path in paths)
assert image_template_dir().is_dir()
assert terrain_atlas_template_path().is_file()
assert terrain_atlas_topology_reference_path().is_file()
assert terrain_atlas_lookup_path().is_file()
style_resources = load_image_style_resources()
assert image_style_skill_path().read_text(encoding="utf-8").startswith(
    "---\\nname: anchor-image-style\\n"
)
assert image_style_vocabulary_path().is_file()
assert image_style_resource_digests() == {
    "skill_sha256": style_resources.skill.sha256,
    "vocabulary_sha256": style_resources.vocabulary_sha256,
}
snapshot = load_active_model_policy_snapshot()
assert snapshot.kind == "stage-gen-model-policy-snapshot-v1"
assert snapshot.routes and snapshot.policies
assert snapshot.recipes == () and snapshot.generated_files == ()
face_surfaces = {
    "stage_gen.components.portrait_motion.face_crop": ("create_working_crop", "restore_feature"),
    "stage_gen.components.portrait_motion.face_location": (
        "locator_node_type", "validate_location"
    ),
    "stage_gen.components.portrait_motion.face_patches": (
        "make_face_input", "isolate_patch", "apply_offset_patch"
    ),
    "stage_gen.components.portrait_motion.face_playback": (
        "build_face_combinations", "encode_face_preview"
    ),
    "stage_gen.orchestration.portrait_face": (
        "prepare_face_run", "run_face_pipeline", "verify_face_run"
    ),
    "stage_gen.orchestration.portrait_face_location": (
        "prepare_locator", "run_locator", "verify_locator", "load_locator_plan"
    ),
}
for name, names in face_surfaces.items():
    module = importlib.import_module(name)
    assert Path(module.__file__).resolve().is_relative_to(Path("installed").resolve())
    assert all(callable(getattr(module, name)) for name in names)
"""
    probe_environment = environment | {"PYTHONPATH": str(installed)}
    subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tmp_path,
        env=probe_environment,
        check=True,
        capture_output=True,
        text=True,
    )


def test_repository_media_obeys_git_size_and_location_policy() -> None:
    repository = Path(__file__).resolve().parents[2]
    worktree_files = _worktree_files(repository)
    relative_paths = {
        PurePosixPath(name)
        for name in worktree_files
        if PurePosixPath(name).suffix.lower() in MEDIA_SUFFIXES
    }
    docs_root = repository / "docs"
    relative_paths.update(
        PurePosixPath(path.relative_to(repository).as_posix())
        for path in docs_root.rglob("*")
        if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES
    )
    for prefix in CONCEPT_MEDIA_PREFIXES:
        concept_media_root = repository.joinpath(*prefix)
        assert not concept_media_root.is_symlink()
        if concept_media_root.exists():
            assert concept_media_root.is_dir()
            for path in concept_media_root.rglob("*"):
                assert not path.is_symlink()
                if path.suffix.lower() in MEDIA_SUFFIXES:
                    relative_paths.add(PurePosixPath(path.relative_to(repository).as_posix()))
    readme_marketing_root = repository / README_MARKETING_ROOT
    assert not readme_marketing_root.is_symlink()
    if readme_marketing_root.exists():
        assert readme_marketing_root.is_dir()
        relative_paths.update(
            PurePosixPath(path.relative_to(repository).as_posix())
            for path in readme_marketing_root.iterdir()
            if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES
        )

    total = 0
    for relative in sorted(relative_paths):
        assert relative.parts[0] in {
            ".github",
            "concept-studio",
            "docs",
            "fixtures",
            "godot",
            "src",
            "web",
        }
        concept_prefix = relative.parts[:2]
        is_concept_media = concept_prefix in CONCEPT_MEDIA_PREFIXES
        is_style_dictionary = concept_prefix == CONCEPT_STYLE_DICTIONARY_PREFIX
        if relative.parts[0] == "concept-studio":
            assert is_concept_media
            assert len(relative.parts) > len(concept_prefix)
            assert relative.suffix.lower() in IMAGE_MEDIA_SUFFIXES
        if relative.parts[0] == ".github":
            assert relative.parent == README_MARKETING_ROOT
            assert relative.suffix.lower() == ".webp"
        if is_style_dictionary:
            assert relative.parent == STYLE_DICTIONARY_ROOT / "images"
            assert relative.suffix.lower() == ".webp"
        if relative.parts[0] == "src" and relative.parts[:3] != ("src", "stage_gen", "resources"):
            assert relative == PurePosixPath(
                "src/stage_gen/recipes/universe/examples/lantern_ferry/references/poster.png"
            )
            example = repository / relative.parent.parent
            contract = tomllib.loads((example / "universe.toml").read_text())
            assert (
                hashlib.sha256((repository / relative).read_bytes()).hexdigest()
                == (contract["poster"]["source_sha256"])
            )
            assert contract["poster"]["rights_status"] == "unreviewed"
            assert contract["poster"]["rights_basis"]
            assert contract["rights"]["publication_authorized"] is False
        is_game_resource = relative.is_relative_to(
            "godot/tools/python/src/demo_game_collection/resources"
        )
        if is_game_resource:
            assert relative.relative_to(
                "godot/tools/python/src/demo_game_collection/resources"
            ).parts == ("music", "preview-loop.mp3")
            artifact = repository / relative
            sidecar = json.loads(Path(f"{artifact}.meta.json").read_text())
            assert (
                sidecar["artifact"]["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
            )
            assert sidecar["artifact"]["bytes"] == artifact.stat().st_size
            assert sidecar["rights"]["status"] == "redistribution-approved"
            assert sidecar["rights"]["basis"]
        if relative.parts[0] == "godot" and not is_game_resource:
            input_root = next(
                (root for root in GAME_INPUT_ROOTS if relative.is_relative_to(root)), None
            )
            assert input_root is not None, f"{relative} is outside approved game input roots"
            package_parts = relative.relative_to(input_root).parts
            assert len(package_parts) >= 2
            is_pinned_take = (
                package_parts[:2] == ("runner", "audio")
                and len(package_parts) == 3
                and relative.suffix.lower() == ".mp3"
            )
            is_package_font = (
                package_parts[0] == "fonts"
                and len(package_parts) == 2
                and relative.suffix.lower() in FONT_MEDIA_SUFFIXES
            )
            if is_pinned_take:
                assert relative.with_suffix(".mp3.meta.json").as_posix() in worktree_files
            elif is_package_font:
                licences = {
                    name
                    for name in worktree_files
                    if name.startswith(f"{relative.parent.as_posix()}/")
                    and PurePosixPath(name).suffix.lower() in {".md", ".txt"}
                }
                assert licences, f"{relative} has no licence text beside it"
            else:
                assert package_parts[0] == "references" or (
                    package_parts[0] == "rooms"
                    and len(package_parts) >= 4
                    and package_parts[2] == "references"
                )
                assert relative.suffix.lower() in IMAGE_MEDIA_SUFFIXES
        if relative.parts[0] == "web":
            assert relative.parts[:2] in {("web", "public"), ("web", "scripts")}
        if relative.suffix.lower() in {".mp4", ".webm"}:
            assert relative.parts[0] == "docs"
        path = repository / relative
        assert path.is_file() and not path.is_symlink()
        size = path.stat().st_size
        family = _media_family(relative.suffix.lower())
        assert 0 < size <= GIT_MEDIA_LIMITS[family]
        total += size
        if relative.parts[0] == "docs" or is_concept_media:
            ignored = subprocess.run(
                ["git", "check-ignore", "--quiet", "--", relative.as_posix()],
                cwd=repository,
                check=False,
            )
            assert ignored.returncode == 1
        if relative.parts[0] == "docs":
            # Documentation media is not a publication root, so it carries no provenance
            # sidecar. The one allowance is a record kept for its content rather than for
            # the gate: the source prompts and redistribution basis behind a published
            # AI-generated image, cited from docs/visual-content-direction-case-study.md.
            assert (Path(f"{path}.meta.json").exists()) == (relative == DOCUMENTED_MEDIA_RECORD)
        if concept_prefix == CONCEPT_GALLERY_PREFIX:
            sidecar = Path(f"{path}.meta.json")
            assert sidecar.is_file() and not sidecar.is_symlink()
            sidecar_relative = sidecar.relative_to(repository).as_posix()
            sidecar_ignored = subprocess.run(
                ["git", "check-ignore", "--quiet", "--", sidecar_relative],
                cwd=repository,
                check=False,
            )
            assert sidecar_ignored.returncode == 1
        if is_style_dictionary:
            assert not Path(f"{path}.meta.json").exists()
    assert total <= GIT_MEDIA_TOTAL_LIMIT


def test_style_dictionary_collection_has_shared_review_record() -> None:
    repository = Path(__file__).resolve().parents[2]
    for relative in (
        STYLE_DICTIONARY_MANIFEST,
        STYLE_DICTIONARY_REVIEW,
    ):
        _assert_worktree_regular_file(repository, relative)

    manifest_path = repository / STYLE_DICTIONARY_MANIFEST
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    manifest = json.loads(manifest_bytes)
    assert isinstance(manifest, dict)
    assert manifest.get("schema_version") == 1
    assert manifest.get("dictionary_id") == "illustration_style_dictionary_v1"

    entries = manifest.get("entries")
    assert isinstance(entries, list)
    assert len(entries) == manifest.get("entry_count") == 48
    preview_paths: set[PurePosixPath] = set()
    slot_count = 0
    blocked_slot_count = 0
    for entry in entries:
        assert isinstance(entry, dict)
        entry_id = entry.get("entry_id")
        assert isinstance(entry_id, str) and entry_id
        slots = entry.get("slots")
        assert isinstance(slots, list) and len(slots) == 2
        model_slots: set[str] = set()
        for slot in slots:
            assert isinstance(slot, dict)
            slot_count += 1
            model_slot = slot.get("model_slot")
            assert model_slot in {"gpt_image_2", "grok_image_2"}
            assert isinstance(model_slot, str) and model_slot not in model_slots
            model_slots.add(model_slot)
            if slot.get("status") == "blocked":
                blocked_slot_count += 1
                assert slot.get("preview") is None
                continue
            assert slot.get("status") == "preview"
            preview = slot.get("preview")
            assert isinstance(preview, dict)
            preview_path = preview.get("path")
            assert isinstance(preview_path, str)
            relative = PurePosixPath(preview_path)
            assert relative == STYLE_DICTIONARY_ROOT / "images" / (f"{entry_id}--{model_slot}.webp")
            assert relative not in preview_paths
            preview_paths.add(relative)
            digest = preview.get("sha256")
            assert isinstance(digest, str) and len(digest) == 64
            image_bytes = (repository / relative).read_bytes()
            assert len(image_bytes) == preview.get("bytes")
            assert hashlib.sha256(image_bytes).hexdigest() == digest

    assert slot_count == manifest.get("slot_count") == 96
    assert len(preview_paths) == manifest.get("preview_count") == 92
    assert blocked_slot_count == manifest.get("blocked_slot_count") == 4
    discovered_previews = {
        PurePosixPath(path.relative_to(repository).as_posix())
        for path in (repository / STYLE_DICTIONARY_ROOT / "images").glob("*.webp")
    }
    assert preview_paths == discovered_previews

    review = (repository / STYLE_DICTIONARY_REVIEW).read_text(encoding="utf-8")
    assert manifest_sha256 in review
    assert "92/92 exact previews: PASS" in review
    for category, reviewer_ids in STYLE_DICTIONARY_REVIEWERS.items():
        assert category in review
        assert all(reviewer_id in review for reviewer_id in reviewer_ids)

    inventory = json.loads(
        (repository / "docs/generated-media-inventory.json").read_text(encoding="utf-8")
    )
    assert STYLE_DICTIONARY_ROOT.as_posix() not in inventory["roots"]
    assert all(
        not item["path"].startswith(f"{STYLE_DICTIONARY_ROOT.as_posix()}/")
        for item in inventory["media"]
    )


def _assert_worktree_regular_file(repository: Path, relative: PurePosixPath) -> None:
    path = repository / relative
    assert path.is_file() and not path.is_symlink()
    assert relative.as_posix() in _worktree_files(repository)


def _worktree_files(repository: Path) -> set[str]:
    """Inspect staged and unstaged source files; publication is a separate gate."""
    discovered = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return {
        name
        for name in discovered.stdout.split("\0")
        if name and ((repository / name).exists() or (repository / name).is_symlink())
    }


def _sdist_file_entries(members: list[tarfile.TarInfo]) -> tuple[str, dict[str, int]]:
    files = [member for member in members if member.isfile()]
    roots = {PurePosixPath(member.name).parts[0] for member in files}
    assert len(roots) == 1
    root = roots.pop()
    assert root.startswith("stage_gen-")
    entries: dict[str, int] = {}
    for member in files:
        parts = PurePosixPath(member.name).parts
        assert len(parts) > 1
        relative = PurePosixPath(*parts[1:]).as_posix()
        assert relative not in entries
        entries[relative] = member.size
    return root, entries


def _assert_archive_hygiene(entries: Mapping[str, int], *, resource_prefix: str) -> None:
    assert entries
    for name in entries:
        path = PurePosixPath(name)
        assert not path.is_absolute()
        assert ".." not in path.parts
        lowered_parts = tuple(part.lower() for part in path.parts)
        assert lowered_parts[0] not in LEGACY_TOP_LEVEL
        assert not BANNED_SEGMENTS.intersection(lowered_parts)
        basename = lowered_parts[-1]
        assert basename == ".env.example" or not basename.startswith(".env")
        assert basename not in {"credentials.json", "id_rsa", "secrets.json"}
        assert path.suffix.lower() not in SECRET_SUFFIXES
        assert not name.lower().endswith((".pyc", ".pyo", ".ts", ".tsx", ".tsbuildinfo"))
        assert basename not in {"bun.lock", "package.json", "tsconfig.json"}
        if path.suffix.lower() in MEDIA_SUFFIXES:
            assert name.startswith(resource_prefix)


def _is_docs_media(name: str) -> bool:
    path = PurePosixPath(name)
    return "docs" in path.parts and path.suffix.lower() in MEDIA_SUFFIXES


def _media_family(suffix: str) -> str:
    if suffix in {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"}:
        return "audio"
    if suffix in {".mp4", ".webm"}:
        return "video"
    if suffix in FONT_MEDIA_SUFFIXES:
        return "font"
    return "image"


def _env_value(contents: str, key: str) -> str:
    prefix = f"{key}="
    matches = [line[len(prefix) :] for line in contents.splitlines() if line.startswith(prefix)]
    assert len(matches) == 1
    return matches[0]
