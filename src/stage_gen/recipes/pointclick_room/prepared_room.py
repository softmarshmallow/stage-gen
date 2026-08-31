"""Execute one point-and-click room node: cards, validators, and the bundle.

Every provider operation stays inside a component service, which owns the whole
retry-validate-persist contract. The plan is the single source of every static
instruction: each generation handler sends its node card's prompt verbatim,
with the runtime-selected style anchor appended once.
"""

from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image

from gnode import (
    ArtifactRights,
    BinaryArtifact,
    CacheDisposition,
    ImageGenerationRequest,
    ImageReference,
    NodeArtifact,
    NodeExecutionError,
    NodeExecutionResult,
    NodeTypeRegistry,
    ProvenanceInput,
    RetryExhaustedError,
    SoftwareIdentity,
    StructuredGenerationRequest,
    StructuredOutputSchema,
    atomic_write_json,
    dependency_port,
    resolve_relative_path_within_root,
    write_artifact_with_provenance_async,
)
from stage_gen.identity import STAGE_GEN_TOOL
from stage_gen.image_prompting import build_image_style_compiler_request
from stage_gen.image_style import (
    CanonicalStyleAnchor,
    ImageAssetKind,
    append_style_anchor_once,
    compile_style_prompt_anchor,
)
from stage_gen.media import inspect_image
from stage_gen.recipes.dialogue_scene.identity import content_sha256
from stage_gen.recipes.node_cache import NodeArtifactCache
from stage_gen.recipes.pointclick_room.models import prove_room_solvable
from stage_gen.recipes.pointclick_room.room_graph import (
    POINTCLICK_CACHE_NAMESPACE,
    POINTCLICK_CACHE_RECORD_KIND,
    PointClickRoomGraph,
    RoomOperationKind,
)
from stage_gen.recipes.pointclick_room.room_prompts import narration_ids, narration_json_schema
from stage_gen.recipes.pointclick_room.room_types import (
    BACKDROP_GENERATE,
    COVER_GENERATE,
    HOTSPOT_SPRITE_GENERATE,
    HOTSPOT_SPRITE_KIND,
    HOTSPOT_SPRITE_VALIDATE,
    ITEM_ICON_GENERATE,
    ITEM_ICON_KIND,
    ITEM_ICON_VALIDATE,
    MANIFEST_KIND,
    NARRATION_COMPILE,
    PUZZLE_VALIDATE,
    ROOM_BUNDLE,
    ROOM_RESOLVE,
    STYLE_SELECT,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from gnode import (
        ImageGenerationService,
        Node,
        NodeExecutionContext,
        NodeHandler,
        StructuredGenerationService,
    )
    from stage_gen.recipes.pointclick_room.room_request import ResolvedPointClickRoom

_COMPONENT = SoftwareIdentity(name="@stage-gen/pointclick-room", version="1")

SPRITE_SIZE = 1024

#: The one image every other image is generated against.
COVER_REF = "references/cover.png"


def _data_url(data: bytes) -> str:
    return f"data:image/png;base64,{base64.b64encode(data).decode('ascii')}"


def room_target_node_ids(graph: PointClickRoomGraph) -> tuple[str, ...]:
    """Every node except the terminal bundle, which the caller publishes explicitly."""

    return tuple(node.node_id for node in graph.nodes if node.node_id != graph.terminal_node_id)


class PointClickRoomNodeHandler:
    """Dispatch room nodes while provider operations stay component-owned."""

    def __init__(
        self,
        graph: PointClickRoomGraph,
        resolved: ResolvedPointClickRoom,
        *,
        run_dir: Path,
        cache_dir: Path,
        image_service: ImageGenerationService,
        structured_service: StructuredGenerationService[Any],
        capability_timeout_s: float | None = None,
    ) -> None:
        self._graph = graph
        self._resolved = resolved
        self._run_dir = run_dir
        self._images = image_service
        self._structured = structured_service
        self._timeout = capability_timeout_s
        self._cache = NodeArtifactCache(
            graph,
            run_dir=run_dir,
            cache_dir=cache_dir,
            namespace=POINTCLICK_CACHE_NAMESPACE,
            record_kind=POINTCLICK_CACHE_RECORD_KIND,
        )
        self._registry = self._build_registry()

    async def __call__(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        cached = self._cache.read(node, context)
        if cached is not None:
            return cached
        try:
            result = await self._registry(node, context)
        except NodeExecutionError:
            raise
        except Exception as error:
            external = node.operation != RoomOperationKind.LOCAL
            attempts = int(getattr(error, "attempts", 1))
            raise NodeExecutionError(
                str(error),
                attempts=attempts,
                provider_operations=attempts if external else 0,
            ) from error
        self._cache.write(node, context, result)
        return result

    # ---------------------------------------------------------------- dispatch

    def _build_registry(self) -> NodeTypeRegistry:
        registry = NodeTypeRegistry()
        registry.register(ROOM_RESOLVE, self._bind(self._write_room))
        registry.register(STYLE_SELECT, self._bind(self._select_style))
        registry.register(COVER_GENERATE, self._bind(self._cover))
        registry.register(BACKDROP_GENERATE, self._bind(self._backdrop))
        registry.register(HOTSPOT_SPRITE_GENERATE, self._bind(self._sprite))
        registry.register(ITEM_ICON_GENERATE, self._bind(self._sprite))
        registry.register(HOTSPOT_SPRITE_VALIDATE, self._bind(self._validate_sprite))
        registry.register(ITEM_ICON_VALIDATE, self._bind(self._validate_sprite))
        registry.register(NARRATION_COMPILE, self._bind(self._narration))
        registry.register(PUZZLE_VALIDATE, self._bind(self._puzzle))
        registry.register(ROOM_BUNDLE, self._bind(self._bundle))
        return registry

    def _bind(self, method: Callable[[Node], Awaitable[NodeExecutionResult]]) -> NodeHandler:
        async def handler(node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
            return await method(node)

        return handler

    # ------------------------------------------------------------------ nodes

    async def _write_room(self, node: Node) -> NodeExecutionResult:
        await self._write_local(
            node.port("room").artifact_ref,
            self._resolved.room_bytes + b"\n",
            "application/json",
            "Canonicalize and admit the authored room document.",
            params={"room_sha256": self._resolved.room_sha256},
        )
        return self._result(node, provider_operations=0)

    async def _select_style(self, node: Node) -> NodeExecutionResult:
        request = build_image_style_compiler_request(
            prompt=self._card_prompt(node),
            artifact_path=self._run_dir / node.port("anchor").artifact_ref,
            asset_kinds=("environment_background", "illustration"),
            timeout_seconds=self._timeout,
        )
        result = await self._provider_call(
            node, "style-anchor", request.prompt, lambda: self._structured.generate(request)
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _cover(self, node: Node) -> NodeExecutionResult:
        scene = self._resolved.room.scene
        result = await self._image(
            node,
            role="cover",
            output=node.port("image").artifact_ref,
            asset_kind="illustration",
            width=scene.width,
            height=scene.height,
            transparent=False,
            references=(),
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _backdrop(self, node: Node) -> NodeExecutionResult:
        room = self._resolved.room.scene
        result = await self._image(
            node,
            role="backdrop",
            output=node.port("image").artifact_ref,
            asset_kind="environment_background",
            width=room.width,
            height=room.height,
            transparent=False,
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _sprite(self, node: Node) -> NodeExecutionResult:
        port = node.ports[0]
        role = node.params.get("hotspot_id") or node.params.get("item_id") or node.node_id
        result = await self._image(
            node,
            role=role,
            output=port.artifact_ref,
            asset_kind="illustration",
            width=SPRITE_SIZE,
            height=SPRITE_SIZE,
            transparent=True,
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _validate_sprite(self, node: Node) -> NodeExecutionResult:
        expected_kind = HOTSPOT_SPRITE_KIND if "hotspot_id" in node.params else ITEM_ICON_KIND
        _producer, port = dependency_port(self._graph, node, kind=expected_kind)
        data = self._read(port.artifact_ref)
        facts = inspect_image(data, expected_media_type="image/png")
        if not facts.has_alpha:
            raise ValueError(f"{node.node_id}: sprite requires an alpha channel")
        with Image.open(BytesIO(data)) as opened:
            alpha = opened.convert("RGBA").getchannel("A").tobytes()
        transparent = sum(value == 0 for value in alpha)
        opaque = sum(value > 128 for value in alpha)
        total = len(alpha)
        if transparent < total // 20 or opaque < total // 50:
            raise ValueError(
                f"{node.node_id}: sprite must be one isolated subject on transparent ground "
                f"(transparent={transparent}, opaque={opaque}, total={total})"
            )
        atomic_write_json(
            self._run_dir / node.port("validation").artifact_ref,
            {
                "schema_version": 1,
                "kind": "pointclick-sprite-validation-v1",
                "source": port.artifact_ref,
                "source_sha256": content_sha256(data),
                "width": facts.width,
                "height": facts.height,
                "transparent_pixels": transparent,
                "opaque_pixels": opaque,
            },
        )
        return self._result(node, provider_operations=0)

    async def _narration(self, node: Node) -> NodeExecutionResult:
        expected = set(narration_ids(self._resolved.room))
        prompt = self._card_prompt(node)

        def parse(value: object) -> dict[str, str]:
            if not isinstance(value, dict):
                raise ValueError("narration payload must be an object")
            entries = value.get("narrations")
            if not isinstance(entries, list):
                raise ValueError("narration payload must carry a narrations array")
            lines: dict[str, str] = {}
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ValueError("narration entries must be objects")
                key, text = entry.get("id"), entry.get("text")
                if not isinstance(key, str) or not isinstance(text, str) or not text.strip():
                    raise ValueError("narration entries must carry id and non-empty text")
                lines[key] = text.strip()
            if set(lines) != expected:
                raise ValueError(
                    "narration ids must cover exactly the authored gaps; "
                    f"missing={sorted(expected - set(lines))} extra={sorted(set(lines) - expected)}"
                )
            return lines

        request = StructuredGenerationRequest(
            prompt=prompt,
            system=(
                "Return only the strict narration JSON. No puzzle hints beyond the listed "
                "facts, no new items, no meta commentary."
            ),
            artifact_path=self._run_dir / node.port("document").artifact_ref,
            schema=StructuredOutputSchema(
                name="pointclick_narration_v1",
                json_schema=narration_json_schema(),
                strict=True,
            ),
            parse=parse,
            artifact_value=lambda lines: {
                "schema_version": 1,
                "kind": "room-narration-v1",
                "room_sha256": self._resolved.room_sha256,
                "narrations": dict(sorted(lines.items())),
            },
            metadata={"node": node.node_id, "room_sha256": self._resolved.room_sha256},
            timeout_seconds=self._timeout,
            provenance_schema_version=2,
        )
        result = await self._provider_call(
            node, "narration", prompt, lambda: self._structured.generate(request)
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _puzzle(self, node: Node) -> NodeExecutionResult:
        room = self._resolved.room
        report = prove_room_solvable(room)
        if not report.solvable:
            raise ValueError("room is not finishable; refusing to bundle")
        atomic_write_json(
            self._run_dir / node.port("puzzle").artifact_ref,
            {
                "schema_version": 1,
                "kind": "room-puzzle-v1",
                "room_sha256": self._resolved.room_sha256,
                "hotspots": [hotspot.model_dump(mode="json") for hotspot in room.hotspots],
                "items": [item.model_dump(mode="json") for item in room.items],
                "interactions": [
                    interaction.model_dump(mode="json") for interaction in room.interactions
                ],
                "win": room.win.model_dump(mode="json"),
            },
        )
        atomic_write_json(
            self._run_dir / node.port("solvability").artifact_ref,
            report.model_dump(mode="json"),
        )
        return self._result(node, provider_operations=0)

    async def _bundle(self, node: Node) -> NodeExecutionResult:
        room = self._resolved.room
        records: list[dict[str, object]] = []
        for graph_node in self._graph.nodes:
            path = self._run_dir / "attempts" / f"{graph_node.node_id}.json"
            if not path.is_file():
                continue
            ledger = json.loads(path.read_text(encoding="utf-8"))
            entries = ledger.get("attempts")
            if isinstance(entries, list):
                records.extend(entry for entry in entries if isinstance(entry, dict))
        atomic_write_json(self._run_dir / "attempts.json", _ledger(records))

        narration: dict[str, object] = (
            json.loads(self._read("narration.json"))["narrations"] if narration_ids(room) else {}
        )

        def resolved_line(authored: str | None, key: str) -> str:
            if authored is not None:
                return authored
            line = narration.get(key)
            if not isinstance(line, str):
                raise ValueError(f"narration is missing the generated line for {key}")
            return line

        artifacts = [COVER_REF, "assets/backdrop.png"]
        hotspots = []
        for hotspot in room.hotspots:
            sprite_ref = (
                f"assets/hotspots/{hotspot.hotspot_id}.png" if hotspot.art == "sprite" else None
            )
            if sprite_ref is not None:
                artifacts.append(sprite_ref)
            hotspots.append(
                {
                    "id": hotspot.hotspot_id,
                    "label": hotspot.label,
                    "art": hotspot.art,
                    "region": hotspot.region.model_dump(mode="json"),
                    "hidden": hotspot.hidden,
                    "sprite": sprite_ref,
                }
            )
        items = []
        for item in room.items:
            icon_ref = f"assets/items/{item.item_id}.png"
            artifacts.append(icon_ref)
            items.append({"id": item.item_id, "label": item.label, "icon": icon_ref})
        interactions = [
            {
                "on": interaction.on.model_dump(mode="json"),
                "requires": list(interaction.requires),
                "effects": [
                    effect.model_dump(mode="json", exclude_none=True)
                    for effect in interaction.effects
                ],
                "narration": resolved_line(interaction.narration, f"interaction-{index}"),
            }
            for index, interaction in enumerate(room.interactions)
        ]
        digests = {ref: content_sha256(self._read(ref)) for ref in artifacts}
        manifest = {
            "schema_version": 1,
            "kind": MANIFEST_KIND,
            "room_id": room.room_id,
            "display_name": room.display_name,
            "revision": room.revision,
            "room_sha256": self._resolved.room_sha256,
            # The cover is the art direction of record: every other image in this
            # manifest was generated against it, so it ships with them.
            "cover": COVER_REF,
            "scene": {
                "width": room.scene.width,
                "height": room.scene.height,
                "backdrop": "assets/backdrop.png",
            },
            "hotspots": hotspots,
            "items": items,
            "interactions": interactions,
            "win": {
                "requires": list(room.win.requires),
                "narration": resolved_line(room.win.narration, "win"),
            },
            "closure": {
                "artifact_count": len(artifacts),
                "artifacts": [
                    {"path": ref, "sha256": digest} for ref, digest in sorted(digests.items())
                ],
            },
        }
        atomic_write_json(self._run_dir / node.port("manifest").artifact_ref, manifest)
        return self._result(node, provider_operations=0)

    # ---------------------------------------------------------------- helpers

    async def _image(
        self,
        node: Node,
        *,
        role: str,
        output: str,
        asset_kind: ImageAssetKind,
        width: int,
        height: int,
        transparent: bool,
        references: tuple[str, ...] = (COVER_REF,),
    ) -> Any:
        prompt = self._card_prompt(node)
        anchor = self._style_anchor()
        request = ImageGenerationRequest(
            prompt=prompt,
            artifact_path=self._run_dir / output,
            input_references=tuple(
                ImageReference(url=_data_url(self._read(ref)), provenance_ref=ref)
                for ref in references
            ),
            quality="high",
            background="transparent" if transparent else "opaque",
            output_format="png",
            size=f"{width}x{height}",
            metadata={
                "recipe": "pointclick-room-v1",
                "node": node.node_id,
                "role": role,
                "room_sha256": self._resolved.room_sha256,
            },
            timeout_seconds=self._timeout,
            validate=_image_validator(width=width, height=height, alpha=transparent),
            provenance_schema_version=2,
            prompt_anchor=compile_style_prompt_anchor(anchor, asset_kind),
        )
        return await self._provider_call(
            node,
            role,
            append_style_anchor_once(prompt, anchor, asset_kind),
            lambda: self._images.generate(request),
        )

    async def _provider_call(
        self, node: Node, role: str, prompt: str, call: Callable[[], Any]
    ) -> Any:
        try:
            result = await call()
        except RetryExhaustedError as error:
            self._write_attempts(node, _records(node.node_id, role, prompt, error.attempts, None))
            raise
        artifact_ref = node.ports[0].artifact_ref
        self._write_attempts(
            node,
            _records(
                node.node_id,
                role,
                prompt,
                result.attempts,
                content_sha256(self._read(artifact_ref)),
            ),
        )
        return result

    def _write_attempts(self, node: Node, records: list[dict[str, object]]) -> None:
        atomic_write_json(self._run_dir / "attempts" / f"{node.node_id}.json", _ledger(records))

    async def _write_local(
        self,
        relative: str,
        data: bytes,
        media_type: str,
        prompt: str,
        *,
        params: dict[str, object] | None = None,
    ) -> None:
        await write_artifact_with_provenance_async(
            self._run_dir / relative,
            BinaryArtifact(data=data, media_type=media_type),
            ProvenanceInput(
                schema_version=2,
                provider="local",
                model="deterministic-pointclick-room-v1",
                prompt=prompt,
                params=params or {},
                validation={"nonempty": True},
                component=_COMPONENT,
                tool=STAGE_GEN_TOOL,
                attempts=1,
                rights=ArtifactRights(
                    status="unreviewed", attribution=[], basis=[], reviewed_at=None
                ),
            ),
        )

    def _result(
        self, node: Node, *, attempts: int = 1, provider_operations: int
    ) -> NodeExecutionResult:
        refs: list[str] = []
        for port in node.ports:
            refs.append(port.artifact_ref)
            if port.sidecar_ref is not None:
                refs.append(port.sidecar_ref)
        artifacts = tuple(
            NodeArtifact(
                artifact_ref=ref,
                sha256=content_sha256(self._read(ref)),
                bytes=len(self._read(ref)),
            )
            for ref in refs
            if (self._run_dir / ref).is_file()
        )
        return NodeExecutionResult(
            cache=CacheDisposition.MISS,
            attempts=attempts,
            provider_operations=provider_operations,
            artifacts=artifacts,
        )

    def _card_prompt(self, node: Node) -> str:
        """The plan is the single source of a node's static instruction text."""

        if node.card is None or node.card.prompt is None:
            raise ValueError(f"node {node.node_id} declares no card prompt")
        return node.card.prompt

    def _style_anchor(self) -> CanonicalStyleAnchor:
        return CanonicalStyleAnchor.model_validate_json(self._read("style-anchor.json"))

    def _read(self, relative: str) -> bytes:
        return resolve_relative_path_within_root(
            self._run_dir, relative, "room artifact path"
        ).read_bytes()


def _ledger(records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "pointclick-attempt-ledger-v1",
        "attempts": records,
    }


def _records(
    node_id: str, role: str, prompt: str, attempts: int, selected_sha256: str | None
) -> list[dict[str, object]]:
    prompt_digest = content_sha256(prompt.encode())
    rejected = attempts if selected_sha256 is None else attempts - 1
    records: list[dict[str, object]] = [
        {
            "stage": node_id,
            "role": role,
            "attempt": ordinal,
            "outcome": "rejected",
            "prompt_sha256": prompt_digest,
            "reason": "service retry rejected the candidate",
        }
        for ordinal in range(1, rejected + 1)
    ]
    if selected_sha256 is not None:
        records.append(
            {
                "stage": node_id,
                "role": role,
                "attempt": attempts,
                "outcome": "selected",
                "artifact_sha256": selected_sha256,
                "prompt_sha256": prompt_digest,
            }
        )
    return records


def _image_validator(
    *, width: int, height: int, alpha: bool
) -> Callable[[BinaryArtifact], dict[str, object]]:
    def validate(artifact: BinaryArtifact) -> dict[str, object]:
        facts = inspect_image(artifact.data, expected_media_type="image/png")
        if (facts.width, facts.height) != (width, height):
            raise ValueError(
                f"room image dimensions must be {width}x{height}; "
                f"received {facts.width}x{facts.height}"
            )
        if alpha and not facts.has_alpha:
            raise ValueError("room sprite requires native alpha")
        return {
            "width": facts.width,
            "height": facts.height,
            "alpha": facts.has_alpha,
            "recipe_contract": "pointclick-room-v1",
        }

    return validate


__all__ = ["PointClickRoomNodeHandler", "room_target_node_ids"]
