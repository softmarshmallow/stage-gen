"""The dust-sprite node family: one generated atlas and its admission."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from gnode import (
    AuthoredInput,
    Graph,
    GraphBuilder,
    ImageGenerationRequest,
    Node,
    NodeCard,
    NodeType,
    Port,
    PortRef,
    ViewArchetype,
    atomic_write_json,
    dependency_port,
)
from stage_gen.components._node_kit import (
    artifact_port,
    card_prompt,
    object_digest,
    record_port,
)
from stage_gen.components.game_fx._host import (
    _P,
    _PLATE_COMMON,
    _PROVIDER,
    IMAGE_FEATURES,
    FxCutInHost,
    _authored_references,
    _write_local_image,
)
from stage_gen.components.game_fx.models import (
    GameFx,
)
from stage_gen.components.game_fx.sprite import (
    DUST_ATLAS_KIND,
    SPRITE_CANVAS,
    canonicalize_dust_atlas,
    dust_atlas_contract,
    validate_dust_atlas,
)

#: The dust atlas's cache contract. Separate from the cut-in's: the two families share a
#: module and nothing else, and one shared constant would re-bill every cut-in plate to
#: reword a sentence about dust.
FX_SPRITE_DUST_CONTRACT_VERSION = "prepared-fx-sprite-dust-v1"
FX_SPRITE_DUST_VALIDATION_VERSION = "prepared-fx-sprite-dust-validation-v1"

FX_SPRITE_DUST_RAW_KIND = "fx-sprite-dust-raw-v1"
FX_SPRITE_DUST_ATLAS_KIND = DUST_ATLAS_KIND
FX_SPRITE_DUST_VALIDATION_KIND = "fx-sprite-dust-validation-v1"

FX_SPRITE_DUST_GENERATE = NodeType(
    type_id=f"{_P}/sprite/dust.generate",
    title="Ground dust atlas",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    features=IMAGE_FEATURES,
    policy=_PROVIDER,
    contract_version="fx-sprite-dust-v1",
)

FX_SPRITE_DUST_VALIDATE = NodeType(
    type_id=f"{_P}/sprite/dust.validate",
    title="Ground dust atlas admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="fx-sprite-dust-validate-v1",
)

FX_SPRITE_NODE_TYPES = (
    FX_SPRITE_DUST_GENERATE,
    FX_SPRITE_DUST_VALIDATE,
)


# ------------------------------------------------------------------- graph


#: What a particle must survive. Round one of the spike asked for dust and got beautiful
#: plates whose wisps, grit flecks and hairline outlines all became grey speckle at the size
#: a puff is actually drawn. The instruction that fixed it is not about dust at all: it is a
#: size, a floor on lobe scale, and an explicit list of what must not be drawn.
_SPRITE_SMALL = (
    "This is a small game particle: it must stay bold and readable when it is scaled down to "
    "about forty pixels across. Build it from only a few large simple rounded lobes. No thin "
    "wisps, no trailing streaks, no small scattered flecks or specks, no fine internal detail, "
    "no faint haze, no thin tapering tails."
)

#: The sheet's shape. The four silhouettes are named in the reading order
#: ``DUST_CELL_KINDS`` fixes, because that order is what binds a cell to the contact it
#: draws; the gate checks separation and solidity, and this sentence is what makes them
#: likely in the first place.
_DUST_TASK = (
    "A sprite sheet of cartoon dust puffs for a game, laid out as a two-by-two grid of four "
    "separate clouds on one canvas, each puff centred in its own quarter, well clear of the "
    "others and of the canvas edges, and all four drawn at a similar size. The four "
    "silhouettes differ, in reading order: the first low and wide, the second tall and "
    "rounded, the third small and compact, the fourth leaning to one side as if swept. "
    "{direction} " + _SPRITE_SMALL
)


def dust_content_task(direction: str) -> str:
    """The dust atlas brief: the sheet's shape, the package's register, the alpha rule."""

    return f"{_DUST_TASK.format(direction=direction.strip())} {_PLATE_COMMON}"


def sprite_dust_node_ids(*, prefix: str = "fx") -> tuple[str, str]:
    """The generate and validate ids the dust atlas occupies in a host graph."""

    base = f"{prefix}-sprite-dust"
    return (f"{base}-generate", f"{base}-validate")


def sprite_dust_artifact_refs() -> tuple[str, str, str]:
    """Every path the dust atlas writes: raw, canonical, validation."""

    return (
        "fx/sprite/dust.raw.png",
        "fx/sprite/dust.png",
        "fx/sprite/dust.validation.json",
    )


def add_sprite_nodes(
    builder: GraphBuilder,
    *,
    root: str,
    fx: GameFx,
    style_prompt: Callable[[str], str],
    direction_digests: Sequence[str] = (),
    domain: str = "fx",
    prefix: str = "fx",
    attempts_port: Callable[[str], Port] | None = None,
) -> list[str]:
    """Add the world-space sprite atlases the document declares.

    One family today. There is no review node: what a reviewer would judge on a cut-in is
    a face and a composition, and what makes dust right or wrong is whether four solid
    clouds came back separable — which the gate measures exactly, offline, for nothing.
    A second family that needs taste rather than measurement brings its own reviewer.
    """

    dust = None if fx.sprite is None else fx.sprite.dust
    if dust is None:
        return []
    references = {entry.reference_id: entry for entry in fx.references}
    authored = tuple(
        AuthoredInput(
            label=reference_id,
            ref=references[reference_id].source,
            sha256=references[reference_id].source_sha256,
        )
        for reference_id in dust.reference_ids
    )
    generate_id, validate_id = sprite_dust_node_ids(prefix=prefix)
    raw_ref, atlas_ref, validation_ref = sprite_dust_artifact_refs()
    direction = object_digest(dust.model_dump(mode="json"))
    params = {"sprite": "dust"}

    ports: list[Port] = [artifact_port("image", raw_ref, FX_SPRITE_DUST_RAW_KIND)]
    if attempts_port is not None:
        ports.append(attempts_port(generate_id))
    produced = builder.add(
        FX_SPRITE_DUST_GENERATE,
        generate_id,
        domain=domain,
        description="generate the ground-dust atlas",
        depends_on=(root,),
        cache_depends_on=(),
        params=params,
        input_digests=(
            *direction_digests,
            object_digest({"contract": FX_SPRITE_DUST_CONTRACT_VERSION}),
            direction,
            *(entry.sha256 for entry in authored),
        ),
        ports=tuple(ports),
        card=NodeCard(
            prompt=style_prompt(dust_content_task(dust.prompt)),
            authored_inputs=authored,
        ),
    )
    validated = builder.add(
        FX_SPRITE_DUST_VALIDATE,
        validate_id,
        domain=domain,
        description="admit the dust atlas, lift its body opaque, and measure its cells",
        depends_on=(produced.node_id,),
        params=params,
        input_digests=(object_digest({"contract": FX_SPRITE_DUST_VALIDATION_VERSION}),),
        ports=(
            artifact_port("image", atlas_ref, FX_SPRITE_DUST_ATLAS_KIND),
            record_port("validation", validation_ref, FX_SPRITE_DUST_VALIDATION_KIND),
        ),
        card=NodeCard(reference_inputs=(PortRef(node_id=produced.node_id, port_id="image"),)),
        duration_seconds=2.0,
    )
    return [validated.node_id]


def sprite_dust_generate_request(host: FxCutInHost, node: Node) -> ImageGenerationRequest:
    """The exact image request the dust generate node sends.

    The gate runs inside the request, which is what makes a sheet that came back as one
    merged mass or a spray of specks a retry rather than a dead run - the same shape of
    failure the six-attempt owner exists for, and offline besides.
    """

    dust = None if host.fx.sprite is None else host.fx.sprite.dust
    if dust is None:
        raise ValueError("dust atlas node on a document that declares no sprite.dust")
    return ImageGenerationRequest(
        prompt=card_prompt(node),
        artifact_path=host.run_dir / node.port("image").artifact_ref,
        input_references=_authored_references(host, dust.reference_ids),
        quality="high",
        background="transparent",
        output_format="png",
        size=f"{SPRITE_CANVAS[0]}x{SPRITE_CANVAS[1]}",
        timeout_seconds=600,
        metadata={
            "checkpoint": "fx",
            "effect": "sprite",
            "sprite": "dust",
            "layout": dust.layout,
            "alpha_policy": dust.alpha_policy,
        },
        validate=lambda artifact: validate_dust_atlas(artifact.data),
    )


def derive_sprite_dust_validation(raw: bytes) -> tuple[bytes, dict[str, object], dict[str, Any]]:
    """Canonical atlas, the record a consumer reads, and the facts behind it."""

    canonical, facts = canonicalize_dust_atlas(raw)
    record: dict[str, object] = {
        "schema_version": 1,
        "kind": FX_SPRITE_DUST_VALIDATION_KIND,
        "sprite": "dust",
        "pixel_rewrite": facts["pixel_rewrite"],
        "source": facts["source"],
        "canonical": facts["canonical"],
        **dust_atlas_contract(facts),
    }
    return canonical, record, facts


async def write_sprite_dust_validation(
    host: FxCutInHost,
    graph: Graph,
    node: Node,
    *,
    read: Callable[[str], bytes],
) -> dict[str, object]:
    """Run one dust validate node end to end: canonical atlas and record, both written."""

    _producer, raw_port = dependency_port(graph, node, kind=FX_SPRITE_DUST_RAW_KIND)
    raw = read(raw_port.artifact_ref)
    canonical, record, _facts = derive_sprite_dust_validation(raw)
    await _write_local_image(
        host,
        host.run_dir / node.port("image").artifact_ref,
        canonical,
        prompt=(
            "Clear the already-transparent exterior to alpha 0, lift the near-opaque body to "
            "fully opaque, and erase the specks the gate measured around; nothing else is "
            "rewritten."
        ),
        inputs=((raw_port.artifact_ref, raw),),
        validation=record,
        model=str(record["kind"]),
    )
    atomic_write_json(host.run_dir / node.port("validation").artifact_ref, record)
    return record


__all__ = [
    "FX_SPRITE_DUST_ATLAS_KIND",
    "FX_SPRITE_DUST_CONTRACT_VERSION",
    "FX_SPRITE_DUST_GENERATE",
    "FX_SPRITE_DUST_RAW_KIND",
    "FX_SPRITE_DUST_VALIDATE",
    "FX_SPRITE_DUST_VALIDATION_KIND",
    "FX_SPRITE_DUST_VALIDATION_VERSION",
    "FX_SPRITE_NODE_TYPES",
    "add_sprite_nodes",
    "derive_sprite_dust_validation",
    "dust_content_task",
    "sprite_dust_artifact_refs",
    "sprite_dust_generate_request",
    "sprite_dust_node_ids",
    "write_sprite_dust_validation",
]
