from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from scripts.graph_contracts import document_contract, render

REPOSITORY_ROOT = Path(__file__).parents[2]
PIPELINE_DOCUMENT = REPOSITORY_ROOT / "godot/games/bellweather/docs/generation-pipeline.md"


def _load_contract_writer(relative: str, name: str) -> ModuleType:
    path = REPOSITORY_ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_writer = _load_contract_writer("godot/tools/write_game_graph_contract.py", "game_graph_contract")
CONTRACT_KIND = _writer.CONTRACT_KIND
FIXTURE_REF = _writer.FIXTURE_REF
RUNNER_PIPELINE_DOCUMENT = REPOSITORY_ROOT / "godot/games/iron_petal_unit/docs/runner.md"
RUNNER_CONTRACT_KIND = _writer.RUNNER_CONTRACT_KIND
RUNNER_FIXTURE_REF = _writer.RUNNER_FIXTURE_REF
SURVIVAL_DOCUMENT = REPOSITORY_ROOT / "godot/games/ember_hollow/docs/generation-v1.md"
SURVIVAL_CONTRACT_KIND = _writer.OBLIQUE_SURVIVAL_CONTRACT_KIND
SURVIVAL_FIXTURE_REF = _writer.OBLIQUE_SURVIVAL_FIXTURE_REF
SURVIVAL_SCOPE = _writer.OBLIQUE_SURVIVAL_SCOPE
build_oblique_survival_graph_contract = _writer.build_oblique_survival_graph_contract
build_graph_contract = _writer.build_graph_contract
build_runner_graph_contract = _writer.build_runner_graph_contract


def test_generation_pipeline_document_tracks_the_executable_stage_graphs() -> None:
    # The snapshot is derived by godot/tools/write_game_graph_contract.py,
    # so the writer and this check cannot drift. Regenerate with `--write` after any graph change.
    assert document_contract(PIPELINE_DOCUMENT) == build_graph_contract(REPOSITORY_ROOT)


def test_generation_pipeline_contract_declares_its_identity_and_fixture() -> None:
    contract = document_contract(PIPELINE_DOCUMENT)
    assert contract["kind"] == CONTRACT_KIND
    assert contract["fixture_ref"] == FIXTURE_REF
    assert (REPOSITORY_ROOT / contract["fixture_ref"]).is_dir()


def test_generation_pipeline_contract_block_is_rendered_canonically() -> None:
    # Guards the writer's own formatting: a hand-edited block that happens to parse equal must
    # still fail, or the document and the regenerated output would differ byte for byte.
    source = PIPELINE_DOCUMENT.read_text(encoding="utf-8")
    assert render(document_contract(PIPELINE_DOCUMENT)) in source


def test_runner_pipeline_document_tracks_the_executable_stage_graph() -> None:
    assert document_contract(RUNNER_PIPELINE_DOCUMENT) == build_runner_graph_contract(
        REPOSITORY_ROOT
    )


def test_runner_pipeline_contract_declares_its_identity_and_fixture() -> None:
    contract = document_contract(RUNNER_PIPELINE_DOCUMENT)
    assert contract["kind"] == RUNNER_CONTRACT_KIND
    assert contract["fixture_ref"] == RUNNER_FIXTURE_REF
    assert (REPOSITORY_ROOT / contract["fixture_ref"]).is_dir()


def test_runner_pipeline_contract_block_is_rendered_canonically() -> None:
    source = RUNNER_PIPELINE_DOCUMENT.read_text(encoding="utf-8")
    assert render(document_contract(RUNNER_PIPELINE_DOCUMENT)) in source


ROOM_DOCUMENT = REPOSITORY_ROOT / "godot/games/the_grain/docs/pointclick-room.md"
SCENE_DOCUMENT = REPOSITORY_ROOT / "godot/games/the_grain/docs/dialogue-scene-assets.md"
GRAIN_CONTRACTS = (
    pytest.param(
        ROOM_DOCUMENT,
        _writer.ROOM_CONTRACT_KIND,
        "godot/games/the_grain/inputs/rooms/window",
        _writer.build_room_graph_contract,
        id="room",
    ),
    pytest.param(
        SCENE_DOCUMENT,
        _writer.SCENE_CONTRACT_KIND,
        "godot/games/the_grain/inputs",
        _writer.build_scene_graph_contract,
        id="scene",
    ),
)


@pytest.mark.parametrize(("document", "kind", "fixture_ref", "build"), GRAIN_CONTRACTS)
def test_the_grain_documents_track_their_builders_plans(
    document: Path, kind: str, fixture_ref: str, build: Any
) -> None:
    contract = document_contract(document)
    assert contract == build(REPOSITORY_ROOT)
    assert contract["kind"] == kind
    assert contract["fixture_ref"] == fixture_ref
    assert (REPOSITORY_ROOT / fixture_ref).is_dir()
    assert render(contract) in document.read_text(encoding="utf-8")


def test_survival_document_tracks_the_executable_stage_graph() -> None:
    assert document_contract(SURVIVAL_DOCUMENT) == build_oblique_survival_graph_contract(
        REPOSITORY_ROOT
    )


def test_survival_contract_declares_its_identity_its_fixture_and_its_scope() -> None:
    contract = document_contract(SURVIVAL_DOCUMENT)
    assert contract["kind"] == SURVIVAL_CONTRACT_KIND
    assert contract["fixture_ref"] == SURVIVAL_FIXTURE_REF
    assert (REPOSITORY_ROOT / contract["fixture_ref"]).is_dir()
    # The scope is the one header field in this recipe's topology identity: it
    # selects a subset of the nodes. The snapshot is of the widest rung, so the
    # narrower ones are subsets of a checked graph.
    assert contract["scope"] == SURVIVAL_SCOPE == "full"


def test_survival_contract_block_is_rendered_canonically() -> None:
    source = SURVIVAL_DOCUMENT.read_text(encoding="utf-8")
    assert render(document_contract(SURVIVAL_DOCUMENT)) in source


def _survival_scope_table_rows() -> list[tuple[str, list[int]]]:
    """The eight count columns of the survival scope table, per row."""

    source = SURVIVAL_DOCUMENT.read_text(encoding="utf-8")
    body = source.split("## The graph", 1)[1]
    rows: list[tuple[str, list[int]]] = []
    for line in body.splitlines():
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = [cell.strip().strip("*` ") for cell in line.strip().strip("|").split("|")]
        if len(cells) != 9:
            continue
        counts = cells[1:]
        if not all(re.fullmatch(r"\d+", count) for count in counts):
            continue
        rows.append((cells[0], [int(count) for count in counts]))
    assert rows, "the survival scope table was not found or no longer parses"
    return rows


def test_survival_scope_table_agrees_with_the_graphs_the_code_builds() -> None:
    """The human table beside the machine block is derived from the same graphs.

    The block above it snapshots the widest scope only; the ladder is the claim a
    reader budgets a narrow run from, and nothing else recomputes it.
    """

    from ember_hollow_pipeline.survival_graph import build_graph
    from ember_hollow_pipeline.survival_request import resolve_survival_source
    from stage_gen.config import StageGenConfig

    package = resolve_survival_source(REPOSITORY_ROOT / SURVIVAL_FIXTURE_REF)
    config = StageGenConfig()
    rows = _survival_scope_table_rows()
    assert [name for name, _ in rows] == ["minimal", "props", "actors", "full"]
    for name, counts in rows:
        graph = build_graph(config, package, name)
        operations = graph.operation_counts()
        assert counts == [
            len(graph.nodes),
            operations["image_generation"],
            operations["structured_generation"],
            operations["tool_loop"],
            operations["music_generation"],
            operations["sound_effect_generation"],
            operations["video_generation"],
            operations["local"],
        ], name


def _linked_files(document: Path) -> set[Path]:
    """Resolve local Markdown links so ownership moves cannot weaken discoverability."""

    targets = re.findall(r"\]\(([^()\s]+)\)", document.read_text(encoding="utf-8"))
    return {
        (document.parent / target.partition("#")[0]).resolve()
        for target in targets
        if not target.startswith("#") and ":" not in target
    }


def test_survival_documents_are_discoverable_and_name_their_siblings() -> None:
    """Every survival contract is reachable from the index and from the recipe.

    This is also the Checked-by anchor for the three sibling contracts:
    godot/games/ember_hollow/docs/generation-v1.md, godot/games/ember_hollow/docs/ground.md,
    godot/games/ember_hollow/docs/seasons.md and
    godot/games/ember_hollow/docs/crafting.md each name this file,
    and the rule in scripts/check_docs.py requires the named test to contain the
    document's own path.
    """

    indexed_files = _linked_files(REPOSITORY_ROOT / "docs/README.md")
    recipe_links = _linked_files(SURVIVAL_DOCUMENT)
    for relative in (
        "godot/games/ember_hollow/docs/generation-v1.md",
        "godot/games/ember_hollow/docs/ground.md",
        "godot/games/ember_hollow/docs/seasons.md",
        "godot/games/ember_hollow/docs/crafting.md",
        "godot/games/ember_hollow/docs/world.md",
    ):
        target = REPOSITORY_ROOT / relative
        assert target in indexed_files, relative
        assert target.is_file()
    for sibling in ("ground.md", "seasons.md", "crafting.md", "world.md"):
        assert SURVIVAL_DOCUMENT.parent / sibling in recipe_links
    # The host that plays the manifest is linked by the recipe, not inferred.
    assert SURVIVAL_DOCUMENT.parent / "runtime.md" in recipe_links


def test_generation_pipeline_document_is_discoverable_from_game_authorities() -> None:
    for authority in (
        "docs/README.md",
        "godot/games/_shared/docs/formats/authored-contract-schema.md",
        "godot/games/_shared/docs/game-contract.md",
        "godot/games/_shared/docs/game-package.md",
    ):
        assert PIPELINE_DOCUMENT in _linked_files(REPOSITORY_ROOT / authority), authority


def _topology_table_rows() -> list[tuple[str, list[int]]]:
    """The four operation columns of the human topology table, per row."""

    source = PIPELINE_DOCUMENT.read_text(encoding="utf-8")
    body = source.split("## Bellweather operation topology", 1)[1]
    rows: list[tuple[str, list[int]]] = []
    for line in body.splitlines():
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 6 or cells[0] in {"Domain", "---"} or set(cells[1]) == {"-"}:
            continue
        counts = [cell.strip("* ") for cell in cells[2:]]
        if not all(re.fullmatch(r"\d+", count) for count in counts):
            continue
        rows.append((cells[0].strip("* "), [int(count) for count in counts]))
    assert rows, "the topology table was not found or no longer parses"
    return rows


def test_topology_table_total_row_equals_its_own_domain_rows() -> None:
    """The human table beside the machine block is checked too.

    It drifted three separate ways before this existed - a Maps row that counted only reviews, a
    Total row carrying the numbers from two changes ago, and a provider-operation sentence derived
    from both - because the contract block above it is gated and the prose below it was not. Every
    number here is now derived from the same graph the block is.
    """

    rows = _topology_table_rows()
    *domains, (label, total) = rows
    assert label.startswith("Total")
    for column in range(4):
        assert total[column] == sum(row[column] for _, row in domains)


def test_topology_table_agrees_with_the_executable_graph_contract() -> None:
    counts = document_contract(PIPELINE_DOCUMENT)["first_take_operation_counts"]
    _, total = _topology_table_rows()[-1]

    assert total == [
        counts["image.edit"],
        counts["structured.generate"],
        counts["music.generate"],
        counts["local"],
    ]


def test_topology_table_step_count_agrees_with_the_graph_contract() -> None:
    source = PIPELINE_DOCUMENT.read_text(encoding="utf-8")
    declared = re.search(r"\| \*\*Total\*\* \| \*\*(\d+) steps\*\*", source)
    assert declared is not None

    assert int(declared.group(1)) == document_contract(PIPELINE_DOCUMENT)["step_count"]


def test_declared_provider_call_count_is_the_sum_of_the_provider_columns() -> None:
    source = PIPELINE_DOCUMENT.read_text(encoding="utf-8")
    declared = re.search(r"default package's plan make (\d+) provider calls", source)
    assert declared is not None
    counts = document_contract(PIPELINE_DOCUMENT)["first_take_operation_counts"]

    assert int(declared.group(1)) == (
        counts["image.edit"] + counts["structured.generate"] + counts["music.generate"]
    )
