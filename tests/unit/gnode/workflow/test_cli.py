"""The gnode command line over a project on disk, offline."""

from __future__ import annotations

import io
import json
from pathlib import Path

import yaml

from gnode import cli
from tests.unit.gnode.workflow._project import project, write

FLOW = """
gnode: workflow/v1
id: shouts
title: Shouts
inputs:
  names: { type: list, items: { type: string } }
  greeting: { type: string, default: hello }
steps:
  loud:
    for_each: ${{ inputs.names }}
    key: ${{ item }}
    uses: ./nodes/test_nodes.py#shout
    with: { text: "${{ inputs.greeting }} ${{ item }}" }
  joined:
    uses: ./nodes/test_nodes.py#join
    with: { parts: "${{ steps.loud.*.outputs.text }}" }
outputs:
  each: ${{ steps.loud.*.outputs.text }}
  all: ${{ steps.joined.outputs.text }}
"""


def _gnode(root: Path, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    status = cli.main(list(argv), stdout=out, stderr=err, cwd=root)
    return status, out.getvalue(), err.getvalue()


def _project(root: Path) -> Path:
    project(root, FLOW)
    write(root, {"inputs/names.yaml": "names: [ada, bo]\n"})
    return root


def test_plan_prints_the_summary_and_checks(tmp_path: Path) -> None:
    root = _project(tmp_path)
    status, out, err = _gnode(root, "plan", "shouts", "--inputs", "inputs/names.yaml")
    assert status == 0, err
    assert out.startswith("shouts  ·  1 phase")
    assert "cached    0 of 2 known steps" in out

    status, _, err = _gnode(root, "plan", "shouts", "--check")
    assert status == 2 and "'names' is a required property" in err


def test_input_flags_are_the_kebab_case_of_each_input(tmp_path: Path) -> None:
    root = _project(tmp_path)
    status, out, err = _gnode(
        root, "expand", "shouts", "--inputs", "inputs/names.yaml", "--greeting", "hi"
    )
    assert status == 0, err
    graph = json.loads(out)
    loud = [i for i in graph["instances"] if i["step"] == "loud"]
    assert [i["path"] for i in loud] == ["loud['ada']", "loud['bo']"]

    status, _, err = _gnode(root, "plan", "shouts", "--inputs", "inputs/names.yaml", "--nope", "1")
    assert status == 2 and "unknown input flag --nope" in err


def test_schema_and_nodes(tmp_path: Path) -> None:
    root = _project(tmp_path)
    status, out, _ = _gnode(root, "schema", "shouts")
    schema = json.loads(out)
    assert status == 0 and schema["required"] == ["names"]
    assert schema["properties"]["greeting"]["default"] == "hello"

    status, out, _ = _gnode(root, "nodes", "image.generate")
    assert status == 0 and "gnode/image.generate@1" in out and "output  image" in out


def test_run_records_delivers_and_continues(tmp_path: Path) -> None:
    root = _project(tmp_path)
    args = ["run", "shouts", "--inputs", "inputs/names.yaml", "--run", "runs/one"]
    status, out, err = _gnode(root, *args, "--deliver", "each=out/{key}.txt")
    assert status == 0, out + err
    assert (root / "out/ada.txt").read_text() == "HELLO ADA"
    assert (root / "runs/one/outputs/all.txt").read_text() == "ada=HELLO ADA|bo=HELLO BO"

    status, out, err = _gnode(root, *args)
    assert status == 0, out + err
    status, out, _ = _gnode(root, "project", "runs/one")
    projected = json.loads(out)
    assert projected["instances"]["joined#1"]["state"] == "succeeded"


def test_reroll_and_pick_write_the_takes_file(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _gnode(root, "run", "shouts", "--inputs", "inputs/names.yaml", "--run", "runs/one")

    status, out, err = _gnode(root, "reroll", "runs/one", "loud['ada']")
    assert status == 0, err
    takes = yaml.safe_load((root / "workflows/shouts.takes.yaml").read_text())
    assert takes == {"loud['ada']": {"take": 2}}

    status, out, err = _gnode(root, "expand", "shouts", "--inputs", "inputs/names.yaml")
    ids = [i["id"] for i in json.loads(out)["instances"]]
    assert "loud['ada']#2" in ids and "loud['bo']#1" in ids

    status, out, err = _gnode(root, "pick", "runs/one", "loud['ada']", "1")
    assert status == 0, err
    takes = yaml.safe_load((root / "workflows/shouts.takes.yaml").read_text())
    assert takes["loud['ada']"]["take"] == 1
    assert takes["loud['ada']"]["result"].startswith("sha256:")

    status, out, _ = _gnode(root, "takes", "mv", "shouts", "loud['ada']", "loud['ana']")
    assert status == 0
    status, out, _ = _gnode(root, "takes", "list", "shouts")
    assert out.startswith("loud['ana']  take 1")


def test_identity_and_price_are_json(tmp_path: Path) -> None:
    root = _project(tmp_path)
    status, out, _ = _gnode(root, "identity", "shouts", "--inputs", "inputs/names.yaml")
    identities = json.loads(out)
    assert status == 0 and set(identities) == {"loud['ada']#1", "loud['bo']#1", "joined#1"}
    status, out, _ = _gnode(root, "price", "shouts", "--inputs", "inputs/names.yaml")
    assert status == 0 and json.loads(out)["estimate"] == {"low_usd": 0.0, "high_usd": 0.0}


VERSIONED = """
from gnode import Ctx, node


@node("stamp", params={"text": str}, outputs={"text": "text"}, version=1)
def stamp(ctx: Ctx) -> dict:
    return {"text": ctx.out.text(ctx.params["text"])}
"""


def test_lock_pins_the_node_folder_the_project_names(tmp_path: Path) -> None:
    write(
        tmp_path,
        {
            "gnode.yaml": "gnode: project/v1\nnodes: pipeline/nodes\n",
            "pipeline/nodes/stamps.py": VERSIONED,
        },
    )

    status, out, _ = _gnode(tmp_path, "lock")

    assert status == 0, out
    locked = yaml.safe_load((tmp_path / "gnode.lock").read_text(encoding="utf-8"))["nodes"]
    assert list(locked) == ["pipeline/nodes/stamps.py#stamp@1"]


def test_a_builder_that_refuses_its_input_is_a_plan_error(tmp_path: Path) -> None:
    write(
        tmp_path,
        {
            "gnode.yaml": "gnode: project/v1\n",
            "build.py": (
                "def build(level: str):\n    raise ValueError(f'no level named {level}')\n"
            ),
        },
    )

    status, _, err = _gnode(tmp_path, "plan", "build.py:build", "--arg", "level=docks")

    assert status != 0
    assert "no level named docks" in err and "Traceback" not in err
