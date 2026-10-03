"""The Grain's gnode project in a scratch folder, and stand-ins for every paid call it makes.

A package's references are project files, so each test copies the game's project
(``gnode.yaml``, the lock, ``pipeline/nodes`` and the builders) and puts the package it
builds inside it. Paid calls are answered offline with what the game's judges admit,
recognised by what they were asked for: an interface sheet by the template among its
pictures, a cut-out or a face by its transparent background, a chroma face by its canvas,
and a structured answer by the fields its schema declares.
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
from typing import Any

from PIL import Image

from demo_game_collection.resources import bundled_music_path
from demo_game_tools.kits.ui_art.nodes import UI_SHEET_ROLES, sheet_family
from gnode import CallRecord, HostServices, Plan, Route, RunOutcome, Store, WorkflowRun, plan_async
from tests.unit._ui_atlas_fixture import ui_sheet

REPOSITORY = Path(__file__).resolve().parents[3]
GAME = REPOSITORY / "godot/games/the_grain"
ROOM = "pipeline/workflow.py:room"
SCENE = "pipeline/workflow.py:scene"
STYLE_MODE = "cel_shaded_anime_2d"
_NARRATION_ID = re.compile(r'- id "([a-z0-9_-]+)"')


def grain_project(tmp_path: Path) -> Path:
    """The game's gnode project in a scratch folder, with no package in it yet."""

    project = tmp_path / "project"
    (project / "pipeline").mkdir(parents=True)
    settings = (GAME / "gnode.yaml").read_text(encoding="utf-8")
    settings = settings.replace("runs: ../../../out/runs", "runs: runs")
    settings = settings.replace("cache: ../../../out/gnode-cache", "cache: cache")
    (project / "gnode.yaml").write_text(settings, encoding="utf-8")
    shutil.copy(GAME / "gnode.lock", project / "gnode.lock")
    shutil.copytree(GAME / "pipeline/nodes", project / "pipeline/nodes")
    shutil.copy(GAME / "pipeline/workflow.py", project / "pipeline/workflow.py")
    return project


def plan(project: Path, builder: str, package: str) -> Plan:
    return asyncio.run(plan_async(builder, cwd=project, arguments={"package": package}))


def first_takes(planned: Plan) -> list[Any]:
    return [i for i in planned.instances if i.state != "absent" and set(i.takes) <= {1}]


def cover_digest(path: Path) -> str:
    """A package file's digest, as a request names a picture."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def calls_of(planned: Plan) -> Counter[str]:
    return Counter(route for instance in first_takes(planned) for route in instance.routes)


# ------------------------------------------------------------------------------- pictures


def png(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def _size(value: str) -> tuple[int, int]:
    width, height = (int(side) for side in value.split("x"))
    return width, height


def opaque(size: str) -> bytes:
    return png(Image.new("RGB", _size(size), (20, 30, 80)))


def cutout(size: str) -> bytes:
    """One isolated opaque subject on transparent ground."""

    width, height = _size(size)
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    image.paste((180, 140, 60, 255), (width // 4, height // 4, width - width // 4, height * 3 // 4))
    return png(image)


def keyed(size: str) -> bytes:
    """One subject on the chroma key, opaque everywhere."""

    width, height = _size(size)
    image = Image.new("RGB", (width, height), (255, 0, 255))
    image.paste((20, 30, 80), (width // 4, height // 6, width - width // 4, height * 5 // 6))
    return png(image)


# ------------------------------------------------------------------------------- stand-ins


class StandIns:
    """Every paid call a room or scene build makes, answered offline.

    ``refuse`` names kinds of answer (``cutout``, ``face``, ``backdrop``, ``plan``,
    ``narration``) and how many times each is answered wrongly before it is answered
    right, so a test can watch a judge send a take back.
    """

    def __init__(self, store: Store, *, refuse: Mapping[str, int] | None = None) -> None:
        self.store = store
        self.calls: Counter[str] = Counter()
        self.requests: dict[str, list[Mapping[str, Any]]] = {}
        self.refuse: Counter[str] = Counter(refuse or {})
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

    def _note(self, kind: str, request: Mapping[str, Any]) -> bool:
        """Count the call; true when this one is to be answered wrongly."""

        self.calls[kind] += 1
        self.requests.setdefault(kind, []).append(request)
        if self.refuse[kind] > 0:
            self.refuse[kind] -= 1
            return True
        return False

    def pictures(self, request: Mapping[str, Any]) -> list[str]:
        values = [request.get("image"), *(request.get("references") or [])]
        return [value.digest for value in values if value is not None]

    def _paint(self, request: Mapping[str, Any]) -> tuple[str, bytes]:
        size = str(request["size"])
        transparent = request.get("background") == "transparent"
        roles = {self._templates.get(digest) for digest in self.pictures(request)} - {None}
        if roles:
            return "ui", ui_sheet(str(roles.pop()))
        width, height = _size(size)
        if width == height:
            return "cutout", cutout(size)
        if width > height:
            return "backdrop", opaque(size)
        return "face", cutout(size) if transparent else keyed(size)

    async def _image(self, route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
        kind, data = self._paint(request)
        if self._note(kind, request):
            data = opaque("64x64")
        stored = self.store.put_bytes(data, kind="image/png", name="image")
        return CallRecord({"image": stored}, None, 0.01)

    async def _structured(self, route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
        schema = json.loads(self.store.file_path(request["schema"].digest).read_text())
        fields = set(schema.get("properties") or {})
        prompt = str(request["prompt"])
        answer: dict[str, Any]
        if "style_mode" in fields:
            self._note("style", request)
            answer = {
                "schema_version": 1,
                "kind": "image_style_selection_v1",
                "style_mode": STYLE_MODE,
            }
        elif "narrations" in fields:
            wrong = self._note("narration", request)
            ids = _NARRATION_ID.findall(prompt)[: -1 if wrong else None]
            answer = {
                "narrations": [{"id": found, "text": f"A line for {found}."} for found in ids]
            }
        elif "shared_locks" in fields:
            wrong = self._note("plan", request)
            locks = {
                key: f"Stand-in {key} lock."
                for key in ("identity", "wardrobe", "pose", "lighting", "style")
            }
            answer = {"shared_locks": {**locks, "pose": ""} if wrong else locks}
        elif "verdict" in fields:
            self._note("review", request)
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

    async def _music(self, route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
        self._note("track", request)
        audio = self.store.put_bytes(
            bundled_music_path().read_bytes(), kind="audio/mpeg", name="audio"
        )
        return CallRecord({"audio": audio}, None, 0.05)


def stand_ins_for(project: Path, builder: str, package: str, **options: Any) -> StandIns:
    return StandIns(plan(project, builder, package).planner.store, **options)


def run(
    project: Path, builder: str, package: str, stand_ins: StandIns, name: str = "run"
) -> RunOutcome:
    planned = plan(project, builder, package)
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
