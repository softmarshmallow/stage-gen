"""The examples Bellweather made, published through the product's public example contract.

Four of Bellweather's outputs are shown as examples made by this game: its parallax
backgrounds, its terrain tiles, its UI kit and its player's animation set. Each needs the
whole game package to make, so none is a product workflow. The game owns everything about
them: ``godot/games/bellweather/examples.toml`` declares each one (title, promise, run
command, steps over its node ids, the runs it was made from, and the pins of its frozen
export), ``examples/<id>/page.mdx`` holds its prose, and the importers in this package turn
the runs into ``workflow-example-v1`` documents with ``stage_gen.examples``.

``demo-games example export bellweather`` writes them into the local example store. The
dependency runs from the game to the product: the product lists whatever a game wrote into
the store and never names a game.
"""

from __future__ import annotations

import tempfile
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from bellweather_pipeline.execution_graph import ExecutionGraph
from bellweather_pipeline.package_types import platformer_type_index
from gnode import atomic_write_bytes
from stage_gen.examples import (
    ENTRY_FILE,
    EXAMPLE_FILE,
    PAGE_FILE,
    Currency,
    ExamplePin,
    ExampleTool,
    FiguresLedger,
    GameExampleEntry,
    GameExampleStep,
    ImportRequest,
    MadeBy,
    WorkflowExample,
    currency,
    document_bytes,
    read_example,
    read_figures,
    store_directory,
    verify,
)

from . import parallax_layers, sprite_set, terrain_atlas, ui_kit
from ._common import Imported, ImporterOptions

GAME_ID = "bellweather"
#: The game's folder; examples.toml and the pages are read from the checkout, not the wheel.
GAME_ROOT = Path(__file__).resolve().parents[4]
REPOSITORY_ROOT = GAME_ROOT.parents[2]
MANIFEST_FILE = "examples.toml"
PAGES_DIR = "examples"
EXAMPLE_ID_PATTERN = r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"

type ImporterName = Literal["parallax_layers", "terrain_atlas", "ui_kit", "sprite_set"]


@dataclass(frozen=True, slots=True)
class Importer:
    """One importer: the model of its run table and the function that makes the example."""

    options: type[ImporterOptions]
    build: Callable[[ImportRequest, Any], Imported]

    def run(self, request: ImportRequest, table: Mapping[str, Any]) -> Imported:
        return self.build(request, self.options.model_validate(table))


IMPORTERS: dict[str, Importer] = {
    "parallax_layers": Importer(parallax_layers.ParallaxOptions, parallax_layers.build),
    "terrain_atlas": Importer(terrain_atlas.TerrainOptions, terrain_atlas.build),
    "ui_kit": Importer(ui_kit.UiKitOptions, ui_kit.build),
    "sprite_set": Importer(sprite_set.SpriteSetOptions, sprite_set.build),
}


class _Declared(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExampleDeclaration(_Declared):
    """One ``[[examples]]`` entry: what the game says about an example it made.

    ``steps`` group the example's node ids for readers and ``labels`` title each of them;
    ``run`` is the importer's table: the runs, oldest first, and its own settings. The pins
    are the sha256 of the frozen ``example.json`` and ``figures.json``.
    """

    id: str = Field(pattern=EXAMPLE_ID_PATTERN)
    title: str = Field(min_length=1)
    promise: str = Field(min_length=1)
    status: Literal["draft", "approved"]
    order: int | None = Field(default=None, ge=1)
    related: list[str] = Field(default_factory=list)
    command: str = Field(min_length=1)
    footer: str | None = None
    importer: ImporterName
    example_sha256: str = Field(pattern=SHA256_PATTERN)
    figures_sha256: str = Field(pattern=SHA256_PATTERN)
    tools: list[ExampleTool] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    steps: list[GameExampleStep] = Field(min_length=1)
    run: dict[str, Any]

    @property
    def pin(self) -> ExamplePin:
        return ExamplePin(self.example_sha256, self.figures_sha256)

    def members(self) -> list[str]:
        return [member for step in self.steps for member in step.members]


class ExamplesManifest(_Declared):
    """``examples.toml`` (schema 1): the examples one game made."""

    schema_version: Literal[1]
    kind: Literal["game-examples-v1"]
    game: str = Field(min_length=1)
    title: str = Field(min_length=1)
    examples: list[ExampleDeclaration]


def read_manifest(path: Path | None = None) -> ExamplesManifest:
    path = path or GAME_ROOT / MANIFEST_FILE
    if not path.is_file():
        raise ValueError(f"{MANIFEST_FILE} is missing; exporting examples needs a checkout")
    return ExamplesManifest.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))


def page_of(example_id: str, game_root: Path = GAME_ROOT) -> Path:
    return game_root / PAGES_DIR / example_id / PAGE_FILE


def graph_kinds() -> frozenset[str]:
    """Every graph kind Bellweather's execution document still reads."""
    return frozenset(get_args(ExecutionGraph.model_fields["kind"].annotation))


def currency_of(example: WorkflowExample) -> Currency:
    """``current`` when every node ran as a type the game declares today, in a graph kind it
    still reads; otherwise the example was made with an earlier version."""
    return currency(example, platformer_type_index(), graph_kinds())


def problems_of(declaration: ExampleDeclaration, example: WorkflowExample) -> list[str]:
    """Where a declaration and its example disagree: each node sits in exactly one step and
    has a title, and the example is the one declared."""
    problems: list[str] = []
    members = declaration.members()
    if doubled := sorted({m for m in members if members.count(m) > 1}):
        problems.append(f"nodes placed in two steps: {', '.join(doubled)}")
    if unplaced := sorted(set(example.nodes) - set(members)):
        problems.append(f"nodes in no step: {', '.join(unplaced)}")
    if unknown := sorted(set(members) - set(example.nodes)):
        problems.append(f"steps place nodes the example does not have: {', '.join(unknown)}")
    if untitled := sorted(set(members) - set(declaration.labels)):
        problems.append(f"nodes without a title: {', '.join(untitled)}")
    if stray := sorted(set(declaration.labels) - set(members)):
        problems.append(f"titles for nodes in no step: {', '.join(stray)}")
    if example.example_id != declaration.id or example.made_by != MadeBy(kind="game", id=GAME_ID):
        problems.append("the stored document names another example or maker")
    if example.importer != declaration.importer:
        problems.append(f"made by the {example.importer} importer, not {declaration.importer}")
    return problems


def rederive(
    declaration: ExampleDeclaration, *, base: Path, out: Path
) -> tuple[WorkflowExample, FiguresLedger]:
    """Make the example again from its runs, with its media written under ``out/media``."""
    table = declaration.run
    request = ImportRequest(
        example_id=declaration.id,
        made_by=MadeBy(kind="game", id=GAME_ID),
        base=base,
        runs=tuple(base / run for run in table.get("runs", [])),
        out=out,
    )
    return IMPORTERS[declaration.importer].run(request, table)


def entry_of(
    manifest: ExamplesManifest, declaration: ExampleDeclaration, example: WorkflowExample
) -> GameExampleEntry:
    return GameExampleEntry(
        made_by=MadeBy(kind="game", id=manifest.game),
        game_title=manifest.title,
        title=declaration.title,
        promise=declaration.promise,
        order=declaration.order,
        related=declaration.related,
        command=declaration.command,
        footer=declaration.footer,
        tools=declaration.tools,
        labels=declaration.labels,
        steps=declaration.steps,
        currency=currency_of(example),
        example_sha256=declaration.example_sha256,
        figures_sha256=declaration.figures_sha256,
    )


@dataclass(frozen=True, slots=True)
class Exported:
    """One example written into the store: where, how it was checked, and its currency."""

    example_id: str
    directory: Path
    rederived: bool
    currency: Currency


def ledger_differences(made: FiguresLedger, pinned: FiguresLedger, limit: int = 5) -> list[str]:
    """Each derived file whose ledger entry differs between a re-derivation and the pins."""
    ours, theirs = {entry.file: entry for entry in made.files}, pinned.latest()
    differing = sorted(
        name for name in ours.keys() | theirs.keys() if ours.get(name) != theirs.get(name)
    )
    found = [f"ledger run {made.run} is not {pinned.run}"] if made.run != pinned.run else []
    found += [f"{name} differs from its pinned ledger entry" for name in differing[:limit]]
    if len(differing) > limit:
        found.append(f"and {len(differing) - limit} more derived files")
    return found


def export(
    manifest: ExamplesManifest,
    *,
    store: Path,
    base: Path = REPOSITORY_ROOT,
    game_root: Path = GAME_ROOT,
    from_frozen: bool = False,
) -> list[Exported]:
    """Write each declared example's ``page.mdx`` and ``entry.json`` beside its frozen export.

    The frozen ``example.json`` and ``figures.json`` must already be in the store and match
    their pins. By default each example is first made again from its runs, into a scratch
    folder, with today's importers: every derived file must match its pinned ledger entry and
    the document must match the pinned one (apart from ``source_files``, which an export
    converted from an older record does not carry). ``from_frozen`` skips that, for when a
    source run has moved on. Nothing is written unless every example passes.
    """
    if manifest.game != GAME_ID:
        raise ValueError(f"{MANIFEST_FILE} declares {manifest.game}, not {GAME_ID}")
    refusals: list[str] = []
    ready: list[tuple[ExampleDeclaration, Path, GameExampleEntry, bytes]] = []
    for declaration in manifest.examples:
        directory = store_directory(store, manifest.game, declaration.id)
        name = f"{manifest.game}/{declaration.id}"
        problems = (
            ["is not in the example store"]
            if not (directory / EXAMPLE_FILE).is_file()
            else verify(directory, declaration.pin)
        )
        if declaration.order is not None and declaration.status != "approved":
            problems.append("only an approved example has a landing order")
        page = page_of(declaration.id, game_root)
        if not page.is_file():
            problems.append(f"{page.relative_to(game_root).as_posix()} is missing")
        if problems:
            refusals += [f"{name}: {problem}" for problem in problems]
            continue
        stored = read_example(directory)
        problems = problems_of(declaration, stored)
        if not from_frozen:
            with tempfile.TemporaryDirectory(prefix=f"{manifest.game}-example-") as scratch:
                made, ledger = rederive(declaration, base=base, out=Path(scratch))
            problems += ledger_differences(ledger, read_figures(directory))
            if _without_reads(made) != _without_reads(stored):
                problems.append("the re-derived document differs from the pinned one")
        if problems:
            refusals += [f"{name}: {problem}" for problem in problems]
            continue
        entry = entry_of(manifest, declaration, stored)
        ready.append((declaration, directory, entry, page.read_bytes()))
    if refusals:
        raise ValueError("refusing to export:\n" + "\n".join(refusals))
    exported: list[Exported] = []
    for declaration, directory, entry, page_bytes in ready:
        atomic_write_bytes(directory / PAGE_FILE, page_bytes, mode=0o644)
        atomic_write_bytes(directory / ENTRY_FILE, document_bytes(entry), mode=0o644)
        exported.append(Exported(declaration.id, directory, not from_frozen, entry.currency))
    return exported


def _without_reads(example: WorkflowExample) -> dict[str, Any]:
    return example.model_dump(mode="json", exclude={"source_files"})


__all__ = [
    "GAME_ID",
    "GAME_ROOT",
    "IMPORTERS",
    "REPOSITORY_ROOT",
    "ExampleDeclaration",
    "ExamplesManifest",
    "Exported",
    "Importer",
    "currency_of",
    "entry_of",
    "export",
    "graph_kinds",
    "ledger_differences",
    "page_of",
    "problems_of",
    "read_manifest",
    "rederive",
]
