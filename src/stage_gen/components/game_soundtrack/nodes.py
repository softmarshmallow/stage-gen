"""The soundtrack node family: one generated track and its admission.

Two recipes carried this pair as their own node types with their own handler
methods, and the runner's admission record silently dropped the five facts that
tie a measured clip back to the authored intent. The family lives here once. A
recipe declares its pair through ``soundtrack_node_types``, which is where a
recipe that shipped under an older type id keeps that id as the cache identity:
the family may move home, the artifacts it already paid for do not move with it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from gnode import (
    Graph,
    GraphBuilder,
    MusicGenerationRequest,
    MusicGenerationService,
    Node,
    NodeCard,
    NodeExecutionResult,
    NodePolicy,
    NodeType,
    Port,
    PortRef,
    ViewArchetype,
    atomic_write_json,
    dependency_port,
)
from stage_gen.components._node_kit import ProviderCall, card_prompt, node_result, object_digest
from stage_gen.components.game_soundtrack.models import SoundtrackTrack
from stage_gen.media import probe_audio, validate_music_payload

#: The taxonomy's complete path for the family: a soundtrack is not camera-scoped.
_P = "soundtrack"
MUSIC_FEATURES = ("instrumental_loop",)

SOUNDTRACK_TRACK_KIND = "soundtrack-track-v1"
SOUNDTRACK_VALIDATION_KIND = "soundtrack-validation-v1"
#: A track shorter than this cannot carry a scene; the provider is asked again.
MINIMUM_TRACK_SECONDS = 15.0

SOUNDTRACK_GENERATE = NodeType(
    type_id=f"{_P}.generate",
    title="Soundtrack track",
    archetype=ViewArchetype.MUSIC,
    operation="music_generation",
    features=MUSIC_FEATURES,
    policy=NodePolicy(max_attempts=6),
    contract_version="soundtrack-track-v1",
)
SOUNDTRACK_VALIDATE = NodeType(
    type_id=f"{_P}.validate",
    title="Track admission",
    archetype=ViewArchetype.VALIDATE,
    operation="local",
    contract_version="soundtrack-validate-v1",
)


@dataclass(frozen=True, slots=True)
class SoundtrackNodeTypes:
    generate: NodeType
    validate: NodeType


def soundtrack_node_types(
    *,
    identity_prefix: str | None = None,
    track_version: str = SOUNDTRACK_GENERATE.contract_version,
) -> SoundtrackNodeTypes:
    """The pair as one recipe declares it.

    ``identity_prefix`` is the type-id prefix a recipe shipped the family under; it
    becomes the cache identity so every track already generated keeps its key.
    ``track_version`` likewise keeps a recipe's own generation contract until it
    chooses to converge. Admission is local and free, so it always converges.
    """

    generate = SOUNDTRACK_GENERATE
    validate = SOUNDTRACK_VALIDATE
    if identity_prefix is not None:
        generate = replace(generate, identity=f"{identity_prefix}/soundtrack.generate")
        validate = replace(validate, identity=f"{identity_prefix}/soundtrack.validate")
    if track_version != generate.contract_version:
        generate = replace(generate, contract_version=track_version)
    return SoundtrackNodeTypes(generate=generate, validate=validate)


# ------------------------------------------------------------------- graph


def add_soundtrack_nodes(
    builder: GraphBuilder,
    *,
    types: SoundtrackNodeTypes,
    tracks: Iterable[SoundtrackTrack],
    depends_on: Sequence[str],
    node_id: Callable[[SoundtrackTrack, str], str],
    prompt: Callable[[SoundtrackTrack], str],
    generate_digests: Callable[[SoundtrackTrack, str], Sequence[str]],
    attempts_port: Callable[[str], Port] | None = None,
    domain: str = "soundtrack",
) -> list[str]:
    """One generate-then-validate pair per track; returns the validation node ids.

    The host names the nodes and keys the generation - both are cache identity, and
    both differ between the recipes that shipped this family - while the family owns
    the ports, the card, and the admission's own key, which is the authored intent.
    """

    validations: list[str] = []
    for track in tracks:
        provider_prompt = prompt(track)
        generate_id = node_id(track, "generate")
        ports: list[Port] = [
            Port(
                port_id="audio",
                artifact_ref=f"soundtrack/{track.track_id}.mp3",
                kind=SOUNDTRACK_TRACK_KIND,
                sidecar_ref=f"soundtrack/{track.track_id}.mp3.meta.json",
            )
        ]
        if attempts_port is not None:
            ports.append(attempts_port(generate_id))
        generated = builder.add(
            types.generate,
            generate_id,
            domain=domain,
            description=f"generate soundtrack track {track.track_id}",
            params={"track_id": track.track_id},
            depends_on=tuple(depends_on),
            cache_depends_on=(),
            input_digests=tuple(generate_digests(track, provider_prompt)),
            ports=tuple(ports),
            card=NodeCard(prompt=provider_prompt),
        )
        validated = builder.add(
            types.validate,
            node_id(track, "validate"),
            domain=domain,
            description=(
                "validate audio container, duration, channels, and loop intent for "
                f"{track.track_id}"
            ),
            params={"track_id": track.track_id},
            depends_on=(generated.node_id,),
            input_digests=(object_digest(track.generation.model_dump(mode="json")),),
            ports=(
                Port(
                    port_id="validation",
                    artifact_ref=f"soundtrack/{track.track_id}.validation.json",
                    kind=SOUNDTRACK_VALIDATION_KIND,
                ),
            ),
            card=NodeCard(reference_inputs=(PortRef(node_id=generated.node_id, port_id="audio"),)),
            duration_seconds=1.0,
        )
        validations.append(validated.node_id)
    return validations


# ----------------------------------------------------------------- handler


@dataclass(frozen=True)
class SoundtrackHost:
    """Everything the pair needs from whichever recipe hosts it."""

    #: The run the host is writing into.
    run_dir: Path
    #: One authored track by its id.
    track: Callable[[str], SoundtrackTrack]


class SoundtrackHandlers:
    """The two coroutines behind the soundtrack node types, owned by no recipe.

    A host binds these into its own registry and keeps its caching, tracing, and error
    translation. ``provider_call`` is the seam for a recipe that writes attempt ledgers.
    """

    def __init__(
        self,
        host: SoundtrackHost,
        *,
        graph: Graph,
        music_service: MusicGenerationService | None,
        provider_call: ProviderCall | None = None,
    ) -> None:
        self._host = host
        self._graph = graph
        self._music = music_service
        self._provider_call = provider_call

    def request(self, node: Node) -> MusicGenerationRequest:
        """The exact request a generate node sends; a host that re-proves provenance reads it."""

        track = self._host.track(str(node.params["track_id"]))
        return MusicGenerationRequest(
            prompt=card_prompt(node),
            artifact_path=self._host.run_dir / node.port("audio").artifact_ref,
            output_format="mp3",
            timeout_seconds=900,
            metadata={
                "track_id": track.track_id,
                "target_duration_seconds": track.generation.target_duration_seconds,
                "seamless_loop": track.generation.seamless_loop,
            },
            validate=lambda artifact: validate_music_payload(artifact.data),
        )

    async def generate(self, node: Node) -> NodeExecutionResult:
        music = self._music
        if music is None:
            raise ValueError("soundtrack generation requires a music service")
        request = self.request(node)
        call = self._provider_call
        if call is None:
            result = await music.generate(request)
        else:
            result = await call(node, "soundtrack", request.prompt, lambda: music.generate(request))
        return node_result(
            self._host.run_dir,
            node,
            attempts=result.attempts,
            provider_operations=result.attempts,
        )

    async def validate(self, node: Node) -> NodeExecutionResult:
        """Admit the container and duration, and record the measured clip against the intent."""

        track = self._host.track(str(node.params["track_id"]))
        _producer, port = dependency_port(self._graph, node, kind=SOUNDTRACK_TRACK_KIND)
        probe = await probe_audio(self._host.run_dir / port.artifact_ref, timeout_seconds=120)
        if probe.duration_seconds < MINIMUM_TRACK_SECONDS:
            raise ValueError(
                f"generated soundtrack track is shorter than {MINIMUM_TRACK_SECONDS:g} seconds"
            )
        target = track.generation.target_duration_seconds
        atomic_write_json(
            self._host.run_dir / node.port("validation").artifact_ref,
            {
                "schema_version": 1,
                "kind": SOUNDTRACK_VALIDATION_KIND,
                "track_id": track.track_id,
                "format_name": probe.format_name,
                "duration_seconds": round(probe.duration_seconds, 3),
                "target_duration_seconds": target,
                "target_delta_seconds": round(probe.duration_seconds - target, 3),
                "bit_rate": probe.bit_rate,
                "instrumental_intent": track.generation.instrumental,
                "seamless_loop_intent": track.generation.seamless_loop,
                "container_valid": True,
                "listening_verdict": "not_performed",
            },
        )
        return node_result(self._host.run_dir, node)


__all__ = [
    "MINIMUM_TRACK_SECONDS",
    "MUSIC_FEATURES",
    "SOUNDTRACK_GENERATE",
    "SOUNDTRACK_TRACK_KIND",
    "SOUNDTRACK_VALIDATE",
    "SOUNDTRACK_VALIDATION_KIND",
    "SoundtrackHandlers",
    "SoundtrackHost",
    "SoundtrackNodeTypes",
    "add_soundtrack_nodes",
    "soundtrack_node_types",
]
