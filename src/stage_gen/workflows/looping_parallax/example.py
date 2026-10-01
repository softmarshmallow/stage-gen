"""Make a looping-parallax example from the run that composed the background."""

from __future__ import annotations

from stage_gen.examples import (
    Delivered,
    ImportRequest,
    PipelineRuns,
    WorkflowExample,
    import_pipeline_run,
    sha256,
)

#: The node whose manifest and preview the consumer receives.
OUTPUT_NODE = "compose"


def deliver(runs: PipelineRuns) -> Delivered:
    """Every supplied layer, and the composed background with its preview frame."""
    request, reader, media = runs.request, runs.request.reader, runs.request.media
    inputs: dict[str, dict[str, object]] = {}
    for path, digest in runs.declared_inputs().items():
        source = request.base / path
        if path.endswith(".png") and source.is_file() and sha256(reader.path(source)) == digest:
            inputs[source.stem] = {
                "kind": "image",
                "picture": media.still_alpha(f"input-{source.stem}.webp", source),
                "file": source.name,
            }
    artifacts = {path.name: path for path, _ in runs.artifacts(OUTPUT_NODE)}
    manifest, preview = artifacts["manifest.json"], artifacts["preview.png"]
    layers = reader.json(manifest)["layers"]
    return Delivered(
        inputs=inputs,
        outputs={
            "background": {
                "kind": "image",
                "file": manifest.name,
                "bytes": manifest.stat().st_size,
                "sha256": sha256(manifest),
                "poster": media.still("output-preview.webp", reader.path(preview), 640),
            }
        },
        metrics={"layers": len(layers)},
    )


def import_example(request: ImportRequest) -> WorkflowExample:
    return import_pipeline_run(request, output_node=OUTPUT_NODE, deliver=deliver)
