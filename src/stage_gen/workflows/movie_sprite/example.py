"""Make a movie-sprite example from the gnode run that drew or adopted a clip and finished it."""

from __future__ import annotations

from stage_gen.examples import (
    Delivered,
    GnodeRun,
    ImportRequest,
    WorkflowExample,
    import_gnode_run,
    sha256,
    video_frames,
)
from stage_gen.workflows._gnode import GnodeWorkflow


def deliver(run: GnodeRun) -> Delivered:
    """The character picture a take was drawn from, if any, and the finished loop.

    A run that finished supplied footage has no character picture among its inputs.
    """
    reader, media = run.request.reader, run.request.media
    character = run.input_file("character")
    inputs = (
        {}
        if character is None
        else {
            "character": {
                "kind": "image",
                "picture": media.still_alpha("input.webp", character[0], 720),
                "file": character[1],
            }
        }
    )
    loop = run.output("loop")
    manifest = reader.json(run.output("manifest"))
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
    workflow = GnodeWorkflow.read(__package__ or "stage_gen.workflows.movie_sprite")
    return import_gnode_run(
        request, type_of=lambda step: workflow.types[step].type_id, deliver=deliver
    )
