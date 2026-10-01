"""Examples: frozen, digest-pinned exports of real runs, and the contract that reads them.

An example is the only result a page shows. It is written once into a local store, never
regenerated, and pinned by the sha256 of its two documents:

    out/examples/<owner>/<example_id>/
        example.json   workflow-example-v1: nodes, pictures, raw metrics, inputs and outputs
        figures.json   the figures ledger: every derived picture with the run file it came from
        media/         the derived pictures themselves
        entry.json     only for an example a game made: its title, promise, command, steps,
                       currency and the game's pins
        page.mdx       only for an example a game made: its prose, copied from the game

The owner is the workflow id, or the game id for an example made inside a game. A workflow
pins its examples in its own ``workflow.toml``; a game pins its own. The store is ignored by
Git, and nothing in it is published by being here.

An importer turns run folders into an example. It reads through a ``RecordingReader``, so
the example names the digest of every file it was made from, and writes pictures through
``Media``, so every derived picture lands in the ledger. The example holds values, never
wording: pages decide what to say about them.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import tomllib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

from PIL import Image, ImageChops
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from gnode import atomic_write_bytes

EXAMPLE_KIND: Literal["workflow-example-v1"] = "workflow-example-v1"
GAME_ENTRY_KIND: Literal["game-example-entry-v1"] = "game-example-entry-v1"
EXAMPLE_FILE = "example.json"
FIGURES_FILE = "figures.json"
ENTRY_FILE = "entry.json"
#: The prose of an example a game made, copied into the store beside it.
PAGE_FILE = "page.mdx"
MEDIA_DIR = "media"
#: The document that identifies a run folder, in the order an importer looks for it.
ANCHOR_DOCUMENTS = ("execution-plan.json", "graph.json", "execution.json", "manifest.json")
SHA256_PATTERN = r"^[0-9a-f]{64}$"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

type Origin = Literal["run", "derived"]
type Currency = Literal["current", "earlier_version"]


# ---------------------------------------------------------------- display names


@dataclass(frozen=True, slots=True)
class DisplayNames:
    """Model and provider display names from ``resources/model_names.toml``."""

    models: Mapping[str, str]
    providers: Mapping[str, str]

    def model(self, model: str | None) -> str | None:
        return self.models.get(model, model) if model else None

    def provider(self, provider: str | None) -> str | None:
        return self.providers.get(provider, provider) if provider else None

    def knows_model(self, name: str) -> bool:
        """True for a recorded identifier with a display name, or for a display name itself."""
        return name in self.models or name in set(self.models.values())


@cache
def display_names() -> DisplayNames:
    document = tomllib.loads(
        resources.files("stage_gen.resources").joinpath("model_names.toml").read_text("utf-8")
    )
    if document.get("schema_version") != 1:
        raise ValueError("model_names.toml must declare schema_version = 1")
    return DisplayNames(
        models={str(key): str(value) for key, value in document["models"].items()},
        providers={str(key): str(value) for key, value in document["providers"].items()},
    )


def model_name(model: str | None) -> str | None:
    return display_names().model(model)


def provider_name(provider: str | None) -> str | None:
    return display_names().provider(provider)


# ---------------------------------------------------------------- documents


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MadeBy(_Strict):
    kind: Literal["workflow", "game"]
    id: str = Field(min_length=1)


class SourceRun(_Strict):
    """One run an example was made from, bound by the digest of its anchor document."""

    path: str = Field(min_length=1)
    anchor: str = Field(min_length=1)
    anchor_sha256: str = Field(pattern=SHA256_PATTERN)


class ExampleModel(_Strict):
    name: str
    provider: str | None
    roles: list[str]
    nodes: int
    called_by: list[str]


class ExampleNode(_Strict):
    """One node as it ran. ``origin`` is ``derived`` for a node an importer composed from
    records outside the run's own graph, such as a crop the parent run made by hand."""

    id: str
    type_id: str
    kind: str
    description: str
    provider: str | None
    model: str | None
    retry_owner: str | None
    max_attempts: int | None
    depends_on: list[str]
    state: str
    attempts: int | None
    duration_ms: int | float | None
    cost_usd: float | None
    provider_operations: int | None
    cache: str | None
    not_needed: str | None
    verdict: dict[str, JsonValue] | None
    checks: list[dict[str, JsonValue]]
    prompt: str | None
    rationale: str | None
    open_issues: list[JsonValue]
    record_ref: str | None
    thumb: dict[str, JsonValue] | None
    pictures: list[dict[str, JsonValue]]
    origin: Origin


class TreeEntry(TypedDict):
    kind: Literal["dir", "file"]
    bytes: int
    files: NotRequired[int]
    entries: NotRequired[int]


class WorkflowExample(_Strict):
    """``workflow-example-v1``: one example, as values only.

    ``delivered_run`` is the run folder a consumer receives; ``source_runs`` are every run
    the example was made from. ``graph_kind`` is the persisted kind of the graph whose
    digest ``graph_sha256`` gives, or None when no source run persisted one.
    ``source_files`` maps each file the importer read to its digest; it is None for an
    example converted from a record made before importers recorded their reads.
    """

    schema_version: Literal[1] = 1
    kind: Literal["workflow-example-v1"] = EXAMPLE_KIND
    example_id: str = Field(min_length=1)
    made_by: MadeBy
    importer: str
    delivered_run: str
    source_runs: list[SourceRun] = Field(min_length=1)
    source_files: dict[str, str] | None
    status: str | None
    graph_kind: str | None
    graph_sha256: str | None
    inputs: dict[str, dict[str, JsonValue]]
    outputs: dict[str, dict[str, JsonValue]]
    metrics: dict[str, int | float]
    models: list[ExampleModel]
    tree: dict[str, TreeEntry]
    nodes: dict[str, ExampleNode]

    def run_type_ids(self) -> frozenset[str]:
        """The type ids of nodes that ran inside a source run's own graph."""
        return frozenset(node.type_id for node in self.nodes.values() if node.origin == "run")


class FigureSource(_Strict):
    path: str
    sha256: str = Field(pattern=SHA256_PATTERN)


class FigureEntry(_Strict):
    file: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    bytes: int
    size: list[int] | None = None
    sources: list[FigureSource]
    transform: str


class FiguresLedger(_Strict):
    """Every derived file of an example, with the run files and digests it came from."""

    run: str
    files: list[FigureEntry]

    def latest(self) -> dict[str, FigureEntry]:
        """The last entry for each file: a file written twice keeps its final bytes."""
        return {entry.file: entry for entry in self.files}


class GameExampleStep(_Strict):
    """A labelled group of the example's node ids, with a one-line note."""

    label: str = Field(min_length=1)
    note: str
    members: list[str] = Field(min_length=1)


class ExampleTool(_Strict):
    name: str = Field(min_length=1)
    role: str = Field(min_length=1)


class GameExampleEntry(_Strict):
    """``entry.json``: what a game says about an example it made, beside the example.

    The game writes it when it exports the example. ``game_title`` names the game for the
    line a page shows ("Made inside the ... example game"); ``labels`` title the node ids its
    ``steps`` group; ``currency`` is derived by the game from the node types and graph kinds
    it has today; the two pins are the game's own, so the store can be checked without it.
    """

    schema_version: Literal[1] = 1
    kind: Literal["game-example-entry-v1"] = GAME_ENTRY_KIND
    made_by: MadeBy
    game_title: str = Field(min_length=1)
    title: str = Field(min_length=1)
    promise: str = Field(min_length=1)
    order: int | None = Field(default=None, ge=1)
    related: list[str] = Field(default_factory=list)
    command: str = Field(min_length=1)
    footer: str | None = None
    tools: list[ExampleTool] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    steps: list[GameExampleStep] = Field(default_factory=list)
    currency: Currency
    example_sha256: str = Field(pattern=SHA256_PATTERN)
    figures_sha256: str = Field(pattern=SHA256_PATTERN)

    @property
    def pin(self) -> ExamplePin:
        return ExamplePin(self.example_sha256, self.figures_sha256)


def document_bytes(document: BaseModel) -> bytes:
    """The exact bytes a document is stored and pinned as."""
    payload = document.model_dump(mode="json", exclude_none=False)
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode()


def figures_bytes(ledger: FiguresLedger) -> bytes:
    payload = ledger.model_dump(mode="json", exclude_none=True)
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


# ---------------------------------------------------------------- currency and pins


def currency(
    example: WorkflowExample, type_ids: Iterable[str], graph_kinds: Iterable[str]
) -> Currency:
    """``current`` when every node that ran is a type of the workflow and the graph kind,
    if any, is one the workflow writes; otherwise the example was made with an earlier
    version and a page shows it only behind its production notes."""
    if not example.run_type_ids() <= frozenset(type_ids):
        return "earlier_version"
    if example.graph_kind is not None and example.graph_kind not in frozenset(graph_kinds):
        return "earlier_version"
    return "current"


@dataclass(frozen=True, slots=True)
class ExamplePin:
    example_sha256: str
    figures_sha256: str


def store_directory(store: Path, owner: str, example_id: str) -> Path:
    for segment in (owner, example_id):
        if not segment or segment in {".", ".."} or "/" in segment or "\\" in segment:
            raise ValueError(f"invalid example store segment: {segment!r}")
    return store / owner / example_id


def read_example(directory: Path) -> WorkflowExample:
    return WorkflowExample.model_validate_json((directory / EXAMPLE_FILE).read_bytes())


def read_figures(directory: Path) -> FiguresLedger:
    return FiguresLedger.model_validate_json((directory / FIGURES_FILE).read_bytes())


def read_entry(directory: Path) -> GameExampleEntry | None:
    path = directory / ENTRY_FILE
    return GameExampleEntry.model_validate_json(path.read_bytes()) if path.is_file() else None


def pin_of(directory: Path) -> ExamplePin:
    return ExamplePin(
        example_sha256=sha256(directory / EXAMPLE_FILE),
        figures_sha256=sha256(directory / FIGURES_FILE),
    )


def verify(directory: Path, pin: ExamplePin | None = None) -> list[str]:
    """Every way a stored example differs from its pins and its own ledger; empty when ok.

    The two documents must match their pins byte for byte and parse, and every file the
    ledger lists must exist under ``media/`` with its recorded digest; a media file the
    ledger does not list is refused too.
    """
    problems: list[str] = []
    for name in (EXAMPLE_FILE, FIGURES_FILE):
        if not (directory / name).is_file():
            problems.append(f"{name} is missing")
    if problems:
        return problems
    if pin is not None:
        actual = pin_of(directory)
        if actual.example_sha256 != pin.example_sha256:
            problems.append(f"{EXAMPLE_FILE} sha256 {actual.example_sha256} differs from its pin")
        if actual.figures_sha256 != pin.figures_sha256:
            problems.append(f"{FIGURES_FILE} sha256 {actual.figures_sha256} differs from its pin")
    try:
        read_example(directory)
        ledger = read_figures(directory)
    except ValueError as error:
        return [*problems, f"unreadable document: {error}"]
    listed = ledger.latest()
    for name, entry in listed.items():
        path = directory / name
        if not path.is_file():
            problems.append(f"{name} is listed but missing")
        elif sha256(path) != entry.sha256:
            problems.append(f"{name} differs from its ledger digest")
    media = directory / MEDIA_DIR
    if media.is_dir():
        for path in sorted(media.rglob("*")):
            name = path.relative_to(directory).as_posix()
            if path.is_file() and name not in listed:
                problems.append(f"{name} is not in the ledger")
    return problems


def verify_game_example(directory: Path) -> list[str]:
    """``verify`` for an example a game wrote, against the pins in its ``entry.json``.

    Without an entry the game has not exported it yet, and only its ledger is checked.
    """
    try:
        entry = read_entry(directory)
    except ValueError as error:
        return [f"unreadable {ENTRY_FILE}: {error}"]
    problems = verify(directory, None if entry is None else entry.pin)
    if entry is not None and not problems:
        document = read_example(directory)
        if document.example_id != directory.name or document.made_by != entry.made_by:
            problems.append(f"{EXAMPLE_FILE} names another example or maker than {ENTRY_FILE}")
    return problems


def write_example(
    directory: Path,
    example: WorkflowExample,
    ledger: FiguresLedger,
    *,
    entry: GameExampleEntry | None = None,
) -> ExamplePin:
    """Write an example's documents beside the media already in ``directory/media``."""
    directory.mkdir(parents=True, exist_ok=True)
    example_data, figures_data = document_bytes(example), figures_bytes(ledger)
    atomic_write_bytes(directory / EXAMPLE_FILE, example_data, mode=0o644)
    atomic_write_bytes(directory / FIGURES_FILE, figures_data, mode=0o644)
    if entry is not None:
        atomic_write_bytes(directory / ENTRY_FILE, document_bytes(entry), mode=0o644)
    return ExamplePin(sha256_bytes(example_data), sha256_bytes(figures_data))


# ---------------------------------------------------------------- reading run folders


class RecordingReader:
    """Reads run files for an importer and records the digest of each one it opens."""

    def __init__(self, base: Path) -> None:
        self.base = base.resolve()
        self._files: dict[str, str] = {}

    def _key(self, path: Path) -> str:
        resolved = path.resolve()
        return (
            resolved.relative_to(self.base).as_posix()
            if resolved.is_relative_to(self.base)
            else resolved.name
        )

    def path(self, path: Path) -> Path:
        """Record a file another library will open, such as an image or a video."""
        self._files[self._key(path)] = sha256(path)
        return path

    def bytes(self, path: Path) -> bytes:
        data = path.read_bytes()
        self._files[self._key(path)] = sha256_bytes(data)
        return data

    def json(self, path: Path) -> Any:
        return json.loads(self.bytes(path))

    @property
    def files(self) -> dict[str, str]:
        return dict(sorted(self._files.items()))


def anchor_of(run_dir: Path) -> str:
    for name in ANCHOR_DOCUMENTS:
        if (run_dir / name).is_file():
            return name
    raise ValueError(f"{run_dir.name} holds none of {', '.join(ANCHOR_DOCUMENTS)}")


def source_run(base: Path, run_dir: Path) -> SourceRun:
    anchor = anchor_of(run_dir)
    return SourceRun(
        path=relative_to_base(base, run_dir),
        anchor=anchor,
        anchor_sha256=sha256(run_dir / anchor),
    )


def relative_to_base(base: Path, path: Path) -> str:
    resolved, root = path.resolve(), base.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"{path.name} lies outside the directory examples are recorded from")
    return resolved.relative_to(root).as_posix()


def index(root: Path) -> dict[str, TreeEntry]:
    """An index of a run folder: every file and folder with its size, nothing else.

    Keys are run-relative POSIX paths; folders carry their total bytes, every file below
    them, and their immediate entries. Symlinks are skipped, so nothing outside the run is
    ever counted.
    """
    root = root.resolve()
    tree: dict[str, TreeEntry] = {"": {"kind": "dir", "bytes": 0, "files": 0, "entries": 0}}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            continue
        rel = path.relative_to(root).as_posix()
        parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
        if path.is_dir():
            tree[rel] = {"kind": "dir", "bytes": 0, "files": 0, "entries": 0}
        elif path.is_file():
            size = path.stat().st_size
            tree[rel] = {"kind": "file", "bytes": size}
            ancestor = rel
            while ancestor:
                ancestor = ancestor.rsplit("/", 1)[0] if "/" in ancestor else ""
                folder = tree[ancestor]
                folder["bytes"] += size
                folder["files"] = folder.get("files", 0) + 1
        else:
            continue
        folder = tree[parent]
        folder["entries"] = folder.get("entries", 0) + 1
    return tree


NODE_DEFAULTS: dict[str, Any] = {
    "type_id": "",
    "kind": "Local",
    "description": "",
    "provider": None,
    "model": None,
    "retry_owner": None,
    "max_attempts": None,
    "depends_on": [],
    "state": "succeeded",
    "attempts": None,
    "duration_ms": None,
    "cost_usd": None,
    "provider_operations": None,
    "cache": None,
    "not_needed": None,
    "verdict": None,
    "checks": [],
    "prompt": None,
    "rationale": None,
    "open_issues": [],
    "record_ref": None,
    "thumb": None,
    "pictures": [],
    "origin": "run",
}


def node(node_id: str, **fields: Any) -> dict[str, Any]:
    """One example node with every field present, so importers cannot drift apart."""
    unknown = set(fields) - set(NODE_DEFAULTS)
    if unknown:
        raise ValueError(f"unknown node fields {sorted(unknown)}")
    return {"id": node_id, **NODE_DEFAULTS, **fields}


def models_of(
    nodes: Mapping[str, Mapping[str, Any]], role: Callable[[Mapping[str, Any]], str] | None = None
) -> list[dict[str, Any]]:
    """The models a set of nodes called, with their roles and how many nodes each served."""
    models: dict[str, dict[str, Any]] = {}
    for item in nodes.values():
        if item["model"]:
            entry = models.setdefault(
                item["model"],
                {
                    "name": item["model"],
                    "provider": item["provider"],
                    "roles": set(),
                    "nodes": 0,
                    "called_by": [],
                },
            )
            entry["roles"].add(role(item) if role else item["kind"])
            entry["nodes"] += 1
    return [{**entry, "roles": sorted(entry["roles"])} for entry in models.values()]


def outputs_of(record: Mapping[str, Any]) -> dict[str, str]:
    return {
        artifact["artifact_ref"]: artifact["sha256"]
        for artifact in record["artifacts"]
        if not artifact["artifact_ref"].endswith(".meta.json")
    }


class Lineage:
    """Where each delivered node actually ran, across a series of runs of one package.

    A package's current run usually restores most nodes from the cache, so the time, tries
    and prompt of a node live in whichever earlier run executed it. A node is taken from the
    newest listed run where it ran (a cache miss that succeeded) and produced exactly the
    bytes the delivering run holds; anything else is refused rather than guessed.
    """

    def __init__(self, reader: RecordingReader, runs: Sequence[Path]) -> None:
        self.reader = reader
        self.summaries = [
            (
                run_dir,
                {
                    item["node_id"]: item
                    for item in reader.json(run_dir / "execution-summary.json")["nodes"]
                },
            )
            for run_dir in runs
        ]
        self.last, self.delivered = self.summaries[-1]

    def where_it_ran(self, node_id: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
        """(run folder, summary entry, plan entry) of the run that produced the bytes."""
        want = outputs_of(self.delivered[node_id])
        for run_dir, nodes in reversed(self.summaries):
            item = nodes.get(node_id)
            if (
                item
                and item["cache"] == "miss"
                and item["status"] == "succeeded"
                and outputs_of(item) == want
            ):
                planned = next(
                    entry
                    for entry in self.reader.json(run_dir / "execution-plan.json")["nodes"]
                    if entry["node_id"] == node_id
                )
                return run_dir, item, planned
        raise ValueError(
            f"{node_id}: none of the listed runs produced the bytes {self.last.name} delivered"
        )


LINEAGE_KINDS = {"image_generation": "Image model", "structured_generation": "Language model"}


def record_node(
    node_id: str,
    run_dir: Path,
    summary: Mapping[str, Any],
    planned: Mapping[str, Any],
    kinds: Mapping[str, str] = LINEAGE_KINDS,
    **fields: Any,
) -> dict[str, Any]:
    """An example node from the run where it ran: its summary entry and its plan entry."""
    names = display_names()
    return node(
        node_id,
        type_id=planned["type_id"],
        kind=kinds.get(planned["operation"], "Local"),
        description=planned.get("description", ""),
        provider=names.provider(planned.get("provider")),
        model=names.model(planned.get("model")),
        retry_owner=planned.get("retry_owner"),
        max_attempts=planned.get("max_attempts"),
        state=summary["status"],
        attempts=summary.get("attempts"),
        duration_ms=summary.get("duration_ms"),
        cost_usd=summary.get("known_cost_usd") or None,
        provider_operations=summary.get("provider_operations"),
        cache=summary["cache"],
        record_ref=f"{run_dir.name}/execution-summary.json",
        **fields,
    )


# ---------------------------------------------------------------- derived pictures


def corner_colour(im: Image.Image) -> tuple[int, int, int] | None:
    """Mean corner colour when the four corners agree (a plain ground), else None."""
    rgb = im.convert("RGB")
    w, h = rgb.size
    corners: list[tuple[int, int, int]] = [
        _rgb(rgb.getpixel(c)) for c in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))
    ]
    mean = (
        round(sum(c[0] for c in corners) / 4),
        round(sum(c[1] for c in corners) / 4),
        round(sum(c[2] for c in corners) / 4),
    )
    if any(abs(c[i] - mean[i]) > 10 for c in corners for i in range(3)):
        return None
    return mean


def _rgb(pixel: object) -> tuple[int, int, int]:
    if not isinstance(pixel, tuple) or len(pixel) < 3:
        raise ValueError("expected an RGB pixel")
    return int(pixel[0]), int(pixel[1]), int(pixel[2])


def hex_colour(rgb: tuple[int, int, int] | None) -> str | None:
    return None if rgb is None else f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def has_alpha(im: Image.Image) -> bool:
    if im.mode != "RGBA":
        return False
    extrema: Sequence[object] = im.getextrema()
    alpha = extrema[3]
    return isinstance(alpha, tuple) and float(alpha[0]) < 255


def video_frames(
    path: Path, times: Sequence[float] | None = None, alpha: bool = False
) -> list[Image.Image]:
    """Decode frames with FFmpeg: every frame, or one frame at each given time in seconds."""
    fmt, mode = ("rgba", "RGBA") if alpha else ("rgb24", "RGB")

    def decode(before: list[str], after: list[str]) -> list[Image.Image]:
        raw = subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                *before,
                "-i",
                str(path),
                *after,
                "-f",
                "image2pipe",
                "-vcodec",
                "png",
                "-pix_fmt",
                fmt,
                "-",
            ],
            capture_output=True,
            check=True,
        ).stdout
        starts: list[int] = []
        at = raw.find(PNG_SIGNATURE)
        while at >= 0:
            starts.append(at)
            at = raw.find(PNG_SIGNATURE, at + 1)
        # With no frame at all, ends still holds one entry; zip must then yield nothing.
        ends = [*starts[1:], len(raw)]
        return [
            Image.open(io.BytesIO(raw[s:e])).convert(mode)
            for s, e in zip(starts, ends, strict=False)
        ]

    if times is None:
        return decode([], [])
    return [decode(["-ss", f"{t:.3f}"], ["-frames:v", "1"])[0] for t in times]


type Box = tuple[int, int, int, int]


class Media:
    """Derived pictures for an example, each bound to the run file it came from.

    Every derived file lands in one ledger entry: output path, digest, size, source paths
    with their digests, and the transform in words. The ledger is the basis for a later
    publication review.
    """

    def __init__(
        self,
        out: Path,
        run_root: Path,
        prefix: str = MEDIA_DIR,
        reader: RecordingReader | None = None,
    ) -> None:
        self.out = out
        self.run_root = run_root
        self.prefix = prefix
        self.reader = reader
        self.ledger: list[dict[str, Any]] = []
        out.mkdir(parents=True, exist_ok=True)

    def _source(self, path: Path) -> dict[str, str]:
        if self.reader is not None:
            self.reader.path(path)
        return {"path": self._source_ref(path), "sha256": sha256(path)}

    @staticmethod
    def open_flat(path: Path, ground: tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
        with Image.open(path) as im:
            im.load()
            if im.mode in ("RGBA", "LA", "P"):
                rgba = im.convert("RGBA")
                flat = Image.new("RGBA", rgba.size, (*ground, 255))
                flat.alpha_composite(rgba)
                return flat.convert("RGB")
            return im.convert("RGB")

    @staticmethod
    def subject_box(im: Image.Image, pad: float = 0.06) -> Box | None:
        """Box around pixels unlike a plain ground, with a margin; None without a ground."""
        ground = corner_colour(im)
        if ground is None:
            return None
        diff = ImageChops.difference(im.convert("RGB"), Image.new("RGB", im.size, ground))
        box = diff.convert("L").point(lambda v: 255 if v > 24 else 0).getbbox()
        if box is None:
            return None
        m = round(max(box[2] - box[0], box[3] - box[1]) * pad)
        w, h = im.size
        return (max(0, box[0] - m), max(0, box[1] - m), min(w, box[2] + m), min(h, box[3] + m))

    @staticmethod
    def pad_to(im: Image.Image, aspect: float) -> Image.Image:
        """Extend the canvas with its own ground to a width/height ratio; subject untouched."""
        fill = corner_colour(im) or (255, 255, 255)
        w, h = im.size
        size = (round(h * aspect), h) if w / h < aspect else (w, round(w / aspect))
        canvas = Image.new("RGB", size, fill)
        canvas.paste(im, ((size[0] - w) // 2, (size[1] - h) // 2))
        return canvas

    @staticmethod
    def fit(frames: list[Image.Image], box: Box | None, max_height: int) -> list[Image.Image]:
        if box:
            frames = [f.crop(box) for f in frames]
        if frames[0].height > max_height:
            size = (round(frames[0].width * max_height / frames[0].height), max_height)
            frames = [f.resize(size, Image.Resampling.LANCZOS) for f in frames]
        return frames

    def _record(
        self, name: str, sources: Sequence[Path], transform: str, alpha: bool = False
    ) -> dict[str, Any]:
        target = self.out / name
        with Image.open(target) as im:
            width, height = im.size
            ground = None if alpha else corner_colour(im.convert("RGB"))
        self.ledger.append(
            {
                "file": f"{self.prefix}/{name}",
                "sha256": sha256(target),
                "bytes": target.stat().st_size,
                "size": [width, height],
                "sources": [self._source(p) for p in sources],
                "transform": transform,
            }
        )
        return {
            "src": f"{self.prefix}/{name}",
            "width": width,
            "height": height,
            "bg": "transparent" if alpha else (hex_colour(ground) or "#ffffff"),
            "alpha": alpha,
        }

    def _source_ref(self, path: Path) -> str:
        resolved = path.resolve()
        return (
            str(resolved.relative_to(self.run_root))
            if resolved.is_relative_to(self.run_root)
            else resolved.name
        )

    def _save(
        self, frames: list[Image.Image], name: str, durations: list[int] | int, quality: int
    ) -> None:
        if len(frames) == 1:
            frames[0].save(self.out / name, "WEBP", quality=quality, method=6)
        else:
            frames[0].save(
                self.out / name,
                "WEBP",
                save_all=True,
                append_images=frames[1:],
                duration=durations,
                loop=0,
                quality=quality,
                method=4,
            )

    def still(self, name: str, source: Path, max_height: int, crop: bool = False) -> dict[str, Any]:
        im = self.open_flat(source)
        if crop and (box := self.subject_box(im)):
            im = im.crop(box)
        self._save(self.fit([im], None, max_height), name, 0, 84)
        steps = ["cropped to subject" if crop else "", f"at most {max_height} px high", "WebP q84"]
        return self._record(name, [source], ", ".join(s for s in steps if s))

    def still_alpha(self, name: str, source: Path, max_height: int = 480) -> dict[str, Any]:
        """Like still(), but keeps transparency instead of flattening it."""
        with Image.open(source) as im:
            return self.image(name, im.convert("RGBA"), [source], "transparency kept", max_height)

    def image(
        self,
        name: str,
        im: Image.Image,
        sources: Sequence[Path],
        transform: str,
        max_height: int = 480,
        box: Box | None = None,
    ) -> dict[str, Any]:
        """A picture derived in memory, such as a decoded video frame or an annotated source."""
        alpha = has_alpha(im)
        self._save(self.fit([im if alpha else im.convert("RGB")], box, max_height), name, 0, 84)
        return self._record(
            name, sources, f"{transform}, at most {max_height} px high, WebP q84", alpha
        )

    def png(
        self, name: str, im: Image.Image, sources: Sequence[Path], transform: str
    ) -> dict[str, Any]:
        """An exact, lossless picture, for pixels a page lays out by measurement."""
        im.save(self.out / name, "PNG", optimize=True)
        return self._record(name, sources, f"{transform}, lossless PNG", has_alpha(im))

    def sequence(
        self,
        name: str,
        frames: list[Image.Image],
        durations: list[int] | int,
        sources: Sequence[Path],
        transform: str,
        max_height: int = 480,
        box: Box | None = None,
        quality: int = 78,
    ) -> dict[str, Any]:
        """An animated WebP from frames in memory; transparency is kept when they carry it."""
        alpha = has_alpha(frames[0])
        frames = self.fit([f if alpha else f.convert("RGB") for f in frames], box, max_height)
        self._save(frames, name, durations, quality)
        return self._record(
            name,
            sources,
            f"{transform}, {len(frames)} frames, at most {max_height} px high, "
            f"animated WebP q{quality}",
            alpha,
        )

    def cycle(
        self,
        name: str,
        sources: Sequence[Path],
        height: int,
        ms: int,
        aspect: float | None = None,
    ) -> dict[str, Any]:
        frames = [self.open_flat(p) for p in sources]
        boxes = [self.subject_box(f) for f in frames]
        known = [box for box in boxes if box is not None]
        if boxes and len(known) == len(boxes):
            union = (
                min(b[0] for b in known),
                min(b[1] for b in known),
                max(b[2] for b in known),
                max(b[3] for b in known),
            )
            frames = [f.crop(union) for f in frames]
        if aspect:
            frames = [self.pad_to(f, aspect) for f in frames]
        width = round(frames[0].width * height / frames[0].height)
        self._save(
            [f.resize((width, height), Image.Resampling.LANCZOS) for f in frames], name, ms, 84
        )
        return self._record(
            name,
            sources,
            f"{len(frames)} frames at {ms} ms, cropped to the subject of all frames, "
            f"{'padded, ' if aspect else ''}{height} px, animated WebP q84",
        )

    def copy(self, name: str, source: Path, note: str) -> dict[str, Any]:
        shutil.copyfile(source, self.out / name)
        self.ledger.append(
            {
                "file": f"{self.prefix}/{name}",
                "sha256": sha256(source),
                "bytes": source.stat().st_size,
                "sources": [self._source(source)],
                "transform": f"byte copy; {note}",
            }
        )
        return {"src": f"{self.prefix}/{name}", "bytes": source.stat().st_size}

    def figures(self, run: str) -> FiguresLedger:
        return FiguresLedger.model_validate({"run": run, "files": self.ledger})


# ---------------------------------------------------------------- importers


@dataclass(slots=True)
class ImportRequest:
    """What an importer is asked to make: one example from ``runs``, oldest first.

    Paths inside the example are recorded relative to ``base``, and derived pictures are
    written under ``out/media``. ``options`` are the importer's own settings, such as the
    node whose output the example delivers. The request's reader and media record every
    file the importer opens.
    """

    example_id: str
    made_by: MadeBy
    base: Path
    runs: tuple[Path, ...]
    out: Path
    options: Mapping[str, str] = field(default_factory=dict)
    reader: RecordingReader = field(init=False)
    media: Media = field(init=False)

    def __post_init__(self) -> None:
        if not self.runs:
            raise ValueError("an example is made from at least one run")
        self.reader = RecordingReader(self.base)
        self.media = Media(self.out / MEDIA_DIR, self.base.resolve(), reader=self.reader)

    def option(self, name: str, default: str | None = None) -> str:
        value = self.options.get(name, default)
        if value is None:
            raise ValueError(f"this importer needs the option {name}")
        return value

    def flag(self, name: str) -> bool:
        return self.options.get(name, "false").lower() in {"1", "true", "yes"}

    def figures(self, example: WorkflowExample) -> FiguresLedger:
        return self.media.figures(example.delivered_run)


type ExampleImporter = Callable[[ImportRequest], WorkflowExample]

PIPELINE_RUN_KINDS = {
    "video_generation": "Video model",
    "image_generation": "Image model",
    "structured_generation": "Vision model",
}


@dataclass(frozen=True, slots=True)
class PipelineRuns:
    """SDK runs merged into one chain, for a workflow to say what was delivered.

    ``chosen`` maps each node id to the run where it executed and its view entry; ``order``
    is the order nodes first appear in. ``last`` is the run the consumer receives.
    """

    request: ImportRequest
    run_dirs: tuple[Path, ...]
    chosen: Mapping[str, tuple[Path, Mapping[str, Any]]]
    order: tuple[str, ...]

    @property
    def last(self) -> Path:
        return self.run_dirs[-1]

    def artifacts(self, node_id: str) -> list[tuple[Path, dict[str, Any]]]:
        run_dir, item = self.chosen[node_id]
        return pipeline_artifacts(run_dir, item)

    def declared_inputs(self) -> dict[str, str]:
        """The first run's input files, base-relative, with the digests it bound."""
        inputs = self.request.reader.json(self.run_dirs[0] / "pipeline.json")["inputs"]
        return {str(path): str(digest) for path, digest in inputs.items()}


@dataclass(frozen=True, slots=True)
class Delivered:
    """What a workflow's runs delivered: its named inputs and outputs, and the measures
    of what it made (frames, layers) in the order a page lists them."""

    inputs: dict[str, dict[str, Any]]
    outputs: dict[str, dict[str, Any]]
    metrics: dict[str, int | float]


def pipeline_artifacts(run_dir: Path, item: Mapping[str, Any]) -> list[tuple[Path, dict[str, Any]]]:
    return [
        (run_dir / a["artifact_ref"], a)
        for a in item["artifacts"]
        if a["present"] and not a["artifact_ref"].endswith(".meta.json")
    ]


def import_pipeline_run(
    request: ImportRequest,
    *,
    output_node: str,
    deliver: Callable[[PipelineRuns], Delivered],
) -> WorkflowExample:
    """An example from runs that persist an SDK execution view (``execution-view.json``).

    A workflow may span several runs, as movie sprite does: generate a take live, then
    finish the chosen take locally. Runs are merged by node id, preferring the run where the
    node actually executed. A later run's entry node is linked to a node of an earlier run
    only when they share an artifact digest; runs that do not connect are refused. The last
    run is the folder the consumer receives, and ``deliver`` names what it holds.

    Every node shows its PNG artifacts, frames of an MP4 named ``raw`` or ``source``, and,
    on ``output_node``, its Matroska loop. The ``ledger`` option names a base-relative
    budget ledger whose validated attempts price the provider calls.
    """
    reader, media, names = request.reader, request.media, display_names()
    run_dirs = tuple(run.resolve() for run in request.runs)
    views = [(d, reader.json(d / "execution-view.json")) for d in run_dirs]

    chosen: dict[str, tuple[Path, dict[str, Any]]] = {}
    order: list[str] = []
    for run_dir, view in views:
        for item in view["nodes"]:
            if item["state"] != "succeeded":
                continue
            previous = chosen.get(item["node_id"])
            if previous is None or (item["cache"] == "miss" and previous[1]["cache"] != "miss"):
                chosen[item["node_id"]] = (run_dir, item)
            if item["node_id"] not in order:
                order.append(item["node_id"])
    if output_node not in chosen:
        raise ValueError(f"no run delivered the output node {output_node}")

    # Link each later run's entry nodes to the earlier node whose output they consumed.
    produced: dict[str, str] = {}
    depends: dict[str, list[str]] = {}
    for nid in order:
        run_dir, item = chosen[nid]
        deps = [d for d in item["depends_on"] if d in chosen]
        earlier = {sha: p for sha, p in produced.items() if chosen[p][0] != run_dir}
        if not deps and earlier:
            linked = sorted(
                {
                    earlier[a["sha256"]]
                    for _, a in pipeline_artifacts(run_dir, item)
                    if a["sha256"] in earlier
                }
            )
            if not linked:
                raise ValueError(
                    f"{nid} in {run_dir.name} consumes nothing an earlier run produced"
                )
            deps = linked
        depends[nid] = deps
        for _, a in pipeline_artifacts(run_dir, item):
            produced.setdefault(a["sha256"], nid)

    pictured: set[str] = set()
    nodes: dict[str, dict[str, Any]] = {}
    request_ids: list[str | None] = []
    for nid in order:
        run_dir, item = chosen[nid]
        pictures: list[dict[str, Any]] = []
        checks: list[dict[str, Any]] = []
        prompt: str | None = None
        thumb: dict[str, Any] | None = None
        for path, a in pipeline_artifacts(run_dir, item):
            if a["sha256"] in pictured:
                continue
            pictured.add(a["sha256"])
            meta = path.with_name(path.name + ".meta.json")
            sidecar = reader.json(meta) if meta.is_file() else {}
            if sidecar.get("provider") not in (None, "local") and sidecar.get("prompt"):
                prompt = sidecar["prompt"]
                request_ids.append((sidecar.get("response") or {}).get("request_id"))
            media_type = a["media_type"] or ""
            if media_type == "image/png":
                with Image.open(reader.path(path)) as im:
                    alpha = im.mode in ("RGBA", "LA")
                pictures.append(
                    media.still_alpha(f"{nid}-{path.stem}.webp", path)
                    if alpha
                    else media.still(f"{nid}-{path.stem}.webp", path, 640)
                )
            elif media_type == "video/mp4" and path.stem in ("raw", "source"):
                times = [0.0, 2.0, 4.0, 6.0]
                for t, frame in zip(times, video_frames(reader.path(path), times), strict=True):
                    pictures.append(
                        media.image(
                            f"{nid}-{path.stem}-{int(t)}s.webp",
                            frame,
                            [path],
                            f"frame at {t:.0f} s",
                        )
                    )
            elif path.suffix == ".mkv" and nid == output_node:
                frames = video_frames(reader.path(path), alpha=True)
                fps = reader.json(run_dir / "body" / "manifest.json")["playback_fps"]
                thumb = media.sequence(
                    f"{nid}-loop-small.webp",
                    frames[::2],
                    round(2000 / fps),
                    [path],
                    "every other frame of the loop",
                    max_height=240,
                    quality=70,
                )
            elif path.name == "processing-report.json":
                report = reader.json(path)
                checks = [
                    {"name": k, "passed": v} for k, v in report.items() if isinstance(v, bool)
                ]
        nodes[nid] = node(
            nid,
            type_id=item["type_id"],
            kind=PIPELINE_RUN_KINDS.get(item["operation"] or "", "Local"),
            description=item.get("description", ""),
            provider=names.provider(item.get("provider")),
            model=names.model(item.get("model")),
            retry_owner=item.get("retry_owner"),
            max_attempts=item.get("max_attempts"),
            depends_on=depends[nid],
            state=item["state"],
            attempts=item.get("attempts"),
            duration_ms=item.get("duration_ms"),
            cost_usd=item.get("known_cost_usd") or None,
            provider_operations=item.get("provider_operations"),
            cache=item.get("cache"),
            checks=checks,
            prompt=prompt,
            record_ref=f"{run_dir.name}/execution-view.json",
            thumb=thumb or (pictures[0] if pictures else None),
            pictures=pictures,
        )

    delivered = deliver(PipelineRuns(request, run_dirs, chosen, tuple(order)))
    ran = [chosen[nid][1] for nid in order if chosen[nid][1]["cache"] == "miss"]
    metrics: dict[str, int | float] = {
        "wall_seconds": sum(item["duration_ms"] or 0 for item in ran) / 1000,
        "provider_operations": sum(item.get("provider_operations") or 0 for item in ran),
        **delivered.metrics,
    }
    if ledger := request.options.get("ledger"):
        attempts = reader.json(request.base / ledger).get("attempts", [])
        matched = [
            a
            for a in attempts
            if a.get("request_id") in request_ids and a.get("status") == "validated"
        ]
        if matched:
            metrics["estimated_cost_usd"] = sum(float(a["estimated_usd"]) for a in matched)

    last = run_dirs[-1]
    plan = reader.json(last / "execution-plan.json")
    return WorkflowExample.model_validate(
        {
            "example_id": request.example_id,
            "made_by": request.made_by,
            "importer": "pipeline_run",
            "delivered_run": relative_to_base(request.base, last),
            "source_runs": [source_run(request.base, d) for d in run_dirs],
            "source_files": reader.files,
            "status": "succeeded",
            "graph_kind": plan["kind"],
            "graph_sha256": views[-1][1]["graph_sha256"],
            "inputs": delivered.inputs,
            "outputs": delivered.outputs,
            "metrics": metrics,
            "models": models_of(nodes),
            "tree": index(last),
            "nodes": nodes,
        }
    )


__all__ = [
    "ANCHOR_DOCUMENTS",
    "ENTRY_FILE",
    "EXAMPLE_FILE",
    "EXAMPLE_KIND",
    "FIGURES_FILE",
    "GAME_ENTRY_KIND",
    "MEDIA_DIR",
    "PAGE_FILE",
    "Currency",
    "Delivered",
    "DisplayNames",
    "ExampleImporter",
    "ExampleModel",
    "ExampleNode",
    "ExamplePin",
    "ExampleTool",
    "FigureEntry",
    "FigureSource",
    "FiguresLedger",
    "GameExampleEntry",
    "GameExampleStep",
    "ImportRequest",
    "Lineage",
    "MadeBy",
    "Media",
    "PipelineRuns",
    "RecordingReader",
    "SourceRun",
    "TreeEntry",
    "WorkflowExample",
    "anchor_of",
    "currency",
    "display_names",
    "document_bytes",
    "figures_bytes",
    "has_alpha",
    "import_pipeline_run",
    "index",
    "model_name",
    "models_of",
    "node",
    "outputs_of",
    "pin_of",
    "pipeline_artifacts",
    "provider_name",
    "read_entry",
    "read_example",
    "read_figures",
    "record_node",
    "relative_to_base",
    "sha256",
    "sha256_bytes",
    "source_run",
    "store_directory",
    "verify",
    "verify_game_example",
    "video_frames",
    "write_example",
]
