from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from PIL import Image, ImageDraw

from stage_gen.components import (
    ImageGenerationRequest,
    MusicGenerationRequest,
    StructuredGenerationRequest,
)
from stage_gen.config import StageGenConfig
from stage_gen.orchestration.execution_graph import DependencyExecutor
from stage_gen.recipes.scrolling_preview.motion_contract import (
    motion_source_facing,
    runtime_mirrors_source,
)
from stage_gen.recipes.scrolling_preview.package_executor import PreparedPackageExecutor
from stage_gen.recipes.scrolling_preview.prepared_content import (
    PreparedContentNodeHandler,
    _dialogue_grid,
    _validate_atlas,
    _validate_transparent_image,
    content_target_node_ids,
)

REPOSITORY_ROOT = Path(__file__).parents[4]
BELLWEATHER = REPOSITORY_ROOT / "library/games/bellweather"


def _atlas(*, missing_cell: int | None = None) -> bytes:
    image = Image.new("RGBA", (1536, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    cell_width = image.width // 4
    cell_height = image.height
    for index in range(4):
        if index == missing_cell:
            continue
        row, column = divmod(index, 4)
        left = column * cell_width + 40
        top = row * cell_height + 40
        draw.ellipse(
            (left, top, left + cell_width - 80, top + cell_height - 80),
            fill=(120, 180, 240, 255),
        )
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def test_motion_atlas_requires_native_alpha_and_all_cells() -> None:
    facts = _validate_atlas(_atlas(), columns=4, rows=1, required_cells=4)
    assert facts["all_required_cells_visible"] is True
    assert len(cast(list[float], facts["cell_visible_fractions"])) == 4

    with pytest.raises(ValueError, match="missing a required visible cell"):
        _validate_atlas(_atlas(missing_cell=3), columns=4, rows=1, required_cells=4)


def test_motion_source_facing_is_runtime_owned_and_climb_is_rear_facing() -> None:
    assert motion_source_facing("player", "walk") == "right"
    assert motion_source_facing("mob", "move") == "right"
    assert motion_source_facing("npc", "idle") == "right"
    assert motion_source_facing("player", "climb") == "back"
    assert runtime_mirrors_source("right") is True
    assert runtime_mirrors_source("back") is False


def test_transparent_image_rejects_opaque_and_dialogue_grid_is_stable() -> None:
    opaque = Image.new("RGBA", (1024, 1024), (1, 2, 3, 255))
    stream = io.BytesIO()
    opaque.save(stream, format="PNG")
    with pytest.raises(ValueError, match="transparent and visible"):
        _validate_transparent_image(stream.getvalue(), width=1024, height=1024)

    contaminated = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    ImageDraw.Draw(contaminated).rectangle((0, 0, 1023, 100), fill=(40, 40, 40, 180))
    stream = io.BytesIO()
    contaminated.save(stream, format="PNG")
    with pytest.raises(ValueError, match="alpha contamination at the canvas border"):
        _validate_transparent_image(stream.getvalue(), width=1024, height=1024)

    assert _dialogue_grid(4) == (2, 2)
    assert _dialogue_grid(5) == (3, 2)


class _FakeImageService:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: ImageGenerationRequest) -> SimpleNamespace:
        self.calls += 1
        return _write_fake_image(request)


def _write_fake_image(request: ImageGenerationRequest) -> SimpleNamespace:
    assert request.size is not None
    width, height = request.size.split("x")
    size = (int(width), int(height))
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (size[0] // 20, size[1] // 20, size[0] * 19 // 20, size[1] * 19 // 20),
        fill=(100, 170, 230, 255),
    )
    output = Path(request.artifact_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG")
    sidecar = Path(f"{output}.meta.json")
    sidecar.write_text("{}", encoding="utf-8")
    return SimpleNamespace(attempts=1, provenance_path=str(sidecar))


class _FakeStructuredService:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: StructuredGenerationRequest[object]) -> SimpleNamespace:
        self.calls += 1
        return _write_fake_structured(request)


def _write_fake_structured(request: StructuredGenerationRequest[object]) -> SimpleNamespace:
    output = Path(request.artifact_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    value = {
        "verdict": "accept",
        "confidence": 1.0,
        "checks": {
            "identity_fidelity": True,
            "style_coherence": True,
            "state_coverage": True,
            "facing_coverage": True,
            "registration_consistency": True,
            "alpha_isolation": True,
            "expression_coverage": True,
            "catalog_coverage": True,
        },
        "issues": [],
        "evidence": "deterministic fake",
    }
    output.write_text(json.dumps(value), encoding="utf-8")
    sidecar = Path(f"{output}.meta.json")
    sidecar.write_text("{}", encoding="utf-8")
    return SimpleNamespace(attempts=1, provenance_path=str(sidecar))


class _FakeMusicService:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: MusicGenerationRequest) -> SimpleNamespace:
        self.calls += 1
        return _write_fake_music(request)


def _write_fake_music(request: MusicGenerationRequest) -> SimpleNamespace:
    output = Path(request.artifact_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(
        (REPOSITORY_ROOT / "src/stage_gen/resources/music/preview-loop.mp3").read_bytes()
    )
    sidecar = Path(f"{output}.meta.json")
    sidecar.write_text("{}", encoding="utf-8")
    return SimpleNamespace(attempts=1, provenance_path=str(sidecar))


async def test_complete_content_handler_dispatches_exact_closure(tmp_path: Path) -> None:
    prepared = PreparedPackageExecutor(StageGenConfig()).plan(BELLWEATHER)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    images = _FakeImageService()
    structured = _FakeStructuredService()
    music = _FakeMusicService()
    handler = PreparedContentNodeHandler(
        prepared.graph,
        prepared.package,
        run_dir=run_dir,
        cache_dir=tmp_path / "cache",
        image_service=images,  # type: ignore[arg-type]
        structured_service=structured,  # type: ignore[arg-type]
        music_service=music,  # type: ignore[arg-type]
    )
    summary = await DependencyExecutor(prepared.graph.resources, node_timeout_seconds=120).run(
        prepared.graph,
        handler,
        invocation_id="content-handler",
        target_node_ids=content_target_node_ids(prepared.package),
    )

    assert summary.ok is True
    assert len(summary.nodes) == 167
    assert images.calls == 72
    assert structured.calls == 13
    assert music.calls == 3
    coverage = json.loads((run_dir / "content/coverage-matrix.json").read_text())
    assert coverage["required_image_operations"] == 72
    assert coverage["required_structured_reviews"] == 13
    assert coverage["required_music_operations"] == 3
    assert (run_dir / "content/players/wayfarer/contact-sheet.png").is_file()
    assert (run_dir / "content/mobs/crowncrag_page_eater/review.json").is_file()
    assert (run_dir / "content/npcs/mara_crumbwell/dialogue.validation.json").is_file()
    assert (run_dir / "content/props/contact-sheet.png").is_file()
    assert (run_dir / "soundtrack/sunpetal_morning.validation.json").is_file()
