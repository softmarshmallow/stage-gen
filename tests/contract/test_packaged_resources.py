from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

WHEEL_RESOURCES = {
    "stage_gen/resources/fixtures/image_gen_templates/inventory_template.png",
    "stage_gen/resources/fixtures/image_gen_templates/terrain_atlas_12x4_template.png",
    "stage_gen/resources/fixtures/image_gen_templates/terrain_atlas_godot_topology_reference.png",
    "stage_gen/resources/fixtures/prompts.txt",
    "stage_gen/resources/fixtures/styles.txt",
    "stage_gen/resources/music/preview-loop.mp3",
    "stage_gen/resources/music/preview-loop.mp3.meta.json",
    "stage_gen/resources/prompting/image_style_vocabulary_v1.json",
    "stage_gen/resources/prompting/game_vocabulary_v1.json",
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
    "pyproject.toml",
    "scripts/check.py",
    "src/stage_gen/__init__.py",
    "src/stage_gen/py.typed",
    "tests/contract/fixtures/tag-vectors.json",
    "tests/contract/test_packaged_resources.py",
    "uv.lock",
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
    ".png",
    ".wav",
    ".webm",
    ".webp",
}
IMAGE_MEDIA_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".webp"}
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
    "image": 5 * 1024 * 1024,
    "video": 25 * 1024 * 1024,
}
GIT_MEDIA_TOTAL_LIMIT = 100 * 1024 * 1024
SECRET_SUFFIXES = {".key", ".p12", ".pem", ".pfx"}


def test_built_distributions_are_small_clean_and_resource_complete(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    distribution_directory = tmp_path / "distributions"
    environment = os.environ.copy()
    environment.pop("OPENAI_API_KEY", None)
    environment.pop("OPENROUTER_API_KEY", None)
    environment.pop("FAL_KEY", None)
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
    assert wheels[0].stat().st_size < 3_000_000
    assert sdists[0].stat().st_size < 4_000_000

    installed = tmp_path / "installed"
    with zipfile.ZipFile(wheels[0]) as wheel:
        wheel_entries = {
            entry.filename: entry.file_size for entry in wheel.infolist() if not entry.is_dir()
        }
        _assert_archive_hygiene(wheel_entries, resource_prefix="stage_gen/resources/")
        # The prepared-package cutover adds eleven deliberate headless modules: the generic DAG,
        # fake verifier, recipe graph builder, thin package executor, live prepared-world handler,
        # live prepared-content handler, runtime-manifest assembler, and shared motion-source
        # contract, plus the provider-neutral sprite repacker, the two-file game UI contract,
        # and the attributed terrain topology reference.
        # Keep the ceiling exact enough to catch accidental packaging growth without treating
        # those boundaries as bloat.
        # The platformer map-design component adds five more: the capability profiles, the design
        # model and its validator, the chunk grammar, the design loop, and the package init.
        # The motion-rebase contract adds its recipe module and the provider-neutral plate
        # compositor it shares with the asset unit.
        # The player-equipment contract adds one: the recipe-owned art directives keyed on the
        # authored equipment, which the prompt builder and the actor review both read.
        # The derived execution view adds two: the generic plan-and-trace join exporter, and the
        # recipe-owned artifact display annotations the CLI wires into it.
        # Splitting the engine out adds the whole gnode package: its import surface and typing
        # marker, graph, scheduler, trace, dry-run handler, run view, model bindings, and the
        # reliability and contract modules that moved with them. The application shrank by the
        # same modules, so the net growth is the engine's own package files.
        assert len(wheel_entries) <= 199
        assert sum(wheel_entries.values()) < 5_000_000
        assert wheel_entries.keys() >= WHEEL_RESOURCES
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
        assert not any(name.startswith("tests/") for name in wheel_entries)
        assert not any(name.startswith("library/") for name in wheel_entries)
        assert not any(name.startswith("concept-studio/") for name in wheel_entries)
        assert not any(_is_docs_media(name) for name in wheel_entries)
        wheel.extractall(installed)

    extracted_sdist_parent = tmp_path / "extracted-sdist"
    with tarfile.open(sdists[0], mode="r:gz") as sdist:
        members = sdist.getmembers()
        assert all(member.isfile() or member.isdir() for member in members)
        root, sdist_entries = _sdist_file_entries(members)
        _assert_archive_hygiene(sdist_entries, resource_prefix="src/stage_gen/resources/")
        # A guard against accidental bloat - a stray directory swept into the sdist - and not
        # a cap on the project growing. Current-only game contracts, maintenance harnesses, and
        # the hardened Concept Studio core and direct native-alpha provider bring the clean
        # source distribution to 337 files. Prepared-package execution, the UI contract, and
        # the terrain-atlas integration add the focused source, tests, templates, and canonical
        # documentation and traversal-contract tests tracked here.
        # The size assertions below are the ones that actually bound the archive. The layer
        # vertical-placement contract adds two source modules and their focused tests. The
        # climbable atlas adds its sizing/envelope module, the terrain authoring compiler, and the
        # pipeline graph-contract writer. The platformer map-design component adds fourteen: its
        # five source modules, the design script, its six focused test modules, and the contract
        # documentation.
        # The asset-scale documentation figures add two: the deterministic renderer that
        # composites them and its focused test. The motion-rebase contract adds four: two
        # source modules and their focused tests. The asset unit adds its own recipe module
        # and focused tests. The projectile asset family adds four: the silhouette art
        # declaration, the authored Bellweather catalog, and two focused test modules.
        # The derived execution view adds its exporter and recipe-annotation source modules
        # and their two focused test modules.
        # Splitting the engine out adds the gnode package's own files plus its two focused test
        # modules: the model-binding table and the pinned plan identity.
        # Recording cancellation adds one: the scheduler test that interrupts a run mid-flight
        # and proves the trace says so rather than leaving it to be inferred.
        # The ring cut nets a few package files: modality and provider package
        # __init__ modules, the signature/inspection modules, and the
        # application's identity and image_style modules (measured 362).
        # The node-ABI pass adds the engine's node_types and build modules, the
        # two recipes' type-census modules, and the whole point-and-click room
        # recipe with its authored library room (measured 379).
        # The scenario contract adds seven source modules: the shared authored-package
        # reader both recipes moved onto, and the scenario component's declarations,
        # parser, compiler, admission proof, resolver, and import surface. Its authored
        # package and focused tests are excluded from the sdist (measured 394).
        assert len(sdist_entries) <= 394
        # Raised once when the loop-construction contract landed: two source modules, their
        # focused tests, and the concurrent presentation work crossed the previous 6MB line by
        # about 27KB. Raised again for the scenario contract, whose seven source modules put the
        # archive about 1KB past the previous line. The archive is still bounded well under the
        # packaging budget; this guards against a stray directory, not against the project growing.
        assert sum(sdist_entries.values()) < 5_200_000
        assert sdist_entries.keys() >= SDIST_RESOURCES | EXPECTED_SDIST_FILES
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
        sdist.extractall(extracted_sdist_parent, filter="data")

    extracted_sdist = extracted_sdist_parent / root
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
from pathlib import Path
from stage_gen.resources import (
    bundled_music_path,
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

paths = required_resource_paths()
assert len(paths) == 11
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
music = bundled_music_path()
assert Path(f"{music}.meta.json").is_file()
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
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repository,
        check=False,
        capture_output=True,
    )
    relative_paths: set[PurePosixPath] = set()
    if tracked.returncode == 0:
        deleted = subprocess.run(
            ["git", "ls-files", "--deleted", "-z"],
            cwd=repository,
            check=False,
            capture_output=True,
        )
        deleted_paths = {
            PurePosixPath(item.decode("utf-8")) for item in deleted.stdout.split(b"\0") if item
        }
        relative_paths.update(
            PurePosixPath(item.decode("utf-8"))
            for item in tracked.stdout.split(b"\0")
            if item
            and PurePosixPath(item.decode("utf-8")) not in deleted_paths
            and PurePosixPath(item.decode("utf-8")).suffix.lower() in MEDIA_SUFFIXES
        )
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
            "library",
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
        if relative.parts[0] == "src":
            assert relative.parts[:3] == ("src", "stage_gen", "resources")
        if relative.parts[0] == "library":
            assert len(relative.parts) >= 5
            assert relative.parts[:2] == ("library", "games")
            assert relative.parts[3] == "references"
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
        _assert_tracked_regular_file(repository, relative)

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


def _assert_tracked_regular_file(repository: Path, relative: PurePosixPath) -> None:
    path = repository / relative
    assert path.is_file() and not path.is_symlink()
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative.as_posix()],
        cwd=repository,
        check=False,
        capture_output=True,
    )
    assert tracked.returncode == 0


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
    return "image"


def _env_value(contents: str, key: str) -> str:
    prefix = f"{key}="
    matches = [line[len(prefix) :] for line in contents.splitlines() if line.startswith(prefix)]
    assert len(matches) == 1
    return matches[0]
