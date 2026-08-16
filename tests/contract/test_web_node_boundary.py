from __future__ import annotations

import os
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LEGACY_CORE_DIRECTORIES = ("components", "stage-gen")
NODE_SOURCE_SUFFIXES = frozenset({".cjs", ".cts", ".js", ".jsx", ".mjs", ".mts", ".ts", ".tsx"})
NODE_MANIFEST_NAMES = frozenset({"bun.lock", "bun.lockb", "bunfig.toml", "package.json"})
EXCLUDED_DIRECTORIES = frozenset(
    {
        ".cache",
        ".git",
        ".hg",
        ".mypy_cache",
        ".next",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".svn",
        ".tox",
        ".turbo",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "htmlcov",
        "node_modules",
        "out",
        "venv",
    }
)


def _is_node_artifact(name: str) -> bool:
    lower_name = name.lower()
    if Path(lower_name).suffix in NODE_SOURCE_SUFFIXES:
        return True
    if lower_name in NODE_MANIFEST_NAMES:
        return True
    return lower_name.endswith(".json") and lower_name.startswith(("jsconfig", "tsconfig"))


def _non_web_node_artifacts() -> list[Path]:
    artifacts: list[Path] = []
    for directory, child_directories, filenames in os.walk(REPOSITORY_ROOT):
        relative_directory = Path(directory).relative_to(REPOSITORY_ROOT)
        if relative_directory.parts[:1] == ("web",):
            child_directories[:] = []
            continue
        child_directories[:] = [
            name for name in child_directories if name not in EXCLUDED_DIRECTORIES and name != "web"
        ]
        artifacts.extend(relative_directory / name for name in filenames if _is_node_artifact(name))
    return sorted(artifacts)


def test_web_is_the_only_node_boundary() -> None:
    remaining_legacy_directories = [
        name for name in LEGACY_CORE_DIRECTORIES if (REPOSITORY_ROOT / name).exists()
    ]
    assert not remaining_legacy_directories, (
        "legacy core directories remain outside web/: " + ", ".join(remaining_legacy_directories)
    )

    artifacts = _non_web_node_artifacts()
    assert not artifacts, "Node/Bun artifacts remain outside web/:\n" + "\n".join(
        str(path) for path in artifacts
    )
