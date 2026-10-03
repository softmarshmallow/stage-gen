"""A real provider-free movie-sprite run (supplied footage) becomes a current example."""

from __future__ import annotations

from pathlib import Path

import pytest

from gnode import run_async
from stage_gen.examples import ImportRequest, MadeBy, currency, verify, write_example
from stage_gen.workflows._registry import load_code
from stage_gen.workflows.movie_sprite.inputs.supplied_clip.make_inputs import make_inputs


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("_STAGE_GEN_DISABLE_DOTENV", "1")


async def test_a_finished_loop_imports_with_its_poster(tmp_path: Path) -> None:
    (tmp_path / "gnode.yaml").write_text("gnode: project/v1\n", encoding="utf-8")
    make_inputs(tmp_path / "inputs")
    result = await run_async(
        "movie-sprite", input_files=[tmp_path / "inputs/clip.yaml"], cwd=tmp_path
    )
    assert result.ok, result.failed

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

    assert example.inputs == {} and example.importer == "gnode_run"
    loop = example.outputs["loop"]
    assert loop["file"] == "loop.mkv" and loop["kind"] == "animation"
    assert example.metrics["frames"] == 12 and example.metrics["provider_operations"] == 0
    assert list(example.nodes) == ["finish#1"]
    finish = example.nodes["finish#1"]
    assert finish.type_id == "movie_sprite/finish" and finish.depends_on == []
    assert finish.thumb is not None and finish.pictures
    assert example.source_runs[0].anchor == "plan.json"
    assert currency(example, code.type_ids(), code.graph_kinds()) == "current"

    pin = write_example(request.out, example, request.figures(example))
    assert verify(request.out, pin) == []
    files = [entry.file for entry in request.figures(example).files]
    assert "media/output-loop.webp" in files
