"""Planning a workflow file: wiring, repeats, phases, judges, takes, identity and price."""

from __future__ import annotations

from pathlib import Path

from tests.unit.gnode.workflow._project import plan, project, write


def _state(planned, prefix: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {i.id: i.state for i in planned.instances if i.id.startswith(prefix)}


async def test_a_linear_workflow_plans_prices_and_wires(tmp_path: Path) -> None:
    path = project(
        tmp_path,
        """
        gnode: workflow/v1
        id: flow
        title: Flow
        inputs:
          brief: { type: file, kind: text/markdown }
        steps:
          count:
            uses: ./nodes/test_nodes.py#words
            with: { text: "${{ inputs.brief }}" }
          draw:
            uses: gnode/image.generate@1
            with:
              prompt: "A picture of ${{ steps.count.outputs.report.count }} words"
        outputs:
          image: ${{ steps.draw.outputs.image }}
        """,
        **{"inputs/brief.md": "three small words"},
    )
    planned = await plan(path, brief="inputs/brief.md")

    assert planned.ok, planned.problems
    count, draw = planned.instances
    assert (count.id, draw.id) == ("count#1", "draw#1")
    assert count.identity is not None and draw.identity is None
    assert draw.waiting_on == {"count#1"}
    assert planned.estimate() == (0.01, 0.04)
    assert "estimate  $0.01 \u2013 $0.04" in planned.render()


async def test_identity_follows_content_never_names(tmp_path: Path) -> None:
    flow = """
        gnode: workflow/v1
        id: flow
        title: Flow
        steps:
          {name}:
            uses: ./nodes/test_nodes.py#shout
            with: {{ text: "{text}" }}
          twin:
            uses: ./nodes/test_nodes.py#shout
            with: {{ text: "hello" }}
        """
    first = await plan(project(tmp_path / "a", flow.format(name="loud", text="hello")))
    renamed = await plan(project(tmp_path / "b", flow.format(name="other", text="hello")))
    edited = await plan(project(tmp_path / "c", flow.format(name="loud", text="bye")))

    loud, twin = first.instances
    assert loud.identity == twin.identity, "identical work is one piece of work"
    assert renamed.instances[0].identity == loud.identity, "a name is not identity"
    assert edited.instances[0].identity != loud.identity


async def test_a_repeat_over_an_input_list_is_keyed_and_collected(tmp_path: Path) -> None:
    path = project(
        tmp_path,
        """
        gnode: workflow/v1
        id: flow
        title: Flow
        inputs:
          names: { type: list, items: { type: string } }
        steps:
          loud:
            for_each: ${{ inputs.names }}
            key: ${{ item }}
            uses: ./nodes/test_nodes.py#shout
            with: { text: "${{ item }}" }
          joined:
            uses: ./nodes/test_nodes.py#join
            with: { parts: "${{ steps.loud.*.outputs.text }}" }
        """,
    )
    planned = await plan(path, names=["ada", "bo"])

    assert planned.ok, planned.problems
    assert [i.id for i in planned.instances] == ["loud['ada']#1", "loud['bo']#1", "joined#1"]
    assert planned.instances[2].waiting_on == {"loud['ada']#1", "loud['bo']#1"}


async def test_a_repeat_over_a_steps_output_is_a_phase_priced_up_to_max(tmp_path: Path) -> None:
    flow = """
        gnode: workflow/v1
        id: flow
        title: Flow
        inputs:
          script: {{ type: file, kind: text/plain }}
        steps:
          lines:
            uses: ./nodes/test_nodes.py#split
            with: {{ text: "${{{{ inputs.script }}}}" }}
          draw:
            for_each: ${{{{ steps.lines.outputs.items.lines }}}}
            key: ${{{{ item.id }}}}
            {limit}
            uses: gnode/image.generate@1
            with: {{ prompt: "${{{{ item.text }}}}" }}
        """
    path = project(tmp_path / "a", flow.format(limit="max: 5"), **{"s.txt": "a\nb"})
    planned = await plan(path, script="s.txt")

    assert planned.ok, planned.problems
    (repeat,) = planned.expansion.pending
    assert (repeat.path, repeat.max, repeat.phase) == ("draw", 5, 2)
    assert planned.estimate() == (0.0, 0.2)
    assert [summary.phase for summary in planned.phases()] == [1, 2]

    unbounded = project(tmp_path / "b", flow.format(limit=""), **{"s.txt": "a"})
    refused = await plan(unbounded, script="s.txt")
    assert any("add max:" in problem.message for problem in refused.problems)


async def test_conditions_known_while_planning_drop_steps(tmp_path: Path) -> None:
    path = project(
        tmp_path,
        """
        gnode: workflow/v1
        id: flow
        title: Flow
        inputs:
          mode: { type: string, enum: [a, b], default: a }
        steps:
          only_a:
            if: ${{ inputs.mode == 'a' }}
            uses: ./nodes/test_nodes.py#shout
            with: { text: a }
          only_b:
            if: ${{ inputs.mode == 'b' }}
            uses: ./nodes/test_nodes.py#shout
            with: { text: b }
          either:
            uses: gnode/select@1
            with:
              first_of:
                - ${{ steps.only_b.outputs.text }}
                - ${{ steps.only_a.outputs.text }}
        """,
    )
    planned = await plan(path)

    assert planned.ok, planned.problems
    assert [i.id for i in planned.instances] == ["only_a#1", "either#1"]
    assert planned.instances[1].with_["first_of"][0] is not None


async def test_a_judge_that_regenerates_plans_every_take_as_maybe(tmp_path: Path) -> None:
    path = project(
        tmp_path,
        """
        gnode: workflow/v1
        id: flow
        title: Flow
        steps:
          draw:
            uses: gnode/image.generate@1
            with: { prompt: a lantern }
          check:
            uses: ./nodes/test_nodes.py#verdict
            judges: draw
            with: { subject: "${{ steps.draw.outputs.image }}", accept_take: 2 }
            on_reject: { regenerate: { max: 3, then: fail } }
          after:
            uses: ./nodes/test_nodes.py#shout
            with: { text: "${{ steps.draw.take }}" }
        """,
    )
    planned = await plan(path)

    assert planned.ok, planned.problems
    assert _state(planned, "draw") == {"draw#1": "planned", "draw#2": "maybe", "draw#3": "maybe"}
    assert _state(planned, "check") == {
        "check#1": "planned",
        "check#2": "maybe",
        "check#3": "maybe",
    }
    after = planned.expansion.instances["after#1"]
    assert after.waiting_on >= {"draw#1", "check#1"}
    assert planned.estimate() == (0.01, 0.12)


async def test_routes_requirements_and_independence_are_checked_offline(tmp_path: Path) -> None:
    path = project(
        tmp_path,
        """
        gnode: workflow/v1
        id: flow
        title: Flow
        steps:
          draw:
            uses: gnode/image.generate@1
            requires: [mask]
            with: { prompt: x }
          write:
            uses: gnode/structured.generate@1
            route: llm-a@acme
            with: { prompt: x, schema: ./schema.json }
          review:
            uses: gnode/vision.review@1
            route: llm-a@other
            independent_of: write
            judges: write
            with: { question: "is it right?" }
          lost:
            uses: gnode/image.generate@1
            route: img-z@nowhere
            with: { prompt: x }
        """,
        **{"schema.json": "{}"},
    )
    planned = await plan(path)

    messages = [str(problem) for problem in planned.problems]
    assert any("img-a@acme does not support mask" in m for m in messages), messages
    assert any("shares the model llm-a with write" in m for m in messages), messages
    assert any("no route img-z@nowhere serves image.generate" in m for m in messages), messages


async def test_a_plan_time_assertion_refuses_with_its_message(tmp_path: Path) -> None:
    path = project(
        tmp_path,
        """
        gnode: workflow/v1
        id: flow
        title: Flow
        inputs:
          names: { type: list, items: { type: string } }
        assert:
          - check: ${{ len(inputs.names) > 0 }}
            message: "give at least one name"
        steps:
          loud:
            for_each: ${{ inputs.names }}
            assert:
              - check: ${{ len(item) <= 3 }}
                message: "${{ item }} is too long"
            uses: ./nodes/test_nodes.py#shout
            with: { text: "${{ item }}" }
        """,
    )
    empty = await plan(path, names=[])
    long = await plan(path, names=["ada", "barnaby"])

    assert [problem.message for problem in empty.problems] == ["give at least one name"]
    assert [problem.message for problem in long.problems] == ["barnaby is too long"]


async def test_the_ceiling_comes_from_the_flag_then_the_workflow_then_the_project(
    tmp_path: Path,
) -> None:
    path = project(
        tmp_path,
        """
        gnode: workflow/v1
        id: flow
        title: Flow
        budget: { max_usd: 4 }
        steps:
          draw: { uses: gnode/image.generate@1, with: { prompt: x } }
        """,
    )
    assert (await plan(path)).ceiling_usd == 4
    assert (await plan(path, max_usd=1.5)).ceiling_usd == 1.5
    write(
        tmp_path, {"workflows/flow.yaml": path.read_text().replace("budget: { max_usd: 4 }\n", "")}
    )
    assert (await plan(path)).ceiling_usd is None
