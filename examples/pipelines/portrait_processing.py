"""Deterministic portrait crop, patch restoration, and animation through the public harness.

The example owns its authored face box and synthetic donor patch. It does not infer
facial geometry or claim semantic/temporal acceptance. Run write_example_inputs()
in a caller-owned directory to produce original synthetic input pixels.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from gnode import (
    BindingTable,
    Graph,
    GraphBuilder,
    Node,
    NodeExecutionResult,
    NodeType,
    ViewArchetype,
    seal_graph,
)
from stage_gen.components.portrait_motion.face_crop import create_working_crop, restore_feature
from stage_gen.pipeline import (
    InputFiles,
    NodeBinding,
    PipelineContext,
    artifact_port,
    define,
    record_port,
)

SOURCE = NodeType("example/portrait.import", "Source portrait", ViewArchetype.SOURCE, "local", "1")
CROP = NodeType("example/portrait.crop", "Working crop", ViewArchetype.TRANSFORM, "local", "1")
PATCH = NodeType("example/portrait.patch", "Synthetic donor", ViewArchetype.IMAGE, "local", "1")
RESTORE = NodeType(
    "example/portrait.restore", "Restore and preview", ViewArchetype.REVIEW, "local", "1"
)


def _png(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def write_example_inputs(root: Path) -> None:
    """Create original synthetic pixels and a caller-authored face box."""
    root.mkdir(parents=True, exist_ok=False)
    image = Image.new("RGBA", (192, 256), (22, 38, 58, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse((40, 24, 152, 172), fill=(212, 158, 120, 255))
    draw.ellipse((65, 73, 79, 85), fill=(40, 30, 30, 255))
    draw.ellipse((114, 73, 128, 85), fill=(40, 30, 30, 255))
    draw.line((77, 124, 116, 124), fill=(116, 48, 50, 255), width=3)
    (root / "source.png").write_bytes(_png(image))
    (root / "face.json").write_text(json.dumps({"box": [40, 24, 152, 172]}))


def build(inputs: InputFiles) -> Graph:
    builder = GraphBuilder(profile=BindingTable(()))
    builder.add(
        SOURCE,
        "source",
        domain="portrait",
        description="Import the caller's portrait pixels",
        input_digests=(inputs.digest("source.png"),),
        ports=[artifact_port("image", "source.png", "image-v1")],
    )
    builder.add(
        CROP,
        "crop",
        domain="portrait",
        description="Crop and uniformly resize the authored face region",
        depends_on=["source"],
        input_digests=(inputs.digest("face.json"),),
        ports=[
            artifact_port("work", "crop/work.png", "image-v1"),
            record_port("transform", "crop/transform.json", "face-transform-v1"),
        ],
    )
    builder.add(
        PATCH,
        "patch",
        domain="portrait",
        description="Create a deterministic donor and localized mask",
        depends_on=["crop"],
        ports=[
            artifact_port("donor", "patch/donor.png", "image-v1"),
            artifact_port("mask", "patch/mask.png", "image-v1"),
        ],
    )
    builder.add(
        RESTORE,
        "restore",
        domain="portrait",
        description="Restore only masked pixels and verify exterior preservation",
        depends_on=["source", "crop", "patch"],
        ports=[
            artifact_port("image", "restored.png", "image-v1"),
            artifact_port("preview", "preview.webp", "animation-v1"),
            record_port("checks", "checks.json", "pixel-checks-v1"),
        ],
    )
    return seal_graph(
        Graph,
        schema_version=1,
        kind="portrait-processing-example-v1",
        resources=builder.resources(),
        nodes=builder.nodes,
        terminal_node_id="restore",
    )


async def source(node: Node, context: PipelineContext) -> NodeExecutionResult:
    data = context.read_input("source.png")
    with Image.open(io.BytesIO(data)) as image:
        image.verify()
    return await context.publish(node, {"image": data}, media_types={"image": "image/png"})


async def crop(node: Node, context: PipelineContext) -> NodeExecutionResult:
    with Image.open(io.BytesIO(context.read_artifact("source.png"))) as image:
        box = json.loads(context.read_input("face.json"))["box"]
        work, transform = create_working_crop(image, box, work_size=(128, 128))
    return await context.publish(
        node, {"work": _png(work), "transform": json.dumps(transform).encode()}
    )


async def patch(node: Node, context: PipelineContext) -> NodeExecutionResult:
    with Image.open(io.BytesIO(context.read_artifact("crop/work.png"))) as work:
        donor = work.convert("RGB")
    ImageDraw.Draw(donor).ellipse((54, 76, 76, 86), fill=(100, 32, 44))
    mask = Image.new("L", donor.size)
    ImageDraw.Draw(mask).ellipse((52, 74, 78, 88), fill=255)
    return await context.publish(node, {"donor": _png(donor), "mask": _png(mask)})


async def restore(node: Node, context: PipelineContext) -> NodeExecutionResult:
    with Image.open(io.BytesIO(context.read_artifact("source.png"))) as image:
        original = image.convert("RGBA")
    with Image.open(io.BytesIO(context.read_artifact("patch/donor.png"))) as image:
        donor = image.convert("RGB")
    with Image.open(io.BytesIO(context.read_artifact("patch/mask.png"))) as image:
        mask = np.asarray(image, dtype=np.float64) / 255.0
    transform = json.loads(context.read_artifact("crop/transform.json"))
    restored, affected = restore_feature(original, donor, mask, transform)
    before, after = np.asarray(original), np.asarray(restored)
    checks = {
        "outside_mask_identical": bool(np.array_equal(before[affected == 0], after[affected == 0])),
        "alpha_identical": bool(np.array_equal(before[..., 3], after[..., 3])),
        "changed_pixels": int(np.any(before != after, axis=2).sum()),
        "semantic_review": "not_performed",
        "temporal_review": "not_performed",
    }
    if not checks["outside_mask_identical"] or not checks["alpha_identical"]:
        raise ValueError("Portrait processing changed pixels outside its allowed mask")
    animation = io.BytesIO()
    original.save(
        animation,
        format="WEBP",
        save_all=True,
        append_images=[restored],
        duration=[400, 400],
        loop=0,
        lossless=True,
    )
    return await context.publish(
        node,
        {
            "image": _png(restored),
            "preview": animation.getvalue(),
            "checks": json.dumps(checks).encode(),
        },
    )


pipeline = define(
    "portrait-processing",
    title="Portrait crop and patch processing",
    build=build,
    bindings=[
        NodeBinding(SOURCE, source),
        NodeBinding(CROP, crop),
        NodeBinding(PATCH, patch),
        NodeBinding(RESTORE, restore),
    ],
)
