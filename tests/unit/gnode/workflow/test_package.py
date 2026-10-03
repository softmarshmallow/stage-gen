"""``gnode/package@1``: results laid out by destination path, beside a manifest written in YAML."""

from __future__ import annotations

import json
from pathlib import Path

from gnode import WorkflowRun, make_plan
from tests.unit.gnode.workflow._project import FakeProvider, planner, project

FLOW = """
gnode: workflow/v1
id: flow
title: Flow
steps:
  count:
    uses: ./nodes/test_nodes.py#words
    with: { text: ./words.txt }
  loud:
    for_each: [harbour, lantern]
    key: ${{ item }}
    steps:
      shout:
        uses: ./nodes/test_nodes.py#shout
        with: { text: "${{ item }}" }
  close:
    uses: gnode/package@1
    with:
      files:
        "words.json": ${{ steps.count.outputs.report }}
        "shouts/{key}.txt": ${{ steps.loud.*.shout.outputs.text }}
      manifest:
        title: Two words
        count: ${{ steps.count.outputs.report.count }}
outputs:
  package: ${{ steps.close.outputs.files }}
  manifest: ${{ steps.close.outputs.manifest }}
"""


async def test_a_package_lays_out_files_and_collections_by_path(tmp_path: Path) -> None:
    path = project(tmp_path, FLOW, **{"words.txt": "two words\n"})
    built = planner(path)
    plan = await make_plan(built)
    assert plan.ok, plan.problems
    run_dir = tmp_path / "runs/one"
    outcome = await WorkflowRun(
        plan, run_dir=run_dir, services=FakeProvider(built.store).services()
    ).run()

    assert outcome.ok, outcome.failed
    outputs = run_dir / "outputs"
    assert json.loads((outputs / "package/words.json").read_text())["count"] == 2
    assert (outputs / "package/shouts/harbour.txt").read_text() == "HARBOUR"
    assert (outputs / "package/shouts/lantern.txt").read_text() == "LANTERN"
    manifest = json.loads((outputs / "manifest.json").read_text())
    assert manifest == {
        "files": ["shouts/harbour.txt", "shouts/lantern.txt", "words.json"],
        "title": "Two words",
        "count": 2,
    }
