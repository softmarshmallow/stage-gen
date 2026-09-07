from __future__ import annotations

import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LEGACY_CORE_DIRECTORIES = ("components", "stage-gen")
NODE_SOURCE_SUFFIXES = frozenset({".cjs", ".cts", ".js", ".jsx", ".mjs", ".mts", ".ts", ".tsx"})
NODE_MANIFEST_NAMES = frozenset({"bun.lock", "bun.lockb", "bunfig.toml", "package.json"})


def _is_node_artifact(name: str) -> bool:
    lower_name = name.lower()
    if Path(lower_name).suffix in NODE_SOURCE_SUFFIXES:
        return True
    if lower_name in NODE_MANIFEST_NAMES:
        return True
    return lower_name.endswith(".json") and lower_name.startswith(("jsconfig", "tsconfig"))


def _repository_files() -> list[Path]:
    """Every path the repository carries: tracked, plus untracked ones a commit would take.

    Ignored paths are working-directory scratch - local spikes, caches, vendored
    viewers - and are not the repository's own content, so the boundary does not
    speak for them.
    """
    listing = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return [Path(entry) for entry in listing.stdout.split("\0") if entry]


def _non_web_node_artifacts() -> list[Path]:
    return sorted(
        path
        for path in _repository_files()
        if path.parts[:1] != ("web",) and _is_node_artifact(path.name)
    )


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
