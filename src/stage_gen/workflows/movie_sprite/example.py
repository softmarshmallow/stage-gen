"""Make a movie-sprite example from a take run and the run that finished it."""

from __future__ import annotations

from stage_gen.examples import (
    Delivered,
    ImportRequest,
    PipelineRuns,
    WorkflowExample,
    import_pipeline_run,
    sha256,
    video_frames,
)

#: The node whose Matroska loop the consumer receives.
OUTPUT_NODE = "finish"


def deliver(runs: PipelineRuns) -> Delivered:
    """The character picture the take was drawn from, and the finished loop.

    A chain that adopted supplied footage has no character picture among its inputs.
    """
    reader, media = runs.request.reader, runs.request.media
    # The input picture, as bound by digest in the first run's inputs.
    source = next(iter(runs.declared_pictures()), None)
    inputs = (
        {}
        if source is None
        else {
            "character": {
                "kind": "image",
                "picture": media.still_alpha("input.webp", source, 720),
                "file": source.name,
            }
        }
    )
    out_dir, _ = runs.chosen[OUTPUT_NODE]
    loop = next(path for path, _ in runs.artifacts(OUTPUT_NODE) if path.suffix == ".mkv")
    manifest = reader.json(out_dir / "body" / "manifest.json")
    poster = media.sequence(
        "output-loop.webp",
        video_frames(reader.path(loop), alpha=True),
        round(1000 / manifest["playback_fps"]),
        [loop],
        "every frame of the loop at its playback rate",
        max_height=640,
        quality=72,
    )
    return Delivered(
        inputs=inputs,
        outputs={
            "loop": {
                "kind": "animation",
                "file": loop.name,
                "bytes": loop.stat().st_size,
                "sha256": sha256(loop),
                "poster": poster,
            }
        },
        metrics={
            "loop_seconds": manifest["playback_seconds"],
            "frames": manifest["frame_count"],
        },
    )


def import_example(request: ImportRequest) -> WorkflowExample:
    return import_pipeline_run(request, output_node=OUTPUT_NODE, deliver=deliver)
