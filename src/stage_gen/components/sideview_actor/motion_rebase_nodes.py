"""The motion-rebase node family: a judge reading and its verification, per drawn actor.

Two recipes carried this pair as their own node types and their own handler methods -
near-textual copies down to the admission closure and its error string - and only the
runner's could host a second actor kind, because only it resolved the subject from the
node's own params rather than assuming the player. The family lives here once, over a
``RebaseSubject`` every host resolves its own way. A recipe declares its pair through
``motion_rebase_node_types``, keeping the type id it shipped under as the cache
identity: the family may move home, the readings it already paid for do not move.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

from gnode import (
    Graph,
    GraphBuilder,
    Node,
    NodeCard,
    NodeExecutionResult,
    NodePolicy,
    NodeType,
    Port,
    PortRef,
    SoftwareIdentity,
    StructuredGenerationRequest,
    StructuredGenerationResult,
    StructuredGenerationService,
    StructuredOutputSchema,
    StructuredReference,
    ViewArchetype,
    dependency_port,
)
from stage_gen.canonical import content_sha256
from stage_gen.components._node_kit import (
    ProviderCall,
    card_prompt,
    node_result,
    write_local_image,
)
from stage_gen.components.sideview_actor.motion_geometry import MotionAtlasGeometry
from stage_gen.components.sideview_actor.motion_rebase import (
    MOTION_REBASE_CORRECTION_SCHEMA_NAME,
    MOTION_REBASE_SCHEMA_NAME,
    MotionRebaseError,
    MotionRebaseReading,
    admit_first_pass_record,
    build_motion_rebase_plate,
    build_motion_rebase_verification_plate,
    evaluate_motion_rebase,
    evaluate_motion_rebase_correction,
    motion_rebase_json_schema,
    motion_rebase_prompt,
    motion_rebase_verification_prompt,
    parse_motion_rebase,
)
from stage_gen.media import data_url
from stage_gen.media.sprite_sheets import split_atlas_columns

_P = "2d/sideview/actor"
STRUCTURED_FEATURES = ("structured_output", "image_input")
#: The judge is told to answer only in the schema; the words are part of the request.
JUDGE_SYSTEM_PROMPT = (
    "You are a sprite-sheet scale judge. Return only the strict structured object."
)

REBASE_PLATE_KIND = "rebase-plate-v1"
REBASE_READING_KIND = "rebase-reading-v1"
REBASE_VERIFICATION_KIND = "rebase-verification-v1"

MOTION_REBASE_JUDGE = NodeType(
    type_id=f"{_P}/motion_rebase.judge",
    title="Scale rebase reading",
    archetype=ViewArchetype.JUDGE,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=NodePolicy(max_attempts=6, gates=("rebase-admission",)),
    contract_version="motion-rebase-v1",
)
MOTION_REBASE_VERIFY = NodeType(
    type_id=f"{_P}/motion_rebase.verify",
    title="Scale rebase residual",
    archetype=ViewArchetype.JUDGE,
    operation="structured_generation",
    features=STRUCTURED_FEATURES,
    policy=NodePolicy(max_attempts=6, gates=("rebase-admission",)),
    contract_version="motion-rebase-verify-v1",
)


@dataclass(frozen=True, slots=True)
class MotionRebaseNodeTypes:
    judge: NodeType
    verify: NodeType


def motion_rebase_node_types(
    *,
    identity_prefix: str | None = None,
    judge_version: str = MOTION_REBASE_JUDGE.contract_version,
    verify_version: str = MOTION_REBASE_VERIFY.contract_version,
) -> MotionRebaseNodeTypes:
    """The pair as one recipe declares it.

    ``identity_prefix`` is the type-id prefix a recipe shipped the family under; it
    becomes the cache identity so every reading already paid for keeps its key. The
    versions likewise keep a recipe's own contracts until it chooses to converge.
    """

    judge = MOTION_REBASE_JUDGE
    verify = MOTION_REBASE_VERIFY
    if identity_prefix is not None:
        judge = replace(judge, identity=f"{identity_prefix}/motion_rebase.judge")
        verify = replace(verify, identity=f"{identity_prefix}/motion_rebase.verify")
    if judge_version != judge.contract_version:
        judge = replace(judge, contract_version=judge_version)
    if verify_version != verify.contract_version:
        verify = replace(verify, contract_version=verify_version)
    return MotionRebaseNodeTypes(judge=judge, verify=verify)


# ------------------------------------------------------------------- graph


@dataclass(frozen=True, slots=True)
class RebaseLayout:
    """Where one actor's four rebase artifacts land, run-relative.

    The host names them: both recipes that shipped the family publish these paths into
    their runtime, and a manifest reads them by path.
    """

    plate: str
    reading: str
    verification_plate: str
    verification: str


def add_motion_rebase_nodes(
    builder: GraphBuilder,
    *,
    types: MotionRebaseNodeTypes,
    judge_id: str,
    verify_id: str,
    domain: str,
    display_name: str,
    states: Sequence[str],
    depends_on: Sequence[str],
    input_digests: Sequence[str],
    layout: RebaseLayout,
    params: Mapping[str, str] | None = None,
    attempts_port: Callable[[str], Port] | None = None,
) -> tuple[str, str]:
    """Judge then verify; returns the two node ids.

    The judge depends on every published atlas, because the plate carries every frame of
    every state: a reading taken against a partial plate would rebase onto a baseline the
    judge could not see beside the states it was rating. The verification depends on the
    judge alone and reads the atlases the judge already depended on.
    """

    prompt = motion_rebase_prompt(display_name, list(states))
    judge_ports: list[Port] = [
        Port(
            port_id="plate",
            artifact_ref=layout.plate,
            kind=REBASE_PLATE_KIND,
            sidecar_ref=f"{layout.plate}.meta.json",
        ),
        Port(
            port_id="reading",
            artifact_ref=layout.reading,
            kind=REBASE_READING_KIND,
            sidecar_ref=f"{layout.reading}.meta.json",
        ),
    ]
    if attempts_port is not None:
        judge_ports.append(attempts_port(judge_id))
    judge = builder.add(
        types.judge,
        judge_id,
        domain=domain,
        description=(
            "judge every motion atlas against the baseline on one comparison plate for "
            f"{display_name}"
        ),
        params=dict(params or {}),
        depends_on=tuple(depends_on),
        input_digests=tuple(input_digests),
        ports=tuple(judge_ports),
        card=NodeCard(prompt=prompt, schema_name="motion_rebase"),
    )
    verify_ports: list[Port] = [
        Port(
            port_id="plate",
            artifact_ref=layout.verification_plate,
            kind=REBASE_PLATE_KIND,
            sidecar_ref=f"{layout.verification_plate}.meta.json",
        ),
        Port(
            port_id="verification",
            artifact_ref=layout.verification,
            kind=REBASE_VERIFICATION_KIND,
            sidecar_ref=f"{layout.verification}.meta.json",
        ),
    ]
    if attempts_port is not None:
        verify_ports.append(attempts_port(verify_id))
    verify = builder.add(
        types.verify,
        verify_id,
        domain=domain,
        description=(
            "close the loop on the rebase: judge the residual on a plate composed with the "
            f"first-pass multipliers applied for {display_name}"
        ),
        params=dict(params or {}),
        depends_on=(judge.node_id,),
        input_digests=tuple(input_digests),
        ports=tuple(verify_ports),
        card=NodeCard(
            prompt=motion_rebase_verification_prompt(display_name, list(states)),
            schema_name="motion_rebase",
            reference_inputs=(PortRef(node_id=judge.node_id, port_id="reading"),),
        ),
    )
    return judge.node_id, verify.node_id


# ----------------------------------------------------------------- handler


@dataclass(frozen=True)
class RebaseSubject:
    """Which drawn actor a rebase node is about, resolved by the host from the node.

    A player, an avatar and a boss differ in their vocabulary, their baseline and where
    their atlases land, and in nothing the judge cares about.
    """

    #: What the host calls this kind of actor; it prefixes the request's trace kind.
    label: str
    entity_id: str
    display_name: str
    states: tuple[str, ...]
    baseline_state: str
    #: The validated atlas for each state, run-relative.
    atlas_refs: Mapping[str, str]
    #: How each state's atlas is cut into frames.
    geometry: Callable[[str], MotionAtlasGeometry]


@dataclass(frozen=True)
class MotionRebaseHost:
    """Everything the pair needs from whichever recipe hosts it."""

    run_dir: Path
    subject: Callable[[Node], RebaseSubject]
    #: The host's software identity, stamped on the plates it composes.
    component: SoftwareIdentity
    handler_version: str
    #: The local model name the plate provenance records.
    plate_model: str
    #: Extra request metadata the host wants on every judge call, such as its checkpoint.
    metadata: Mapping[str, str] = field(default_factory=dict)


class MotionRebaseHandlers:
    """The two coroutines behind the rebase node types, owned by no recipe.

    A host binds these into its own registry and keeps its caching, tracing, and error
    translation. ``provider_call`` is the seam for a recipe that writes attempt ledgers.
    """

    def __init__(
        self,
        host: MotionRebaseHost,
        *,
        graph: Graph,
        structured_service: StructuredGenerationService[object],
        provider_call: ProviderCall | None = None,
    ) -> None:
        self._host = host
        self._graph = graph
        self._structured = structured_service
        self._provider_call = provider_call

    async def judge(self, node: Node) -> NodeExecutionResult:
        """Judge every one of this actor's atlases against its baseline, on one plate.

        Separate states are separate provider calls, so nothing in the pixels ties their
        draw scale together, and an alpha box cannot separate a short pose from a small
        drawing. The plate is composited locally from bytes that have already shipped: it
        costs no generation, cannot be redrawn by a provider, and shows every frame at one
        uniform scale so a state drawn small looks small.
        """

        subject = self._host.subject(node)
        states = list(subject.states)
        frames_by_state = self._frames(subject)
        plate = build_motion_rebase_plate(frames_by_state, baseline_state=subject.baseline_state)
        plate_output = self._host.run_dir / node.port("plate").artifact_ref
        await write_local_image(
            plate_output,
            plate.png,
            prompt=(
                "Compose the complete motion-rebase judging plate for "
                f"{subject.entity_id}: every frame of every state at one uniform source scale."
            ),
            inputs=self._atlas_inputs(subject),
            validation={
                "baseline_state": subject.baseline_state,
                "frame_count": len(plate.frames),
                "band_count": len(plate.bands),
                "band_baseline_px": [band.baseline_drawn_height for band in plate.bands],
            },
            model=self._host.plate_model,
            component=self._host.component,
            handler_version=self._host.handler_version,
        )

        def admit(reading: object) -> dict[str, object]:
            # The service is bound to `object`, so the admitted type is re-established here
            # rather than assumed: an unparsed reading must fail closed like any other.
            if not isinstance(reading, MotionRebaseReading):
                raise MotionRebaseError("judge returned a reading the parser did not admit")
            return evaluate_motion_rebase(
                reading,
                published_states=states,
                plate=plate,
                baseline_state=subject.baseline_state,
            )

        request = StructuredGenerationRequest(
            prompt=card_prompt(node),
            system=JUDGE_SYSTEM_PROMPT,
            artifact_path=self._host.run_dir / node.port("reading").artifact_ref,
            schema=StructuredOutputSchema(
                name=MOTION_REBASE_SCHEMA_NAME,
                description="Per-state draw-scale multipliers against an actor's baseline",
                json_schema=motion_rebase_json_schema(),
                strict=True,
            ),
            parse=parse_motion_rebase,
            references=(self._reference(plate_output),),
            artifact_value=admit,
            validate=admit,
            timeout_seconds=600,
            metadata={
                **self._host.metadata,
                # A distinct kind from the semantic review: both judge the same actor, but
                # one reads appearance and this one reads draw scale, and a consumer of the
                # trace must be able to tell them apart.
                "kind": f"{subject.label}-motion-rebase",
                "entity_id": subject.entity_id,
                "states": states,
                "plate_sha256": plate.sha256,
            },
        )
        result = await self._call(node, request)
        return node_result(
            self._host.run_dir, node, attempts=result.attempts, provider_operations=result.attempts
        )

    async def verify(self, node: Node) -> NodeExecutionResult:
        """Close the loop on the first pass: judge the residual on a plate composed with it.

        The first reading is taken across atlases that disagree by up to a factor of three,
        which is the hard form of the task. This stage applies that reading, composes a
        plate where every state is drawn already rebased, and asks the judge only for the
        small correction that remains - then multiplies the two. The first-pass record is
        re-admitted from disk against a plate rebuilt from today's bytes, so a reading that
        outlived its artwork is refused rather than corrected.
        """

        subject = self._host.subject(node)
        states = list(subject.states)
        frames_by_state = self._frames(subject)
        plate = build_motion_rebase_plate(frames_by_state, baseline_state=subject.baseline_state)
        _judge, reading_port = dependency_port(
            self._graph, node, kind=REBASE_READING_KIND, port_id="reading"
        )
        first_pass_data = (self._host.run_dir / reading_port.artifact_ref).read_bytes()
        first_pass = admit_first_pass_record(
            json.loads(first_pass_data),
            published_states=states,
            plate=plate,
            baseline_state=subject.baseline_state,
        )
        verification_plate = build_motion_rebase_verification_plate(
            frames_by_state, first_pass, baseline_state=subject.baseline_state
        )
        plate_output = self._host.run_dir / node.port("plate").artifact_ref
        await write_local_image(
            plate_output,
            verification_plate.png,
            prompt=(
                "Compose the motion-rebase verification plate for "
                f"{subject.entity_id}: every frame of every state with its first-pass "
                "multiplier applied."
            ),
            inputs=[*self._atlas_inputs(subject), (reading_port.artifact_ref, first_pass_data)],
            validation={
                "baseline_state": subject.baseline_state,
                "frame_count": len(verification_plate.frames),
                "band_count": len(verification_plate.bands),
                "band_baseline_px": [
                    band.baseline_drawn_height for band in verification_plate.bands
                ],
                "first_pass": {state: first_pass[state] for state in sorted(first_pass)},
                "first_pass_sha256": content_sha256(first_pass_data),
            },
            model=self._host.plate_model,
            component=self._host.component,
            handler_version=self._host.handler_version,
        )

        def admit(reading: object) -> dict[str, object]:
            if not isinstance(reading, MotionRebaseReading):
                raise MotionRebaseError("judge returned a reading the parser did not admit")
            return evaluate_motion_rebase_correction(
                reading,
                first_pass=first_pass,
                published_states=states,
                plate=plate,
                verification_plate=verification_plate,
                baseline_state=subject.baseline_state,
            )

        request = StructuredGenerationRequest(
            prompt=card_prompt(node),
            system=JUDGE_SYSTEM_PROMPT,
            artifact_path=self._host.run_dir / node.port("verification").artifact_ref,
            schema=StructuredOutputSchema(
                name=MOTION_REBASE_CORRECTION_SCHEMA_NAME,
                description="Per-state residual corrections against an actor's first-pass rebase",
                json_schema=motion_rebase_json_schema(),
                strict=True,
            ),
            parse=parse_motion_rebase,
            references=(self._reference(plate_output),),
            artifact_value=admit,
            validate=admit,
            timeout_seconds=600,
            metadata={
                **self._host.metadata,
                # A distinct kind from the first pass: both judge the same actor's scale,
                # but one reads the raw disagreement and this one reads the residual after
                # the first pass is applied.
                "kind": f"{subject.label}-motion-rebase-verify",
                "entity_id": subject.entity_id,
                "states": states,
                "plate_sha256": verification_plate.sha256,
            },
        )
        result = await self._call(node, request)
        return node_result(
            self._host.run_dir, node, attempts=result.attempts, provider_operations=result.attempts
        )

    # ----------------------------------------------------------------- shared

    async def _call(
        self, node: Node, request: StructuredGenerationRequest[Any]
    ) -> StructuredGenerationResult[object]:
        call = self._provider_call
        if call is None:
            return await self._structured.generate(request)
        return cast(
            StructuredGenerationResult[object],
            await call(
                node, "motion_rebase", request.prompt, lambda: self._structured.generate(request)
            ),
        )

    def _frames(self, subject: RebaseSubject) -> dict[str, tuple[bytes, ...]]:
        frames: dict[str, tuple[bytes, ...]] = {}
        for state in subject.states:
            geometry = subject.geometry(state)
            frames[state] = split_atlas_columns(
                (self._host.run_dir / subject.atlas_refs[state]).read_bytes(),
                geometry.columns,
                geometry.rows,
            )
        return frames

    def _atlas_inputs(self, subject: RebaseSubject) -> list[tuple[str, bytes]]:
        return [
            (
                subject.atlas_refs[state],
                (self._host.run_dir / subject.atlas_refs[state]).read_bytes(),
            )
            for state in subject.states
        ]

    def _reference(self, path: Path) -> StructuredReference:
        return StructuredReference(
            url=data_url(path.read_bytes(), "image/png"),
            provenance_ref=f"run://{path.relative_to(self._host.run_dir).as_posix()}",
        )


__all__ = [
    "JUDGE_SYSTEM_PROMPT",
    "MOTION_REBASE_JUDGE",
    "MOTION_REBASE_VERIFY",
    "REBASE_PLATE_KIND",
    "REBASE_READING_KIND",
    "REBASE_VERIFICATION_KIND",
    "STRUCTURED_FEATURES",
    "MotionRebaseHandlers",
    "MotionRebaseHost",
    "MotionRebaseNodeTypes",
    "RebaseLayout",
    "RebaseSubject",
    "add_motion_rebase_nodes",
    "motion_rebase_node_types",
]
