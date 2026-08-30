from __future__ import annotations

from pathlib import Path

import pytest

from gnode import (
    assert_safe_path_segment,
    resolve_relative_path_within_root,
    resolve_writable_path_within_root,
)


def test_safe_path_segment_contract() -> None:
    assert assert_safe_path_segment("neutral-run_01.json", "tag") == "neutral-run_01.json"
    for invalid in ("", ".", "..", "../outside", "nested/file", ".hidden", "x" * 129):
        with pytest.raises(ValueError, match="safe path segment"):
            assert_safe_path_segment(invalid, "tag")


def test_relative_path_must_stay_below_root(tmp_path: Path) -> None:
    expected = tmp_path / "nested" / "artifact.png"
    assert (
        resolve_relative_path_within_root(tmp_path, "nested/artifact.png", "outputPath") == expected
    )
    for invalid in ("", "/absolute.png", "../outside.png", "nested\\file.png", "a//b"):
        with pytest.raises(ValueError):
            resolve_relative_path_within_root(tmp_path, invalid, "outputPath")


def test_writable_path_rejects_symlinked_or_nondirectory_parent(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinked parent"):
        resolve_writable_path_within_root(root, "link/out.png", "outputPath")

    (root / "file").write_text("not a directory")
    with pytest.raises(ValueError, match="not a directory"):
        resolve_writable_path_within_root(root, "file/out.png", "outputPath")
