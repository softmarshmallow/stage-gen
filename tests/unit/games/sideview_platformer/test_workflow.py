"""Bellweather's builder through gnode, offline: the plan, its parts, a whole run, the package.

Each run test copies the game's gnode project (``gnode.yaml``, the lock, ``pipeline/nodes`` and
the builder) and the default package into a scratch folder, because a package's references are
project files. Paid calls are stand-ins that answer what the game's judges admit, recognised
by the brief they were sent: cut-outs, one figure per motion or portrait cell, a climbing
roster of narrow subjects, a portal pair, layers that already loop, the packed atlas restated
in one material, the interface sheets the gates promise, a stored terrain composition the
map's validator accepts, and an accepting review.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import re
import shutil
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest
from PIL import Image, ImageDraw

from bellweather_pipeline.briefs import EDITABLE_SPAN
from bellweather_pipeline.input import resolve_game_package
from bellweather_pipeline.motion_contract import motion_atlas_geometry
from bellweather_pipeline.prepared_manifest import runtime_artifact_paths, verify_prepared_runtime
from demo_game_collection.resources import bundled_music_path
from demo_game_tools.kits.sideview_terrain import PAINT_CANVAS_SIZE, terrain_atlas_paint_target
from demo_game_tools.kits.ui_art.nodes import UI_SHEET_ROLES, sheet_family
from demo_game_tools.media.ui import (
    INVENTORY_PANEL_HEIGHT,
    INVENTORY_PANEL_LEFT,
    INVENTORY_PANEL_TOP,
    INVENTORY_PANEL_WIDTH,
)
from gnode import (
    CallRecord,
    HostServices,
    Plan,
    PlanError,
    Route,
    RunOutcome,
    Store,
    WorkflowRun,
    plan_async,
)
from tests.unit._ui_atlas_fixture import ui_sheet

REPOSITORY = Path(__file__).resolve().parents[4]
GAME = REPOSITORY / "godot/games/bellweather"
BUILDER = "pipeline/workflow.py:build"
FFPROBE = shutil.which("ffprobe")
needs_ffprobe = pytest.mark.skipif(FFPROBE is None, reason="the track record measures with it")

#: Compositions each shipped map's validator accepts: the ones the last accepted world drew.
DESIGNS: dict[str, dict[str, object]] = {
    "sunpetal-crossing": {
        "design_notes": "A village lane with one hollow and a gentle rise.",
        "start_height_tiles": 3,
        "chunks": [
            {"kind": "run", "len": 6},
            {"kind": "hollow", "width": 10, "depth": 1},
            {"kind": "run", "len": 14},
            {
                "kind": "hop_chain",
                "count": 1,
                "jump_rise": 1,
                "gap": 2,
                "platform_width": 4,
                "dir": "up",
            },
            {
                "kind": "hop_chain",
                "count": 1,
                "jump_rise": 1,
                "gap": 2,
                "platform_width": 4,
                "dir": "down",
            },
            {"kind": "run", "len": 8},
            {"kind": "slope", "rise": 1, "grade": "gentle", "dir": "up"},
            {"kind": "run", "len": 8},
        ],
    },
    "crowncrag-road": {
        "design_notes": "Three climbs around a stack of shelves.",
        "start_height_tiles": 3,
        "chunks": [
            {"kind": "run", "len": 3},
            {"kind": "perch", "platform_width": 2, "climb_rise": 4, "variant": "bellroot_ladder"},
            {
                "kind": "shelves",
                "tiers": 3,
                "decks": 3,
                "platform_width": 6,
                "gap": 5,
                "lean": "right",
            },
            {
                "kind": "perch",
                "platform_width": 3,
                "climb_rise": 4,
                "variant": "shrine_rope_ladder",
            },
            {"kind": "run", "len": 1},
            {"kind": "perch", "platform_width": 3, "climb_rise": 4, "variant": "bellrope_climb"},
        ],
    },
}


def game_project(tmp_path: Path) -> Path:
    """The game's gnode project in a scratch folder, with the default package in ``inputs``."""

    project = tmp_path / "project"
    (project / "pipeline").mkdir(parents=True)
    settings = (GAME / "gnode.yaml").read_text(encoding="utf-8")
    settings = settings.replace("runs: ../../../out/runs", "runs: runs")
    settings = settings.replace("cache: ../../../out/gnode-cache", "cache: cache")
    (project / "gnode.yaml").write_text(settings, encoding="utf-8")
    shutil.copy(GAME / "gnode.lock", project / "gnode.lock")
    shutil.copytree(GAME / "pipeline/nodes", project / "pipeline/nodes")
    shutil.copy(GAME / "pipeline/workflow.py", project / "pipeline/workflow.py")
    shutil.copytree(GAME / "inputs/default", project / "inputs/default")
    return project


def plan(project: Path, package: str = "inputs/default", **arguments: str) -> Plan:
    return asyncio.run(
        plan_async(BUILDER, cwd=project, arguments={"package": package, **arguments})
    )


def first_takes(planned: Plan) -> list[Any]:
    return [i for i in planned.instances if i.state != "absent" and set(i.takes) <= {1}]


def steps_of(planned: Plan) -> set[str]:
    return {instance.step for instance in first_takes(planned)}


# ------------------------------------------------------------------------------- stand-ins


def _png(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def _canvas(size: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    width, height = (int(side) for side in size.split("x"))
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image)


def _cells(size: str, columns: int, rows: int, required: int) -> bytes:
    """One figure in each required cell of a row-major grid."""

    image, draw = _canvas(size)
    cell_width, cell_height = image.width / columns, image.height / rows
    for index in range(required):
        row, column = divmod(index, columns)
        draw.ellipse(
            (
                round(column * cell_width + cell_width * 0.2),
                round(row * cell_height + cell_height * 0.2),
                round((column + 1) * cell_width - cell_width * 0.2),
                round((row + 1) * cell_height - cell_height * 0.2),
            ),
            fill=(100, 170, 230, 255),
        )
    return _png(image)


def _cutout(size: str) -> bytes:
    return _cells(size, 1, 1, 1)


def _climbables(size: str, roles: list[str]) -> bytes:
    """A ladder four times taller than wide and a rope fifteen, at one height, in a row."""

    image, draw = _canvas(size)
    column = image.width / len(roles)
    height = image.height * 6 // 10
    top = (image.height - height) // 2
    for index, role in enumerate(roles):
        width = height // (4 if role == "ladder" else 15)
        centre = round(column * (index + 0.5))
        draw.rectangle(
            (centre - width // 2, top, centre + width // 2, top + height), fill=(120, 90, 60, 255)
        )
    return _png(image)


def _layer(size: str, *, transparent: bool) -> bytes:
    """A layer that already loops: every column is the same."""

    image, draw = _canvas(size)
    for y in range(image.height):
        if transparent and y < image.height * 6 // 10:
            continue
        shade = 90 + y * 120 // image.height
        draw.line((0, y, image.width, y), fill=(shade // 2, shade, shade // 3, 255))
    return _png(image)


def _atlas() -> bytes:
    """The packed atlas target restated in one material, shaded by its own luminance."""

    with Image.open(io.BytesIO(terrain_atlas_paint_target())) as opened:
        image = opened.convert("RGB")
    pixels = image.load()
    assert pixels is not None
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue = cast(tuple[int, int, int], pixels[x, y])
            shade = 0.55 + 0.75 * (red * 0.299 + green * 0.587 + blue * 0.114) / 255.0
            variation = ((x // 19 + y // 23) % 9) - 4
            pixels[x, y] = cast(
                tuple[int, int, int],
                tuple(
                    max(0, min(255, round(channel * shade) + variation))
                    for channel in (132, 86, 50)
                ),
            )
    return _png(image)


def _inventory() -> bytes:
    image, draw = _canvas("1536x1024")
    draw.rectangle(
        (
            INVENTORY_PANEL_LEFT,
            INVENTORY_PANEL_TOP,
            INVENTORY_PANEL_LEFT + INVENTORY_PANEL_WIDTH - 1,
            INVENTORY_PANEL_TOP + INVENTORY_PANEL_HEIGHT - 1,
        ),
        fill=(100, 170, 230, 251),
    )
    return _png(image)


class StandIns:
    """Every paid call the default package makes, answered offline."""

    def __init__(self, store: Store, project: Path, *, rejected_designs: int = 0) -> None:
        self.store = store
        self.package = resolve_game_package(project / "inputs/default")
        self.calls: Counter[str] = Counter()
        self.prompts: dict[str, list[str]] = {}
        #: How many compositions the validator refuses before the stored one is answered.
        self.rejected_designs = rejected_designs
        self._atlas: bytes | None = None
        self._templates = {
            hashlib.sha256(sheet_family(role).template(role)).hexdigest(): name
            for name, role in UI_SHEET_ROLES.items()
        }

    def services(self) -> HostServices:
        return HostServices(
            store=self.store,
            capabilities={
                "image.generate": self._image,
                "image.edit": self._image,
                "structured.generate": self._structured,
                "music.generate": self._music,
            },
            live=True,
        )

    def _put(self, data: bytes, kind: str) -> Any:
        return self.store.put_bytes(data, kind=kind, name=kind.split("/", 1)[0])

    def _note(self, kind: str, prompt: str) -> None:
        self.calls[kind] += 1
        self.prompts.setdefault(kind, []).append(prompt)

    def _paint(self, request: Mapping[str, Any]) -> tuple[str, bytes]:
        prompt = str(request["prompt"])
        size = str(request["size"])
        pictures = [request.get("image"), *(request.get("references") or [])]
        roles = {
            self._templates.get(picture.digest) for picture in pictures if picture is not None
        } - {None}
        if request.get("mask") is not None:
            return "loop", self.store.file_path(request["image"].digest).read_bytes()
        if size == PAINT_CANVAS_SIZE:
            self._atlas = self._atlas or _atlas()
            return "atlas", self._atlas
        if roles:
            return "ui", ui_sheet(str(roles.pop()))
        if "inventory panel" in prompt:
            return "inventory", _inventory()
        if "dialogue portrait atlas" in prompt:
            grid = re.search(r"strict (\d+)-column by (\d+)-row", prompt)
            assert grid is not None
            cells = len(re.findall(r"cell \d+:", prompt))
            return "dialogue", _cells(size, int(grid[1]), int(grid[2]), cells)
        if "side-view motion atlas" in prompt:
            found = re.search(r"for (player|mob|npc) \S+, state (\w+)\.", prompt)
            assert found is not None
            geometry = motion_atlas_geometry(found[1], found[2])  # type: ignore[arg-type]
            return "strip", _cells(size, geometry.columns, geometry.rows, geometry.required_cells)
        if "climbing routes" in prompt:
            return "climbable", _climbables(size, re.findall(r"\d+\. (ladder|rope) —", prompt))
        if "portal structures" in prompt:
            return "portal", _cells(size, 2, 1, 2)
        if "horizontally seamless repeat unit" in prompt:
            transparent = request.get("background") == "transparent"
            return "layer", _layer(size, transparent=transparent)
        return "cutout", _cutout(size)

    async def _image(self, route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
        kind, data = self._paint(request)
        self._note(kind, str(request["prompt"]))
        return CallRecord({"image": self._put(data, "image/png")}, None, 0.01)

    async def _structured(self, route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
        schema = json.loads(self.store.file_path(request["schema"].digest).read_text())
        fields = set(schema.get("properties") or {})
        prompt = str(request["prompt"])
        if "chunks" in fields:
            self._note("design", prompt)
            game_map = next(m for m in self.package.maps if m.terrain.brief in prompt)
            answer: dict[str, Any] = dict(DESIGNS[game_map.map_id])
            if self.rejected_designs:
                self.rejected_designs -= 1
                # A level that leaves a declared climbable unplaced breaks the map's own rules.
                answer = {**answer, "chunks": [{"kind": "run", "len": 4}] * 3}
        elif "verdict" in fields:
            self._note("review", prompt)
            answer = {"verdict": "accept", "confidence": 1.0, "checks": {}, "issues": []}
            answer["evidence"] = "deterministic stand-in"
        else:
            self._note("reading", prompt)
            states = [motion.state for motion in self.package.player.players[0].motions]
            answer = {
                "baseline_state": "idle",
                "states": [
                    {"state": state, "multiplier": 1.0, "evidence": "Drawn at idle's size."}
                    for state in states
                ],
            }
        return CallRecord({}, {"json": answer}, 0.01)

    async def _music(self, route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
        self._note("track", str(request["prompt"]))
        audio = self._put(bundled_music_path().read_bytes(), "audio/mpeg")
        return CallRecord({"audio": audio}, None, 0.05)


def run(project: Path, stand_ins: StandIns, name: str = "run", **arguments: str) -> RunOutcome:
    planned = plan(project, **arguments)
    assert planned.ok, planned.problems
    stand_ins.store = planned.planner.store
    return asyncio.run(
        WorkflowRun(planned, run_dir=project / name, services=stand_ins.services()).run()
    )


def deliver(store: Store, outcome: RunOutcome, folder: Path, output: str = "package") -> Path:
    for key, file in outcome.outputs[output].items:
        target = folder / key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(store.file_path(file.digest), target)
    return folder


def failures(outcome: RunOutcome) -> dict[str, str]:
    return {
        step: str(getattr(outcome.results.get(step), "error", None) or "")
        for step in outcome.failed
    } or {"stopped": str(outcome.stopped)}


def stand_ins_for(project: Path, **options: Any) -> StandIns:
    store = plan(project).planner.store
    return StandIns(store, project, **options)


# ------------------------------------------------------------------------------- the plan


@pytest.mark.parametrize("variant", ["default", "waves"])
def test_each_shipped_package_plans_inside_its_own_project(variant: str) -> None:
    planned = plan(GAME, f"inputs/{variant}")

    assert planned.ok, planned.problems
    assert planned.planner.workflow.id == "bellweather"
    budget = planned.planner.workflow.budget
    assert budget is not None and planned.estimate()[1] <= budget.max_usd


def test_the_plan_draws_what_the_package_declares_once_each() -> None:
    planned = plan(GAME)
    package = resolve_game_package(GAME / "inputs/default")
    calls = Counter(cap for instance in first_takes(planned) for cap in instance.routes)
    strips = sum(len(player.motions) for player in package.player.players)
    strips += sum(len(mob.motions) for mob in package.mobs.mobs)
    actors = len(package.player.players) + len(package.mobs.mobs) + len(package.npcs.npcs)
    catalog = len(package.props.props) + len(package.items.items)
    catalog += 0 if package.projectiles is None else len(package.projectiles.projectiles)
    dialogue = len(package.player.players) + len(package.npcs.npcs)
    layers = sum(len(game_map.layers) for game_map in package.maps)
    presentations = sum(
        (game_map.portal is not None) + (game_map.climbable is not None)
        for game_map in package.maps
    )
    repaints = [i for i in first_takes(planned) if i.step.endswith(".loop") and i.routes]
    # Every concept, strip, NPC world sprite, dialogue atlas, catalog subject, layer, ground
    # atlas, climbable and portal sheet, the inventory panel and each interface sheet; and a
    # seam repaint for each layer whose construction paints one.
    assert len(repaints) == layers
    assert calls["image.edit"] == len(repaints) + (
        actors
        + strips
        + len(package.npcs.npcs)
        + dialogue
        + catalog
        + layers
        + len(package.maps)
        + presentations
        + 1
        + 3
    )
    assert calls["music.generate"] == len(package.soundtrack.tracks)
    # A composition per map, two rebase readings, and a review per map, actor, catalog
    # family and interface sheet.
    families = 2 + (package.projectiles is not None)
    assert calls["structured.generate"] == len(package.maps) * 2 + 2 + actors + families + 4
    assert "package" in steps_of(planned)


def test_every_painting_is_judged_and_drawn_again_at_most_six_times() -> None:
    planned = plan(GAME)
    takes = Counter(instance.step for instance in planned.instances if instance.state != "absent")
    painted = [i for i in first_takes(planned) if set(i.routes) & {"image.edit", "music.generate"}]

    assert painted
    for instance in painted:
        if instance.step.endswith(".loop"):
            continue  # a seam repaint is one edit inside its step, refused into a fallback
        assert instance.judged_by, instance.step
        assert takes[instance.step] == 6, instance.step
    designs = [i for i in first_takes(planned) if i.step.endswith(".terrain.design")]
    assert len(designs) == 2 and {takes[i.step] for i in designs} == {3}


def test_a_seam_repaint_is_briefed_for_the_canvas_it_will_see() -> None:
    planned = plan(GAME)
    loops = [i for i in first_takes(planned) if i.step.endswith(".loop")]

    assert loops
    for instance in loops:
        assert EDITABLE_SPAN in instance.with_["prompt"], instance.step


def test_each_part_builds_its_slice_and_reviews_can_be_left_out() -> None:
    world = steps_of(plan(GAME, part="world"))
    content = steps_of(plan(GAME, part="content"))
    quiet = steps_of(plan(GAME, part="content", reviews="no"))
    soundtrack = steps_of(plan(GAME, part="soundtrack"))

    assert all(step.startswith(("maps.", "files")) for step in world)
    assert not any(step.startswith(("maps.", "soundtrack.")) for step in content)
    assert all(step.startswith(("soundtrack.", "files")) for step in soundtrack)
    assert {step for step in content if step.endswith(".review")}
    assert not {step for step in quiet if step.endswith(".review")}
    assert "package" not in world | content | soundtrack


def test_a_part_that_does_not_exist_is_refused() -> None:
    with pytest.raises(PlanError, match="part is one of all, world, content, soundtrack"):
        plan(GAME, part="maps")


def test_the_package_step_publishes_exactly_the_runtime_closure() -> None:
    planned = plan(GAME)
    (package_step,) = [i for i in first_takes(planned) if i.step == "package"]
    package = resolve_game_package(GAME / "inputs/default")

    assert set(package_step.with_["published"]) == set(runtime_artifact_paths(package))


# ------------------------------------------------------------------------------- a whole run


@needs_ffprobe
def test_a_whole_build_runs_offline_into_a_runtime_the_manifest_verifies(tmp_path: Path) -> None:
    project = game_project(tmp_path)
    stand_ins = stand_ins_for(project)

    outcome = run(project, stand_ins)

    assert outcome.ok, failures(outcome)
    folder = deliver(stand_ins.store, outcome, tmp_path / "runtime")
    verified = verify_prepared_runtime(folder)
    assert verified["valid"] is True and verified["game_id"] == "bellweather"
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["player"]["calibration"]["baseline_state"] == "idle"
    # Nothing loops badly, so no seam was repainted; every other call ran once.
    assert "loop" not in stand_ins.calls
    assert stand_ins.calls["design"] == 2


@needs_ffprobe
def test_a_rejected_composition_is_composed_again_told_what_failed(tmp_path: Path) -> None:
    project = game_project(tmp_path)
    stand_ins = stand_ins_for(project, rejected_designs=1)

    outcome = run(project, stand_ins, part="world", reviews="no")

    assert outcome.ok, failures(outcome)
    first, *later = stand_ins.prompts["design"]
    told = [prompt for prompt in later if "rejected by the game's own validator" in prompt]
    assert "rejected by the game's own validator" not in first
    assert len(told) == 1 and told[0].endswith("\n\nCompose the map.")


@needs_ffprobe
def test_an_edit_no_drawing_depends_on_redraws_nothing(tmp_path: Path) -> None:
    """After one build, retune what a provider cannot draw: the next build paints nothing.

    The level's shape is composed from the map's brief alone, a loop construction is read by
    the loop alone, and playback and a projectile's magnitude by local steps and reviews.
    """

    project = game_project(tmp_path)
    assert run(project, stand_ins_for(project)).ok
    package = project / "inputs/default"
    for member, old, new in (
        (
            "maps/crowncrag-road.toml",
            "Keep the ground itself almost level",
            "Keep the ground itself perfectly level",
        ),
        (
            "maps/crowncrag-road.toml",
            'loop_construction = "seam_repaint"',
            'loop_construction = "fold_repaint"',
        ),
        ("content/mobs.toml", "frames_per_second = 6", "frames_per_second = 9"),
        ("content/projectiles.toml", "length_units = 0.50", "length_units = 0.60"),
    ):
        path = package / member
        text = path.read_text(encoding="utf-8")
        assert old in text, (member, old)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
    again = stand_ins_for(project)

    outcome = run(project, again, "again")

    assert outcome.ok, failures(outcome)
    # One composition of the reshaped level; reviews of what they are now told; nothing drawn.
    assert set(again.calls) <= {"design", "review"}, again.calls
    assert again.calls["design"] == 1
