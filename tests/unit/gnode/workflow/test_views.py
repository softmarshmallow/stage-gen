"""Step views: a run keeps each view and what it shows; its context is a projection of the run."""

from __future__ import annotations

from pathlib import Path

import jsonschema

from gnode import WorkflowRun, document_schemas, make_plan, make_planner, view_contexts
from gnode_std import file_facts, plugin, standard_types
from tests.unit.gnode.workflow._project import ROUTES, FakeProvider, project

VIEWED = """
gnode: workflow/v1
id: flow
title: Flow
steps:
  draw:
    title: Draw a lantern
    uses: gnode/image.generate@1
    with: { prompt: a lantern }
    view: true
  loud:
    uses: ./nodes/test_nodes.py#shout
    with: { text: "take ${{ steps.draw.take }}" }
    view: ./views/words.html
  quiet:
    uses: ./nodes/test_nodes.py#shout
    with: { text: unseen }
outputs:
  image: ${{ steps.draw.outputs.image }}
"""

WORDS = "<!doctype html><p>words</p>\n"


async def test_a_run_keeps_its_views_and_projects_their_contexts(tmp_path: Path) -> None:
    path = project(tmp_path, VIEWED, **{"views/words.html": WORDS})
    planner = make_planner(
        path,
        cwd=tmp_path,
        builtins=standard_types(),
        routes=ROUTES,
        facts_reader=file_facts,
        views=plugin().views,
    )
    run_dir = tmp_path / "runs/one"
    provider = FakeProvider(planner.store)
    outcome = await WorkflowRun(
        await make_plan(planner), run_dir=run_dir, services=provider.services()
    ).run()
    assert outcome.ok, outcome.failed

    contexts = {context["step"]["path"]: context for context in view_contexts(run_dir)}
    assert set(contexts) == {"draw", "loud"}
    schema = document_schemas()["gnode-view-context-v1.schema.json"]
    for context in contexts.values():
        jsonschema.validate(context, schema)
        assert (run_dir / context["template"]).is_file()

    draw = contexts["draw"]
    assert draw["step"]["title"] == "Draw a lantern"
    assert draw["step"]["with"]["prompt"] == "a lantern"
    assert draw["step"]["cost_usd"] == 0.01
    assert draw["inputs"] == {}
    (image,) = draw["outputs"].values()
    assert (run_dir / image["ref"]).is_file()
    assert draw["run"] == {
        "id": "one",
        "workflow": "flow",
        "status": "succeeded",
        "cost_usd": 0.01,
    }
    template = (run_dir / draw["template"]).read_text(encoding="utf-8")
    assert 'from "/_gnode/view.js"' in template

    loud = contexts["loud"]
    assert (run_dir / loud["template"]).read_text(encoding="utf-8") == WORDS
    assert loud["step"]["with"] == {"text": "take 1"}
    assert loud["outputs"]["text"]["kind"] == "text/plain"

    measured = {
        context["step"]["path"]: context
        for context in view_contexts(run_dir, facts_reader=file_facts)
    }
    (image,) = measured["draw"]["outputs"].values()
    assert (image["facts"]["width"], image["facts"]["height"]) == (1, 1)
