"""File loading supports adjacent author modules without changing caller path state."""

import sys
from pathlib import Path

import pytest

from stage_gen.pipeline import load_definition, plan, run

_HELPER = """from gnode import (
    BindingTable, Graph, GraphBuilder, NodeType, ViewArchetype, seal_graph,
)
from stage_gen.pipeline import define, NodeBinding, record_port

COPY = NodeType("example/helper", "Adjacent helper", ViewArchetype.TRANSFORM, "local", "1")

def build(inputs):
    builder = GraphBuilder(profile=BindingTable(()))
    builder.add(COPY, "helper", domain="assets", description="Defined in an adjacent module",
                ports=(record_port("text", "message.txt", "text-v1"),))
    return seal_graph(Graph, schema_version=1, kind="external-example-v1",
                      resources=builder.resources(), nodes=builder.nodes, terminal_node_id="helper")

async def execute(node, context):
    return await context.publish(node, {"text": b"adjacent helper ran"})

def create():
    return define("external-helper", title="External helper", build=build,
                  bindings=(NodeBinding(COPY, execute),))
"""


@pytest.mark.parametrize("factory", [False, True])
async def test_file_definition_imports_adjacent_helper_from_another_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, factory: bool
) -> None:
    author = tmp_path / "author"
    caller = tmp_path / "caller"
    author.mkdir()
    caller.mkdir()
    helper_name = "_stage_gen_loader_test_helper"
    monkeypatch.delitem(sys.modules, helper_name, raising=False)
    (author / f"{helper_name}.py").write_text(_HELPER)
    source = author / "pipeline.py"
    if factory:
        source.write_text(
            f"def create_pipeline():\n    from {helper_name} import create\n    return create()\n"
        )
        reference = f"{source}:create_pipeline"
    else:
        source.write_text(f"from {helper_name} import create\npipeline = create()\n")
        reference = str(source)
    monkeypatch.chdir(caller)
    original_path = sys.path[:]

    try:
        definition = load_definition(reference)
        assert sys.path == original_path
        assert Path.cwd() == caller
        completed = await run(
            plan(definition, input_root=caller),
            output_root=caller / "run",
            cache_root=caller / "cache",
        )
        assert completed.summary.ok
        assert (completed.run_dir / "message.txt").read_bytes() == b"adjacent helper ran"
    finally:
        sys.modules.pop(helper_name, None)
        for name, module in tuple(sys.modules.items()):
            if getattr(module, "__file__", None) == str(source):
                sys.modules.pop(name, None)


def test_failed_factory_restores_import_path_and_prior_entry_module(tmp_path: Path) -> None:
    source = tmp_path / "entry.py"
    source.write_text("pipeline = None\n")
    before_modules = dict(sys.modules)
    original_path = sys.path[:]
    with pytest.raises(TypeError, match="pipeline export"):
        load_definition(str(source))
    assert sys.path == original_path
    assert not any(
        getattr(module, "__file__", None) == str(source)
        for name, module in sys.modules.items()
        if name not in before_modules
    )

    source.write_text(
        "from stage_gen.pipeline import define\n"
        "pipeline=define('x', title='X', build=lambda inputs: None, bindings=())\n"
    )
    load_definition(str(source))
    [module_name] = [
        name
        for name, module in sys.modules.items()
        if getattr(module, "__file__", None) == str(source)
    ]
    previous = sys.modules[module_name]
    source.write_text("def broken_factory():\n    raise RuntimeError('factory failed')\n")
    try:
        with pytest.raises(RuntimeError, match="factory failed"):
            load_definition(f"{source}:broken_factory")
        assert sys.path == original_path
        assert sys.modules[module_name] is previous
    finally:
        sys.modules.pop(module_name, None)
