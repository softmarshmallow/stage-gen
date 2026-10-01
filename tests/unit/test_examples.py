"""The public example contract: documents, pins, the ledger, currency and tamper detection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from stage_gen.examples import (
    Delivered,
    ExamplePin,
    FiguresLedger,
    ImportRequest,
    MadeBy,
    Media,
    RecordingReader,
    WorkflowExample,
    currency,
    display_names,
    document_bytes,
    import_pipeline_run,
    index,
    node,
    pin_of,
    read_example,
    sha256,
    store_directory,
    verify,
    write_example,
)


def _example(nodes: dict[str, dict[str, Any]], graph_kind: str | None = "demo-graph-v1") -> Any:
    return WorkflowExample.model_validate(
        {
            "example_id": "demo",
            "made_by": MadeBy(kind="workflow", id="demo-workflow"),
            "importer": "test",
            "delivered_run": "runs/demo",
            "source_runs": [
                {"path": "runs/demo", "anchor": "graph.json", "anchor_sha256": "0" * 64}
            ],
            "source_files": None,
            "status": "succeeded",
            "graph_kind": graph_kind,
            "graph_sha256": None,
            "inputs": {},
            "outputs": {"still": {"kind": "image", "file": "still.png"}},
            "metrics": {"wall_seconds": 1.5, "provider_operations": 0},
            "models": [],
            "tree": {"": {"kind": "dir", "bytes": 0, "files": 0, "entries": 0}},
            "nodes": nodes,
        }
    )


def _stored(tmp_path: Path) -> tuple[Path, ExamplePin]:
    source = tmp_path / "runs" / "demo" / "still.png"
    source.parent.mkdir(parents=True)
    Image.new("RGB", (8, 6), (30, 60, 90)).save(source)
    directory = store_directory(tmp_path / "store", "demo-workflow", "demo")
    media = Media(directory / "media", tmp_path)
    picture = media.still("still.webp", source, 480)
    example = _example({"make": node("make", type_id="demo.make", thumb=picture)})
    pin = write_example(directory, example, media.figures("runs/demo"))
    return directory, pin


def test_a_stored_example_matches_its_pins_and_ledger(tmp_path: Path) -> None:
    directory, pin = _stored(tmp_path)
    assert verify(directory, pin) == []
    assert pin_of(directory) == pin
    assert read_example(directory).nodes["make"].thumb is not None
    ledger = FiguresLedger.model_validate_json((directory / "figures.json").read_bytes())
    [entry] = ledger.files
    assert entry.file == "media/still.webp"
    assert entry.sources[0].path == "runs/demo/still.png"
    assert entry.transform == "at most 480 px high, WebP q84"


def test_tampering_with_any_stored_file_is_refused(tmp_path: Path) -> None:
    directory, pin = _stored(tmp_path)
    (directory / "media" / "still.webp").write_bytes(b"not the picture")
    assert verify(directory, pin) == ["media/still.webp differs from its ledger digest"]

    directory, pin = _stored(tmp_path / "second")
    (directory / "media" / "extra.webp").write_bytes(b"unlisted")
    assert verify(directory, pin) == ["media/extra.webp is not in the ledger"]

    directory, pin = _stored(tmp_path / "third")
    document = json.loads((directory / "example.json").read_text())
    document["metrics"]["wall_seconds"] = 2
    (directory / "example.json").write_text(json.dumps(document))
    [problem] = verify(directory, pin)
    assert problem.startswith("example.json sha256") and problem.endswith("differs from its pin")

    directory, pin = _stored(tmp_path / "fourth")
    (directory / "figures.json").unlink()
    assert verify(directory, pin) == ["figures.json is missing"]


def test_documents_are_written_byte_for_byte_reproducibly(tmp_path: Path) -> None:
    example = _example({"make": node("make", type_id="demo.make")})
    again = WorkflowExample.model_validate_json(document_bytes(example))
    assert document_bytes(again) == document_bytes(example)
    assert document_bytes(example).endswith(b"}\n")


def test_currency_counts_only_nodes_that_ran_in_a_source_graph() -> None:
    nodes = {
        "make": node("make", type_id="demo.make"),
        "crop": node("crop", type_id="demo.crop_by_hand", origin="derived"),
    }
    example = _example(nodes)
    assert currency(example, {"demo.make"}, {"demo-graph-v1"}) == "current"
    assert currency(example, {"demo.other"}, {"demo-graph-v1"}) == "earlier_version"
    assert currency(example, {"demo.make"}, {"demo-graph-v2"}) == "earlier_version"
    assert currency(_example(nodes, graph_kind=None), {"demo.make"}, set()) == "current"


def test_example_nodes_refuse_unknown_fields_and_origins() -> None:
    with pytest.raises(ValueError, match="unknown node fields"):
        node("make", colour="red")
    with pytest.raises(ValueError):
        _example({"make": node("make", origin="guessed")})


def test_the_store_refuses_paths_that_leave_it(tmp_path: Path) -> None:
    for owner, example_id in (("..", "x"), ("a", "b/c"), ("", "x")):
        with pytest.raises(ValueError, match="invalid example store segment"):
            store_directory(tmp_path, owner, example_id)


def test_the_reader_records_every_file_it_opens_by_digest(tmp_path: Path) -> None:
    (tmp_path / "run").mkdir()
    record = tmp_path / "run" / "record.json"
    record.write_text('{"ok": true}')
    picture = tmp_path / "run" / "still.png"
    Image.new("RGB", (2, 2)).save(picture)
    reader = RecordingReader(tmp_path)
    assert reader.json(record) == {"ok": True}
    reader.path(picture)
    assert reader.files == {"run/record.json": sha256(record), "run/still.png": sha256(picture)}


def test_the_tree_index_counts_files_and_skips_symlinks(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "a.txt").write_text("abc")
    (tmp_path / "b.txt").write_text("de")
    (tmp_path / "link.txt").symlink_to(tmp_path / "b.txt")
    tree = index(tmp_path)
    assert tree[""] == {"kind": "dir", "bytes": 5, "files": 2, "entries": 2}
    assert tree["nested"] == {"kind": "dir", "bytes": 3, "files": 1, "entries": 1}
    assert "link.txt" not in tree


def test_display_names_cover_recorded_ids_and_their_names() -> None:
    names = display_names()
    assert names.model("openai/gpt-6-astra") == "GPT-6 Astra"
    assert names.model("unlisted/model") == "unlisted/model"
    assert names.provider("openrouter") == "OpenRouter"
    assert names.knows_model("GPT-6 Astra") and names.knows_model("openai/gpt-6-astra")
    assert not names.knows_model("unlisted/model")


def _view_run(root: Path, name: str, node_id: str, data: bytes, depends_on: list[str]) -> Path:
    """A hand-authored SDK run folder with one succeeded node and one artifact."""
    run = root / name
    (run / "out").mkdir(parents=True)
    (run / "out" / f"{node_id}.txt").write_bytes(data)
    artifact = {
        "artifact_ref": f"out/{node_id}.txt",
        "sha256": sha256(run / "out" / f"{node_id}.txt"),
        "media_type": "text/plain",
        "present": True,
    }
    item = {
        "node_id": node_id,
        "type_id": f"demo.{node_id}",
        "operation": "local",
        "state": "succeeded",
        "cache": "miss",
        "duration_ms": 1000,
        "provider_operations": 0,
        "depends_on": depends_on,
        "artifacts": [artifact],
    }
    (run / "execution-view.json").write_text(
        json.dumps({"graph_sha256": "1" * 64, "nodes": [item]})
    )
    (run / "execution-plan.json").write_text(json.dumps({"kind": "pipeline-execution-graph-v1"}))
    (run / "pipeline.json").write_text(json.dumps({"inputs": {}}))
    return run


def _chain(tmp_path: Path, *runs: Path) -> WorkflowExample:
    request = ImportRequest(
        example_id="chain",
        made_by=MadeBy(kind="workflow", id="demo-workflow"),
        base=tmp_path,
        runs=runs,
        out=tmp_path / "store",
    )
    return import_pipeline_run(
        request, output_node="b", deliver=lambda _: Delivered(inputs={}, outputs={}, metrics={})
    )


def test_a_later_run_links_to_the_earlier_node_whose_bytes_it_consumed(tmp_path: Path) -> None:
    first = _view_run(tmp_path, "first", "a", b"take", [])
    second = _view_run(tmp_path, "second", "b", b"take", [])
    example = _chain(tmp_path, first, second)
    assert example.nodes["b"].depends_on == ["a"]
    assert example.delivered_run == "second"
    assert [run.path for run in example.source_runs] == ["first", "second"]


def test_runs_that_share_no_bytes_are_refused(tmp_path: Path) -> None:
    first = _view_run(tmp_path, "first", "a", b"take", [])
    second = _view_run(tmp_path, "second", "b", b"another take", [])
    with pytest.raises(ValueError, match="consumes nothing an earlier run produced"):
        _chain(tmp_path, first, second)
