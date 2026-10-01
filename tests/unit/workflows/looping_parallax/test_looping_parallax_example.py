"""A real offline looping-parallax run becomes an example, and the example is current."""

from __future__ import annotations

import dataclasses
import io
import json
import runpy
from pathlib import Path

import pytest

from stage_gen.examples import (
    ExamplePin,
    ImportRequest,
    MadeBy,
    currency,
    verify,
    write_example,
)
from stage_gen.pipeline import load_definition, plan, run
from stage_gen.workflows._registry import load_code
from stage_gen.workflows.looping_parallax.workflow import SAMPLE_INPUTS


async def test_an_offline_run_imports_as_a_current_example(tmp_path: Path) -> None:
    runpy.run_path(str(SAMPLE_INPUTS / "make_inputs.py"))["write_layers"](tmp_path)
    planned = plan(load_definition(str(SAMPLE_INPUTS / "pipeline.py")), input_root=tmp_path)
    result = await run(planned, output_root=tmp_path / "runs/one", cache_root=tmp_path / "cache")
    assert result.summary.ok

    code = load_code("looping-parallax")
    assert code.import_example is not None and code.owns_run(result.run_dir)
    request = ImportRequest(
        example_id="hills",
        made_by=MadeBy(kind="workflow", id="looping-parallax"),
        base=tmp_path,
        runs=(result.run_dir,),
        out=tmp_path / "store/looping-parallax/hills",
    )
    example = code.import_example(request)

    assert example.delivered_run == "runs/one"
    assert example.graph_kind == "pipeline-execution-graph-v1"
    assert [run.anchor for run in example.source_runs] == ["execution-plan.json"]
    assert set(example.inputs) == {"distant_hills", "near_trees"}
    assert example.outputs["background"]["file"] == "manifest.json"
    assert example.metrics["layers"] == 2
    assert all(node.origin == "run" for node in example.nodes.values())
    assert {node.type_id for node in example.nodes.values()} == {
        "parallax.prepare_layer",
        "parallax.compose",
    }
    assert example.source_files is not None
    assert "runs/one/execution-view.json" in example.source_files
    assert currency(example, code.type_ids(), code.graph_kinds()) == "current"

    pin = write_example(request.out, example, request.figures(example))
    assert verify(request.out, pin) == []


async def test_promote_exports_a_draft_and_pins_it_in_the_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from stage_gen.interfaces.cli import main
    from stage_gen.workflows import _registry
    from stage_gen.workflows._registry import read_manifest

    runpy.run_path(str(SAMPLE_INPUTS / "make_inputs.py"))["write_layers"](tmp_path)
    planned = plan(load_definition(str(SAMPLE_INPUTS / "pipeline.py")), input_root=tmp_path)
    result = await run(planned, output_root=tmp_path / "runs/one", cache_root=tmp_path / "cache")
    folder = tmp_path / "src/stage_gen/workflows/looping_parallax"
    folder.mkdir(parents=True)
    real = _registry.find("looping-parallax")
    (folder / "workflow.toml").write_text(real.root.joinpath("workflow.toml").read_text())
    monkeypatch.setattr(_registry, "repository_root", lambda: tmp_path)
    monkeypatch.setattr(
        _registry,
        "find",
        lambda workflow_id: dataclasses.replace(
            real,
            root=folder,
            manifest=read_manifest((folder / "workflow.toml").read_text()),
        ),
    )
    store = tmp_path / "store"
    output, errors = io.StringIO(), io.StringIO()
    argv = ["example", "promote", "looping-parallax", "--run", str(result.run_dir)]
    argv += ["--id", "hills", "--examples", str(store)]
    assert main(argv, stdout=output, stderr=errors) == 0, errors.getvalue()
    report = json.loads(output.getvalue())
    [entry] = read_manifest((folder / "workflow.toml").read_text()).examples
    assert (entry.id, entry.title, entry.status, entry.source) == (
        "hills",
        "Hills",
        "draft",
        "store",
    )
    assert entry.example_sha256 == report["example_sha256"]
    assert (
        verify(
            store / "looping-parallax/hills", ExamplePin(entry.example_sha256, entry.figures_sha256)
        )
        == []
    )
    assert main(argv, stdout=io.StringIO(), stderr=errors) == 2
    assert "already pins an example hills" in errors.getvalue()


async def test_inputs_resolve_in_the_runs_input_root_or_refuse(tmp_path: Path) -> None:
    inputs = tmp_path / "input"
    runpy.run_path(str(SAMPLE_INPUTS / "make_inputs.py"))["write_layers"](inputs)
    planned = plan(load_definition(str(SAMPLE_INPUTS / "pipeline.py")), input_root=inputs)
    result = await run(planned, output_root=tmp_path / "runs/one", cache_root=tmp_path / "cache")
    assert result.summary.ok
    code = load_code("looping-parallax")
    assert code.import_example is not None

    def request(**options: str) -> ImportRequest:
        return ImportRequest(
            example_id="hills",
            made_by=MadeBy(kind="workflow", id="looping-parallax"),
            base=tmp_path,
            runs=(result.run_dir,),
            out=tmp_path / "store/looping-parallax/hills",
            options=options,
        )

    with pytest.raises(ValueError, match="set the option input_root"):
        code.import_example(request())
    with pytest.raises(ValueError, match="outside"):
        code.import_example(request(input_root=".."))
    example = code.import_example(request(input_root="input"))
    assert set(example.inputs) == {"distant_hills", "near_trees"}
