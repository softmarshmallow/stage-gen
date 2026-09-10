"""Every storefront node's work, dispatched by type and cached by content.

The shape is deliberately flat: resolve, compile the look once, write the words,
and then four independent branches that each draw one picture, cut it to its ship
canvas, prove that canvas, and get judged. Nothing here composes anything with
anything else, which is why this recipe is the cheap one.

Review nodes succeed whether they admit or reject. A rejection is a result, not a
failure: the scheduler must still reach the terminal so the package is written
with a status for every surface, and redrawing a rejected picture is a deliberate,
priced decision rather than an automatic retry.
"""

from __future__ import annotations

import json
from io import BytesIO
from typing import TYPE_CHECKING

from PIL import Image, ImageOps

from gnode import (
    ArtifactRights,
    BinaryArtifact,
    ImageGenerationRequest,
    ImageGenerationService,
    ImageReference,
    NodeExecutionResult,
    NodeType,
    ProvenanceInput,
    SoftwareIdentity,
    StructuredGenerationService,
    StructuredReference,
    atomic_write_json,
    inspect_image,
    write_artifact_with_provenance_async,
)
from stage_gen.canonical import content_sha256
from stage_gen.identity import STAGE_GEN_TOOL
from stage_gen.media import data_url
from stage_gen.media.codec import encode_png
from stage_gen.media.images import normalize_png_cover
from stage_gen.recipes.node_handler import NodeMethod, RecipeNodeHandler
from stage_gen.recipes.storefront import models
from stage_gen.recipes.storefront.storefront_graph import (
    REVIEW_PROXY_LONG_EDGE,
    STOREFRONT_CACHE_NAMESPACE,
    STOREFRONT_CACHE_RECORD_KIND,
    StorefrontGraph,
)
from stage_gen.recipes.storefront.storefront_prompts import (
    SYSTEM_PROMPT,
    schema_description,
    surface_prompt,
)
from stage_gen.recipes.storefront.storefront_request import (
    DIRECTION_REF,
    INVENTORY_REF,
    LISTING_REF,
    drawn_ref,
    proxy_ref,
    record_ref,
    review_ref,
    shipped_ref,
    validation_ref,
)
from stage_gen.recipes.storefront.storefront_types import (
    DIRECTION_COMPILE,
    INVENTORY_KIND,
    LISTING_COMPILE,
    STOREFRONT_CLOSE,
    STOREFRONT_KIND,
    STOREFRONT_RESOLVE,
    SURFACE_GENERATE,
    SURFACE_NORMALIZE,
    SURFACE_PROXY,
    SURFACE_RECORD,
    SURFACE_RECORD_KIND,
    SURFACE_REVIEW,
    SURFACE_VALIDATE,
    SURFACE_VALIDATION_KIND,
)
from stage_gen.recipes.storefront.surfaces import surface
from stage_gen.recipes.structured_transport import (
    AttemptLedger,
    generate_structured,
    known_cost,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from gnode import Node
    from stage_gen.recipes.storefront.storefront_request import ResolvedStorefront

STOREFRONT_COMPONENT = SoftwareIdentity(name="@stage-gen/storefront", version="1")

#: Every artifact this recipe writes is exploration. A storefront face is exactly
#: the kind of artwork that must not slip into publication because a run passed:
#: publication is a separate human decision over a package where every surface was
#: admitted, and this recipe never makes it.
STOREFRONT_RIGHTS = ArtifactRights(
    status="unreviewed",
    attribution=[],
    basis=["exploratory storefront generation; publication not authorized"],
    reviewed_at=None,
)

STRUCTURED_TIMEOUT_S = 600.0
IMAGE_TIMEOUT_S = 1_800.0


def make_image_proxy(data: bytes, *, long_edge: int) -> bytes:
    """Downscale for review; never a package asset and never a generation reference."""

    with Image.open(BytesIO(data)) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    if max(image.size) > long_edge:
        image.thumbnail((long_edge, long_edge), Image.Resampling.LANCZOS)
    return encode_png(image, compress_level=6)


def _document_bytes(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")


def flatten_alpha(data: bytes) -> tuple[bytes, bool]:
    """Drop an alpha band over white; a storefront icon refuses one outright.

    Reported rather than done silently: a picture that arrived with alpha is a
    picture the route drew differently from what was asked, and the validation
    record should say so even though the shipped bytes are clean.
    """

    with Image.open(BytesIO(data)) as opened:
        image = ImageOps.exif_transpose(opened)
        if "A" not in image.getbands() and "transparency" not in image.info:
            return data, False
        flattened = Image.new("RGB", image.size, (255, 255, 255))
        rgba = image.convert("RGBA")
        flattened.paste(rgba, mask=rgba.getchannel("A"))
    return encode_png(flattened), True


class StorefrontNodeHandler(RecipeNodeHandler):
    """One run's node work: cache first, then the type's own handler."""

    def __init__(
        self,
        graph: StorefrontGraph,
        resolved: ResolvedStorefront,
        *,
        run_dir: Path,
        cache_dir: Path,
        structured_service: StructuredGenerationService[object] | None = None,
        image_service: ImageGenerationService | None = None,
    ) -> None:
        self._resolved = resolved
        self._structured = structured_service
        self._images = image_service
        super().__init__(
            graph,
            run_dir=run_dir,
            cache_dir=cache_dir,
            namespace=STOREFRONT_CACHE_NAMESPACE,
            record_kind=STOREFRONT_CACHE_RECORD_KIND,
        )
        self._registry.validate_graph_types(graph.nodes)

    def _handlers(self) -> tuple[tuple[NodeType, NodeMethod], ...]:
        return (
            (STOREFRONT_RESOLVE, self._write_storefront),
            (DIRECTION_COMPILE, self._direction),
            (LISTING_COMPILE, self._listing),
            (SURFACE_GENERATE, self._generate),
            (SURFACE_NORMALIZE, self._normalize),
            (SURFACE_VALIDATE, self._validate),
            (SURFACE_PROXY, self._proxy),
            (SURFACE_REVIEW, self._review),
            (SURFACE_RECORD, self._record),
            (STOREFRONT_CLOSE, self._close),
        )

    # ------------------------------------------------------------------ shared

    async def _write_local(
        self,
        ref: str,
        data: bytes,
        *,
        media_type: str,
        model: str,
        prompt: str,
        refs: Sequence[str] = (),
        params: Mapping[str, object] | None = None,
        validation: Mapping[str, object] | None = None,
        rights: ArtifactRights = STOREFRONT_RIGHTS,
    ) -> None:
        await write_artifact_with_provenance_async(
            self._path(ref),
            BinaryArtifact(data=data, media_type=media_type),
            ProvenanceInput(
                schema_version=2,
                provider="local",
                model=model,
                prompt=prompt,
                refs=list(refs),
                inputs=[],
                params={
                    "publication_authorized": False,
                    "recipe": "storefront",
                    **(dict(params) if params else {}),
                },
                validation=dict(validation or {"status": "pass"}),
                component=STOREFRONT_COMPONENT,
                tool=STAGE_GEN_TOOL,
                attempts=1,
                rights=rights,
            ),
        )

    async def _write_ledger(self, node: Node, ledger: AttemptLedger) -> None:
        """The attempts port is written whether or not anything was rejected."""

        path = self._path(node.port("attempts").artifact_ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(ledger.encoded())

    def _run_ref(self, ref: str) -> str:
        return f"run://{ref}#sha256={content_sha256(self._path(ref).read_bytes())}"

    def _package_ref(self, source: str, sha256: str) -> str:
        return f"package://{self._resolved.storefront_id}/{source}#sha256={sha256}"

    def _require_structured(self, node: Node) -> tuple[StructuredGenerationService[object], str]:
        if self._structured is None:
            raise ValueError(f"node {node.node_id} requires a structured generation service")
        return self._structured, self._card_prompt(node)

    def _image_references(self) -> tuple[ImageReference, ...]:
        """The authored art, as pixels, in the order the package declares it."""

        return tuple(
            ImageReference(
                url=data_url(reference.data, reference.media_type),
                provenance_ref=self._package_ref(reference.source, reference.sha256),
            )
            for reference in self._resolved.references
        )

    def _structured_references(self) -> tuple[StructuredReference, ...]:
        return tuple(
            StructuredReference(
                url=data_url(reference.data, reference.media_type),
                provenance_ref=self._package_ref(reference.source, reference.sha256),
            )
            for reference in self._resolved.references
        )

    def _direction_document(self) -> models.StorefrontDirection:
        return models.StorefrontDirection.model_validate_json(
            self._path(DIRECTION_REF).read_bytes()
        )

    def _direction_json(self) -> str:
        """The sealed direction as the text a downstream prompt is shown."""

        document = self._direction_document().model_dump(mode="json")
        return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False)

    @staticmethod
    def _surface_id(node: Node) -> str:
        return str(node.params["surface_id"])

    # ------------------------------------------------------------------- nodes

    async def _write_storefront(self, node: Node) -> NodeExecutionResult:
        source = self._resolved.source
        document = {
            "schema_version": 1,
            "kind": STOREFRONT_KIND,
            "storefront_id": source.storefront_id,
            "display_name": source.display_name,
            "revision": source.revision,
            "positioning": self._resolved.positioning_text,
            "positioning_sha256": self._resolved.positioning_sha256,
            "references": [
                {
                    "reference_id": reference.reference_id,
                    "source": reference.source,
                    "source_sha256": reference.sha256,
                }
                for reference in self._resolved.references
            ],
            "surfaces": [
                {
                    "surface_id": item.surface_id,
                    "kind": item.kind.value,
                    "source": item.source.value,
                    "ship_size": surface(item.kind.value).ship_size,
                    "draw_size": surface(item.kind.value).draw_size,
                    "draw": self._resolved.draws.draw(item.surface_id),
                }
                for item in source.surfaces
            ],
            "publication_authorized": False,
        }
        await self._write_local(
            node.port("storefront").artifact_ref,
            _document_bytes(document),
            media_type="application/json",
            model="storefront-resolve",
            prompt="Canonicalize the authored storefront package into the run.",
            refs=[
                self._package_ref(reference.source, reference.sha256)
                for reference in self._resolved.references
            ],
        )
        return self._result(node)

    async def _direction(self, node: Node) -> NodeExecutionResult:
        service, card_prompt = self._require_structured(node)
        operation_id = "storefront.direction"
        ledger = AttemptLedger(operation_id=operation_id)
        prompt = f"{card_prompt}\n\nPOSITIONING NOTE\n{self._resolved.positioning_text}"

        def accept(value: models.StorefrontDirection) -> list[str]:
            if value.storefront_id != self._resolved.storefront_id:
                return [f"storefront_id must be {self._resolved.storefront_id!r}"]
            return []

        try:
            _value, operation = await generate_structured(
                service,
                model_type=models.StorefrontDirection,
                operation_id=operation_id,
                system=SYSTEM_PROMPT,
                description=schema_description(operation_id),
                prompt=prompt,
                artifact_path=self._path(DIRECTION_REF),
                ledger=ledger,
                references=self._structured_references(),
                semantic_validate=accept,
                max_tokens=12_000,
                timeout_seconds=STRUCTURED_TIMEOUT_S,
                metadata={"storefront_id": self._resolved.storefront_id},
            )
        finally:
            await self._write_ledger(node, ledger)
        return self._result(
            node,
            attempts=operation["attempts"],
            provider_operations=operation["attempts"],
            known_cost_usd=known_cost(operation.get("usage")),
        )

    async def _listing(self, node: Node) -> NodeExecutionResult:
        service, card_prompt = self._require_structured(node)
        operation_id = "storefront.listing"
        ledger = AttemptLedger(operation_id=operation_id)
        prompt = (
            f"{card_prompt}\n\nSEALED DIRECTION\n{self._direction_json()}"
            f"\n\nPOSITIONING NOTE\n{self._resolved.positioning_text}"
        )

        def accept(value: models.StoreListing) -> list[str]:
            if value.storefront_id != self._resolved.storefront_id:
                return [f"storefront_id must be {self._resolved.storefront_id!r}"]
            return []

        try:
            _value, operation = await generate_structured(
                service,
                model_type=models.StoreListing,
                operation_id=operation_id,
                system=SYSTEM_PROMPT,
                description=schema_description(operation_id),
                prompt=prompt,
                artifact_path=self._path(LISTING_REF),
                ledger=ledger,
                semantic_validate=accept,
                max_tokens=12_000,
                timeout_seconds=STRUCTURED_TIMEOUT_S,
                metadata={"storefront_id": self._resolved.storefront_id},
            )
        finally:
            await self._write_ledger(node, ledger)
        return self._result(
            node,
            attempts=operation["attempts"],
            provider_operations=operation["attempts"],
            known_cost_usd=known_cost(operation.get("usage")),
        )

    async def _generate(self, node: Node) -> NodeExecutionResult:
        if self._images is None:
            raise ValueError("storefront surface nodes require an image generation service")
        surface_id = self._surface_id(node)
        authored = self._resolved.source.surface(surface_id)
        declared = surface(authored.kind.value)
        prompt = surface_prompt(
            authored=authored, declared=declared, direction=self._direction_document()
        )

        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            facts = inspect_image(artifact.data, expected_media_type="image/png")
            # The drawn canvas is checked but not required to be exact: the ship
            # canvas is the normalization's job, and refusing a route that drew a
            # near-miss would burn five more attempts for a crop we already own.
            return {"width": facts.width, "height": facts.height, "has_alpha": facts.has_alpha}

        result = await self._images.generate(
            ImageGenerationRequest(
                prompt=prompt,
                artifact_path=self._path(node.port("image").artifact_ref),
                input_references=self._image_references(),
                mask_reference=None,
                quality="max",
                background="opaque",
                output_format="png",
                size=declared.draw_size,
                metadata={
                    "operation_id": f"storefront.surface.{surface_id}",
                    "invocation_id": self.invocation_id,
                    "recipe": "storefront",
                    "storefront_id": self._resolved.storefront_id,
                    "surface_id": surface_id,
                    "surface_kind": declared.kind.value,
                    "draw_size": declared.draw_size,
                    "ship_size": declared.ship_size,
                    "draw": str(node.params.get("draw", "0")),
                    "input_reference_count": len(self._resolved.references),
                    "mask_reference_count": 0,
                    "direction_ref": self._run_ref(DIRECTION_REF),
                    "publication_authorized": False,
                },
                timeout_seconds=IMAGE_TIMEOUT_S,
                validate=validate,
                provenance_schema_version=2,
                resolved_binding=self._graph.resolved_route_for(node).to_resolved_binding(),
            )
        )
        return self._result(
            node,
            attempts=result.attempts,
            provider_operations=result.attempts,
            known_cost_usd=known_cost(result.response_metadata.usage),
        )

    async def _normalize(self, node: Node) -> NodeExecutionResult:
        surface_id = self._surface_id(node)
        declared = self._resolved.declared(surface_id)
        drawn = self._path(drawn_ref(surface_id)).read_bytes()
        shipped, record = normalize_png_cover(
            drawn, width=declared.ship_width, height=declared.ship_height
        )
        flattened = False
        if declared.forbids_alpha_channel:
            shipped, flattened = flatten_alpha(shipped)
        await self._write_local(
            node.port("image").artifact_ref,
            shipped,
            media_type="image/png",
            model="ship-canvas-normalization",
            prompt=self._card_prompt(node),
            refs=[self._run_ref(drawn_ref(surface_id))],
            params={
                "surface_id": surface_id,
                "ship_size": declared.ship_size,
                "draw_size": declared.draw_size,
                "operation": record.operation,
                "alpha_flattened": flattened,
            },
        )
        return self._result(node)

    async def _validate(self, node: Node) -> NodeExecutionResult:
        surface_id = self._surface_id(node)
        declared = self._resolved.declared(surface_id)
        shipped = shipped_ref(surface_id)
        data = self._path(shipped).read_bytes()
        facts = inspect_image(data, expected_media_type="image/png")
        errors: list[str] = []
        if (facts.width, facts.height) != (declared.ship_width, declared.ship_height):
            errors.append(f"ship canvas is {facts.width}x{facts.height}, not {declared.ship_size}")
        if declared.forbids_alpha_channel and facts.has_alpha:
            errors.append("this surface refuses an alpha channel, and one is present")
        if len(data) > declared.max_bytes:
            errors.append(f"{len(data)} bytes is past the {declared.max_bytes} byte ceiling")
        if errors:
            raise ValueError(f"{surface_id} failed its output contract: " + "; ".join(errors))
        atomic_write_json(
            self._path(node.port("validation").artifact_ref),
            {
                "schema_version": 1,
                "kind": SURFACE_VALIDATION_KIND,
                "surface_id": surface_id,
                "surface_kind": declared.kind.value,
                "status": "pass",
                "width": facts.width,
                "height": facts.height,
                "has_alpha": facts.has_alpha,
                "bytes": len(data),
                "byte_ceiling": declared.max_bytes,
                "artifact_ref": shipped,
                "artifact_sha256": content_sha256(data),
            },
        )
        return self._result(node)

    async def _proxy(self, node: Node) -> NodeExecutionResult:
        surface_id = self._surface_id(node)
        shipped = shipped_ref(surface_id)
        proxy = make_image_proxy(self._path(shipped).read_bytes(), long_edge=REVIEW_PROXY_LONG_EDGE)
        await self._write_local(
            node.port("proxy").artifact_ref,
            proxy,
            media_type="image/png",
            model="review-proxy",
            prompt=self._card_prompt(node),
            refs=[self._run_ref(shipped)],
            params={"surface_id": surface_id, "long_edge": REVIEW_PROXY_LONG_EDGE},
        )
        return self._result(node)

    async def _review(self, node: Node) -> NodeExecutionResult:
        service, card_prompt = self._require_structured(node)
        surface_id = self._surface_id(node)
        operation_id = f"storefront.review.{surface_id}"
        ledger = AttemptLedger(operation_id=operation_id)
        prompt = f"{card_prompt}\n\nSEALED DIRECTION\n{self._direction_json()}"

        def accept(value: models.SurfaceReview) -> list[str]:
            return [] if value.surface_id == surface_id else [f"surface_id must be {surface_id!r}"]

        try:
            _value, operation = await generate_structured(
                service,
                model_type=models.SurfaceReview,
                operation_id=operation_id,
                system=SYSTEM_PROMPT,
                description=schema_description(operation_id),
                prompt=prompt,
                artifact_path=self._path(node.port("review").artifact_ref),
                ledger=ledger,
                references=(
                    StructuredReference(
                        url=data_url(self._path(proxy_ref(surface_id)).read_bytes(), "image/png"),
                        provenance_ref=self._run_ref(proxy_ref(surface_id)),
                    ),
                ),
                semantic_validate=accept,
                max_tokens=8_000,
                timeout_seconds=STRUCTURED_TIMEOUT_S,
                metadata={"storefront_id": self._resolved.storefront_id, "surface_id": surface_id},
            )
        finally:
            await self._write_ledger(node, ledger)
        return self._result(
            node,
            attempts=operation["attempts"],
            provider_operations=operation["attempts"],
            known_cost_usd=known_cost(operation.get("usage")),
        )

    async def _record(self, node: Node) -> NodeExecutionResult:
        surface_id = self._surface_id(node)
        authored = self._resolved.source.surface(surface_id)
        declared = surface(authored.kind.value)
        review = models.SurfaceReview.model_validate_json(
            self._path(review_ref(surface_id)).read_bytes()
        )
        validation = json.loads(self._path(validation_ref(surface_id)).read_bytes())
        atomic_write_json(
            self._path(node.port("record").artifact_ref),
            {
                "schema_version": 1,
                "kind": SURFACE_RECORD_KIND,
                "surface_id": surface_id,
                "surface_kind": declared.kind.value,
                "title": declared.title,
                "source": authored.source.value,
                "brief": authored.brief,
                "ship_size": declared.ship_size,
                "draw_size": declared.draw_size,
                "draw": self._resolved.draws.draw(surface_id),
                "artifact_ref": shipped_ref(surface_id),
                "artifact_sha256": validation["artifact_sha256"],
                "bytes": validation["bytes"],
                "review": review.model_dump(mode="json"),
                "status": review.verdict,
                "publication_authorized": False,
            },
        )
        return self._result(node)

    async def _close(self, node: Node) -> NodeExecutionResult:
        await self._publish_references()
        records = []
        for authored in self._resolved.source.surfaces:
            record = json.loads(self._path(record_ref(authored.surface_id)).read_bytes())
            records.append(
                {
                    "surface_id": record["surface_id"],
                    "surface_kind": record["surface_kind"],
                    "artifact_ref": record["artifact_ref"],
                    "artifact_sha256": record["artifact_sha256"],
                    "ship_size": record["ship_size"],
                    "status": record["status"],
                }
            )
        listing = json.loads(self._path(LISTING_REF).read_bytes())
        atomic_write_json(
            self._path(INVENTORY_REF),
            {
                "schema_version": 1,
                "kind": INVENTORY_KIND,
                "storefront_id": self._resolved.storefront_id,
                "display_name": self._resolved.title,
                "surfaces": records,
                "admitted": sum(1 for item in records if item["status"] == "pass"),
                "rejected": sum(1 for item in records if item["status"] != "pass"),
                "listing_ref": LISTING_REF,
                "app_name": listing["app_name"],
                "references": [
                    {"reference_id": item.reference_id, "artifact_ref": item.source}
                    for item in self._resolved.references
                ],
                "publication_authorized": False,
            },
        )
        merged: list[dict[str, object]] = []
        for graph_node in self._graph.nodes:
            path = self._run_dir / "attempts" / f"{graph_node.node_id}.json"
            if not path.is_file():
                continue
            entries = json.loads(path.read_text(encoding="utf-8")).get("attempts")
            if isinstance(entries, list):
                merged.extend(entry for entry in entries if isinstance(entry, dict))
        atomic_write_json(
            self._run_dir / "attempts.json",
            {
                "schema_version": 1,
                "kind": "attempt-ledger-merged-v1",
                "rejected_attempts": len(merged),
                "attempts": merged,
            },
        )
        return self._result(node)

    async def _publish_references(self) -> None:
        """Copy the authored art into the run, rights and digest intact.

        The run is what a reader opens, so the bytes the inventory names have to
        be in it. This is the one place the recipe crosses the package boundary,
        and it carries the author's own rights decision across rather than minting
        a fresh one.
        """

        authored_rights = self._resolved.source.rights
        for reference in self._resolved.references:
            await self._write_local(
                reference.source,
                reference.data,
                media_type=reference.media_type,
                model="reference-republish",
                prompt="Republish the authored reference art into the storefront run.",
                params={
                    "reference_id": reference.reference_id,
                    "source": reference.source,
                    "source_sha256": reference.sha256,
                },
                rights=ArtifactRights(
                    status=authored_rights.status,
                    attribution=[],
                    basis=list(authored_rights.basis),
                    reviewed_at=None,
                ),
            )


__all__ = [
    "IMAGE_TIMEOUT_S",
    "STOREFRONT_COMPONENT",
    "STOREFRONT_RIGHTS",
    "STRUCTURED_TIMEOUT_S",
    "StorefrontNodeHandler",
    "flatten_alpha",
    "make_image_proxy",
]
