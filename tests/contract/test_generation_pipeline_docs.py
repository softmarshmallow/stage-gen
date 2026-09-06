from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

from stage_gen.config import StageGenConfig
from stage_gen.orchestration.game_package import ResolvedGamePackage, resolve_game_package
from stage_gen.recipes.sideview_platformer.execution_graph import ExecutionGraph
from stage_gen.recipes.sideview_platformer.package_graph import (
    build_package_execution_graph,
    package_graph_profile,
)

REPOSITORY_ROOT = Path(__file__).parents[2]
PIPELINE_DOCUMENT = REPOSITORY_ROOT / "docs/spec/game/generation-pipeline.md"


def _load_contract_writer() -> ModuleType:
    path = REPOSITORY_ROOT / "scripts/write_pipeline_graph_contract.py"
    spec = importlib.util.spec_from_file_location("stage_gen_pipeline_graph_contract", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_writer = _load_contract_writer()
CONTRACT_KIND = _writer.CONTRACT_KIND
FIXTURE_REF = _writer.FIXTURE_REF
RUNNER_PIPELINE_DOCUMENT = REPOSITORY_ROOT / "docs/spec/game/runner.md"
RUNNER_CONTRACT_KIND = _writer.RUNNER_CONTRACT_KIND
RUNNER_FIXTURE_REF = _writer.RUNNER_FIXTURE_REF
UNIVERSE_DOCUMENT = REPOSITORY_ROOT / "docs/spec/universe/generation-v1.md"
UNIVERSE_SEMANTIC_CONTRACT_KIND = _writer.UNIVERSE_SEMANTIC_CONTRACT_KIND
UNIVERSE_GALLERY_CONTRACT_KIND = _writer.UNIVERSE_GALLERY_CONTRACT_KIND
UNIVERSE_FIXTURE_REF = _writer.UNIVERSE_FIXTURE_REF
UNIVERSE_ADMITTED_REF = _writer.UNIVERSE_ADMITTED_REF
SURVIVAL_DOCUMENT = REPOSITORY_ROOT / "docs/spec/survival/generation-v1.md"
SURVIVAL_CONTRACT_KIND = _writer.OBLIQUE_SURVIVAL_CONTRACT_KIND
SURVIVAL_FIXTURE_REF = _writer.OBLIQUE_SURVIVAL_FIXTURE_REF
SURVIVAL_SCOPE = _writer.OBLIQUE_SURVIVAL_SCOPE
build_oblique_survival_graph_contract = _writer.build_oblique_survival_graph_contract
build_graph_contract = _writer.build_graph_contract
build_runner_graph_contract = _writer.build_runner_graph_contract
build_universe_semantic_graph_contract = _writer.build_universe_semantic_graph_contract
build_universe_gallery_graph_contract = _writer.build_universe_gallery_graph_contract
document_contract = _writer.document_contract
render = _writer.render


def test_generation_pipeline_document_tracks_the_executable_stage_graphs() -> None:
    # The snapshot is derived by scripts/write_pipeline_graph_contract.py rather than transcribed,
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


def test_universe_document_tracks_both_of_its_phase_graphs() -> None:
    # Universe is the one recipe that seals two graphs, because the size of its
    # gallery is a result of its semantic phase. Each phase carries its own
    # labelled block in the one document that describes both.
    assert document_contract(
        UNIVERSE_DOCUMENT, label="semantic"
    ) == build_universe_semantic_graph_contract(REPOSITORY_ROOT)
    assert document_contract(
        UNIVERSE_DOCUMENT, label="gallery"
    ) == build_universe_gallery_graph_contract(REPOSITORY_ROOT)


def test_universe_contracts_declare_their_identity_and_their_fixtures() -> None:
    semantic = document_contract(UNIVERSE_DOCUMENT, label="semantic")
    gallery = document_contract(UNIVERSE_DOCUMENT, label="gallery")
    assert semantic["kind"] == UNIVERSE_SEMANTIC_CONTRACT_KIND
    assert gallery["kind"] == UNIVERSE_GALLERY_CONTRACT_KIND
    assert semantic["phase"] == "semantic"
    assert gallery["phase"] == "gallery"
    assert semantic["fixture_ref"] == gallery["fixture_ref"] == UNIVERSE_FIXTURE_REF
    assert (REPOSITORY_ROOT / UNIVERSE_FIXTURE_REF).is_dir()
    # The gallery graph is planned offline against a committed admission, so the
    # fan-out has a checked identity without a paid semantic run behind it.
    assert gallery["admitted_ref"] == UNIVERSE_ADMITTED_REF
    assert (REPOSITORY_ROOT / UNIVERSE_ADMITTED_REF).is_file()
    assert gallery["entity_count"] > 0


def test_universe_contract_blocks_are_rendered_canonically() -> None:
    source = UNIVERSE_DOCUMENT.read_text(encoding="utf-8")
    for label in ("semantic", "gallery"):
        assert render(document_contract(UNIVERSE_DOCUMENT, label=label), label=label) in source


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
    """The seven count columns of the survival scope table, per row."""

    source = SURVIVAL_DOCUMENT.read_text(encoding="utf-8")
    body = source.split("## The graph", 1)[1]
    rows: list[tuple[str, list[int]]] = []
    for line in body.splitlines():
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = [cell.strip().strip("*` ") for cell in line.strip().strip("|").split("|")]
        if len(cells) != 8:
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

    from stage_gen.config import StageGenConfig
    from stage_gen.recipes.oblique_survival.survival_graph import build_graph
    from stage_gen.recipes.oblique_survival.survival_request import resolve_survival_source

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
            operations["local"],
        ], name


def test_survival_documents_are_discoverable_and_name_their_siblings() -> None:
    """Every survival contract is reachable from the index and from the recipe.

    This is also the Checked-by anchor for the three sibling contracts:
    spec/survival/generation-v1.md, spec/survival/ground.md,
    spec/survival/seasons.md and spec/survival/crafting.md each name this file,
    and the rule in scripts/check_docs.py requires the named test to contain the
    document's own path.
    """

    docs_index = (REPOSITORY_ROOT / "docs/README.md").read_text(encoding="utf-8")
    recipe = SURVIVAL_DOCUMENT.read_text(encoding="utf-8")
    for relative in (
        "spec/survival/generation-v1.md",
        "spec/survival/ground.md",
        "spec/survival/seasons.md",
        "spec/survival/crafting.md",
        "spec/survival/world.md",
    ):
        assert relative in docs_index, relative
        assert (REPOSITORY_ROOT / "docs" / relative).is_file()
    for sibling in ("ground.md", "seasons.md", "crafting.md", "world.md"):
        assert sibling in recipe
    # The host that plays the manifest is named by the recipe, not inferred.
    assert "godot-host.md" in recipe


def test_universe_document_is_discoverable_from_the_docs_index() -> None:
    docs_index = (REPOSITORY_ROOT / "docs/README.md").read_text(encoding="utf-8")
    taxonomy = (REPOSITORY_ROOT / "docs/spec/universe/taxonomy-v0.md").read_text(encoding="utf-8")
    assert "spec/universe/generation-v1.md" in docs_index
    assert "generation-v1.md" in taxonomy


def test_generation_pipeline_document_is_discoverable_from_game_authorities() -> None:
    required_link = "generation-pipeline.md"
    same_directory_authority = (
        REPOSITORY_ROOT / "docs/spec/game/authored-contract-schema.md"
    ).read_text(encoding="utf-8")
    docs_index = (REPOSITORY_ROOT / "docs/README.md").read_text(encoding="utf-8")
    game_contract = (REPOSITORY_ROOT / "docs/game-contract.md").read_text(encoding="utf-8")
    game_package = (REPOSITORY_ROOT / "docs/game-package.md").read_text(encoding="utf-8")

    assert required_link in same_directory_authority
    assert "spec/game/generation-pipeline.md" in docs_index
    assert "spec/game/generation-pipeline.md" in game_contract
    assert "spec/game/generation-pipeline.md" in game_package


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
    contract = build_graph_contract(REPOSITORY_ROOT)
    counts = contract["operation_counts"]
    _, total = _topology_table_rows()[-1]

    assert total == [
        counts["image_generation"],
        counts["structured_generation"],
        counts["music_generation"],
        counts["local"],
    ]


def test_topology_table_node_count_agrees_with_the_graph_contract() -> None:
    source = PIPELINE_DOCUMENT.read_text(encoding="utf-8")
    declared = re.search(r"\| \*\*Total\*\* \| \*\*(\d+) nodes\*\*", source)
    assert declared is not None

    assert int(declared.group(1)) == build_graph_contract(REPOSITORY_ROOT)["node_count"]


def test_declared_provider_operation_count_is_the_sum_of_the_provider_columns() -> None:
    source = PIPELINE_DOCUMENT.read_text(encoding="utf-8")
    declared = re.search(r"first-pass graph contains (\d+) provider operations", source)
    assert declared is not None
    counts = build_graph_contract(REPOSITORY_ROOT)["operation_counts"]

    assert int(declared.group(1)) == (
        counts["image_generation"] + counts["structured_generation"] + counts["music_generation"]
    )


def _closure(graph: ExecutionGraph, targets: tuple[str, ...]) -> set[str]:
    by_id = {node.node_id: node for node in graph.nodes}
    seen: set[str] = set()
    stack = list(targets)
    while stack:
        node_id = stack.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        stack.extend(by_id[node_id].depends_on)
    return seen


def _bellweather_graph() -> tuple[ResolvedGamePackage, ExecutionGraph]:
    package = resolve_game_package(REPOSITORY_ROOT / FIXTURE_REF)
    graph = build_package_execution_graph(package, profile=package_graph_profile(StageGenConfig()))
    return package, graph


def test_checkpoint_closure_paragraphs_state_the_real_closure_sizes() -> None:
    """The prose beside the gated table is checked too.

    Both paragraphs drifted silently while the machine block above them stayed exact - the World
    one by ten nodes, the Content one by six - because a checkpoint closure is a number nobody
    recomputes by hand. A reader sizing a paid run off either was under-budgeting.
    """

    from stage_gen.recipes.sideview_platformer.prepared_content import content_target_node_ids
    from stage_gen.recipes.sideview_platformer.prepared_world import world_target_node_ids

    _package, graph = _bellweather_graph()
    source = PIPELINE_DOCUMENT.read_text(encoding="utf-8")

    world = re.search(r"World checkpoint is the exact (\d+)-node closure", source)
    content = re.search(r"Content checkpoint is the exact (\d+)-node closure", source)
    assert world is not None and content is not None

    assert int(world.group(1)) == len(_closure(graph, world_target_node_ids(graph)))
    assert int(content.group(1)) == len(_closure(graph, content_target_node_ids(graph)))


def test_every_required_runtime_artifact_is_produced_by_a_checkpoint_closure() -> None:
    """The reason the closure sizes are worth gating at all.

    `runtime_artifact_paths` requires the projectile sprite whenever a package declares the
    catalog, but the content checkpoint did not name a projectile terminal, so integration failed
    on a missing artifact for any package that shipped one. The sizes above are a proxy; this is
    the property they protect.
    """

    from stage_gen.recipes.sideview_platformer.prepared_content import content_target_node_ids
    from stage_gen.recipes.sideview_platformer.prepared_manifest import runtime_artifact_paths
    from stage_gen.recipes.sideview_platformer.prepared_world import world_target_node_ids

    package, graph = _bellweather_graph()
    by_id = {node.node_id: node for node in graph.nodes}
    reachable = _closure(graph, world_target_node_ids(graph)) | _closure(
        graph, content_target_node_ids(graph)
    )
    produced = {ref for node_id in reachable for ref in by_id[node_id].declared_artifact_refs()}

    assert [path for path in runtime_artifact_paths(package) if path not in produced] == []


def test_projected_duration_and_cost_track_the_graph_projection() -> None:
    from gnode import project_schedule

    _, graph = _bellweather_graph()
    projection = project_schedule(graph)
    source = PIPELINE_DOCUMENT.read_text(encoding="utf-8")

    duration = re.search(r"projected terminal offset is \*\*([\d.]+) seconds", source)
    cost = re.search(r"USD ([\d.]+)[-\u2013]([\d.]+) budgetary allowance", source)
    assert duration is not None and cost is not None

    assert float(duration.group(1)) == projection.duration_ms / 1000
    assert float(cost.group(1)) == projection.estimated_cost_low_usd
    assert float(cost.group(2)) == projection.estimated_cost_high_usd
