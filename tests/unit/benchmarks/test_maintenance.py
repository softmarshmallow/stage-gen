from __future__ import annotations

import io
import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from stage_gen.benchmarks.maintenance import chroma_spotcheck, main


def _png(width: int, height: int, pixels: list[tuple[int, int, int, int]]) -> bytes:
    image = Image.new("RGBA", (width, height))
    image.putdata(pixels)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_chroma_spotcheck_matches_legacy_pixel_classes_and_cli_json(tmp_path: Path) -> None:
    name = "items_test-chroma.png"
    (tmp_path / name).write_bytes(
        _png(
            2,
            2,
            [
                (255, 0, 255, 0),
                (200, 10, 10, 255),
                (240, 20, 230, 255),
                (0, 0, 0, 255),
            ],
        )
    )

    result = chroma_spotcheck(tmp_path)
    assert len(result) == 1
    assert result[0].to_dict() == {
        "file": name,
        "W": 2,
        "H": 2,
        "exactMagenta": 1,
        "painted": 3,
        "reddish": 1,
        "interiorNearMagenta": 1,
    }
    stdout = io.StringIO()
    assert main(["chroma-spotcheck", str(tmp_path), name], stdout=stdout) == 0
    assert json.loads(stdout.getvalue()) == [result[0].to_dict()]


def test_chroma_spotcheck_rejects_symlinked_asset(tmp_path: Path) -> None:
    target = tmp_path / "target.png"
    target.write_bytes(_png(1, 1, [(255, 0, 255, 255)]))
    link = tmp_path / "items_link.png"
    link.symlink_to(target)

    with pytest.raises(ValueError) as captured:
        chroma_spotcheck(tmp_path, [link.name])

    assert str(captured.value) == "chroma spotcheck asset contains a symlink"


@pytest.mark.parametrize("symlink_at", ["run-directory", "parent"])
def test_chroma_spotcheck_rejects_symlinked_run_directory_before_resolution(
    tmp_path: Path, symlink_at: str
) -> None:
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    real_run = real_parent / "run"
    real_run.mkdir()
    if symlink_at == "run-directory":
        supplied = tmp_path / "linked-run"
        supplied.symlink_to(real_run, target_is_directory=True)
    else:
        linked_parent = tmp_path / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        supplied = linked_parent / "run"

    with pytest.raises(ValueError) as captured:
        chroma_spotcheck(supplied)

    assert str(captured.value) == "chroma spotcheck run directory contains a symlink"
    stderr = io.StringIO()
    assert main(["chroma-spotcheck", str(supplied)], stderr=stderr) == 1
    assert (
        stderr.getvalue()
        == "stage-gen maintenance: chroma spotcheck run directory contains a symlink\n"
    )


def test_chroma_spotcheck_rejects_unsafe_or_outside_lexical_paths(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "items_safe.png").write_bytes(_png(1, 1, [(255, 0, 255, 255)]))

    with pytest.raises(ValueError) as captured_root:
        chroma_spotcheck(run_dir / ".." / "run")
    assert str(captured_root.value) == (
        "chroma spotcheck run directory contains an unsafe path segment"
    )
    with pytest.raises(ValueError, match="must be one safe path segment"):
        chroma_spotcheck(run_dir, ["../items_safe.png"])
