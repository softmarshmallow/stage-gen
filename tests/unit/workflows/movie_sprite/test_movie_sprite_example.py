"""A real provider-free movie-sprite run (supplied footage) becomes a current example."""

from __future__ import annotations

from pathlib import Path

from stage_gen.examples import ImportRequest, MadeBy, currency, verify, write_example
from stage_gen.pipeline import load_definition, plan, run
from stage_gen.workflows._registry import load_code
from stage_gen.workflows.movie_sprite.inputs.supplied_clip.make_inputs import make_inputs

EXAMPLE = (
    Path(__file__).resolve().parents[4]
    / "src/stage_gen/workflows/movie_sprite/inputs/supplied_clip/pipeline.py"
)


async def test_a_finished_loop_imports_with_its_poster_and_checks(tmp_path: Path) -> None:
    make_inputs(tmp_path)
    planned = plan(load_definition(str(EXAMPLE)), input_root=tmp_path)
    result = await run(planned, output_root=tmp_path / "runs/loop", cache_root=tmp_path / "cache")
    assert result.summary.ok

    code = load_code("movie-sprite")
    assert code.import_example is not None and code.owns_run(result.run_dir)
    request = ImportRequest(
        example_id="loop",
        made_by=MadeBy(kind="workflow", id="movie-sprite"),
        base=tmp_path,
        runs=(result.run_dir,),
        out=tmp_path / "store/movie-sprite/loop",
    )
    example = code.import_example(request)

    assert example.inputs == {}
    loop = example.outputs["loop"]
    assert loop["file"] == "loop.mkv" and loop["kind"] == "animation"
    assert example.metrics["frames"] == 12 and example.metrics["provider_operations"] == 0
    assert list(example.nodes) == ["adopt", "finish"]
    finish = example.nodes["finish"]
    assert finish.thumb is not None and finish.thumb["src"] == "media/finish-loop-small.webp"
    assert finish.checks and all(isinstance(check["passed"], bool) for check in finish.checks)
    assert example.nodes["adopt"].depends_on == []
    assert finish.depends_on == ["adopt"]
    assert currency(example, code.type_ids(), code.graph_kinds()) == "current"

    pin = write_example(request.out, example, request.figures(example))
    assert verify(request.out, pin) == []
    files = [entry.file for entry in request.figures(example).files]
    assert "media/output-loop.webp" in files
