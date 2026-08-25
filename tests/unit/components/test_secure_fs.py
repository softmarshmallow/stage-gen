from __future__ import annotations

from pathlib import Path

import pytest

from stage_gen.components._secure_fs import (
    SecurePathError,
    open_absolute_directory,
    read_absolute_regular_file,
    read_relative_regular_file,
)


def test_absolute_regular_file_read_rejects_parent_segments_before_open(tmp_path: Path) -> None:
    target = tmp_path / "secret.toml"
    target.write_text("secret", encoding="utf-8")
    source = tmp_path / "library" / ".." / target.name
    assert ".." in source.absolute().parts

    with pytest.raises(SecurePathError, match="must not contain dot or parent path segments"):
        read_absolute_regular_file(source, label="authored source")


@pytest.mark.parametrize(
    "parts",
    [
        (),
        ("library", "..", "secret.toml"),
        ("library", "bad\\name.toml"),
        ("library", "bad:name.toml"),
    ],
)
def test_relative_regular_file_read_rejects_nonportable_parts(
    tmp_path: Path,
    parts: tuple[str, ...],
) -> None:
    with (
        open_absolute_directory(tmp_path, label="test root") as root_fd,
        pytest.raises(SecurePathError, match="portable relative path segments"),
    ):
        read_relative_regular_file(root_fd, parts, label="authored source")
