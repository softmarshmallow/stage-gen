"""An offline character run and a library character become character-3d examples."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from stage_gen.examples import (
    ImportRequest,
    MadeBy,
    currency,
    document_bytes,
    sha256_bytes,
    verify,
    write_example,
)
from stage_gen.workflows._registry import load_code
from stage_gen.workflows.character_3d.example import read_library
from tests.unit.workflows.character_3d.test_workflow import StandIn, _run

REPOSITORY = Path(__file__).resolve().parents[4]


async def test_an_accepted_character_run_imports_as_an_example(
    tmp_path: Path, blender: Path
) -> None:
    outcome = await _run(tmp_path, StandIn(), "example")
    assert outcome.ok, outcome.failed

    code = load_code("character-3d")
    assert code.import_example is not None and code.owns_run(outcome.run_dir)
    request = ImportRequest(
        example_id="courier",
        made_by=MadeBy(kind="workflow", id="character-3d"),
        base=tmp_path,
        runs=(outcome.run_dir,),
        out=tmp_path / "store/character-3d/courier",
    )
    example = code.import_example(request)

    assert example.importer == "gnode_run"
    assert str(example.inputs["brief"]["text"]).startswith("# Pell")
    export = example.outputs["export"]
    assert export["kind"] == "model" and export["src"] == "media/export.glb"
    assert {"cheer", "rest"} <= set(cast(list[str], export["clips"]))
    assert example.metrics["numeric_findings"] == 0 and example.metrics["missing_weights"] == 0
    assert example.metrics["provider_operations"] == 15
    assert currency(example, code.type_ids(), code.graph_kinds()) == "current"
    # The poster turns through the pose rows only, in pose order: the face strip and the
    # torso close-ups that follow them in the atlas are the reviewer's, not the page's.
    poster = request.figures(example).latest()["media/export-poses.webp"]
    assert [Path(s.path).name for s in poster.sources] == [f"{n}.png" for n in range(6)]
    pin = write_example(request.out, example, request.figures(example))
    assert verify(request.out, pin) == []


@pytest.mark.parametrize("character", ["nami", "riko", "helix"])
def test_a_library_character_builds_from_its_tracked_files(character: str) -> None:
    example, figures = read_library(REPOSITORY, f"library/characters/{character}")
    assert example.example_id == character and example.importer == "library"
    assert example.made_by.id == "character-3d" and example.nodes == {}
    assert example.outputs["export"]["src"] == "media/sd_3d.glb"
    assert {entry.file for entry in figures.files} >= {"media/sd_3d.glb", "media/sd_3d.webp"}
    again, _ = read_library(REPOSITORY, f"library/characters/{character}")
    assert sha256_bytes(document_bytes(again)) == sha256_bytes(document_bytes(example))
