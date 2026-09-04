"""The soundtrack node family: declared once, hosted by two recipes under their own identity."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

import pytest

from gnode import (
    Binding,
    BindingTable,
    GraphBuilder,
    ModelRef,
    MusicGenerationRequest,
    Port,
)
from stage_gen.components._node_kit import object_digest
from stage_gen.components.game_soundtrack import SoundtrackTrack, TrackGenerationIntent
from stage_gen.components.game_soundtrack import nodes as family
from stage_gen.components.game_soundtrack.nodes import (
    SOUNDTRACK_GENERATE,
    SOUNDTRACK_VALIDATE,
    SoundtrackHandlers,
    SoundtrackHost,
    add_soundtrack_nodes,
    soundtrack_node_types,
)
from stage_gen.media.audio import AudioProbe
from stage_gen.recipes.graph_document import RecipeGraph


class _Ops(StrEnum):
    LOCAL = "local"
    MUSIC_GENERATION = "music_generation"


class _Graph(RecipeGraph):
    OPERATIONS = _Ops

    schema_version: Literal[1]
    kind: Literal["soundtrack-family-test-graph-v1"]
    recipe: Literal["soundtrack-family-test"]


TRACK = SoundtrackTrack(
    track_id="sunpetal_morning",
    display_name="Sunpetal Morning",
    creative_brief="A bright morning theme.",
    generation=TrackGenerationIntent(
        intent="generate", instrumental=True, seamless_loop=True, target_duration_seconds=60
    ),
)
PROFILE = BindingTable(
    [
        Binding(
            operation="music_generation",
            model=ModelRef(model="test-music", provider="openrouter"),
            features=frozenset(family.MUSIC_FEATURES),
            resource_id="openrouter-music",
            estimated_duration_seconds=1.0,
            estimated_cost_low_usd=0.0,
            estimated_cost_high_usd=0.0,
            verified_on="2026-09-04",
        )
    ]
)


def test_a_recipe_keeps_its_shipped_identity_and_contract() -> None:
    types = soundtrack_node_types(
        identity_prefix="2d/sideview/runner", track_version="runner-soundtrack-track-v3"
    )
    assert types.generate.type_id == SOUNDTRACK_GENERATE.type_id == "soundtrack.generate"
    assert types.generate.cache_identity == "2d/sideview/runner/soundtrack.generate"
    assert types.generate.contract_version == "runner-soundtrack-track-v3"
    # Admission is local and free, so it converges on the family's contract.
    assert types.validate.cache_identity == "2d/sideview/runner/soundtrack.validate"
    assert types.validate.contract_version == SOUNDTRACK_VALIDATE.contract_version
    plain = soundtrack_node_types()
    assert plain.generate is SOUNDTRACK_GENERATE and plain.validate is SOUNDTRACK_VALIDATE


def _graph(*, attempts: bool) -> _Graph:
    builder = GraphBuilder(profile=PROFILE)
    validations = add_soundtrack_nodes(
        builder,
        types=soundtrack_node_types(),
        tracks=[TRACK],
        depends_on=(),
        node_id=lambda track, stage: f"track-{track.track_id}-{stage}",
        prompt=lambda track: f"compose {track.display_name}",
        generate_digests=lambda track, prompt: (object_digest({"prompt": prompt}),),
        attempts_port=(
            (
                lambda node_id: Port(
                    port_id="attempts", artifact_ref=f"attempts/{node_id}.json", kind="ledger-v1"
                )
            )
            if attempts
            else None
        ),
    )
    assert validations == ["track-sunpetal_morning-validate"]
    return _Graph.seal(
        resources=builder.resources(), nodes=builder.nodes, terminal_node_id=validations[0]
    )


def test_the_graph_helper_declares_the_pair_with_the_prompt_on_the_card() -> None:
    graph = _graph(attempts=True)
    generate = graph.node("track-sunpetal_morning-generate")
    validate = graph.node("track-sunpetal_morning-validate")
    assert generate.card is not None and generate.card.prompt == "compose Sunpetal Morning"
    assert [port.port_id for port in generate.ports] == ["audio", "attempts"]
    assert generate.ports[0].sidecar_ref == "soundtrack/sunpetal_morning.mp3.meta.json"
    assert validate.depends_on == (generate.node_id,)
    assert validate.ports[0].kind == family.SOUNDTRACK_VALIDATION_KIND
    # Without a ledger port the generate node declares the audio alone.
    assert [port.port_id for port in _graph(attempts=False).node(generate.node_id).ports] == [
        "audio"
    ]


@dataclass
class _Result:
    attempts: int


class _FakeMusic:
    def __init__(self) -> None:
        self.requests: list[MusicGenerationRequest] = []

    async def generate(self, request: MusicGenerationRequest) -> _Result:
        self.requests.append(request)
        _publish(Path(request.artifact_path))
        return _Result(attempts=2)


def _publish(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"ID3" + bytes(2048))
    output.with_name(output.name + ".meta.json").write_text("{}")


@pytest.mark.asyncio
async def test_the_handlers_generate_from_the_card_and_record_the_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = _graph(attempts=False)
    music = _FakeMusic()
    calls: list[str] = []

    async def provider_call(node, role, prompt, thunk):  # type: ignore[no-untyped-def]
        calls.append(f"{node.node_id}:{role}:{prompt}")
        return await thunk()

    handlers = SoundtrackHandlers(
        SoundtrackHost(run_dir=tmp_path, track=lambda _id: TRACK),
        graph=graph,
        music_service=music,  # type: ignore[arg-type]
        provider_call=provider_call,
    )
    generated = await handlers.generate(graph.node("track-sunpetal_morning-generate"))
    assert generated.provider_operations == 2 and generated.attempts == 2
    assert [artifact.artifact_ref for artifact in generated.artifacts] == [
        "soundtrack/sunpetal_morning.mp3",
        "soundtrack/sunpetal_morning.mp3.meta.json",
    ]
    assert calls == ["track-sunpetal_morning-generate:soundtrack:compose Sunpetal Morning"]
    assert music.requests[0].metadata["target_duration_seconds"] == 60

    async def probe(path: Path, *, timeout_seconds: float) -> AudioProbe:
        return AudioProbe(duration_seconds=58.25, format_name="mp3", bit_rate=128000.0)

    monkeypatch.setattr(family, "probe_audio", probe)
    validated = await handlers.validate(graph.node("track-sunpetal_morning-validate"))
    record = json.loads((tmp_path / "soundtrack/sunpetal_morning.validation.json").read_text())
    assert validated.provider_operations == 0
    assert record == {
        "schema_version": 1,
        "kind": "soundtrack-validation-v1",
        "track_id": "sunpetal_morning",
        "format_name": "mp3",
        "duration_seconds": 58.25,
        "target_duration_seconds": 60,
        "target_delta_seconds": -1.75,
        "bit_rate": 128000.0,
        "instrumental_intent": True,
        "seamless_loop_intent": True,
        "container_valid": True,
        "listening_verdict": "not_performed",
    }


@pytest.mark.asyncio
async def test_a_short_track_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    graph = _graph(attempts=False)
    handlers = SoundtrackHandlers(
        SoundtrackHost(run_dir=tmp_path, track=lambda _id: TRACK), graph=graph, music_service=None
    )

    async def probe(path: Path, *, timeout_seconds: float) -> AudioProbe:
        return AudioProbe(duration_seconds=4.0, format_name="mp3", bit_rate=None)

    monkeypatch.setattr(family, "probe_audio", probe)
    with pytest.raises(ValueError, match="shorter than 15 seconds"):
        await handlers.validate(graph.node("track-sunpetal_morning-validate"))
    with pytest.raises(ValueError, match="requires a music service"):
        await handlers.generate(graph.node("track-sunpetal_morning-generate"))
