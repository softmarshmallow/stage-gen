"""Bellweather publishes the examples it made: declaration, pages and typed importers.

``godot/games/bellweather/examples.toml`` declares four examples the game made. Its steps
must place nodes today's Bellweather plan has, of types the game declares, each once and
each titled; its commands must parse with the real ``demo-games`` parser; and every example
needs a page. The importers run here on small synthetic runs that hold only what each one
reads, and ``export`` is shown to write an entry beside a pinned example and to refuse one
whose files no longer match its pins.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shlex
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from PIL import Image, ImageDraw

from bellweather_pipeline.examples import (
    GAME_ROOT,
    IMPORTERS,
    ExampleDeclaration,
    ExamplesManifest,
    currency_of,
    export,
    graph_kinds,
    problems_of,
    read_manifest,
    rederive,
)
from bellweather_pipeline.examples.parallax_layers import GAME_SCRIPTS
from bellweather_pipeline.package_executor import PreparedPackageExecutor
from bellweather_pipeline.package_types import platformer_type_index
from demo_game_collection.parser import build_parser
from stage_gen.components.sideview_terrain.atlas import terrain_atlas_paint_target
from stage_gen.components.ui_art import ATLAS_ROLES, render_atlas_template
from stage_gen.config import StageGenConfig
from stage_gen.examples import (
    ENTRY_FILE,
    PAGE_FILE,
    GameExampleEntry,
    MadeBy,
    WorkflowExample,
    node,
    read_entry,
    verify,
    verify_game_example,
    write_example,
)
from stage_gen.media.sprite_sheets import AlphaComponentRepackContract, repack_alpha_components
from stage_gen.resources import terrain_atlas_lookup_path, terrain_atlas_template_path
from stage_gen.workflows._registry import discover

REPOSITORY_ROOT = Path(__file__).parents[4]
BELLWEATHER = REPOSITORY_ROOT / "godot/games/bellweather/inputs/default"
KIND_V2 = "sideview-platformer-execution-graph-v2"
P = "2d/sideview/platformer"


@pytest.fixture(scope="module")
def manifest() -> ExamplesManifest:
    return read_manifest()


# ---------------------------------------------------------------- the declaration


def test_the_four_examples_are_declared_in_landing_order(manifest: ExamplesManifest) -> None:
    assert manifest.game == "bellweather"
    assert [(e.id, e.order) for e in manifest.examples] == [
        ("parallax-backgrounds", 1),
        ("terrain-tiles", 2),
        ("game-ui-kit", 3),
        ("sprite-animation-set", 4),
    ]
    for declaration in manifest.examples:
        assert declaration.status == "approved"
        IMPORTERS[declaration.importer].options.model_validate(declaration.run)


def test_every_example_has_a_page_without_front_matter(manifest: ExamplesManifest) -> None:
    pages = GAME_ROOT / "examples"
    assert {p.name for p in pages.iterdir() if p.is_dir()} == {e.id for e in manifest.examples}
    for declaration in manifest.examples:
        text = (pages / declaration.id / PAGE_FILE).read_text(encoding="utf-8")
        assert text.strip()
        assert not text.lstrip().startswith(("+++", "---"))


def test_steps_place_nodes_of_todays_plan_once_each_with_a_title(
    manifest: ExamplesManifest,
) -> None:
    graph = PreparedPackageExecutor(StageGenConfig()).plan(BELLWEATHER).graph
    planned = {planned_node.node_id: planned_node.type_id for planned_node in graph.nodes}
    types = platformer_type_index()
    for declaration in manifest.examples:
        members = declaration.members()
        assert len(members) == len(set(members)), declaration.id
        assert set(members) == set(declaration.labels), declaration.id
        assert all(title.strip() for title in declaration.labels.values())
        for member in members:
            assert member in planned, f"{declaration.id}: {member} is not a planned node"
            assert planned[member] in types, f"{declaration.id}: {planned[member]} is unknown"


def test_commands_parse_with_the_demo_games_parser(manifest: ExamplesManifest) -> None:
    for declaration in manifest.examples:
        words = shlex.split(declaration.command)
        assert words[0] == "demo-games"
        build_parser().parse_args(words[1:])
    exporting = build_parser().parse_args(["example", "export", "bellweather", "--from-frozen"])
    assert (exporting.game, exporting.from_frozen, exporting.store) == ("bellweather", True, None)


def test_related_names_product_workflows(manifest: ExamplesManifest) -> None:
    workflows = {found.id for found in discover()}
    for declaration in manifest.examples:
        assert set(declaration.related) <= workflows


def test_currency_follows_todays_types_and_the_kinds_the_game_reads() -> None:
    assert graph_kinds() == {
        "sideview-platformer-execution-graph-v1",
        "sideview-platformer-execution-graph-v2",
    }
    current = _example([f"{P}/map_ground.generate"], "sideview-platformer-execution-graph-v1")
    assert currency_of(current) == "current"
    retired = _example([f"{P}/ui_atlas.generate"], KIND_V2)
    assert currency_of(retired) == "earlier_version"


# ---------------------------------------------------------------- synthetic runs


@dataclass
class Node:
    node_id: str
    type_id: str
    operation: str = "local"
    artifacts: Sequence[str] = ()
    depends_on: Sequence[str] = ()
    estimated: float | None = None
    provider: str | None = None
    model: str | None = None


@dataclass
class Fixture:
    """A repository-like folder: a package, runs, and the files the importers read."""

    base: Path

    def png(self, rel: str, image: Image.Image) -> str:
        path = self.base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, "PNG")
        return _sha(path)

    def json(self, rel: str, document: object) -> str:
        path = self.base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document), encoding="utf-8")
        return _sha(path)

    def text(self, rel: str, text: str) -> None:
        path = self.base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run(self, rel: str, nodes: Sequence[Node], kind: str = KIND_V2) -> str:
        """Write a run's summary and plan, every node a cache miss that succeeded."""
        root = self.base / rel
        summary = [
            {
                "node_id": n.node_id,
                "status": "succeeded",
                "cache": "miss",
                "duration_ms": 1500,
                "attempts": 1,
                "known_cost_usd": None,
                "provider_operations": 1 if n.operation != "local" else 0,
                "artifacts": [{"artifact_ref": a, "sha256": _sha(root / a)} for a in n.artifacts],
            }
            for n in nodes
        ]
        plan = [
            {
                "node_id": n.node_id,
                "type_id": n.type_id,
                "operation": n.operation,
                "description": f"{n.node_id} as planned",
                "provider": n.provider,
                "model": n.model,
                "retry_owner": None,
                "max_attempts": 6 if n.operation != "local" else 1,
                "depends_on": list(n.depends_on),
                "estimated_cost_high_usd": n.estimated,
            }
            for n in nodes
        ]
        self.json(f"{rel}/execution-summary.json", {"duration_ms": 9000, "nodes": summary})
        self.json(
            f"{rel}/execution-plan.json", {"kind": kind, "graph_sha256": "f" * 64, "nodes": plan}
        )
        return rel


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plain(size: tuple[int, int], colour: tuple[int, int, int, int]) -> Image.Image:
    image = Image.new("RGBA", size, colour)
    ImageDraw.Draw(image).rectangle((2, 2, size[0] // 2, size[1] // 2), fill=(30, 90, 60, 255))
    return image


def _blobs(count: int, cell: int = 64) -> Image.Image:
    """``count`` separate opaque shapes in one row on a transparent ground."""
    image = Image.new("RGBA", (cell * count, cell), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for i in range(count):
        draw.ellipse(
            (i * cell + 10, 8, i * cell + cell - 12, cell - 4), fill=(180, 60 + i, 40, 255)
        )
    return image


def _repacked(
    fixture: Fixture, source: str, target: str, contract: AlphaComponentRepackContract
) -> str:
    data, _ = repack_alpha_components((fixture.base / source).read_bytes(), contract)
    path = fixture.base / target
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _sha(path)


def _declaration(
    example_id: str, importer: str, run: dict[str, Any], members: list[str]
) -> ExampleDeclaration:
    return ExampleDeclaration.model_validate(
        {
            "id": example_id,
            "title": "A synthetic example",
            "promise": "Small runs in. A checked example out.",
            "status": "approved",
            "command": "demo-games generate --input my-game --checkpoint world --output runs/w",
            "importer": importer,
            "example_sha256": "0" * 64,
            "figures_sha256": "0" * 64,
            "labels": {member: f"Step {i}" for i, member in enumerate(members)},
            "steps": [{"label": "All", "note": "Every node.", "members": members}],
            "run": run,
        }
    )


def _example(type_ids: list[str], kind: str) -> WorkflowExample:
    nodes = {f"n{i}": node(f"n{i}", type_id=t) for i, t in enumerate(type_ids)}
    return WorkflowExample.model_validate(
        {
            "example_id": "x",
            "made_by": MadeBy(kind="game", id="bellweather"),
            "importer": "terrain_atlas",
            "delivered_run": "out/x",
            "source_runs": [
                {"path": "out/x", "anchor": "execution-plan.json", "anchor_sha256": "0" * 64}
            ],
            "source_files": None,
            "status": "succeeded",
            "graph_kind": kind,
            "graph_sha256": None,
            "inputs": {},
            "outputs": {},
            "metrics": {},
            "models": [],
            "tree": {},
            "nodes": nodes,
        }
    )


def _terrain(fixture: Fixture) -> ExampleDeclaration:
    scene_sha = fixture.png("package/references/scene.png", _plain((96, 64), (210, 190, 150, 255)))
    maps = "out/world/maps/m1"
    fixture.json(f"{maps}/terrain.json", {"occupancy": ["0000", "0110", "1111"]})
    target_sha = hashlib.sha256(terrain_atlas_paint_target()).hexdigest()
    fixture.png(f"{maps}/ground.raw.png", _plain((96, 32), (120, 110, 90, 255)))
    fixture.json(
        f"{maps}/ground.raw.png.meta.json",
        {
            "prompt": "Repaint the template as warm paving.",
            "inputs": [
                {"sha256": target_sha, "ref": "resource://image_gen_templates/target.png"},
                {"sha256": scene_sha, "ref": "package://bellweather/references/scene.png"},
            ],
            "validation": {
                "source": {"width": 2880, "height": 960},
                "thresholds": {
                    "paint_canvas": "2880x960",
                    "maximum_join_tone_step": 40,
                    "minimum_painted_material_standard_deviation": 2,
                },
                "worst_join_tone_step": 12,
                "painted_material_mean_standard_deviation": 6,
            },
        },
    )
    atlas_sha = fixture.png(f"{maps}/ground.png", _plain((1440, 480), (140, 120, 90, 255)))
    evidence = Image.new("RGBA", (64, 48), (0, 0, 0, 0))
    ImageDraw.Draw(evidence).rectangle((8, 20, 56, 47), fill=(140, 120, 90, 255))
    fixture.png(f"{maps}/ground.evidence.png", evidence)
    fixture.json(
        f"{maps}/ground.validation.json",
        {
            "lookup_sha256": _sha(terrain_atlas_lookup_path()),
            "template_sha256": _sha(terrain_atlas_template_path()),
            "lookup_masks": 47,
            "canonical": {
                "sha256": atlas_sha,
                "width": 1440,
                "height": 480,
                "cell_px": 120,
                "published_transparent_pixels": 0,
                "placeholder_transparent_in_canonical": True,
            },
            "maps": {"steps": {"rows": ["01", "11"]}},
        },
    )
    ids = [f"map-m1-{step}" for step in ("terrain-generate", "ground-generate", "ground-validate")]
    run = fixture.run(
        "out/world",
        [
            Node(
                ids[0], f"{P}/map_terrain.design", "structured_generation", ["maps/m1/terrain.json"]
            ),
            Node(
                ids[1],
                f"{P}/map_ground.generate",
                "image_generation",
                ["maps/m1/ground.raw.png"],
                estimated=0.25,
                provider="openai",
                model="gpt-image-2",
            ),
            Node(
                ids[2],
                f"{P}/map_ground.validate",
                artifacts=["maps/m1/ground.png"],
                depends_on=[ids[1]],
            ),
        ],
    )
    return _declaration(
        "terrain-tiles",
        "terrain_atlas",
        {"runs": [run], "package": "package", "maps": [{"map": "m1", "name": "village"}]},
        ids,
    )


def _ui_kit(fixture: Fixture) -> ExampleDeclaration:
    cover_sha = fixture.png("package/references/cover.png", _plain((80, 60), (240, 230, 210, 255)))
    template_sha = hashlib.sha256(render_atlas_template(ATLAS_ROLES["panel_frame"])).hexdigest()
    ui = "out/ui/ui"
    fixture.png(f"{ui}/panel_frame.raw.png", _plain((96, 96), (90, 60, 40, 255)))
    fixture.json(
        f"{ui}/panel_frame.raw.png.meta.json",
        {
            "prompt": "Paint a wooden panel frame.",
            "inputs": [
                {"sha256": template_sha, "ref": "template"},
                {"sha256": cover_sha, "ref": "package://bellweather/references/cover.png"},
            ],
        },
    )
    sheet = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(sheet).rectangle((4, 4, 59, 59), fill=(90, 60, 40, 255))
    fixture.png(f"{ui}/panel_frame.png", sheet)
    fixture.png("out/package/ui/panel_frame.png", sheet)
    fixture.png(f"{ui}/panel_frame.evidence.png", _plain((64, 32), (255, 255, 255, 255)))
    cell = {"x": 0, "y": 0, "width": 64, "height": 64}
    fixture.json(
        f"{ui}/panel_frame.validation.json",
        {
            "facts": {
                "source": {
                    "thresholds": {
                        "transparent_admission_max": 8,
                        "tile_seam_excess_max": 4,
                        "content_luma_std_max": 20,
                        "content_contrast_min": 4.5,
                    },
                    "alpha": {"border_max": 0},
                    "cells": [
                        {
                            "tile_seam_excess": {"x": 1.0, "y": 0.5},
                            "content": {"luma_std": 3, "best_contrast": 7, "best_text": "#f4efe6"},
                        }
                    ],
                    "state_checks": {},
                }
            },
            "cells": [
                {
                    "state": "normal",
                    "cell": cell,
                    "content_rect": {"x": 12, "y": 12, "width": 40, "height": 40},
                }
            ],
            "insets": {"left": 12, "top": 12, "right": 12, "bottom": 12},
            "draw_scale": 1.0,
            "band_fill": "tile",
        },
    )
    fixture.json(
        f"{ui}/panel_frame.review.json",
        {"verdict": "accept", "checks": {"style_matches": True}, "issues": [], "evidence": "Fits."},
    )
    ids = [f"ui-panel_frame-{step}" for step in ("generate", "validate", "review")]
    run = fixture.run(
        "out/ui",
        [
            Node(
                ids[0],
                "2d/ui/atlas.generate",
                "image_generation",
                ["ui/panel_frame.raw.png"],
                depends_on=["package-resolve"],
                estimated=0.2,
                provider="openai",
                model="gpt-image-2",
            ),
            Node(
                ids[1],
                "2d/ui/atlas.validate",
                artifacts=["ui/panel_frame.png"],
                depends_on=[ids[0]],
            ),
            Node(
                ids[2],
                "2d/ui/atlas.review",
                "structured_generation",
                ["ui/panel_frame.review.json"],
                depends_on=[ids[1]],
                estimated=0.01,
            ),
        ],
    )
    return _declaration(
        "game-ui-kit",
        "ui_kit",
        {
            "runs": [run],
            "package": "package",
            "delivered": "out/package",
            "sheets": ["panel_frame"],
        },
        ids,
    )


def _player_manifest(
    fixture: Fixture, delivered: str, actor: str, states: Sequence[str]
) -> dict[str, Any]:
    folder = f"{delivered}/content/players/{actor}"
    specs: dict[str, Any] = {}
    for state in states:
        strip = f"{folder}/states/{state}.png"
        if not (fixture.base / strip).is_file():
            fixture.png(strip, _blobs(2))
        specs[state] = {
            "source_facing": "right",
            "runtime_mirror": True,
            "columns": 2,
            "rows": 1,
            "source_frame_count": 2,
            "anchor": "bottom",
            "playback": {"mode": "loop", "canonical_frame_indices": [0, 1], "frames_per_second": 4},
            "asset": {"sha256": _sha(fixture.base / strip)},
        }
    return {
        "player_id": actor,
        "calibration": {
            "source_px_per_unit": 60.0,
            "baseline_state": states[0],
            "state_rebase": {state: 1.0 for state in states},
        },
        "states": specs,
    }


def _sprite_set(fixture: Fixture) -> ExampleDeclaration:
    actor, made = "hero", "out/content/content/players/hero"
    cover_sha = fixture.png("package/references/cover.png", _plain((80, 60), (240, 230, 210, 255)))
    fixture.text(
        "package/content/player.toml",
        '[[players]]\nplayer_id = "hero"\nprompt = "A small knight with a red scarf."\n',
    )
    fixture.png(f"{made}/concept.png", _blobs(1))
    fixture.json(
        f"{made}/concept.png.meta.json",
        {
            "prompt": "Draw the hero. A small knight with a red scarf.",
            "inputs": [{"sha256": cover_sha}],
        },
    )
    contract = AlphaComponentRepackContract(rows=1, columns=2, required_cells=2, anchor="bottom")
    validation = {
        "source_validation": {
            "alpha_min": 0,
            "alpha_max": 255,
            "border_alpha_max": 0,
            "border_alpha_mean": 0.0,
            "all_required_cells_visible": True,
        },
        "repack": {"anchor": "bottom", "selected_component_count": 2, "required_cells": 2},
    }
    delivered = "out/package/content/players/hero"
    fixture.png(f"{made}/states/idle.source.png", _blobs(2))
    fixture.json(f"{made}/states/idle.source.png.meta.json", {"prompt": "Draw idle.", "inputs": []})
    _repacked(fixture, f"{made}/states/idle.source.png", f"{made}/states/idle.png", contract)
    (fixture.base / f"{delivered}/states").mkdir(parents=True)
    shutil.copyfile(
        fixture.base / f"{made}/states/idle.png", fixture.base / f"{delivered}/states/idle.png"
    )
    fixture.json(f"{made}/states/idle.validation.json", validation)
    fixture.png(f"{made}/dialogue.source.png", _blobs(2))
    fixture.json(
        f"{made}/dialogue.source.png.meta.json", {"prompt": "Draw two faces.", "inputs": []}
    )
    dialogue_sha = _repacked(
        fixture,
        f"{made}/dialogue.source.png",
        f"{delivered}/dialogue.png",
        AlphaComponentRepackContract(rows=1, columns=2, required_cells=2, anchor="center"),
    )
    fixture.json(
        f"{made}/dialogue.validation.json",
        {**validation, "rows": 1, "columns": 2, "expressions": ["calm", "glad"]},
    )
    plate = fixture.png(f"{made}/motion-rebase-plate.png", _plain((64, 32), (250, 250, 250, 255)))
    checked = fixture.png(
        f"{made}/motion-rebase-verification-plate.png", _plain((64, 32), (245, 245, 245, 255))
    )
    fixture.json(
        f"{made}/motion-rebase-first-pass.json",
        {"states": {"idle": 1.0}, "evidence": {"idle": "Baseline."}},
    )
    fixture.json(
        f"{made}/motion-rebase.json",
        {
            "states": {"idle": 1.0},
            "evidence": {"idle": "Holds."},
            "plate_sha256": plate,
            "verification_plate_sha256": checked,
        },
    )
    fixture.png(f"{made}/contact-sheet.png", _plain((64, 32), (250, 250, 250, 255)))
    fixture.json(
        f"{made}/review.json",
        {"verdict": "reject", "checks": {"one_size": False}, "issues": ["small"]},
    )
    player = _player_manifest(fixture, "out/package", actor, ["idle"])
    player["dialogue"] = {"expressions": ["calm", "glad"], "asset": {"sha256": dialogue_sha}}
    fixture.json("out/package/manifest.json", {"player": player})
    p = "player-hero-"
    nodes = [
        Node(
            f"{p}concept-generate",
            f"{P}/actor_concept.generate",
            "image_generation",
            ["content/players/hero/concept.png"],
            estimated=0.2,
        ),
        Node(
            f"{p}state-idle-generate",
            f"{P}/motion_atlas.generate",
            "image_generation",
            ["content/players/hero/states/idle.source.png"],
            [f"{p}concept-generate"],
            0.2,
        ),
        Node(
            f"{p}state-idle-validate",
            f"{P}/motion_atlas.validate",
            artifacts=["content/players/hero/states/idle.png"],
            depends_on=[f"{p}state-idle-generate"],
        ),
        Node(
            f"{p}dialogue-generate",
            f"{P}/dialogue_atlas.generate",
            "image_generation",
            ["content/players/hero/dialogue.source.png"],
            [f"{p}concept-generate"],
            0.2,
        ),
        Node(
            f"{p}dialogue-validate",
            f"{P}/dialogue_atlas.validate",
            depends_on=[f"{p}dialogue-generate"],
        ),
        Node(
            f"{p}motion-rebase",
            "2d/sideview/actor/motion_rebase.judge",
            "structured_generation",
            ["content/players/hero/motion-rebase-plate.png"],
            [f"{p}state-idle-validate"],
            0.05,
        ),
        Node(
            f"{p}motion-rebase-verify",
            "2d/sideview/actor/motion_rebase.verify",
            "structured_generation",
            ["content/players/hero/motion-rebase.json"],
            [f"{p}motion-rebase"],
            0.05,
        ),
        Node(
            f"{p}contact-sheet",
            f"{P}/actor.contact_sheet",
            artifacts=["content/players/hero/contact-sheet.png"],
            depends_on=[f"{p}motion-rebase-verify"],
        ),
        Node(
            f"{p}review",
            f"{P}/actor.review",
            "structured_generation",
            ["content/players/hero/review.json"],
            [f"{p}contact-sheet"],
            0.05,
        ),
    ]
    run = fixture.run("out/content", nodes)
    return _declaration(
        "sprite-animation-set",
        "sprite_set",
        {"runs": [run], "package": "package", "delivered": "out/package", "actor": actor},
        [n.node_id for n in nodes],
    )


def _parallax(fixture: Fixture) -> ExampleDeclaration:
    for script in GAME_SCRIPTS:
        target = fixture.base / script
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / script, target)
    reference_sha = fixture.png("package/references/m1.png", _plain((96, 54), (150, 190, 230, 255)))
    authored = [
        'display_name = "Meadow"',
        "[[references]]",
        'source = "references/m1.png"',
        f'source_sha256 = "{reference_sha}"',
        "[[layers]]",
        'layer_id = "sky"',
        'plane = "background"',
        "order = 0",
        "parallax = 0.2",
        "[layers.presentation]",
        "contrast = 1.1",
        "saturation = 0.9",
        "atmosphere_strength = 0.1",
        'atmosphere_color = "#aabbcc"',
        "detail_blur_screen_pixels = 0.5",
    ]
    fixture.text("package/maps/m1.toml", "\n".join(authored) + "\n")
    world, maps = "out/world", "out/world/maps/m1"
    fixture.json(f"{maps}/terrain.json", {"occupancy": ["0000", "1111"], "walk_surface_row": 1})
    layer = Image.new("RGBA", (96, 48), (120, 160, 220, 255))
    for rel in ("layers/sky.raw.png", "layers/sky.loop.png", "layers/sky.png"):
        fixture.png(f"{maps}/{rel}", layer)
    fixture.json(
        f"{maps}/layers/sky.raw.png.meta.json",
        {"prompt": "Draw a sky.", "inputs": [{"sha256": reference_sha}]},
    )
    fixture.json(
        f"{maps}/layers/sky.loop.json",
        {"construction": "none", "repeat": {"joins": [{"verdict": "pass"}]}},
    )
    fixture.json(
        f"{maps}/layers/sky.validation.json",
        {
            "placement": {
                "source_height": 48,
                "trimmed_top": 0,
                "vertical_anchor": "screen_top",
                "vertical_offset": 0.0,
            },
            "repeat": {"verdict": "pass"},
            "width": 96,
        },
    )
    fixture.png(f"{maps}/composite.png", _plain((64, 36), (200, 200, 200, 255)))
    fixture.json(
        f"{maps}/review.json",
        {"verdict": "accept", "checks": {"loops": True}, "evidence": "Seamless."},
    )
    fixture.png(f"{maps}/ground.png", _plain((1440, 480), (110, 90, 70, 255)))
    ids = [f"map-m1-layer-sky-{step}" for step in ("generate", "loop", "validate")]
    nodes = [
        Node(
            ids[0],
            "2d/sideview/loop_x.generate",
            "image_generation",
            ["maps/m1/layers/sky.raw.png"],
            estimated=0.2,
        ),
        Node(
            ids[1],
            "2d/sideview/loop_x.loop_paint",
            artifacts=["maps/m1/layers/sky.loop.png"],
            depends_on=[ids[0]],
        ),
        Node(
            ids[2],
            "2d/sideview/loop_x.validate",
            artifacts=["maps/m1/layers/sky.png"],
            depends_on=[ids[1]],
        ),
        Node(
            "map-m1-composite",
            f"{P}/map.composite",
            artifacts=["maps/m1/composite.png"],
            depends_on=[ids[2]],
        ),
        Node(
            "map-m1-review",
            f"{P}/map.review",
            "structured_generation",
            ["maps/m1/review.json"],
            ["map-m1-composite"],
            0.05,
        ),
        Node(
            "map-m1-ground-validate", f"{P}/map_ground.validate", artifacts=["maps/m1/ground.png"]
        ),
    ]
    run = fixture.run(world, nodes)
    walker = _player_manifest(fixture, "out/package", "hero", ["idle", "walk", "run", "jump"])
    fixture.json(
        "out/package/manifest.json", {"player": walker, "scale": {"player_height_tiles": 2.0}}
    )
    return _declaration(
        "parallax-backgrounds",
        "parallax_layers",
        {"runs": [run], "package": "package", "maps": ["m1"], "walker": "out/package"},
        [n.node_id for n in nodes[:-1]],
    )


# ---------------------------------------------------------------- the importers


@pytest.mark.parametrize("build", [_terrain, _ui_kit, _sprite_set, _parallax])
def test_each_importer_makes_a_complete_example_from_synthetic_runs(
    tmp_path: Path, build: Any
) -> None:
    fixture = Fixture(tmp_path / "repository")
    declaration: ExampleDeclaration = build(fixture)
    example, ledger = rederive(declaration, base=fixture.base, out=tmp_path / "example")

    assert problems_of(declaration, example) == []
    assert example.made_by == MadeBy(kind="game", id="bellweather")
    assert example.importer == declaration.importer
    assert [run.path for run in example.source_runs] == declaration.run["runs"]
    assert currency_of(example) == "current"
    # Every file the importer opened is named with its digest, package files included.
    assert example.source_files is not None
    assert any(name.startswith("package/") for name in example.source_files)
    for name, digest in example.source_files.items():
        if (fixture.base / name).is_file():
            assert _sha(fixture.base / name) == digest
    # Every derived picture is in the ledger with its digest, and nothing else is in media/.
    written = write_example(tmp_path / "example", example, ledger)
    assert verify(tmp_path / "example", written) == []
    assert ledger.files and all(entry.sources for entry in ledger.files)


def test_the_parallax_importer_refuses_a_game_script_that_moved_its_view(tmp_path: Path) -> None:
    fixture = Fixture(tmp_path / "repository")
    declaration = _parallax(fixture)
    maps_script = fixture.base / GAME_SCRIPTS[0]
    maps_script.write_text(
        maps_script.read_text(encoding="utf-8").replace(
            "const VIEW_HEIGHT := 720.0", "const VIEW_HEIGHT := 768.0"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="VIEW_HEIGHT"):
        rederive(declaration, base=fixture.base, out=tmp_path / "example")


def test_an_importer_refuses_a_sheet_the_package_does_not_deliver(tmp_path: Path) -> None:
    fixture = Fixture(tmp_path / "repository")
    declaration = _ui_kit(fixture)
    fixture.png("out/package/ui/panel_frame.png", _plain((64, 64), (1, 2, 3, 255)))
    with pytest.raises(ValueError, match="panel_frame: the gated sheet"):
        rederive(declaration, base=fixture.base, out=tmp_path / "example")


# ---------------------------------------------------------------- export


def _pinned_store(tmp_path: Path) -> tuple[Fixture, ExamplesManifest, Path, Path]:
    """A synthetic repository, a game folder with a page, and a store holding the pinned
    export of the terrain example."""
    fixture = Fixture(tmp_path / "repository")
    declaration = _terrain(fixture)
    store, game = tmp_path / "store", tmp_path / "game"
    directory = store / "bellweather" / declaration.id
    example, ledger = rederive(declaration, base=fixture.base, out=directory)
    pin = write_example(directory, example, ledger)
    (game / "examples" / declaration.id).mkdir(parents=True)
    (game / "examples" / declaration.id / PAGE_FILE).write_text("The page.\n", encoding="utf-8")
    pinned = declaration.model_copy(
        update={"example_sha256": pin.example_sha256, "figures_sha256": pin.figures_sha256}
    )
    manifest = ExamplesManifest(
        schema_version=1,
        kind="game-examples-v1",
        game="bellweather",
        title="Bellweather",
        examples=[pinned],
    )
    return fixture, manifest, store, game


def test_export_rederives_then_writes_the_page_and_entry(tmp_path: Path) -> None:
    fixture, manifest, store, game = _pinned_store(tmp_path)
    (exported,) = export(manifest, store=store, base=fixture.base, game_root=game)

    assert exported.rederived and exported.currency == "current"
    assert (exported.directory / PAGE_FILE).read_text(encoding="utf-8") == "The page.\n"
    entry = read_entry(exported.directory)
    assert isinstance(entry, GameExampleEntry)
    assert entry.made_by == MadeBy(kind="game", id="bellweather")
    assert entry.game_title == "Bellweather"
    assert entry.pin == manifest.examples[0].pin
    assert verify_game_example(exported.directory) == []


def test_export_refuses_media_that_no_longer_match_the_pins(tmp_path: Path) -> None:
    fixture, manifest, store, game = _pinned_store(tmp_path)
    directory = store / "bellweather" / "terrain-tiles"
    media = sorted((directory / "media").iterdir())[0]
    media.write_bytes(media.read_bytes() + b"\0")

    for from_frozen in (True, False):
        with pytest.raises(ValueError, match="bellweather/terrain-tiles: media/"):
            export(
                manifest, store=store, base=fixture.base, game_root=game, from_frozen=from_frozen
            )
    assert not (directory / ENTRY_FILE).exists()


def test_export_refuses_runs_that_no_longer_make_the_pinned_example(tmp_path: Path) -> None:
    fixture, manifest, store, game = _pinned_store(tmp_path)
    # A run file that still passes the importer's own checks, but no longer makes the
    # pictures that were pinned.
    evidence = fixture.base / "out/world/maps/m1/ground.evidence.png"
    with Image.open(evidence) as opened:
        image = opened.convert("RGBA")
    ImageDraw.Draw(image).rectangle((0, 40, 63, 47), fill=(10, 10, 10, 255))
    image.save(evidence, "PNG")

    with pytest.raises(
        ValueError, match=re.escape("terrain-tiles: media/village-level-preview.webp differs")
    ):
        export(manifest, store=store, base=fixture.base, game_root=game)
    (exported,) = export(manifest, store=store, base=fixture.base, game_root=game, from_frozen=True)
    assert not exported.rederived


def test_the_real_declaration_matches_the_store_when_present(manifest: ExamplesManifest) -> None:
    """The pinned exports, when this checkout holds them, verify against the pins."""
    store = REPOSITORY_ROOT / "out" / "examples" / "bellweather"
    if not store.is_dir():
        pytest.skip("the local example store is absent")
    for declaration in manifest.examples:
        directory = store / declaration.id
        assert verify(directory, declaration.pin) == [], declaration.id
        document = WorkflowExample.model_validate_json((directory / "example.json").read_bytes())
        assert problems_of(declaration, document) == [], declaration.id
        expected = "earlier_version" if declaration.id == "game-ui-kit" else "current"
        assert currency_of(document) == expected
        if (directory / ENTRY_FILE).is_file():
            assert verify_game_example(directory) == []


def test_the_command_refuses_a_store_without_the_frozen_exports(tmp_path: Path) -> None:
    from demo_game_collection.cli import main

    errors = io.StringIO()
    argv = ["example", "export", "bellweather", "--store", str(tmp_path), "--from-frozen"]
    assert main(argv, stdout=io.StringIO(), stderr=errors) == 1
    message = errors.getvalue()
    assert "refusing to export" in message
    assert "bellweather/parallax-backgrounds: is not in the example store" in message
    assert not any(tmp_path.iterdir())
