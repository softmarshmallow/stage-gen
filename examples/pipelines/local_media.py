"""A provider-free custom pipeline: authored palette -> PNG + WAV -> JSON catalog.

Load this file's ``pipeline`` export with the public CLI or Python loader. Create
``palette.json`` in your input directory containing {"color": [48, 132, 184]}.
The generated media are valid synthetic examples, with no game/runtime contract.
"""

from __future__ import annotations

import io
import json
import math
import struct
import wave

from PIL import Image

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
from stage_gen.pipeline import (
    InputFiles,
    NodeBinding,
    PipelineContext,
    artifact_port,
    define,
    record_port,
)

IMAGE = NodeType("example/swatch.create", "Color swatch", ViewArchetype.IMAGE, "local", "1")
TONE = NodeType("example/tone.create", "Sine tone", ViewArchetype.SOUND, "local", "1")
CATALOG = NodeType("example/catalog.create", "Asset catalog", ViewArchetype.PACKAGE, "local", "1")


def build(inputs: InputFiles) -> Graph:
    builder = GraphBuilder(profile=BindingTable(()))
    builder.add(
        IMAGE,
        "swatch",
        domain="assets",
        description="Create an original solid color swatch",
        input_digests=(inputs.digest("palette.json"),),
        ports=(artifact_port("image", "swatch.png", "image-v1"),),
    )
    builder.add(
        TONE,
        "tone",
        domain="assets",
        description="Synthesize a short 440 Hz reference tone",
        ports=(artifact_port("audio", "tone.wav", "audio-v1"),),
    )
    builder.add(
        CATALOG,
        "catalog",
        domain="assets",
        description="Index the generated image and audio",
        depends_on=("swatch", "tone"),
        ports=(record_port("catalog", "catalog.json", "asset-catalog-v1"),),
    )
    return seal_graph(
        Graph,
        schema_version=1,
        kind="example-custom-graph-v1",
        resources=builder.resources(),
        nodes=builder.nodes,
        terminal_node_id="catalog",
    )


async def image(node: Node, context: PipelineContext) -> NodeExecutionResult:
    color = json.loads(context.read_input("palette.json"))["color"]
    if len(color) != 3 or any(
        type(channel) is not int or not 0 <= channel <= 255 for channel in color
    ):
        raise ValueError("palette color must have three integer channels between 0 and 255")
    output = io.BytesIO()
    Image.new("RGB", (64, 64), tuple(color)).save(output, format="PNG")
    return await context.publish(
        node, {"image": output.getvalue()}, media_types={"image": "image/png"}
    )


async def tone(node: Node, context: PipelineContext) -> NodeExecutionResult:
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16_000)
        writer.writeframes(
            b"".join(
                struct.pack("<h", round(8192 * math.sin(2 * math.pi * 440 * index / 16_000)))
                for index in range(4_000)
            )
        )
    return await context.publish(
        node, {"audio": output.getvalue()}, media_types={"audio": "audio/wav"}
    )


async def catalog(node: Node, context: PipelineContext) -> NodeExecutionResult:
    images = Image.open(io.BytesIO(context.read_artifact("swatch.png")))
    with wave.open(io.BytesIO(context.read_artifact("tone.wav"))) as audio:
        document = {
            "kind": "asset-catalog-v1",
            "image": {"ref": "swatch.png", "width": images.width, "height": images.height},
            "audio": {
                "ref": "tone.wav",
                "sample_rate": audio.getframerate(),
                "frames": audio.getnframes(),
            },
        }
    return await context.publish(node, {"catalog": json.dumps(document).encode()})


def admit_image(_node: Node, payloads: tuple[bytes, ...]) -> bool:
    try:
        with Image.open(io.BytesIO(payloads[0])) as image:
            image.verify()
        return True
    except (OSError, ValueError):
        return False


def admit_audio(_node: Node, payloads: tuple[bytes, ...]) -> bool:
    try:
        with wave.open(io.BytesIO(payloads[0])) as audio:
            return bool(audio.getnframes() == 4_000 and audio.getframerate() == 16_000)
    except (EOFError, wave.Error):
        return False


pipeline = define(
    "local-media",
    title="Local image and audio assets",
    build=build,
    bindings=(
        NodeBinding(IMAGE, image, admit_image),
        NodeBinding(TONE, tone, admit_audio),
        NodeBinding(CATALOG, catalog),
    ),
)
