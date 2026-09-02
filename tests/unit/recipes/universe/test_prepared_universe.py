"""The node handlers that need no provider, run for real against the fixture package."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from gnode import Scheduler
from stage_gen.config import StageGenConfig
from stage_gen.recipes.universe.prepared_universe import (
    UniverseNodeHandler,
    make_image_proxy,
    render_entity_markdown,
)
from stage_gen.recipes.universe.universe_graph import (
    POSTER_PROXY_REF,
    SOURCE_LOCK_REF,
    UniverseGraph,
    build_universe_semantic_graph,
    universe_graph_profile,
)
from stage_gen.recipes.universe.universe_request import (
    ResolvedUniverseSource,
    read_universe_document,
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
