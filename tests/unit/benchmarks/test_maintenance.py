from __future__ import annotations

import io
import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from stage_gen.benchmarks.maintenance import chroma_spotcheck, main, regenerate_tileset
from stage_gen.config import StageGenConfig, TransparencyMode
from stage_gen.contracts import BinaryArtifact, ProvenanceInput
from stage_gen.recipes.base import StageContext
from stage_gen.reliability import write_artifact_with_provenance


def _png(width: int, height: int, pixels: list[tuple[int, int, int, int]]) -> bytes:
    image = Image.new("RGBA", (width, height))
    image.putdata(pixels)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class _TilesetRuntime:
    def __init__(self) -> None:
        self.context: StageContext | None = None

    async def run_recipe_stage(
        self, recipe_id: str, stage_name: str, context: StageContext
    ) -> tuple[str, str]:
        assert recipe_id == "scrolling-preview"
        assert stage_name == "maintenance-regenerate-tileset"
        self.context = context
        output = context.run_dir / f"tileset_{context.tag}.png"
        image = Image.new("RGBA", (2400, 800), (30, 60, 90, 255))
        image.putpixel((0, 0), (255, 0, 255, 0))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        data = buffer.getvalue()
        sidecar = write_artifact_with_provenance(
            output,
            BinaryArtifact(data=data, media_type="image/png"),
            ProvenanceInput(
                provider="offline",
                model="fake-tileset",
                prompt="tileset",
                params={"transparency": {"mode": str(context.config.transparency_mode)}},
                validation={
                    "alpha_nontrivial": True,
                    "output_width": 2400,
                    "output_height": 800,
                },
                attempts=4,
            ),
        )
        return str(output), str(sidecar)


async def test_regenerate_tileset_uses_existing_run_mode_and_targeted_public_stage(
    tmp_path: Path,
) -> None:
    tag = "existing-run"
    run_dir = tmp_path / tag
    run_dir.mkdir()
    (run_dir / f"concept_{tag}.png").write_bytes(_png(1, 1, [(10, 20, 30, 255)]))
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "schema_version": 3,
                "kind": "recipe_run_v3",
                "recipe": "scrolling-preview",
                "tag": tag,
                "run_dir": tag,
                "started_at": "2026-08-25T00:00:00Z",
                "ended_at": "2026-08-25T00:00:00.001Z",
                "duration_ms": 1,
                "ok": True,
                "input": {"prompt": "existing prompt", "transparency_mode": "chroma"},
                "stages": [
                    {
                        "stage": "concept",
                        "ok": True,
                        "duration_ms": 1,
                        "artifacts": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    runtime = _TilesetRuntime()
    result = await regenerate_tileset(
        tag,
        StageGenConfig(
            out_dir=tmp_path,
            open_router_api_key="offline-key",
            transparency_mode=TransparencyMode.AI,
        ),
        runtime=runtime,
    )

    assert runtime.context is not None
    assert runtime.context.input == {
        "prompt": "existing prompt",
        "transparency_mode": "chroma",
    }
    assert runtime.context.config.transparency_mode is TransparencyMode.CHROMA
    assert result.attempts == 4
    assert (result.width, result.height) == (2400, 800)
    assert result.bytes > 0
    assert result.to_dict()["imagePath"] == str(run_dir / f"tileset_{tag}.png")


async def test_regenerate_tileset_requires_a_current_run_summary(tmp_path: Path) -> None:
    tag = "existing-run"
    run_dir = tmp_path / tag
    run_dir.mkdir()
    (run_dir / f"concept_{tag}.png").write_bytes(_png(1, 1, [(10, 20, 30, 255)]))

    with pytest.raises(ValueError, match="tileset run summary does not exist"):
        await regenerate_tileset(
            tag,
            StageGenConfig(out_dir=tmp_path, open_router_api_key="offline-key"),
            runtime=_TilesetRuntime(),
        )


@pytest.mark.parametrize("linked_boundary", ["output-root", "run-directory"])
async def test_regenerate_tileset_rejects_symlinked_directory_boundary(
    tmp_path: Path, linked_boundary: str
) -> None:
    tag = "existing-run"
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    runtime = _TilesetRuntime()
    if linked_boundary == "output-root":
        output_root = tmp_path / "linked-root"
        output_root.symlink_to(real_root, target_is_directory=True)
        expected = "tileset output root contains a symlink"
    else:
        real_run = tmp_path / "real-run"
        real_run.mkdir()
        (real_run / f"concept_{tag}.png").write_bytes(_png(1, 1, [(10, 20, 30, 255)]))
        (real_root / tag).symlink_to(real_run, target_is_directory=True)
        output_root = real_root
        expected = "tileset run directory contains a symlink"

    with pytest.raises(ValueError) as captured:
        await regenerate_tileset(
            tag,
            StageGenConfig(out_dir=output_root, open_router_api_key="offline-key"),
            runtime=runtime,
        )

    assert str(captured.value) == expected
    assert runtime.context is None


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
