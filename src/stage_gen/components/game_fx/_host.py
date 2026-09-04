"""What both fx node families need from a host, and the helpers both write with.

The cut-in and the dust sprite are two families with one host: the authored fx document,
the run they write into, the package that holds their references.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from gnode import (
    BinaryArtifact,
    Graph,
    ImageReference,
    InputProvenance,
    Node,
    NodePolicy,
    PortRef,
    ProvenanceInput,
    SoftwareIdentity,
    write_artifact_with_provenance_async,
)
from stage_gen.canonical import content_sha256
from stage_gen.components.game_fx.cut_in import (
    CUT_IN_FRAME,
    CUT_IN_PORTRAIT,
    CutInPlate,
)
from stage_gen.components.game_fx.models import (
    CutInFrameDirection,
    CutInPortraitDirection,
    GameFx,
)
from stage_gen.media import data_url

_P = "2d/fx"
_PROVIDER = NodePolicy(max_attempts=6)

IMAGE_FEATURES = ("transparent_background", "reference_images")
STRUCTURED_FEATURES = ("structured_output", "image_input")
TOOL_LOOP_FEATURES = ("tool_use", "image_input")
#: What the agent looks at: the composition at this width, JPEG, over the stage colour.
_RENDER_WIDTH = 768
_RENDER_STAGE = (28, 34, 48)
_START_SCALE = 0.5


# ------------------------------------------------------------------ prompt


_PLATE_COMMON = (
    "Everything outside the described subject is fully transparent, alpha 0, with no glow, "
    "drop shadow, colour wash, backdrop, vignette, or scenery behind it. No text, numbers, "
    "labels, logos, signatures, or watermarks anywhere."
)


# ----------------------------------------------------------------- host


class _PackageFile(Protocol):
    """The two facts the node set needs about an authored file, however a host stores it."""

    @property
    def data(self) -> bytes: ...

    @property
    def sha256(self) -> str: ...


@dataclass(frozen=True)
class FxCutInHost:
    """Everything the shared node set needs from whichever recipe hosts it."""

    fx: GameFx
    run_dir: Path
    package_id: str
    file: Callable[[str], _PackageFile]
    component: SoftwareIdentity
    tool: SoftwareIdentity


def cut_in_direction(
    fx: GameFx, node: Node
) -> tuple[CutInPlate, CutInFrameDirection | CutInPortraitDirection]:
    """Which plate a node works on, read off its params."""

    if fx.cut_in is None:
        raise ValueError(f"node {node.node_id} needs a cut_in the document does not declare")
    if str(node.params["plate"]) == "frame":
        return CUT_IN_FRAME, fx.cut_in.frame
    return CUT_IN_PORTRAIT, fx.cut_in.portrait(str(node.params["portrait_id"]))


def _authored_references(
    host: FxCutInHost, reference_ids: Sequence[str]
) -> tuple[ImageReference, ...]:
    by_id = {entry.reference_id: entry for entry in host.fx.references}
    values = []
    for reference_id in reference_ids:
        source = by_id[reference_id].source
        package_file = host.file(source)
        values.append(
            ImageReference(
                url=data_url(package_file.data, _media_type(source)),
                provenance_ref=f"package://{host.package_id}/{source}#sha256={package_file.sha256}",
            )
        )
    return tuple(values)


def subject_port(
    node: Node, direction: CutInFrameDirection | CutInPortraitDirection
) -> PortRef | None:
    """The port a portrait's drawn subject comes from, or None if it has none.

    ``add_cut_in_nodes`` writes it last on the card at both the generate and the review
    end, which is the whole convention: the plan card and the provider request read the
    same entry, so they cannot name different images.
    """

    if not isinstance(direction, CutInPortraitDirection) or direction.subject is None:
        return None
    card = node.card
    if card is None or not card.reference_inputs:
        raise ValueError(f"node {node.node_id} draws a subject its card does not name")
    return card.reference_inputs[-1]


def _produced_reference(
    graph: Graph, port_ref: PortRef, read: Callable[[str], bytes]
) -> tuple[str, bytes]:
    artifact_ref = graph.node(port_ref.node_id).port(port_ref.port_id).artifact_ref
    return artifact_ref, read(artifact_ref)


# ----------------------------------------------------------------- helpers


async def _write_local_image(
    host: FxCutInHost,
    path: Path,
    data: bytes,
    *,
    prompt: str,
    inputs: Sequence[tuple[str, bytes]],
    validation: Mapping[str, object],
    model: str,
) -> Path:
    return await write_artifact_with_provenance_async(
        path,
        BinaryArtifact(data=data, media_type="image/png"),
        ProvenanceInput(
            provider="local",
            model=model,
            prompt=prompt,
            refs=[ref for ref, _ in inputs],
            inputs=[
                InputProvenance(
                    ref=ref,
                    sha256=content_sha256(payload),
                    source="content",
                    bytes=len(payload),
                    media_type="image/png",
                )
                for ref, payload in inputs
            ],
            params={"version": host.component.version},
            validation=dict(validation),
            component=host.component,
            tool=host.tool,
            attempts=1,
        ),
    )


def _media_type(path: str) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }[PurePosixPath(path).suffix.lower()]


__all__ = [
    "FxCutInHost",
    "IMAGE_FEATURES",
    "STRUCTURED_FEATURES",
    "TOOL_LOOP_FEATURES",
    "cut_in_direction",
    "subject_port",
]
