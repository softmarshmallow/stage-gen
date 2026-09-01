from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from PIL import Image, ImageDraw

from gnode import (
    ImageGenerationRequest,
    MusicGenerationRequest,
    Scheduler,
    StructuredGenerationRequest,
)
from stage_gen.components.game_ui import (
    INVENTORY_PANEL_HEIGHT,
    INVENTORY_PANEL_LEFT,
    INVENTORY_PANEL_TOP,
    INVENTORY_PANEL_WIDTH,
)
from stage_gen.components.sideview_actor.motion_geometry import (
    dialogue_atlas_grid,
    runtime_mirrors_source,
)
from stage_gen.config import StageGenConfig
from stage_gen.recipes.sideview_platformer.motion_contract import (
    motion_semantic_direction,
    motion_source_facing,
)
from stage_gen.recipes.sideview_platformer.package_executor import PreparedPackageExecutor
from stage_gen.recipes.sideview_platformer.prepared_content import (
    PreparedContentNodeHandler,
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
    assert motion_source_facing("npc", "idle", npc_world_orientation="front") == "front"
    with pytest.raises(ValueError, match="requires world_orientation"):
        motion_source_facing("npc", "idle")
    assert motion_source_facing("player", "climb_ladder") == "back"
    assert motion_source_facing("player", "climb_rope") == "back"
    assert runtime_mirrors_source("right") is True
    assert runtime_mirrors_source("back") is False
    assert runtime_mirrors_source("front") is False


def test_crouch_visual_semantics_are_stationary_and_distinct_from_crawl() -> None:
    direction = motion_semantic_direction("player", "crouch")

    assert "low stationary crouch loop" in direction
    assert "does not crawl" in direction
    assert motion_semantic_direction("player", "walk") == (
        "four clear game-animation key poses that communicate walk"
    )


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

    assert dialogue_atlas_grid(4) == (2, 2)
    assert dialogue_atlas_grid(5) == (3, 2)


class _FakeImageService:
    def __init__(self) -> None:
        self.calls = 0
        self.requests: list[ImageGenerationRequest] = []

    async def generate(self, request: ImageGenerationRequest) -> SimpleNamespace:
        self.calls += 1
        self.requests.append(request)
        return _write_fake_image(request)


def _write_fake_image(request: ImageGenerationRequest) -> SimpleNamespace:
    assert request.size is not None
    width, height = request.size.split("x")
    size = (int(width), int(height))
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    atlas_columns = request.metadata.get("atlas_columns")
    atlas_rows = request.metadata.get("atlas_rows")
    if isinstance(atlas_columns, int) and isinstance(atlas_rows, int):
        expressions = request.metadata.get("expressions")
        required_cells = len(expressions) if isinstance(expressions, list) else 4
        cell_width = size[0] / atlas_columns
        cell_height = size[1] / atlas_rows
        for index in range(required_cells):
            row, column = divmod(index, atlas_columns)
            left = round(column * cell_width + cell_width * 0.15)
            top = round(row * cell_height + cell_height * 0.15)
            right = round((column + 1) * cell_width - cell_width * 0.15)
            bottom = round((row + 1) * cell_height - cell_height * 0.15)
            draw.ellipse((left, top, right, bottom), fill=(100, 170, 230, 255))
    elif request.metadata.get("role") == "inventory_panel":
        draw.rectangle(
            (
                INVENTORY_PANEL_LEFT,
                INVENTORY_PANEL_TOP,
                INVENTORY_PANEL_LEFT + INVENTORY_PANEL_WIDTH - 1,
                INVENTORY_PANEL_TOP + INVENTORY_PANEL_HEIGHT - 1,
            ),
            fill=(100, 170, 230, 251),
        )
    else:
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
        self.requests: list[StructuredGenerationRequest[object]] = []

    async def generate(self, request: StructuredGenerationRequest[object]) -> SimpleNamespace:
        self.calls += 1
        self.requests.append(request)
        return _write_fake_structured(request)


def _write_fake_structured(request: StructuredGenerationRequest[object]) -> SimpleNamespace:
    output = Path(request.artifact_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if request.metadata.get("kind") in {"player-motion-rebase", "player-motion-rebase-verify"}:
        # The rebase artifacts are read back by the verify stage and the manifest, so the fake
        # must route a well-formed reading through the request's own parse and admission instead
        # of writing a review-shaped verdict.
        states = request.metadata["states"]
        assert isinstance(states, list)
        decoded = {
            "baseline_state": "idle",
            "states": [
                {"state": state, "multiplier": 1.0, "evidence": "deterministic fake"}
                for state in states
            ],
        }
        assert request.artifact_value is not None
        record = request.artifact_value(request.parse(decoded))
        output.write_text(json.dumps(record), encoding="utf-8")
        sidecar = Path(f"{output}.meta.json")
        sidecar.write_text("{}", encoding="utf-8")
        return SimpleNamespace(attempts=1, provenance_path=str(sidecar))
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
    summary = await Scheduler(prepared.graph.resources, node_timeout_seconds=120).run(
        prepared.graph,
        handler,
        invocation_id="content-handler",
        target_node_ids=content_target_node_ids(prepared.graph),
    )

    assert summary.ok is True
    assert len(summary.nodes) == 180
    assert images.calls == 76
    assert structured.calls == 17
    assert music.calls == 3
    ui_request = next(
        request for request in images.requests if request.metadata.get("role") == "inventory_panel"
    )
    assert ui_request.background == "transparent"
    assert len(ui_request.input_references) == 2
    assert "every empty slot well must be solid, filled, and fully opaque alpha 255" in (
        ui_request.prompt
    )
    assert "Do not cut transparent or semi-transparent holes" in ui_request.prompt
    crouch_request = next(
        request
        for request in images.requests
        if request.metadata.get("kind") == "player" and request.metadata.get("state") == "crouch"
    )
    assert crouch_request.background == "transparent"
    assert crouch_request.metadata["source_facing"] == "right"
    assert "low stationary crouch loop" in crouch_request.prompt
    assert "does not crawl, kneel, move forward" in crouch_request.prompt
    npc_request = next(
        request
        for request in images.requests
        if request.metadata.get("kind") == "npc"
        and request.metadata.get("entity_id") == "mara_crumbwell"
        and request.metadata.get("state") == "idle"
    )
    assert npc_request.metadata["source_facing"] == "front"
    assert "strict symmetrical front view" in npc_request.prompt
    player_review = next(
        request for request in structured.requests if request.metadata.get("kind") == "player"
    )
    assert "exact required visual meaning for each motion" in player_review.prompt
    assert "low stationary crouch loop" in player_review.prompt
    # Equipment was absent from every review criterion until this landed, which is exactly why the
    # measured sword drift was never reported by a review that saw every strip.
    assert "declared equipment is hand_weapon_v1" in player_review.prompt
    assert "never missing from a frame" in player_review.prompt
    # Only the player declares equipment, so no other actor's review may acquire the clause.
    for other in structured.requests:
        if other.metadata.get("kind") in {"mob", "npc"}:
            assert "declared equipment" not in other.prompt

    # The directive leads, and it reaches both the identity concept and every state strip - a
    # weapon present in the concept and absent from the walk cycle is the failure being prevented.
    player_images = [
        request for request in images.requests if request.metadata.get("kind") == "player"
    ]
    assert player_images
    # The concept and every motion strip carry it. A weapon drawn into the identity concept and
    # missing from the walk cycle is the measured drift this exists to prevent, so state coverage
    # is asserted rather than assumed.
    drawn_figures = [request for request in player_images if "expressions" not in request.metadata]
    for request in drawn_figures:
        # Leading the content task, in the same position the projectile axis directive takes: the
        # shared universe and style preamble comes first for every image in the package.
        assert "Content task:\nEQUIPMENT, before anything else:" in request.prompt
    assert {"idle", "walk", "basic_attack", "skill_cast"} <= {
        request.metadata.get("state") for request in drawn_figures
    }

    # The dialogue atlas deliberately does not carry it. Those cells are busts, and a directive
    # demanding a held weapon in every frame of a set of facial expressions would be asking for
    # something the framing cannot show. It inherits the concept as its identity reference, which
    # is where the equipment was already decided.
    dialogue = [request for request in player_images if "expressions" in request.metadata]
    assert len(dialogue) == 1
    assert "EQUIPMENT, before anything else:" not in dialogue[0].prompt
    assert "For hold playback, judge motion semantics only on the selected canonical frame" in (
        player_review.prompt
    )
    coverage = json.loads((run_dir / "content/coverage-matrix.json").read_text())
    # The projectile catalog is a content family like props and items: one drawn subject and one
    # board-and-review pass. It was absent from both totals when the family was introduced, so a
    # package that fires a round under-reported exactly the family it fires.
    assert coverage["projectile_ids"] == ["paperwing_dart"]
    assert coverage["required_image_operations"] == 76
    assert coverage["required_structured_reviews"] == 15
    # The matrix demanded 76 while the closure it describes performed 75, because the content
    # checkpoint named no projectile terminal. The two agreeing is the point of both fixes.
    assert coverage["required_image_operations"] == images.calls
    # And the projectile generator, its single-subject validator, its board and its review are now
    # actually executed here. Before this they had never run outside a live provider run.
    projectile_request = next(
        request for request in images.requests if request.metadata.get("kind") == "projectile"
    )
    assert projectile_request.metadata["entity_id"] == "paperwing_dart"
    assert "AXIS, before anything else:" in projectile_request.prompt
    assert (run_dir / "content/projectiles/paperwing_dart.png").is_file()
    assert (run_dir / "content/projectiles/contact-sheet.png").is_file()
    assert (run_dir / "content/projectiles/review.json").is_file()
    assert coverage["required_music_operations"] == 3
    assert (run_dir / "content/players/wayfarer/contact-sheet.png").is_file()
    assert (run_dir / "content/players/wayfarer/states/idle.source.png").is_file()
    assert (run_dir / "content/players/wayfarer/states/idle.png").is_file()
    assert (run_dir / "content/players/wayfarer/states/crouch.source.png").is_file()
    assert (run_dir / "content/players/wayfarer/states/crouch.png").is_file()
    assert (run_dir / "ui/inventory_panel.png").is_file()
    idle_validation = json.loads(
        (run_dir / "content/players/wayfarer/states/idle.validation.json").read_text()
    )
    assert idle_validation["kind"] == "prepared-motion-atlas-validation-v3"
    assert idle_validation["repack"]["processor_version"] == "alpha-component-repack-v1"
    crouch_validation = json.loads(
        (run_dir / "content/players/wayfarer/states/crouch.validation.json").read_text()
    )
    assert crouch_validation["state"] == "crouch"
    assert crouch_validation["source_facing"] == "right"
    assert crouch_validation["runtime_horizontal_mirroring"] is True
    assert (run_dir / "content/mobs/crowncrag_page_eater/review.json").is_file()
    assert (run_dir / "content/npcs/mara_crumbwell/dialogue.validation.json").is_file()
    npc_validation = json.loads(
        (run_dir / "content/npcs/mara_crumbwell/world.validation.json").read_text()
    )
    assert npc_validation["source_facing"] == "front"
    assert npc_validation["runtime_horizontal_mirroring"] is False
    assert (run_dir / "content/props/contact-sheet.png").is_file()
    prop_validation = json.loads(
        (run_dir / "content/props/sunwheel_bread_stall.validation.json").read_text()
    )
    assert prop_validation["kind"] == "prepared-isolated-prop-validation-v2"
    assert prop_validation["ground_contact"]["kind"] == "alpha-ground-contact-v1"
    assert prop_validation["ground_contact"]["ground_contact_y_normalized"] == 0.9501953125
    assert (run_dir / "soundtrack/sunpetal_morning.validation.json").is_file()
