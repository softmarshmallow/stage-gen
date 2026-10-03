"""Ember Hollow's gnode project in a scratch folder, and stand-ins for every paid call it makes.

A package's references and takes are project files, so each test copies the game's project
(``gnode.yaml``, the lock, ``pipeline/nodes`` and the builder) and puts a package inside it.
Paid calls are answered offline with flat drawings that pass the game's real gates,
recognised by the exact brief the builder sends: the stand-ins compute every brief with the
same prompt functions the builder calls. An agent's anchor episode submits the measured
starting point it is offered.
"""

from __future__ import annotations

import asyncio
import io
import math
import re
import shutil
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter

from demo_game_collection.resources import bundled_music_path
from demo_game_tools.kits.ui_art.nodes import UI_SHEET_ROLES, sheet_family
from ember_hollow_pipeline import survival_prompts as prompts
from ember_hollow_pipeline.build import STRIKE_CELL_KINDS
from ember_hollow_pipeline.models import Package
from ember_hollow_pipeline.survival_request import load_package
from gnode import CallRecord, HostServices, Plan, Route, RunOutcome, Store, WorkflowRun, plan_async
from tests.unit._ui_atlas_fixture import ui_sheet
from tests.unit.games.oblique_survival import _survival_fixture as fixture

REPOSITORY = Path(__file__).resolve().parents[4]
GAME = REPOSITORY / "godot/games/ember_hollow"
BUILDER = "pipeline/workflow.py:build"
PACKAGE = "inputs"
_TAKE_LINE = re.compile(r"^\s*take\s*=.*$\n?", flags=re.M)


def ember_project(tmp_path: Path, *, takes: bool = False) -> Path:
    """The game's project in a scratch folder, its package in ``inputs``.

    Without ``takes`` every auditioned take is struck from the package, so each one is
    drawn: a clone does not carry the takes, and a test must not depend on them.
    """

    project = tmp_path / "project"
    (project / "pipeline").mkdir(parents=True)
    settings = (GAME / "gnode.yaml").read_text(encoding="utf-8")
    settings = settings.replace("runs: ../../../out/runs", "runs: runs")
    settings = settings.replace("cache: ../../../out/gnode-cache", "cache: cache")
    (project / "gnode.yaml").write_text(settings, encoding="utf-8")
    shutil.copy(GAME / "gnode.lock", project / "gnode.lock")
    shutil.copytree(GAME / "pipeline/nodes", project / "pipeline/nodes")
    shutil.copy(GAME / "pipeline/workflow.py", project / "pipeline/workflow.py")
    shutil.copytree(GAME / PACKAGE, project / PACKAGE)
    if not takes:
        for document in (project / PACKAGE).glob("*.toml"):
            text = document.read_text(encoding="utf-8")
            struck = _TAKE_LINE.sub("", text)
            if struck != text:
                document.write_text(struck, encoding="utf-8")
    return project


def plan(project: Path, scope: str = "minimal") -> Plan:
    return asyncio.run(
        plan_async(BUILDER, cwd=project, arguments={"package": PACKAGE, "scope": scope})
    )


def first_takes(planned: Plan) -> list[Any]:
    return [i for i in planned.instances if i.state != "absent" and set(i.takes) <= {1}]


def calls_of(planned: Plan) -> Counter[str]:
    return Counter(route for instance in first_takes(planned) for route in instance.routes)


# ------------------------------------------------------------------------------- drawings


def png(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def _open(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as opened:
        return opened.convert("RGBA")


def _size(value: str) -> tuple[int, int]:
    width, height = (int(side) for side in value.split("x"))
    return width, height


def sprite(size: tuple[int, int] = (1024, 1024)) -> bytes:
    """A rock standing on its foot, as the prop gate wants one."""

    data = fixture._fixture_sprite("rock")
    if size == (1024, 1024):
        return data
    return png(_open(data).resize(size))


def sheet(columns: int, rows: int, cell: int = 512) -> bytes:
    """One standing subject per cell, each well inside its own cell."""

    canvas = Image.new("RGBA", (columns * cell, rows * cell), (0, 0, 0, 0))
    subject = _open(fixture._fixture_sprite("rock")).resize((cell, cell))
    for index in range(columns * rows):
        canvas.alpha_composite(subject, ((index % columns) * cell, (index // columns) * cell))
    return png(canvas)


def lattice(template: bytes) -> bytes:
    """The paintover lattice with one blob painted inside each cell, guides untouched."""

    image = _open(template)
    from ember_hollow_pipeline.templates import LATTICE_CELL_PX

    draw = ImageDraw.Draw(image)
    cell = LATTICE_CELL_PX if image.width % LATTICE_CELL_PX == 0 else image.width // 4
    columns, rows = image.width // cell, image.height // cell
    for row in range(rows):
        for column in range(columns):
            cx, cy = column * cell + cell // 2, row * cell + cell // 2
            # A little larger each cell, so no two frames of a strip are the same drawing.
            radius = cell // 6 + (row * columns + column) % 8
            draw.ellipse(
                (cx - radius, cy - radius, cx + radius, cy + radius), fill=(150, 110, 60, 255)
            )
    return png(image)


def decal(size: tuple[int, int] = (1024, 1024)) -> bytes:
    """A lopsided soft patch: irregular, and fading to nothing at its edge."""

    width, height = size
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    points = []
    for index in range(24):
        angle = 2 * math.pi * index / 24
        radius = width * (0.28 + 0.1 * math.sin(3 * angle) + 0.05 * math.cos(5 * angle))
        points.append((width / 2 + radius * math.cos(angle), height / 2 + radius * math.sin(angle)))
    draw.polygon(points, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(24))
    image = Image.new("RGBA", size, (86, 68, 50, 255))
    image.putalpha(mask)
    return png(image)


def plate(*, luma: int = 120) -> bytes:
    """An even material swatch at one value."""

    return png(Image.new("RGB", (1024, 1024), (luma, luma - 10, luma - 30)))


# ------------------------------------------------------------------------------- stand-ins


class EmberStandIns:
    """Every paid call a build of this package makes, answered offline.

    ``refuse`` names kinds of answer and how many times each is answered wrongly first, so
    a test can watch a judge send a take back.
    """

    def __init__(
        self, store: Store, package: Package, *, refuse: Mapping[str, int] | None = None
    ) -> None:
        self.store = store
        self.calls: Counter[str] = Counter()
        self.prompts: dict[str, list[str]] = {}
        self.refuse: Counter[str] = Counter(refuse or {})
        self._templates = {
            sheet_family(role).template(role): name for name, role in UI_SHEET_ROLES.items()
        }
        self.kinds = _kinds(package)
        self.baselines = {actor.display_name: actor.baseline_key for actor in package.actors}

    def services(self) -> HostServices:
        return HostServices(
            store=self.store,
            capabilities={
                "image.generate": self._image,
                "image.edit": self._image,
                "structured.generate": self._structured,
                "music.generate": self._audio,
                "sound.generate": self._audio,
                "agent.turn": self._agent,
            },
            live=True,
        )

    def _note(self, kind: str, prompt: str) -> bool:
        self.calls[kind] += 1
        self.prompts.setdefault(kind, []).append(prompt)
        if self.refuse[kind] > 0:
            self.refuse[kind] -= 1
            return True
        return False

    def _bytes(self, value: Any) -> bytes:
        return self.store.file_path(value.digest).read_bytes()

    def _draw(self, request: Mapping[str, Any]) -> tuple[str, bytes]:
        prompt = str(request["prompt"])
        size = _size(str(request["size"]))
        pictures = [request.get("image"), *(request.get("references") or [])]
        for picture in pictures:
            if picture is not None and self._bytes(picture) in self._templates:
                return "ui", ui_sheet(self._templates[self._bytes(picture)])
        kind, info = self.kinds.get(prompt, ("", None))
        if kind == "sheet":
            return kind, sheet(*info)
        if kind == "look":
            return kind, fixture._fixture_look(self._bytes(request["image"]))
        if kind in {"pieces", "fire"}:
            return kind, lattice(self._bytes(request["image"]))
        if kind == "decal":
            return kind, decal(size)
        if kind == "plate":
            return kind, plate(luma=info)
        if kind == "macro":
            return kind, fixture._fixture_macro()
        if kind == "motion":
            return kind, fixture._fixture_strip("player", info)
        if kind == "dust":
            return kind, fixture._fixture_dust(info)
        if kind == "drops":
            return kind, fixture._fixture_drops()
        if kind == "splash":
            return kind, fixture._fixture_splash(info)
        if kind == "strike":
            return kind, fixture._fixture_strike()
        if kind == "shell":
            return kind, plate(luma=110) if request.get("background") == "opaque" else sprite(size)
        if kind in {"prop", "item", "concept"}:
            return kind, sprite(size)
        raise AssertionError(f"no stand-in for this brief: {prompt[:120]!r}")

    async def _image(self, route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
        kind, data = self._draw(request)
        if self._note(kind, str(request["prompt"])):
            data = png(Image.new("RGBA", (64, 64), (0, 0, 0, 0)))
        stored = self.store.put_bytes(data, kind="image/png", name="image")
        return CallRecord({"image": stored}, None, 0.01)

    async def _structured(self, route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
        import json

        schema = json.loads(self.store.file_path(request["schema"].digest).read_text())
        fields = set(schema.get("properties") or {})
        prompt = str(request["prompt"])
        if "consistent_pitch" in fields:
            wrong = self._note("review", prompt)
            answer: dict[str, Any] = {
                "consistent_pitch": not wrong,
                "consistent_style": True,
                "clean_cutouts": True,
                "consistent_state_pairs": True,
                "readable_at_play_size": True,
                "findings": [],
                "summary": "Deterministic stand-in review.",
            }
        elif "states" in fields:
            self._note("rebase", prompt)
            listed = re.search(r"For each of these states, [^:]*: (.+)\.\n", prompt)
            actor = re.match(r"This image is a \w+ plate for ([^.]+)\.", prompt)
            assert listed is not None and actor is not None
            states = listed[1].split(", ")
            answer = {
                "baseline_state": self.baselines[actor[1]],
                "states": [
                    {"state": state, "multiplier": 1.0, "evidence": "Drawn at one scale."}
                    for state in states
                ],
            }
        elif "verdict" in fields:
            self._note("shell_review", prompt)
            answer = {
                "verdict": "accept",
                "confidence": 1.0,
                "checks": {},
                "issues": [],
                "evidence": "deterministic stand-in",
            }
        else:
            raise AssertionError(f"unexpected structured schema: {sorted(fields)}")
        return CallRecord({}, {"json": answer}, 0.01)

    async def _audio(self, route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
        self._note("audio", str(request["prompt"]))
        audio = self.store.put_bytes(
            bundled_music_path().read_bytes(), kind="audio/mpeg", name="audio"
        )
        return CallRecord({"audio": audio}, None, 0.05)

    async def _agent(self, route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
        opening = str(request["messages"][0]["content"])
        prop = re.search(r"one 2D billboard prop: ([a-z_]+),", opening)
        start = re.search(r"anchor \(([0-9.]+), ([0-9.]+)\), radius ([0-9]*\.?[0-9]+)", opening)
        assert prop is not None and start is not None
        self._note("anchor", prop[1])
        answer = {
            "anchor_x": float(start[1]),
            "anchor_y": float(start[2]),
            "footprint_radius_units": max(0.02, float(start[3])),
            "motion_hint": "none",
            "rationale": "The measured starting point sits under the object.",
        }
        calls = [{"id": "stand-in", "name": "submit", "arguments": answer}]
        return CallRecord({}, {"text": "", "tool_calls": calls}, 0.0)


def _kinds(package: Package) -> dict[str, tuple[str, Any]]:
    """Every brief the builder can send, and what kind of drawing answers it."""

    kinds: dict[str, tuple[str, Any]] = {}
    for prop in package.props:
        if prop.sheet is not None:
            kinds[prompts.prop_sheet_prompt(package, prop)] = (
                "sheet",
                (prop.sheet.columns, prop.sheet.rows),
            )
        for state in prop.states:
            kinds[prompts.prop_prompt(package, prop, state)] = ("prop", None)
            if package.seasons is not None:
                for look in package.seasons.looks:
                    kinds[prompts.season_look_prompt(package, prop, state, look)] = ("look", None)
    for item in package.items:
        kinds[prompts.item_prompt(package, item.item_id, item.prompt)] = ("item", None)
    kinds[prompts.icon_sheet_prompt(package, package.icons, package.items)] = ("pieces", None)
    for biome in package.biomes:
        kinds[prompts.ground_prompt(package, biome)] = ("plate", 120)
    if package.macro is not None:
        kinds[prompts.macro_prompt(package.macro)] = ("macro", None)
    if package.road is not None:
        kinds[prompts.road_prompt(package, package.road)] = ("plate", 120)
    if package.water is not None:
        kinds[prompts.water_prompt(package, package.water)] = ("plate", 70)
    if package.forage is not None:
        kinds[prompts.forage_prompt(package, package.forage)] = ("pieces", None)
    for decal_spec in package.decals:
        kinds[prompts.decal_prompt(package, decal_spec)] = ("decal", None)
    for actor in package.actors:
        kinds[prompts.actor_concept_prompt(package, actor)] = ("concept", None)
        for state, facing in actor.strips:
            prompt = prompts.actor_motion_prompt(package, actor, state, facing=facing)
            kinds[prompt] = ("motion", state)
    kinds[prompts.fire_strip_prompt(package, package.fire.columns, package.fire.rows)] = (
        "fire",
        None,
    )
    kinds[prompts.dust_prompt(package)] = ("dust", package.dust.kinds)
    for condition in package.weather:
        if condition.drops is not None:
            kinds[prompts.drops_sheet_prompt(package, condition.drops)] = ("drops", None)
        if condition.ground is not None:
            kinds[prompts.splash_sheet_prompt(package, condition.ground)] = (
                "splash",
                condition.ground.kinds,
            )
        if condition.strike is not None:
            kinds[prompts.strike_sheet_prompt(package, condition.strike)] = (
                "strike",
                STRIKE_CELL_KINDS,
            )
        if condition.cover is not None:
            kinds[prompts.cover_prompt(package, condition.cover)] = ("plate", 200)
        if condition.ice is not None:
            kinds[prompts.ice_prompt(package, condition.ice)] = ("plate", 200)
    return kinds


def stand_ins_for(project: Path, scope: str = "minimal", **options: Any) -> EmberStandIns:
    planned = plan(project, scope)
    assert planned.ok, planned.problems
    return EmberStandIns(planned.planner.store, load_package(project / PACKAGE), **options)


def run(
    project: Path, stand_ins: EmberStandIns, scope: str = "minimal", name: str = "run"
) -> RunOutcome:
    planned = plan(project, scope)
    assert planned.ok, planned.problems
    stand_ins.store = planned.planner.store
    return asyncio.run(
        WorkflowRun(planned, run_dir=project / name, services=stand_ins.services()).run()
    )


def deliver(store: Store, outcome: RunOutcome, folder: Path) -> Path:
    for key, file in outcome.outputs["package"].items:
        target = folder / key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(store.file_path(file.digest), target)
    return folder


def failures(outcome: RunOutcome) -> dict[str, str]:
    return {
        step: str(getattr(outcome.results.get(step), "error", None) or "")
        for step in outcome.failed
    } or {"stopped": str(outcome.stopped)}
