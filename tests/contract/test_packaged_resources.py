from __future__ import annotations

import os
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

WHEEL_RESOURCES = {
    "stage_gen/resources/fixtures/image_gen_templates/character_template.png",
    "stage_gen/resources/fixtures/image_gen_templates/character_template_combined.png",
    "stage_gen/resources/fixtures/image_gen_templates/inventory_template.png",
    "stage_gen/resources/fixtures/image_gen_templates/obstacle_template.png",
    "stage_gen/resources/fixtures/image_gen_templates/wireframe.png",
    "stage_gen/resources/fixtures/loading.gif",
    "stage_gen/resources/fixtures/prompts.txt",
    "stage_gen/resources/fixtures/styles.txt",
    "stage_gen/resources/music/preview-loop.mp3",
    "stage_gen/resources/music/preview-loop.mp3.meta.json",
    "stage_gen/resources/music/preview-loop.LICENSE.md",
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
MEDIA_SUFFIXES = {".gif", ".jpeg", ".jpg", ".mp3", ".png", ".wav", ".webp"}
SECRET_SUFFIXES = {".key", ".p12", ".pem", ".pfx"}


def test_built_distributions_are_small_clean_and_resource_complete(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    distribution_directory = tmp_path / "distributions"
    environment = os.environ.copy()
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
        assert len(wheel_entries) <= 160
        assert sum(wheel_entries.values()) < 5_000_000
        assert wheel_entries.keys() >= WHEEL_RESOURCES
        assert all(wheel_entries[name] > 0 for name in WHEEL_RESOURCES)
        assert {
            "stage_gen/__init__.py",
            "stage_gen/py.typed",
            "stage_gen/resources/__init__.py",
        } <= wheel_entries.keys()
        assert any(name.endswith(".dist-info/METADATA") for name in wheel_entries)
        assert any(name.endswith(".dist-info/entry_points.txt") for name in wheel_entries)
        assert not any(name.startswith("tests/") for name in wheel_entries)
        wheel.extractall(installed)

    extracted_sdist_parent = tmp_path / "extracted-sdist"
    with tarfile.open(sdists[0], mode="r:gz") as sdist:
        members = sdist.getmembers()
        assert all(member.isfile() or member.isdir() for member in members)
        root, sdist_entries = _sdist_file_entries(members)
        _assert_archive_hygiene(sdist_entries, resource_prefix="src/stage_gen/resources/")
        assert len(sdist_entries) <= 240
        assert sum(sdist_entries.values()) < 6_000_000
        assert sdist_entries.keys() >= SDIST_RESOURCES | EXPECTED_SDIST_FILES
        assert all(sdist_entries[name] > 0 for name in SDIST_RESOURCES)
        env_handle = sdist.extractfile(f"{root}/.env.example")
        assert env_handle is not None
        env_example = env_handle.read().decode("utf-8")
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
            "tests/unit/orchestration/test_config_tags.py",
        ],
        cwd=extracted_sdist,
        env=sdist_test_environment,
        check=True,
        capture_output=True,
        text=True,
    )

    probe = """
from pathlib import Path
from stage_gen.resources import bundled_music_path, image_template_dir, required_resource_paths

paths = required_resource_paths()
assert len(paths) == 11
assert all(path.is_file() and path.stat().st_size > 0 for path in paths)
assert image_template_dir().is_dir()
music = bundled_music_path()
assert Path(f"{music}.meta.json").is_file()
assert (music.parent / "preview-loop.LICENSE.md").is_file()
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


def _env_value(contents: str, key: str) -> str:
    prefix = f"{key}="
    matches = [line[len(prefix) :] for line in contents.splitlines() if line.startswith(prefix)]
    assert len(matches) == 1
    return matches[0]
