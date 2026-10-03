"""Groups, nested repeats, workflows used as steps, and the Python builder."""

from __future__ import annotations

from pathlib import Path

from gnode import Workflow, make_plan, make_planner
from gnode_std import file_facts, standard_types
from tests.unit.gnode.workflow._project import ROUTES, planner, project


async def test_a_member_may_refer_back_into_an_earlier_instance_of_a_repeat(
    tmp_path: Path,
) -> None:
    # `summary` reads every `cell`, and each cell's `patch` reads `summary`: acyclic as data,
    # though expanding the repeat in full before `summary` would loop.
    path = project(
        tmp_path,
        """
        gnode: workflow/v1
        id: flow
        title: Flow
        inputs:
          names: { type: list, items: { type: string } }
        steps:
          cell:
            for_each: ${{ inputs.names }}
            key: ${{ item }}
            steps:
              cut:
                uses: ./nodes/test_nodes.py#shout
                with: { text: "${{ item }}" }
              patch:
                uses: ./nodes/test_nodes.py#join
                with: { parts: "${{ steps.summary.outputs.text }}" }
          summary:
            uses: ./nodes/test_nodes.py#join
            with: { parts: "${{ steps.cell.*.cut.outputs.text }}" }
        """,
    )
    planned = await make_plan(planner(path, names=["a", "b"]))

    assert planned.ok, planned.problems
    states = {i.id: i.state for i in planned.instances}
    assert states == {
        "cell['a'].cut#1": "planned",
        "cell['a'].patch#1": "planned",
        "cell['b'].cut#1": "planned",
        "cell['b'].patch#1": "planned",
        "summary#1": "planned",
    }


async def test_nested_repeats_collect_with_compound_keys(tmp_path: Path) -> None:
    path = project(
        tmp_path,
        """
        gnode: workflow/v1
        id: flow
        title: Flow
        steps:
          outer:
            for_each: [x, y]
            as: o
            key: ${{ o }}
            steps:
              inner:
                for_each: [1, 2]
                as: i
                key: ${{ i }}
                uses: ./nodes/test_nodes.py#shout
                with: { text: "${{ o }}${{ i }}" }
          all:
            uses: ./nodes/test_nodes.py#join
            with: { parts: "${{ steps.outer.*.inner.*.outputs.text }}" }
        """,
    )
    planned = await make_plan(planner(path))

    assert planned.ok, planned.problems
    collected = planned.expansion.instances["all#1"].with_["parts"]
    assert collected.keys() == ["x.1", "x.2", "y.1", "y.2"]


async def test_a_used_workflow_gets_defaults_files_and_validation(tmp_path: Path) -> None:
    project(
        tmp_path,
        """
        gnode: workflow/v1
        id: outer
        title: Outer
        steps:
          each:
            uses: ./workflows/inner.yaml
            with:
              notes: [ { text: a, file: inputs/a.txt } ]
        outputs:
          got: ${{ steps.each.outputs.got }}
        """,
        **{
            "workflows/inner.yaml": """
                gnode: workflow/v1
                id: inner
                title: Inner
                inputs:
                  notes:
                    type: list
                    items:
                      text: { type: string }
                      file: { type: file, kind: text }
                      loud: { type: boolean, default: true }
                steps:
                  read:
                    for_each: ${{ inputs.notes }}
                    if: ${{ item.loud }}
                    uses: ./nodes/test_nodes.py#words
                    with: { text: "${{ item.file }}" }
                outputs:
                  got: ${{ steps.read.*.outputs.report }}
                """,
            "inputs/a.txt": "two words",
        },
    )
    planned = await make_plan(planner(tmp_path / "workflows/flow.yaml"))

    assert planned.ok, planned.problems
    (read,) = planned.instances
    assert read.id == "each.read['0']#1"
    assert read.with_["text"].name == "a.txt"


async def test_the_builder_makes_the_same_document_a_file_would(tmp_path: Path) -> None:
    project(
        tmp_path,
        """
        gnode: workflow/v1
        id: unused
        title: Unused
        steps:
          x: { uses: gnode/select@1, with: { first_of: [] } }
        """,
    )
    wf = Workflow("built", title="Built")
    loud = wf.step(
        "loud",
        for_each=["ada", "bo"],
        key="${{ item }}",
        uses="./nodes/test_nodes.py#shout",
        with_={"text": "${{ item }}"},
    )
    joined = wf.step(
        "joined", uses="./nodes/test_nodes.py#join", with_={"parts": loud.all.outputs.text}
    )
    wf.outputs(all=joined.outputs.text)

    built = make_planner(
        wf, cwd=tmp_path, builtins=standard_types(), routes=ROUTES, facts_reader=file_facts
    )
    planned = await make_plan(built)

    assert planned.ok, planned.problems
    assert [i.id for i in planned.instances] == ["loud['ada']#1", "loud['bo']#1", "joined#1"]
    assert wf.document().steps["joined"].with_ == {"parts": "${{ steps.loud.*.outputs.text }}"}
    assert built.workflow_path.name == "test_composition.py"
