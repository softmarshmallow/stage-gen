"""Every universe node's work, dispatched by type and cached by content.

Two phases live here because they share one vocabulary and one run shape. The
semantic handlers turn a source package into an admitted universe; the gallery
handlers turn that admission into one concept image per entity plus the records
that explain them.

Review nodes succeed whether they admit or reject. A rejection is a result, not
a failure: the scheduler must still reach the terminal so the package is written
with a status for every entity, and re-rolling a rejected image is a deliberate,
priced decision rather than an automatic retry.
"""

from __future__ import annotations

import base64
import json
from io import BytesIO
from typing import TYPE_CHECKING, Any, Literal

from PIL import Image, ImageOps

from gnode import (
    ArtifactRights,
    BinaryArtifact,
    CacheDisposition,
    ImageGenerationRequest,
    ImageGenerationService,
    NodeArtifact,
    NodeExecutionError,
    NodeExecutionResult,
    NodeHandler,
    NodeTypeRegistry,
    ProvenanceInput,
    SoftwareIdentity,
    StructuredGenerationService,
    StructuredReference,
    inspect_image,
    write_artifact_with_provenance_async,
)
from stage_gen.canonical import canonical_json_bytes, content_sha256
from stage_gen.identity import STAGE_GEN_TOOL
from stage_gen.recipes.node_cache import NodeArtifactCache
from stage_gen.recipes.universe import models
from stage_gen.recipes.universe.medium import forbidden_terms_present
from stage_gen.recipes.universe.schema import AttemptLedger, generate_structured, known_cost
from stage_gen.recipes.universe.universe_graph import (
    ADMISSION_REF,
    EVALUATION_REF,
    GALLERY_IMAGE_ROUTE,
    GLOBAL_DIRECTION_REF,
    INPUT_POSTER_PROXY_REF,
    PLAN_REF,
    POSTER_PROXY_LONG_EDGE,
    POSTER_PROXY_REF,
    PROPOSAL_REF,
    REVIEW_PROXY_LONG_EDGE,
    SEMANTIC_REVIEW_REF,
    SOURCE_LOCK_REF,
    UNIVERSE_CACHE_NAMESPACE,
    UNIVERSE_CACHE_RECORD_KIND,
    UNIVERSE_REF,
    UniverseGraph,
)
from stage_gen.recipes.universe.universe_prompts import compact_words, image_prompt
from stage_gen.recipes.universe.universe_types import (
    ADMISSION_KIND,
    ADMIT,
    ADMITTED_KIND,
    CONCEPT_IMAGE,
    CONCEPT_PROXY,
    CONCEPT_REVIEW,
    ENTITY_DIRECTION,
    ENTITY_RECORD,
    EVALUATE,
    EVALUATION_KIND,
    GALLERY_CLOSE,
    GLOBAL_DIRECTION,
    INVENTORY_KIND,
    PLAN,
    PROPOSE,
    REVIEW,
    SOURCE_LOCK,
    SOURCE_LOCK_KIND,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, Sequence
    from pathlib import Path

    from gnode import Node, NodeExecutionContext
    from stage_gen.recipes.universe.universe_request import (
        AdmittedUniverse,
        ResolvedUniverseSource,
    )

UNIVERSE_COMPONENT = SoftwareIdentity(name="@stage-gen/universe", version="1")

#: Every artifact this recipe writes is exploration. Publication is a separate
#: human decision over a package where every entity was admitted.
UNIVERSE_RIGHTS = ArtifactRights(
    status="unreviewed",
    attribution=[],
    basis=["exploratory universe generation; publication not authorized"],
    reviewed_at=None,
)


def make_image_proxy(data: bytes, *, long_edge: int, fmt: Literal["JPEG", "PNG"]) -> bytes:
    """Downscale for observation or review; never an image-generation reference."""

    with Image.open(BytesIO(data)) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    if max(image.size) > long_edge:
        image.thumbnail((long_edge, long_edge), Image.Resampling.LANCZOS)
    output = BytesIO()
    if fmt == "JPEG":
        image.save(output, format="JPEG", quality=90, optimize=True)
    else:
        image.save(output, format="PNG", compress_level=6)
    return output.getvalue()


def _data_url(data: bytes, media_type: str) -> str:
    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"


def _document_bytes(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")


def _compact(value: object) -> str:
    return canonical_json_bytes(value).decode("utf-8")


class UniverseNodeHandler:
    """One run's node work: cache first, then the type's own handler."""

    def __init__(
        self,
        graph: UniverseGraph,
        resolved: ResolvedUniverseSource,
        *,
        run_dir: Path,
        cache_dir: Path,
        structured_service: StructuredGenerationService[object] | None = None,
        image_service: ImageGenerationService | None = None,
        admitted: AdmittedUniverse | None = None,
    ) -> None:
        self._graph = graph
        self._resolved = resolved
        self._run_dir = run_dir
        self._structured = structured_service
        self._images = image_service
        self._admitted = admitted
        self._cache = NodeArtifactCache(
            graph,
            run_dir=run_dir,
            cache_dir=cache_dir,
            namespace=UNIVERSE_CACHE_NAMESPACE,
            record_kind=UNIVERSE_CACHE_RECORD_KIND,
            admit=_admit_cached,
        )
        self._registry = NodeTypeRegistry()
        for node_type, method in (
            (SOURCE_LOCK, self._source_lock),
            (PROPOSE, self._propose),
            (PLAN, self._plan),
            (EVALUATE, self._evaluate),
            (REVIEW, self._review),
            (ADMIT, self._admit),
            (GLOBAL_DIRECTION, self._global_direction),
            (ENTITY_DIRECTION, self._entity_direction),
            (CONCEPT_IMAGE, self._image),
            (CONCEPT_PROXY, self._proxy),
            (CONCEPT_REVIEW, self._image_review),
            (ENTITY_RECORD, self._record),
            (GALLERY_CLOSE, self._close),
        ):
            self._registry.register(node_type, _bind(method))
        self._registry.validate_graph_types(graph.nodes)

    async def __call__(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        cached = self._cache.read(node, context)
        if cached is not None:
            return cached
        try:
            result = await self._registry(node, context)
        except NodeExecutionError:
            raise
        except Exception as error:
            attempts = min(max(int(getattr(error, "attempts", 1)), 1), 6)
            raise NodeExecutionError(
                f"{type(error).__name__}: {error}",
                attempts=attempts,
                provider_operations=0 if node.is_local else attempts,
            ) from error
        self._cache.write(node, context, result)
        return result

    # -- utilities ------------------------------------------------------------

    def _path(self, ref: str) -> Path:
        return self._run_dir / ref

    def _result(
        self, node: Node, *, attempts: int = 1, operations: int = 0, cost: float | None = None
    ) -> NodeExecutionResult:
        artifacts: list[NodeArtifact] = []
        for port in node.ports:
            for ref in (port.artifact_ref, port.sidecar_ref):
                if ref is None:
                    continue
                data = self._path(ref).read_bytes()
                artifacts.append(
                    NodeArtifact(artifact_ref=ref, sha256=content_sha256(data), bytes=len(data))
                )
        return NodeExecutionResult(
            cache=CacheDisposition.MISS,
            attempts=attempts,
            provider_operations=operations,
            artifacts=tuple(artifacts),
            known_cost_usd=cost,
        )

    async def _write_local(
        self,
        ref: str,
        data: bytes,
        *,
        media_type: str,
        model: str,
        prompt: str,
        refs: Sequence[str] = (),
        validation: Mapping[str, object] | None = None,
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
                params={"publication_authorized": False, "recipe": "universe"},
                validation=dict(validation or {"status": "pass"}),
                component=UNIVERSE_COMPONENT,
                tool=STAGE_GEN_TOOL,
                attempts=1,
                rights=UNIVERSE_RIGHTS,
            ),
        )

    async def _write_ledger(self, node: Node, ledger: AttemptLedger) -> None:
        """The attempts port is written whether or not anything was rejected.

        A node whose declared ports are not all present cannot be cached, and an
        empty ledger is itself the useful statement that nothing was refused.
        """

        port = node.port("attempts")
        self._path(port.artifact_ref).parent.mkdir(parents=True, exist_ok=True)
        self._path(port.artifact_ref).write_bytes(ledger.encoded())

    def _run_ref(self, ref: str) -> str:
        return f"run://{ref}#sha256={content_sha256(self._path(ref).read_bytes())}"

    def _package_ref(self, source: str, sha256: str) -> str:
        return f"package://{source}#sha256={sha256}"

    def _poster_reference(self) -> StructuredReference:
        """The poster, observed once, as a downscaled proxy and never as an image input."""

        ref = INPUT_POSTER_PROXY_REF if self._admitted is not None else POSTER_PROXY_REF
        return StructuredReference(
            url=_data_url(self._path(ref).read_bytes(), "image/jpeg"),
            provenance_ref=self._run_ref(ref),
        )

    def _source_section(self) -> str:
        paragraphs = "\n".join(
            f"- {pid}: {text}" for pid, text in self._resolved.synopsis_paragraphs()
        )
        requirements = "\n".join(
            f"- {rid}: {text}" for rid, text in self._resolved.direction_requirements()
        )
        return f"""SYNOPSIS PARAGRAPHS (explicit source; the only synopsis evidence ids)
{paragraphs}

EXPANSION DIRECTION REQUIREMENTS (rationale ids, never evidence)
{requirements}

EXPANSION DIRECTION (full text)
{self._resolved.direction_text}"""

    def _load_proposal(self) -> models.UniverseProposal:
        return models.UniverseProposal.model_validate_json(self._path(PROPOSAL_REF).read_bytes())

    def _load_plan(self) -> models.GalleryPlan:
        return models.GalleryPlan.model_validate_json(self._path(PLAN_REF).read_bytes())

    def _proposal_evaluation(self, proposal: models.UniverseProposal) -> models.ProposalEvaluation:
        return models.evaluate_proposal(
            proposal,
            universe_id=self._resolved.universe_id,
            synopsis_ids={pid for pid, _ in self._resolved.synopsis_paragraphs()},
            requirement_ids={rid for rid, _ in self._resolved.direction_requirements()},
            min_entities=self._resolved.source.census.min_entities,
            max_entities=self._resolved.source.census.max_entities,
        )

    def _require_structured(self, node: Node) -> tuple[StructuredGenerationService[object], str]:
        if self._structured is None:
            raise ValueError(f"node {node.node_id} requires a structured generation service")
        if node.card is None or node.card.prompt is None:
            raise ValueError(f"node {node.node_id} carries no prompt")
        return self._structured, node.card.prompt

    def _require_admitted(self) -> AdmittedUniverse:
        if self._admitted is None:
            raise ValueError("gallery handlers require an admitted universe")
        return self._admitted

    # -- semantic phase -------------------------------------------------------

    async def _source_lock(self, node: Node, _context: NodeExecutionContext) -> NodeExecutionResult:
        resolved = self._resolved
        source = resolved.source
        proxy = make_image_proxy(
            resolved.poster_bytes, long_edge=POSTER_PROXY_LONG_EDGE, fmt="JPEG"
        )
        poster_ref = self._package_ref(source.poster.source, resolved.poster_sha256)
        await self._write_local(
            POSTER_PROXY_REF,
            proxy,
            media_type="image/jpeg",
            model="poster-observation-proxy",
            prompt=(
                "Downscale the approved poster for observation only; "
                "never an image-generation reference."
            ),
            refs=[poster_ref],
        )
        lock = {
            "schema_version": 1,
            "kind": SOURCE_LOCK_KIND,
            "universe_id": source.universe_id,
            "title": resolved.title,
            "medium_id": resolved.medium.medium_id,
            "package_sha256": resolved.source_sha256,
            "poster": {
                "source": source.poster.source,
                "sha256": resolved.poster_sha256,
                "role": source.poster.role,
                "rights_status": source.poster.rights_status,
            },
            "poster_proxy_sha256": content_sha256(proxy),
            "synopsis": {"source": source.synopsis.source, "sha256": resolved.synopsis_sha256},
            "expansion_direction": {
                "source": source.expansion_direction.source,
                "sha256": resolved.direction_sha256,
            },
            "synopsis_paragraph_ids": [pid for pid, _ in resolved.synopsis_paragraphs()],
            "direction_requirement_ids": [rid for rid, _ in resolved.direction_requirements()],
            "census": {
                "min_entities": source.census.min_entities,
                "max_entities": source.census.max_entities,
            },
            "publication_authorized": False,
        }
        await self._write_local(
            SOURCE_LOCK_REF,
            _document_bytes(lock),
            media_type="application/json",
            model="source-lock",
            prompt=node.card.prompt if node.card and node.card.prompt else "Lock sources.",
            refs=[poster_ref, self._run_ref(POSTER_PROXY_REF)],
        )
        return self._result(node)

    async def _propose(self, node: Node, _context: NodeExecutionContext) -> NodeExecutionResult:
        service, card_prompt = self._require_structured(node)
        ledger = AttemptLedger(operation_id="universe.propose")
        try:
            _value, operation = await generate_structured(
                service,
                model_type=models.UniverseProposal,
                operation_id="universe.propose",
                prompt=f"{card_prompt}\n\n{self._source_section()}",
                artifact_path=self._path(PROPOSAL_REF),
                ledger=ledger,
                references=(self._poster_reference(),),
                max_tokens=90_000,
                timeout_seconds=2_400,
                semantic_validate=lambda proposal: self._proposal_evaluation(proposal)["errors"],
            )
        finally:
            await self._write_ledger(node, ledger)
        attempts = operation["attempts"]
        return self._result(
            node, attempts=attempts, operations=attempts, cost=known_cost(operation.get("usage"))
        )

    async def _plan(self, node: Node, _context: NodeExecutionContext) -> NodeExecutionResult:
        service, card_prompt = self._require_structured(node)
        proposal = self._load_proposal()
        projection = {
            "universe_id": proposal.universe_id,
            "premise": proposal.premise.claim,
            "present_state": proposal.present_state.claim,
            "entities": [
                {
                    "entity_id": entity.entity_id,
                    "display_name": entity.display_name,
                    "primary_class": entity.primary_class,
                    "facets": entity.facets,
                    "salience": entity.salience,
                    "summary": entity.summary,
                    "how_it_works_or_lives": entity.how_it_works_or_lives,
                    "present_tension": entity.present_tension,
                    "facts": [
                        {"fact_id": fact.fact_id, "claim": fact.claim} for fact in entity.facts
                    ],
                }
                for entity in proposal.entities
            ],
            "relationships": [
                {
                    "relationship_id": relationship.relationship_id,
                    "kind": relationship.relationship_kind,
                    "source": relationship.source_entity_id,
                    "target": relationship.target_entity_id,
                    "summary": relationship.summary,
                }
                for relationship in proposal.relationships
            ],
        }
        ledger = AttemptLedger(operation_id="universe.plan")
        try:
            _value, operation = await generate_structured(
                service,
                model_type=models.GalleryPlan,
                operation_id="universe.plan",
                prompt=f"{card_prompt}\n\nADMITTED UNIVERSE PROJECTION\n{_compact(projection)}",
                artifact_path=self._path(PLAN_REF),
                ledger=ledger,
                max_tokens=60_000,
                timeout_seconds=2_400,
                semantic_validate=lambda plan: models.evaluate_plan(plan, proposal)["errors"],
            )
        finally:
            await self._write_ledger(node, ledger)
        attempts = operation["attempts"]
        return self._result(
            node, attempts=attempts, operations=attempts, cost=known_cost(operation.get("usage"))
        )

    async def _evaluate(self, node: Node, _context: NodeExecutionContext) -> NodeExecutionResult:
        proposal = self._load_proposal()
        plan = self._load_plan()
        proposal_evaluation = self._proposal_evaluation(proposal)
        plan_evaluation = models.evaluate_plan(plan, proposal)
        status = (
            "pass"
            if proposal_evaluation["status"] == "pass" and plan_evaluation["status"] == "pass"
            else "fail"
        )
        evaluation = {
            "schema_version": 1,
            "kind": EVALUATION_KIND,
            "status": status,
            "proposal_sha256": content_sha256(self._path(PROPOSAL_REF).read_bytes()),
            "plan_sha256": content_sha256(self._path(PLAN_REF).read_bytes()),
            "proposal": proposal_evaluation,
            "plan": plan_evaluation,
        }
        await self._write_local(
            EVALUATION_REF,
            _document_bytes(evaluation),
            media_type="application/json",
            model="universe-deterministic-evaluator",
            prompt=node.card.prompt if node.card and node.card.prompt else "Evaluate.",
            refs=[self._run_ref(PROPOSAL_REF), self._run_ref(PLAN_REF)],
            validation={"status": status},
        )
        if status != "pass":
            raise ValueError("persisted proposal or plan failed deterministic evaluation")
        return self._result(node)

    async def _review(self, node: Node, _context: NodeExecutionContext) -> NodeExecutionResult:
        service, card_prompt = self._require_structured(node)
        proposal_bytes = self._path(PROPOSAL_REF).read_bytes()
        plan_bytes = self._path(PLAN_REF).read_bytes()
        proposal_sha = content_sha256(proposal_bytes)
        plan_sha = content_sha256(plan_bytes)
        evaluation = json.loads(self._path(EVALUATION_REF).read_bytes())
        evaluation_summary = _compact(
            {"proposal": evaluation["proposal"], "plan": evaluation["plan"]}
        )
        prompt = "\n\n".join(
            (
                card_prompt,
                f"Required proposal_sha256: {proposal_sha}\nRequired plan_sha256: {plan_sha}",
                f"DETERMINISTIC EVALUATION\n{evaluation_summary}",
                self._source_section(),
                f"PROPOSAL\n{proposal_bytes.decode('utf-8')}",
                f"GALLERY PLAN\n{plan_bytes.decode('utf-8')}",
            )
        )

        def validate(review: models.SemanticReview) -> list[str]:
            errors: list[str] = []
            if review.proposal_sha256 != proposal_sha:
                errors.append("proposal_sha256 must match the persisted proposal")
            if review.plan_sha256 != plan_sha:
                errors.append("plan_sha256 must match the persisted plan")
            return errors

        ledger = AttemptLedger(operation_id="universe.review")
        try:
            _value, operation = await generate_structured(
                service,
                model_type=models.SemanticReview,
                operation_id="universe.review",
                prompt=prompt,
                artifact_path=self._path(SEMANTIC_REVIEW_REF),
                ledger=ledger,
                references=(self._poster_reference(),),
                max_tokens=20_000,
                timeout_seconds=1_800,
                semantic_validate=validate,
            )
        finally:
            await self._write_ledger(node, ledger)
        attempts = operation["attempts"]
        return self._result(
            node, attempts=attempts, operations=attempts, cost=known_cost(operation.get("usage"))
        )

    async def _admit(self, node: Node, _context: NodeExecutionContext) -> NodeExecutionResult:
        review = models.SemanticReview.model_validate_json(
            self._path(SEMANTIC_REVIEW_REF).read_bytes()
        )
        evaluation = json.loads(self._path(EVALUATION_REF).read_bytes())
        proposal_sha = content_sha256(self._path(PROPOSAL_REF).read_bytes())
        plan_sha = content_sha256(self._path(PLAN_REF).read_bytes())
        if (
            evaluation.get("status") != "pass"
            or evaluation.get("proposal_sha256") != proposal_sha
            or evaluation.get("plan_sha256") != plan_sha
        ):
            raise ValueError("evaluation does not bind the persisted proposal and plan")
        if review.proposal_sha256 != proposal_sha or review.plan_sha256 != plan_sha:
            raise ValueError("review does not bind the persisted proposal and plan")
        if review.verdict != "pass":
            raise ValueError(
                "independent semantic review rejected the universe: "
                + "; ".join(review.blocking_findings)
            )
        proposal = self._load_proposal()
        plan = self._load_plan()
        universe = {
            "schema_version": 1,
            "kind": ADMITTED_KIND,
            "universe_id": proposal.universe_id,
            "title": proposal.title,
            "medium_id": self._resolved.medium.medium_id,
            "source_lock_sha256": content_sha256(self._path(SOURCE_LOCK_REF).read_bytes()),
            "proposal_sha256": proposal_sha,
            "plan_sha256": plan_sha,
            "review_sha256": content_sha256(self._path(SEMANTIC_REVIEW_REF).read_bytes()),
            "proposal": proposal.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
            "publication_authorized": False,
        }
        bindings = (SOURCE_LOCK_REF, PROPOSAL_REF, PLAN_REF, EVALUATION_REF, SEMANTIC_REVIEW_REF)
        refs = [self._run_ref(ref) for ref in bindings]
        await self._write_local(
            UNIVERSE_REF,
            _document_bytes(universe),
            media_type="application/json",
            model="universe-admission",
            prompt=node.card.prompt if node.card and node.card.prompt else "Admit.",
            refs=refs,
        )
        admission = {
            "schema_version": 1,
            "kind": ADMISSION_KIND,
            "universe_id": proposal.universe_id,
            "semantic_status": "pass",
            "publication_authorized": False,
            "universe": {
                "path": UNIVERSE_REF,
                "sha256": content_sha256(self._path(UNIVERSE_REF).read_bytes()),
            },
            "bindings": {ref: content_sha256(self._path(ref).read_bytes()) for ref in bindings},
            "note": (
                "Semantic admission authorizes gallery generation only; "
                "it is not publication approval."
            ),
        }
        await self._write_local(
            ADMISSION_REF,
            _document_bytes(admission),
            media_type="application/json",
            model="universe-admission",
            prompt="Bind the admission.",
            refs=[*refs, self._run_ref(UNIVERSE_REF)],
        )
        return self._result(node)

    # -- gallery phase --------------------------------------------------------

    def _entity_projection(self, entity_id: str) -> dict[str, object]:
        admitted = self._require_admitted()
        proposal = admitted.proposal
        entity = proposal.entity(entity_id)
        plan = admitted.plan.plan(entity_id)
        names = {item.entity_id: item.display_name for item in proposal.entities}
        relationships = [
            {
                "relationship_id": relationship.relationship_id,
                "kind": relationship.relationship_kind,
                "with": names.get(_other(relationship, entity_id), "?"),
                "direction": (
                    "outgoing" if relationship.source_entity_id == entity_id else "incoming"
                ),
                "summary": relationship.summary,
            }
            for relationship in proposal.relationships
            if entity_id in (relationship.source_entity_id, relationship.target_entity_id)
        ]
        markers = [
            {"form": marker.form, "materials": marker.materials, "applied_use": marker.applied_use}
            for marker in proposal.identity_markers
            if marker.owner_entity_id == entity_id
        ]
        return {
            "entity": entity.model_dump(mode="json"),
            "incident_relationships": relationships,
            "owned_identity_markers_text_only": markers,
            "plan": plan.model_dump(mode="json"),
        }

    async def _global_direction(
        self, node: Node, _context: NodeExecutionContext
    ) -> NodeExecutionResult:
        service, card_prompt = self._require_structured(node)
        admitted = self._require_admitted()
        proposal = admitted.proposal
        medium = self._resolved.medium
        projection = {
            "universe_id": proposal.universe_id,
            "title": proposal.title,
            "premise": proposal.premise.claim,
            "present_state": proposal.present_state.claim,
            "physical_ecological_rules": [
                fact.claim for fact in proposal.physical_ecological_rules
            ],
            "poster_observations": [
                observation.model_dump(mode="json")
                for observation in proposal.visual_observations
                if observation.canonical_status == "evidence"
            ],
            "entities": [
                {
                    "entity_id": entity.entity_id,
                    "display_name": entity.display_name,
                    "primary_class": entity.primary_class,
                    "entity_kind": entity.entity_kind,
                    "summary": entity.summary,
                }
                for entity in proposal.entities
            ],
            "identity_markers": [
                {
                    "owner": marker.owner_entity_id,
                    "form": marker.form,
                    "materials": marker.materials,
                }
                for marker in proposal.identity_markers
            ],
        }

        def validate(direction: models.GlobalDirection) -> list[str]:
            errors: list[str] = []
            if direction.medium_id != medium.medium_id:
                errors.append(f"medium_id must be {medium.medium_id}")
            if direction.universe_id != proposal.universe_id:
                errors.append("universe_id must match")
            prose = "\n".join(
                (
                    direction.world_silhouette_language,
                    direction.architecture_grammar,
                    direction.costume_grammar,
                    direction.material_language,
                    direction.scale_anchors,
                    direction.technology_and_ecology_rules,
                    *(entry.palette for entry in direction.palette_by_region),
                )
            )
            foreign = forbidden_terms_present(medium, prose)
            if foreign:
                errors.append(f"global direction uses terms foreign to the medium: {foreign}")
            observation_ids = {
                observation.observation_id for observation in proposal.visual_observations
            }
            if set(direction.poster_observation_ids_used) - observation_ids:
                errors.append("poster_observation_ids_used must be admitted observation ids")
            return errors

        ledger = AttemptLedger(operation_id="universe.direction.global")
        try:
            _value, operation = await generate_structured(
                service,
                model_type=models.GlobalDirection,
                operation_id="universe.direction.global",
                prompt=f"{card_prompt}\n\nADMITTED UNIVERSE\n{_compact(projection)}",
                artifact_path=self._path(GLOBAL_DIRECTION_REF),
                ledger=ledger,
                references=(self._poster_reference(),),
                max_tokens=16_000,
                timeout_seconds=1_200,
                semantic_validate=validate,
            )
        finally:
            await self._write_ledger(node, ledger)
        attempts = operation["attempts"]
        return self._result(
            node, attempts=attempts, operations=attempts, cost=known_cost(operation.get("usage"))
        )

    async def _entity_direction(
        self, node: Node, _context: NodeExecutionContext
    ) -> NodeExecutionResult:
        service, card_prompt = self._require_structured(node)
        entity_id = str(node.params["entity_id"])
        admitted = self._require_admitted()
        plan = admitted.plan.plan(entity_id)
        medium = self._resolved.medium
        global_direction = json.loads(self._path(GLOBAL_DIRECTION_REF).read_bytes())
        prompt = "\n\n".join(
            (
                card_prompt,
                f"Bound entity_id: {entity_id}",
                f"GLOBAL VISUAL GRAMMAR\n{_compact(global_direction)}",
                "ENTITY, RELATIONSHIPS, AND SEALED PLAN ENTRY\n"
                + _compact(self._entity_projection(entity_id)),
            )
        )
        ledger = AttemptLedger(operation_id=f"universe.direction.entity.{entity_id}")
        try:
            value, operation = await generate_structured(
                service,
                model_type=models.EntityDirection,
                operation_id=f"universe.direction.entity.{entity_id}",
                prompt=prompt,
                artifact_path=self._path(node.port("direction").artifact_ref),
                ledger=ledger,
                max_tokens=12_000,
                timeout_seconds=900,
                semantic_validate=lambda direction: models.evaluate_direction(
                    direction, plan, medium
                ),
            )
        finally:
            await self._write_ledger(node, ledger)
        warnings = models.direction_warnings(value, plan, medium)
        self._path(node.port("warnings").artifact_ref).write_bytes(
            _document_bytes(
                {
                    "schema_version": 1,
                    "kind": node.port("warnings").kind,
                    "entity_id": entity_id,
                    "warnings": warnings,
                }
            )
        )
        attempts = operation["attempts"]
        return self._result(
            node, attempts=attempts, operations=attempts, cost=known_cost(operation.get("usage"))
        )

    async def _image(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        if self._images is None:
            raise ValueError("gallery image nodes require an image generation service")
        entity_id = str(node.params["entity_id"])
        size = str(node.params["size"])
        direction_ref = f"production/direction/entities/{entity_id}.json"
        direction = models.EntityDirection.model_validate_json(
            self._path(direction_ref).read_bytes()
        )
        global_direction = json.loads(self._path(GLOBAL_DIRECTION_REF).read_bytes())
        prompt = image_prompt(
            entity_id=entity_id,
            direction=direction,
            global_direction=global_direction,
            medium=self._resolved.medium,
        )
        width, height = (int(value) for value in size.split("x", 1))

        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            facts = inspect_image(artifact.data, expected_media_type="image/png")
            if (facts.width, facts.height) != (width, height) or facts.has_alpha:
                raise ValueError("concept image is not the requested opaque native-size PNG")
            return {"width": width, "height": height, "has_alpha": False}

        result = await self._images.generate(
            ImageGenerationRequest(
                prompt=prompt,
                artifact_path=self._path(node.port("image").artifact_ref),
                input_references=(),
                mask_reference=None,
                quality="high",
                background="opaque",
                output_format="png",
                size=size,
                moderation="low",
                metadata={
                    "operation_id": f"universe.image.{entity_id}",
                    "invocation_id": context.invocation_id,
                    "entity_id": entity_id,
                    "medium_id": self._resolved.medium.medium_id,
                    "image_route": GALLERY_IMAGE_ROUTE.route_id,
                    "sample": str(node.params.get("sample", "0")),
                    "direction_ref": self._run_ref(direction_ref),
                    "global_direction_ref": self._run_ref(GLOBAL_DIRECTION_REF),
                    "input_reference_count": 0,
                    "mask_reference_count": 0,
                    "publication_authorized": False,
                },
                timeout_seconds=1_800,
                validate=validate,
                provenance_schema_version=2,
            )
        )
        return self._result(
            node,
            attempts=result.attempts,
            operations=result.attempts,
            cost=known_cost(result.response_metadata.usage),
        )

    async def _proxy(self, node: Node, _context: NodeExecutionContext) -> NodeExecutionResult:
        entity_id = str(node.params["entity_id"])
        image_ref = f"package/entities/{entity_id}.png"
        proxy = make_image_proxy(
            self._path(image_ref).read_bytes(), long_edge=REVIEW_PROXY_LONG_EDGE, fmt="PNG"
        )
        await self._write_local(
            node.port("proxy").artifact_ref,
            proxy,
            media_type="image/png",
            model="review-proxy",
            prompt=node.card.prompt if node.card and node.card.prompt else "Proxy.",
            refs=[self._run_ref(image_ref)],
        )
        return self._result(node)

    async def _image_review(
        self, node: Node, _context: NodeExecutionContext
    ) -> NodeExecutionResult:
        service, card_prompt = self._require_structured(node)
        entity_id = str(node.params["entity_id"])
        image_ref = f"package/entities/{entity_id}.png"
        proxy_ref = f"production/review/proxies/{entity_id}.png"
        artifact_sha = content_sha256(self._path(image_ref).read_bytes())
        direction = models.EntityDirection.model_validate_json(
            self._path(f"production/direction/entities/{entity_id}.json").read_bytes()
        )
        projection = self._entity_projection(entity_id)
        medium = self._resolved.medium
        review_input = {
            "entity": projection["entity"],
            "plan": projection["plan"],
            "direction_summary": {
                "primary_subject": direction.primary_subject,
                "action_beat": direction.action_beat.model_dump(mode="json"),
                "visual_identity": direction.visual_identity.model_dump(mode="json"),
                "register_realization": direction.register_realization,
            },
        }
        prompt = "\n\n".join(
            (
                card_prompt,
                f"MEDIUM CRITERIA ({medium.display_name})\n{medium.review_criteria}",
                f"Required entity_id: {entity_id}\nRequired artifact_sha256: {artifact_sha}",
                f"SEALED RECORD\n{_compact(review_input)}",
            )
        )
        proxy_reference = StructuredReference(
            url=_data_url(self._path(proxy_ref).read_bytes(), "image/png"),
            provenance_ref=self._run_ref(proxy_ref),
        )

        def validate(review: models.ImageReview) -> list[str]:
            errors: list[str] = []
            if review.entity_id != entity_id:
                errors.append("entity_id must match the bound entity")
            if review.artifact_sha256 != artifact_sha:
                errors.append("artifact_sha256 must match the reviewed image")
            return errors

        ledger = AttemptLedger(operation_id=f"universe.review.image.{entity_id}")
        try:
            _value, operation = await generate_structured(
                service,
                model_type=models.ImageReview,
                operation_id=f"universe.review.image.{entity_id}",
                prompt=prompt,
                artifact_path=self._path(node.port("review").artifact_ref),
                ledger=ledger,
                references=(proxy_reference,),
                max_tokens=8_000,
                timeout_seconds=900,
                semantic_validate=validate,
            )
        finally:
            await self._write_ledger(node, ledger)
        attempts = operation["attempts"]
        return self._result(
            node, attempts=attempts, operations=attempts, cost=known_cost(operation.get("usage"))
        )

    async def _record(self, node: Node, _context: NodeExecutionContext) -> NodeExecutionResult:
        entity_id = str(node.params["entity_id"])
        admitted = self._require_admitted()
        proposal = admitted.proposal
        entity = proposal.entity(entity_id)
        plan = admitted.plan.plan(entity_id)
        review = models.ImageReview.model_validate_json(
            self._path(f"production/review/reviews/{entity_id}.json").read_bytes()
        )
        direction = models.EntityDirection.model_validate_json(
            self._path(f"production/direction/entities/{entity_id}.json").read_bytes()
        )
        image_ref = f"package/entities/{entity_id}.png"
        image_bytes = self._path(image_ref).read_bytes()
        if review.artifact_sha256 != content_sha256(image_bytes):
            raise ValueError("review does not bind the current image bytes")
        facts = inspect_image(image_bytes, expected_media_type="image/png")
        names = {item.entity_id: item.display_name for item in proposal.entities}
        relationships = [
            {
                **relationship.model_dump(mode="json"),
                "other_entity_id": _other(relationship, entity_id),
                "other_display_name": names.get(_other(relationship, entity_id), "?"),
                "direction": (
                    "outgoing" if relationship.source_entity_id == entity_id else "incoming"
                ),
            }
            for relationship in proposal.relationships
            if entity_id in (relationship.source_entity_id, relationship.target_entity_id)
        ]
        record = {
            "schema_version": 1,
            "kind": node.port("record").kind,
            "universe_id": proposal.universe_id,
            "status": "admitted" if review.verdict == "admit" else "rejected",
            "entity": entity.model_dump(mode="json"),
            "relationships": relationships,
            "identity_markers": [
                marker.model_dump(mode="json")
                for marker in proposal.identity_markers
                if marker.owner_entity_id == entity_id
            ],
            "concept": plan.model_dump(mode="json"),
            "direction_summary": {
                "primary_subject": direction.primary_subject,
                "action_beat": direction.action_beat.model_dump(mode="json"),
                "visual_identity": direction.visual_identity.model_dump(mode="json"),
            },
            "image": {
                "path": f"entities/{entity_id}.png",
                "sha256": content_sha256(image_bytes),
                "width": facts.width,
                "height": facts.height,
            },
            "review": review.model_dump(mode="json"),
            "publication_authorized": False,
        }
        refs = [
            self._run_ref(image_ref),
            self._run_ref(f"production/review/reviews/{entity_id}.json"),
            f"run://inputs/universe.json#sha256={admitted.universe_sha256}",
        ]
        await self._write_local(
            node.port("record").artifact_ref,
            _document_bytes(record),
            media_type="application/json",
            model="entity-record",
            prompt="Materialize the entity record.",
            refs=refs,
        )
        await self._write_local(
            node.port("markdown").artifact_ref,
            render_entity_markdown(record).encode("utf-8"),
            media_type="text/markdown",
            model="entity-record",
            prompt="Materialize the readable entity record.",
            refs=refs,
        )
        return self._result(node)

    async def _close(self, node: Node, _context: NodeExecutionContext) -> NodeExecutionResult:
        admitted = self._require_admitted()
        entries = []
        for entity in admitted.proposal.entities:
            record = json.loads(
                self._path(f"package/entities/{entity.entity_id}.json").read_bytes()
            )
            entries.append(
                {
                    "entity_id": entity.entity_id,
                    "status": record["status"],
                    "image": record["image"],
                }
            )
        inventory = {
            "schema_version": 1,
            "kind": INVENTORY_KIND,
            "universe_id": admitted.universe_id,
            "entity_count": len(entries),
            "image_count": len(entries),
            "admitted_count": sum(entry["status"] == "admitted" for entry in entries),
            "entries": entries,
            "publication_authorized": False,
        }
        await self._write_local(
            node.port("inventory").artifact_ref,
            _document_bytes(inventory),
            media_type="application/json",
            model="inventory",
            prompt="Close the inventory.",
            refs=[
                self._run_ref(f"package/entities/{entry['entity_id']}.json") for entry in entries
            ],
        )
        return self._result(node)


def _admit_cached(node: Node, payloads: tuple[bytes, ...]) -> bool:
    """Re-prove a restored image against the node that is asking for it now.

    The generation path validates the pixels it received; without this the
    restore path never does, so a cache entry drawn to a superseded canvas
    would be published as the answer to a question it does not answer. The key
    covers this too — the size is an input digest — but a cache is exactly the
    place where two belts are worth their cost.
    """

    if node.type_id != CONCEPT_IMAGE.type_id or not payloads:
        return True
    size = str(node.params.get("size", ""))
    try:
        width, height = (int(value) for value in size.split("x", 1))
        facts = inspect_image(payloads[0], expected_media_type="image/png")
    except (ValueError, TypeError):
        return False
    return (facts.width, facts.height) == (width, height) and not facts.has_alpha


def _bind(
    method: Callable[[Node, NodeExecutionContext], Awaitable[NodeExecutionResult]],
) -> NodeHandler:
    async def handler(node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        return await method(node, context)

    return handler


def _other(relationship: models.Relationship, entity_id: str) -> str:
    if relationship.source_entity_id == entity_id:
        return relationship.target_entity_id
    return relationship.source_entity_id


def render_entity_markdown(record: Mapping[str, Any]) -> str:
    """The readable half of an entity record: what a person reads beside the image."""

    entity = record["entity"]
    lines = [f"# {entity['display_name']}", ""]
    classes = [entity["primary_class"], *entity.get("facets", [])]
    lines.append(
        f"*{' / '.join(classes)}* · {entity['entity_kind']} · "
        f"{entity['salience']} · image {record['status']}"
    )
    lines += [
        "",
        entity["summary"],
        "",
        "## How it works or lives",
        "",
        entity["how_it_works_or_lives"],
        "",
        "## Present tension",
        "",
        entity["present_tension"],
        "",
        "## Facts",
        "",
    ]
    for fact in entity["facts"]:
        lines.append(f"- **{fact['fact_id']}** ({fact['lineage']}): {fact['claim']}")
    lines += ["", "## Relationships", ""]
    for relationship in record["relationships"]:
        arrow = "→" if relationship["direction"] == "outgoing" else "←"
        lines.append(
            f"- {arrow} {relationship['relationship_kind']} "
            f"**{relationship['other_display_name']}**: {relationship['summary']}"
        )
    if record["identity_markers"]:
        lines += ["", "## Identity markers", ""]
        for marker in record["identity_markers"]:
            lines.append(f"- {marker['form']}: {marker['meaning']} ({marker['materials']})")
    concept = record["concept"]
    lines += [
        "",
        "## Concept image",
        "",
        f"Purpose: {concept['primary_purpose']}. Question: {concept['audience_question']}",
        "",
        f"Signature: {concept['signature_motif']['action_verb']} / "
        f"{concept['signature_motif']['dominant_prop']} / "
        f"{concept['signature_motif']['vantage']}. "
        f"Contrast: {concept['in_frame_contrast']}",
        "",
        concept["scene_premise"],
        "",
        f"What this image alone teaches: {record['review']['what_the_image_teaches']}",
    ]
    if record["review"]["verdict"] == "reject":
        lines += ["", "Rejected: " + " ".join(record["review"]["blocking_findings"])]
    return "\n".join(lines) + "\n"


__all__ = [
    "UNIVERSE_COMPONENT",
    "UNIVERSE_RIGHTS",
    "UniverseNodeHandler",
    "compact_words",
    "make_image_proxy",
    "render_entity_markdown",
]
