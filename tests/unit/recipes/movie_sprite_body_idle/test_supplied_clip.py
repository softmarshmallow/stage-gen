"""Real provider-free decoding, portable publication, and finishing cache boundaries."""

from __future__ import annotations

import io
import json
import subprocess
import zipfile
from fractions import Fraction
from pathlib import Path

import pytest
from PIL import Image

from gnode import (
    ArtifactRights,
    BinaryArtifact,
    CacheDisposition,
    ProvenanceInput,
    SoftwareIdentity,
    write_artifact_with_provenance,
)
from stage_gen.pipeline import inspect, load_definition, plan, run
from stage_gen.recipes.movie_sprite_body_idle import create_pipeline
from stage_gen.recipes.movie_sprite_body_idle.examples.supplied_clip.make_inputs import (
    FRAME_COUNT,
    HEIGHT,
    WIDTH,
    make_frame,
    make_inputs,
)

EXAMPLE = (
    Path(__file__).resolve().parents[4]
    / "src/stage_gen/recipes/movie_sprite_body_idle/examples/supplied_clip/pipeline.py"
)


def _decode(path: Path) -> bytes:
    return subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-fps_mode",
            "passthrough",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgba",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    ).stdout


def _video_info(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


async def test_supplied_example_preserves_rgba_and_publishes_portable_loop(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    make_inputs(inputs)
    planned = plan(load_definition(str(EXAMPLE)), input_root=inputs)
    assert all(node.operation == "local" for node in planned.graph.nodes)
    first = await run(planned, output_root=tmp_path / "first", cache_root=tmp_path / "cache")
    assert first.summary.ok
    expected = b"".join(make_frame(index).tobytes() for index in range(FRAME_COUNT))
    assert _decode(first.run_dir / "body/loop.mkv") == expected
    with Image.open(first.run_dir / "body/canonical.png") as canonical:
        assert canonical.convert("RGBA").tobytes() == make_frame(0).tobytes()
    info = _video_info(first.run_dir / "body/loop.mkv")
    assert len(info["streams"]) == 1
    stream = info["streams"][0]
    assert (stream["width"], stream["height"]) == (WIDTH, HEIGHT)
    assert int(stream["nb_read_frames"]) == FRAME_COUNT
    assert Fraction(stream["r_frame_rate"]) == 4
    assert float(info["format"]["duration"]) == pytest.approx(3)
    with zipfile.ZipFile(first.run_dir / "body/frames.zip") as frames:
        names = sorted(name for name in frames.namelist() if name.endswith(".png"))
        assert len(names) == FRAME_COUNT
        for index, name in enumerate(names):
            with Image.open(io.BytesIO(frames.read(name))) as image:
                assert image.convert("RGBA").tobytes() == make_frame(index).tobytes()
    for path in first.run_dir.rglob("*.json"):
        assert str(tmp_path) not in path.read_text(encoding="utf-8")
    second = await run(planned, output_root=tmp_path / "second", cache_root=tmp_path / "cache")
    assert second.summary.ok
    assert all(node.cache is CacheDisposition.HIT for node in second.summary.nodes)
    assert (second.run_dir / "body/loop.mkv").read_bytes() == (
        first.run_dir / "body/loop.mkv"
    ).read_bytes()
    assert inspect(second.run_dir) == second.view


async def test_finishing_change_reuses_adoption_and_keeps_canonical(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    make_inputs(inputs)
    definition = create_pipeline(supplied_video_ref="actor.mkv", finish_ref="finish.json")
    original = plan(definition, input_root=inputs)
    first = await run(original, output_root=tmp_path / "first", cache_root=tmp_path / "cache")
    assert first.summary.ok
    settings = json.loads((inputs / "finish.json").read_text())
    settings["playback_seconds"] = 6
    (inputs / "finish.json").write_text(json.dumps(settings))
    with pytest.raises(ValueError, match="input changed"):
        await run(original, output_root=tmp_path / "stale", cache_root=tmp_path / "cache")
    assert not (tmp_path / "stale").exists()
    revised = plan(definition, input_root=inputs)
    second = await run(revised, output_root=tmp_path / "second", cache_root=tmp_path / "cache")
    assert second.summary.ok
    assert [node.cache for node in second.summary.nodes] == [
        CacheDisposition.HIT,
        CacheDisposition.MISS,
    ]
    assert (first.run_dir / "body/canonical.png").read_bytes() == (
        second.run_dir / "body/canonical.png"
    ).read_bytes()
    assert _decode(first.run_dir / "body/loop.mkv") == _decode(second.run_dir / "body/loop.mkv")
    info = _video_info(second.run_dir / "body/loop.mkv")
    assert float(info["format"]["duration"]) == pytest.approx(6)
    assert Fraction(info["streams"][0]["r_frame_rate"]) == 2


async def test_adoption_validates_decode_before_publishing_source(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    make_inputs(inputs)
    clip = inputs / "actor.mkv"
    clip.write_bytes(clip.read_bytes()[:16])
    planned = plan(
        create_pipeline(supplied_video_ref="actor.mkv", finish_ref="finish.json"),
        input_root=inputs,
        targets=["adopt"],
    )
    result = await run(planned, output_root=tmp_path / "failed", cache_root=tmp_path / "cache")
    assert not result.summary.ok
    assert not (result.run_dir / "body/source.mkv").exists()
    assert not result.summary.provider_operation_counts


async def test_corrupt_finished_cache_is_regenerated_from_reused_source(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    make_inputs(inputs)
    planned = plan(load_definition(str(EXAMPLE)), input_root=inputs)
    first = await run(planned, output_root=tmp_path / "first", cache_root=tmp_path / "cache")
    assert first.summary.ok
    corrupted = False
    for record_path in (tmp_path / "cache").rglob("record.json"):
        record = json.loads(record_path.read_text())
        for index, artifact in enumerate(record["artifacts"]):
            if artifact["artifact_ref"] == "body/loop.mkv":
                (record_path.parent / "artifacts" / f"{index}.bin").write_bytes(b"broken video")
                corrupted = True
    assert corrupted
    second = await run(planned, output_root=tmp_path / "second", cache_root=tmp_path / "cache")
    assert second.summary.ok
    assert [node.cache for node in second.summary.nodes] == [
        CacheDisposition.HIT,
        CacheDisposition.MISS,
    ]
    assert _decode(second.run_dir / "body/loop.mkv") == _decode(first.run_dir / "body/loop.mkv")


@pytest.mark.parametrize(
    "source_arguments",
    [{}, {"authoring_ref": "authoring.json", "supplied_video_ref": "actor.mkv"}],
)
def test_exactly_one_source_is_required(source_arguments: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        create_pipeline(finish_ref="finish.json", **source_arguments)


def test_invalid_finishing_geometry_is_rejected_while_planning(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    make_inputs(inputs)
    settings = json.loads((inputs / "finish.json").read_text())
    settings["source_mode"] = "rgba"
    settings["fixed_regions"] = [{"polygon_xy": [[30, 20], [60, 20], [60, 60], [30, 60]]}]
    (inputs / "finish.json").write_text(json.dumps(settings))
    with pytest.raises(ValueError, match="source_sha256"):
        plan(load_definition(str(EXAMPLE)), input_root=inputs)


def test_supplied_source_traversal_is_rejected_while_planning(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    make_inputs(inputs)
    definition = create_pipeline(supplied_video_ref="../actor.mkv", finish_ref="finish.json")
    with pytest.raises(ValueError):
        plan(definition, input_root=inputs)


async def test_supplied_provenance_preserves_original_identity_and_rights(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    make_inputs(inputs)
    rights = ArtifactRights(
        status="unreviewed",
        basis=["Original geometric test artwork."],
        reviewed_at=None,
    )
    write_artifact_with_provenance(
        inputs / "actor.mkv",
        BinaryArtifact(data=(inputs / "actor.mkv").read_bytes(), media_type="video/x-matroska"),
        ProvenanceInput(
            provider="local",
            model="geometric-example",
            prompt="Original supplied clip.",
            attempts=1,
            component=SoftwareIdentity(name="example-drawing", version="1"),
            tool=SoftwareIdentity(name="stage-gen", version="0.0.0"),
            rights=rights,
        ),
    )
    definition = create_pipeline(
        supplied_video_ref="actor.mkv",
        supplied_provenance_ref="actor.mkv.meta.json",
        finish_ref="finish.json",
    )
    result = await run(
        plan(definition, input_root=inputs),
        output_root=tmp_path / "run",
        cache_root=tmp_path / "cache",
    )
    assert result.summary.ok
    source = json.loads((result.run_dir / "body/source.json").read_text())
    assert source["origin"]["model"] == "geometric-example"
    assert source["origin"]["prompt"] == "Original supplied clip."
    final = json.loads((result.run_dir / "body/loop.mkv.meta.json").read_text())
    assert final["rights"] == rights.model_dump(mode="json")
    sidecar = json.loads((inputs / "actor.mkv.meta.json").read_text())
    sidecar["artifact"]["sha256"] = "0" * 64
    (inputs / "actor.mkv.meta.json").write_text(json.dumps(sidecar))
    with pytest.raises(ValueError, match="does not match"):
        plan(definition, input_root=inputs)


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "/private/tmp/old-render/input.png",
        "https://example.invalid/clip.mp4?token=private-example-value",
    ],
)
def test_unsafe_imported_origin_is_rejected_during_planning(
    tmp_path: Path,
    unsafe_value: str,
) -> None:
    inputs = tmp_path / "inputs"
    make_inputs(inputs)
    sidecar_path = write_artifact_with_provenance(
        inputs / "actor.mkv",
        BinaryArtifact(data=(inputs / "actor.mkv").read_bytes(), media_type="video/x-matroska"),
        ProvenanceInput(
            provider="local",
            model="geometric-example",
            prompt="Original supplied clip.",
            attempts=1,
            component=SoftwareIdentity(name="example-drawing", version="1"),
            tool=SoftwareIdentity(name="stage-gen", version="0.0.0"),
        ),
    )
    sidecar = json.loads(sidecar_path.read_text())
    sidecar["params"]["original_source"] = unsafe_value
    sidecar_path.write_text(json.dumps(sidecar))
    definition = create_pipeline(
        supplied_video_ref="actor.mkv",
        supplied_provenance_ref="actor.mkv.meta.json",
        finish_ref="finish.json",
    )
    with pytest.raises(ValueError):
        plan(definition, input_root=inputs)
    assert not (tmp_path / "run").exists()
