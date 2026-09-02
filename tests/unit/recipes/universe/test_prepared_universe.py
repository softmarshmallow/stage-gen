"""The node handlers that need no provider, run for real against the fixture package."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from gnode import (
    CacheDisposition,
    NodeArtifact,
    NodeExecutionContext,
    NodeExecutionError,
    NodeExecutionResult,
    Scheduler,
)
from stage_gen.canonical import content_sha256
from stage_gen.config import StageGenConfig
from stage_gen.recipes.universe.ontology import SIZE_BY_MODE
from stage_gen.recipes.universe.prepared_universe import (
    UniverseNodeHandler,
    make_image_proxy,
    render_entity_markdown,
)
from stage_gen.recipes.universe.universe_graph import (
    POSTER_PROXY_REF,
    SOURCE_LOCK_REF,
    UniverseGraph,
    build_universe_gallery_graph,
    build_universe_semantic_graph,
    node_safe,
    universe_graph_profile,
)
from stage_gen.recipes.universe.universe_request import (
    ResolvedUniverseSource,
    admitted_universe_from_document,
    read_universe_document,
    resolve_sample_ledger,
    resolve_universe_source,
)

FIXTURE = Path("library/games/lantern_ferry")


def _plan() -> tuple[ResolvedUniverseSource, UniverseGraph]:
    resolved = resolve_universe_source(read_universe_document(FIXTURE), root=FIXTURE)
    graph = build_universe_semantic_graph(
        resolved, profile=universe_graph_profile(StageGenConfig(), images=False)
    )
    return resolved, graph


async def test_source_lock_writes_the_ledger_and_the_observation_proxy(tmp_path: Path) -> None:
    """The one node that runs before any spend, and the only reader of the poster."""

    resolved, graph = _plan()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    handler = UniverseNodeHandler(graph, resolved, run_dir=run_dir, cache_dir=tmp_path / "cache")
    scheduler = Scheduler(graph.resources, node_timeout_seconds=60, secrets=())
    summary = await scheduler.run(
        graph, handler, invocation_id="t", target_node_ids=("source-lock",)
    )
    assert summary.ok

    lock = json.loads((run_dir / SOURCE_LOCK_REF).read_bytes())
    assert lock["universe_id"] == "lantern_ferry"
    assert lock["publication_authorized"] is False
    assert lock["poster"]["role"] == "visual_evidence_and_art_grammar_only"
    assert lock["synopsis_paragraph_ids"][0] == "synopsis_p01"
    assert lock["direction_requirement_ids"]

    # Package-relative, never repository-relative: a run must not record where
    # the operator happened to keep the package.
    assert not Path(lock["poster"]["source"]).is_absolute()
    assert "/Users/" not in json.dumps(lock)

    proxy = run_dir / POSTER_PROXY_REF
    with Image.open(proxy) as opened:
        assert max(opened.size) <= 1600
    assert proxy.with_suffix(".jpg.meta.json").is_file()


async def test_a_second_run_restores_the_source_lock_from_cache(tmp_path: Path) -> None:
    resolved, graph = _plan()
    cache_dir = tmp_path / "cache"
    digests: list[bytes] = []
    for name in ("first", "second"):
        run_dir = tmp_path / name
        run_dir.mkdir()
        handler = UniverseNodeHandler(graph, resolved, run_dir=run_dir, cache_dir=cache_dir)
        scheduler = Scheduler(graph.resources, node_timeout_seconds=60, secrets=())
        summary = await scheduler.run(
            graph, handler, invocation_id=name, target_node_ids=("source-lock",)
        )
        assert summary.ok
        digests.append((run_dir / SOURCE_LOCK_REF).read_bytes())
    assert digests[0] == digests[1]


def test_the_review_proxy_shrinks_the_long_edge_and_stays_a_png() -> None:
    original = Image.new("RGB", (2560, 1440), (30, 40, 60))
    buffer = BytesIO()
    original.save(buffer, format="PNG")
    proxy = make_image_proxy(buffer.getvalue(), long_edge=1280, fmt="PNG")
    with Image.open(BytesIO(proxy)) as opened:
        assert opened.format == "PNG"
        assert max(opened.size) == 1280


def test_the_markdown_record_reads_as_a_page_about_one_entity() -> None:
    record: dict[str, object] = {
        "status": "admitted",
        "entity": {
            "display_name": "The Lantern Ferry",
            "primary_class": "thing",
            "facets": ["place"],
            "entity_kind": "crossing vessel",
            "salience": "major",
            "summary": "a flat-bottomed boat worked after dark",
            "how_it_works_or_lives": "it reads the channel by lantern light",
            "present_tension": "the charter is disputed",
            "facts": [
                {"fact_id": "ferry_f1", "lineage": "explicit_source", "claim": "it crosses nightly"}
            ],
        },
        "relationships": [
            {
                "direction": "outgoing",
                "relationship_kind": "moors_at",
                "other_display_name": "East Landing",
                "summary": "it ties up on the north bank",
            }
        ],
        "identity_markers": [
            {"form": "a painted stripe", "meaning": "which crew", "materials": "pitch"}
        ],
        "concept": {
            "primary_purpose": "explain_mechanism",
            "audience_question": "how do they find the channel?",
            "signature_motif": {
                "action_verb": "reading",
                "dominant_prop": "masthead_lantern",
                "vantage": "eye_level",
            },
            "in_frame_contrast": "the amber column beside the broken green one",
            "scene_premise": "the crew reads the water from the masthead",
        },
        "review": {
            "verdict": "admit",
            "what_the_image_teaches": "that the channel is read, not remembered",
            "blocking_findings": [],
        },
    }
    page = render_entity_markdown(record)
    assert page.startswith("# The Lantern Ferry\n")
    assert "thing / place" in page
    assert "## Facts" in page
    assert "→ moors_at **East Landing**" in page
    assert "Signature: reading / masthead_lantern / eye_level" in page
    assert page.endswith("\n")


def test_a_rejected_record_says_why_on_the_page() -> None:
    record: dict[str, object] = {
        "status": "rejected",
        "entity": {
            "display_name": "East Landing",
            "primary_class": "place",
            "facets": [],
            "entity_kind": "landing",
            "salience": "supporting",
            "summary": "s",
            "how_it_works_or_lives": "h",
            "present_tension": "t",
            "facts": [{"fact_id": "f1", "lineage": "explicit_source", "claim": "c"}],
        },
        "relationships": [],
        "identity_markers": [],
        "concept": {
            "primary_purpose": "establish_place",
            "audience_question": "q",
            "signature_motif": {"action_verb": "a", "dominant_prop": "p", "vantage": "aerial"},
            "in_frame_contrast": "none",
            "scene_premise": "s",
        },
        "review": {
            "verdict": "reject",
            "what_the_image_teaches": "little",
            "blocking_findings": ["register_fidelity: blue sky in an overcast register"],
        },
    }
    page = render_entity_markdown(record)
    assert "image rejected" in page
    assert "Rejected: register_fidelity" in page


def _dependency_results(
    graph: UniverseGraph, node_id: str, run_dir: Path
) -> dict[str, NodeExecutionResult]:
    """What the scheduler would have handed this node about its dependencies.

    The cache binds a node's lineage to the digests its dependencies actually
    produced, so driving one handler in isolation still has to say what those
    were.
    """

    results: dict[str, NodeExecutionResult] = {}
    for dependency in graph.node(node_id).depends_on:
        artifacts: list[NodeArtifact] = []
        for port in graph.node(dependency).ports:
            path = run_dir / port.artifact_ref
            if not path.is_file():
                continue
            data = path.read_bytes()
            artifacts.append(
                NodeArtifact(
                    artifact_ref=port.artifact_ref, sha256=content_sha256(data), bytes=len(data)
                )
            )
        results[dependency] = NodeExecutionResult(
            cache=CacheDisposition.MISS,
            attempts=1,
            provider_operations=0,
            artifacts=tuple(artifacts),
        )
    return results


def _write_entity_artifacts(
    run_dir: Path, entity_id: str, *, verdict: str, size: tuple[int, int]
) -> None:
    """Materialize what an entity branch would have produced, without a provider."""

    from tests.unit.recipes.universe._universe_fixture import entity_direction

    direction = run_dir / f"production/direction/entities/{entity_id}.json"
    direction.parent.mkdir(parents=True, exist_ok=True)
    direction.write_bytes(
        entity_direction(entity_id, "a clear working day at eye level")
        .model_dump_json()
        .encode("utf-8")
    )
    image = run_dir / f"package/entities/{entity_id}.png"
    image.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (40, 60, 80)).save(image, format="PNG")
    review = run_dir / f"production/review/reviews/{entity_id}.json"
    review.parent.mkdir(parents=True, exist_ok=True)
    grades = dict.fromkeys(
        (
            "entity_identity",
            "action_legibility",
            "medium_fidelity",
            "register_fidelity",
            "readable_text_absent",
            "explanatory_form_absent",
            "technical_quality",
        ),
        "pass" if verdict == "admit" else "fail",
    )
    review.write_text(
        json.dumps(
            {
                "review_id": "universe_independent_image_review",
                "entity_id": entity_id,
                "artifact_sha256": content_sha256(image.read_bytes()),
                **grades,
                "verdict": verdict,
                "blocking_findings": [] if verdict == "admit" else ["register_fidelity: wet"],
                "advisory_findings": [],
                "what_the_image_teaches": "how the crossing is read",
            }
        ),
        encoding="utf-8",
    )


async def test_the_record_and_inventory_close_a_gallery_without_a_provider(
    tmp_path: Path,
) -> None:
    """The two local nodes that decide what a finished package says about itself."""

    resolved = resolve_universe_source(read_universe_document(FIXTURE), root=FIXTURE)
    admitted = admitted_universe_from_document(
        Path("tests/contract/fixtures/universe/lantern_ferry.admitted-universe.json"),
        poster_sha256=resolved.poster_sha256,
    )
    samples = resolve_sample_ledger(
        universe_id=admitted.universe_id, entity_ids=admitted.entity_ids()
    )
    graph = build_universe_gallery_graph(
        resolved,
        admitted,
        samples=samples,
        profile=universe_graph_profile(StageGenConfig(), images=True),
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    handler = UniverseNodeHandler(
        graph,
        resolved,
        run_dir=run_dir,
        cache_dir=tmp_path / "cache",
        admitted=admitted,
    )
    rejected = admitted.entity_ids()[0]
    for entity_id in admitted.entity_ids():
        plan = admitted.plan.plan(entity_id)
        width, height = (int(value) for value in SIZE_BY_MODE[plan.concept_mode].split("x", 1))
        _write_entity_artifacts(
            run_dir,
            entity_id,
            verdict="reject" if entity_id == rejected else "admit",
            size=(width, height),
        )
        record_id = f"record-{node_safe(entity_id)}"
        await handler(
            graph.node(record_id),
            NodeExecutionContext(
                invocation_id="t",
                graph_sha256=graph.graph_sha256,
                dependency_results=_dependency_results(graph, record_id, run_dir),
            ),
        )

    await handler(
        graph.node("gallery-close"),
        NodeExecutionContext(
            invocation_id="t",
            graph_sha256=graph.graph_sha256,
            dependency_results=_dependency_results(graph, "gallery-close", run_dir),
        ),
    )

    inventory = json.loads((run_dir / "package/inventory.json").read_bytes())
    assert inventory["entity_count"] == len(admitted.entity_ids())
    assert inventory["image_count"] == inventory["entity_count"]
    assert inventory["admitted_count"] == inventory["entity_count"] - 1
    assert inventory["publication_authorized"] is False

    record = json.loads((run_dir / f"package/entities/{rejected}.json").read_bytes())
    assert record["status"] == "rejected"
    page = (run_dir / f"package/entities/{rejected}.md").read_bytes().decode("utf-8")
    assert page.startswith("# ")
    # The record is written as the text it is, not as opaque bytes.
    sidecar = json.loads((run_dir / f"package/entities/{rejected}.md.meta.json").read_bytes())
    assert sidecar["artifact"]["media_type"] == "text/markdown"


async def test_a_record_refuses_a_review_that_binds_different_image_bytes(
    tmp_path: Path,
) -> None:
    """The review's digest is the only thing tying a verdict to a picture."""

    resolved = resolve_universe_source(read_universe_document(FIXTURE), root=FIXTURE)
    admitted = admitted_universe_from_document(
        Path("tests/contract/fixtures/universe/lantern_ferry.admitted-universe.json"),
        poster_sha256=resolved.poster_sha256,
    )
    samples = resolve_sample_ledger(
        universe_id=admitted.universe_id, entity_ids=admitted.entity_ids()
    )
    graph = build_universe_gallery_graph(
        resolved,
        admitted,
        samples=samples,
        profile=universe_graph_profile(StageGenConfig(), images=True),
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    handler = UniverseNodeHandler(
        graph, resolved, run_dir=run_dir, cache_dir=tmp_path / "cache", admitted=admitted
    )
    entity_id = admitted.entity_ids()[0]
    plan = admitted.plan.plan(entity_id)
    width, height = (int(value) for value in SIZE_BY_MODE[plan.concept_mode].split("x", 1))
    _write_entity_artifacts(run_dir, entity_id, verdict="admit", size=(width, height))
    # Repaint the image after the review was written.
    Image.new("RGB", (width, height), (200, 30, 30)).save(
        run_dir / f"package/entities/{entity_id}.png", format="PNG"
    )
    with pytest.raises(NodeExecutionError, match="does not bind the current image bytes"):
        await handler(
            graph.node(f"record-{node_safe(entity_id)}"),
            NodeExecutionContext(
                invocation_id="t",
                graph_sha256=graph.graph_sha256,
                dependency_results=_dependency_results(
                    graph, f"record-{node_safe(entity_id)}", run_dir
                ),
            ),
        )
