"""The designer loop, driven by a scripted backend. Nothing here touches a network."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from stage_gen.components._types import ProviderResponseMetadata
from stage_gen.components.platformer_map_design import (
    MAX_QUOTED_PROBLEMS,
    DesignBrief,
    design_chunks,
)
from stage_gen.components.structured_generation import (
    ProviderStructuredOutput,
    StructuredGenerationRequest,
    StructuredGenerationService,
)
from stage_gen.reliability import RetryPolicy

from ._profiles import GROUND_FOOTED_PROFILE

_SOUND_SENTENCE: dict[str, object] = {
    "design_notes": "a breather, a climb, a dip, and a jump chain",
    "start_height": 3,
    "chunks": [
        {"kind": "run", "len": 10},
        {"kind": "stairs", "steps": 2, "step_h": 1, "tread": 4, "dir": "up"},
        {"kind": "perch", "platform_width": 6, "climb_rise": 4, "variant": "root_ladder"},
        {"kind": "hollow", "width": 8, "depth": 2},
        {"kind": "perch", "platform_width": 5, "climb_rise": 4, "variant": "rope_climb"},
        {
            "kind": "hop_chain",
            "count": 3,
            "jump_rise": 1,
            "gap": 4,
            "platform_width": 4,
            "dir": "up",
        },
        {"kind": "perch", "platform_width": 7, "climb_rise": 4, "variant": "shrine_rope_ladder"},
        {"kind": "run", "len": 20},
    ],
}

_OVERFLOWING_SENTENCE: dict[str, object] = {
    "design_notes": "wider than the map",
    "start_height": 3,
    "chunks": [
        {"kind": "run", "len": 100},
        {"kind": "hollow", "width": 40, "depth": 1},
        {"kind": "run", "len": 10},
    ],
}

#: More faults than the feedback budget quotes: eight unknown words, then a map with no
#: climbables at all. Nine problems against a budget of six.
_MANY_PROBLEM_SENTENCE: dict[str, object] = {
    "design_notes": "eight words this game does not have",
    "start_height": 3,
    "chunks": [
        *({"kind": f"spiral_{turn}", "turns": turn} for turn in range(1, 9)),
        {"kind": "run", "len": 40},
    ],
}

#: Schema-clean and expandable, but the floor it lays is deeper than this game can carry. The
#: complaint names a column, which is what the chunk translator re-anchors.
_TOO_DEEP_SENTENCE: dict[str, object] = {
    "design_notes": "a floor deeper than this game can carry",
    "start_height": 10,
    "chunks": [
        {"kind": "run", "len": 10},
        {"kind": "run", "len": 30},
        {"kind": "run", "len": 40},
    ],
}


class _ScriptedComposerBackend:
    """Replays canned compositions in order, repeating the last one once the script runs out."""

    provider = "scripted-composer"
    model = "chunk-grammar-test"
    secrets: tuple[str, ...] = ()

    def __init__(self, compositions: Sequence[Mapping[str, object]]) -> None:
        self._compositions = list(compositions)
        self.prompts: list[str] = []
        self.systems: list[str | None] = []
        self.seeds: list[int | None] = []

    async def generate_once(
        self, request: StructuredGenerationRequest[object]
    ) -> ProviderStructuredOutput:
        self.prompts.append(request.prompt)
        self.systems.append(request.system)
        self.seeds.append(request.seed)
        index = min(len(self.prompts) - 1, len(self._compositions) - 1)
        decoded = dict(self._compositions[index])
        return ProviderStructuredOutput(
            decoded=decoded,
            raw_text=json.dumps(decoded),
            response_metadata=ProviderResponseMetadata(request_id=f"compose-{len(self.prompts)}"),
        )

    async def aclose(self) -> None:
        return None


def _service(backend: _ScriptedComposerBackend) -> StructuredGenerationService[object]:
    return StructuredGenerationService[object](
        backend, retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0)
    )


def _attempt_artifacts(directory: Path) -> list[str]:
    """The composition artifacts written to a directory, without their provenance sidecars."""

    return sorted(
        path.name
        for path in directory.glob("attempt-*.json")
        if not path.name.endswith(".meta.json")
    )


async def test_design_chunks_returns_after_one_attempt_when_the_first_sentence_validates(
    tmp_path: Path,
) -> None:
    backend = _ScriptedComposerBackend([_SOUND_SENTENCE])

    attempts = await design_chunks(
        _service(backend),
        GROUND_FOOTED_PROFILE,
        DesignBrief(intent="a quiet valley that grows teeth", shape="a valley"),
        artifact_dir=tmp_path,
    )

    assert len(attempts) == 1
    assert attempts[0].attempt == 1
    assert attempts[0].problems == []
    assert attempts[0].designed is not None
    assert attempts[0].designed.columns == GROUND_FOOTED_PROFILE.geometry.columns
    assert attempts[0].payload_chars > 0
    assert len(backend.prompts) == 1
    assert backend.prompts[0].startswith("a quiet valley that grows teeth")
    assert "THIS MAP'S SHAPE: a valley." in backend.prompts[0]
    assert "rejected by the game's own validator" not in backend.prompts[0]
    assert backend.systems[0] is not None
    assert "THE VOCABULARY" in backend.systems[0]
    assert _attempt_artifacts(tmp_path) == ["attempt-01.json"]


async def test_design_chunks_feeds_the_validators_own_messages_into_the_next_prompt(
    tmp_path: Path,
) -> None:
    """The model is corrected by the same authority that judges it, quoted verbatim."""

    backend = _ScriptedComposerBackend([_OVERFLOWING_SENTENCE, _SOUND_SENTENCE])

    attempts = await design_chunks(
        _service(backend),
        GROUND_FOOTED_PROFILE,
        DesignBrief(intent="a long approach to a shrine"),
        artifact_dir=tmp_path,
    )

    assert len(attempts) == 2
    assert attempts[0].problems != []
    assert attempts[1].problems == []
    assert len(backend.prompts) == 2

    first_complaint = attempts[0].problems[0]
    assert first_complaint.startswith("the chunks total 150 columns of 128")
    assert "rejected by the game's own validator" in backend.prompts[1]
    assert first_complaint in backend.prompts[1]
    for problem in attempts[0].problems[:MAX_QUOTED_PROBLEMS]:
        assert f"  - {problem}" in backend.prompts[1]
    assert backend.prompts[1].endswith("Compose the map.")
    assert backend.seeds == [101, 102]


async def test_design_chunks_quotes_no_more_problems_than_the_feedback_budget_allows(
    tmp_path: Path,
) -> None:
    """Past the budget the feedback stops reading as a fix list, so the surplus is dropped."""

    backend = _ScriptedComposerBackend([_MANY_PROBLEM_SENTENCE, _SOUND_SENTENCE])

    attempts = await design_chunks(
        _service(backend),
        GROUND_FOOTED_PROFILE,
        DesignBrief(intent="a map composed of words this game does not have"),
        artifact_dir=tmp_path,
    )

    problems = attempts[0].problems
    assert len(problems) > MAX_QUOTED_PROBLEMS
    for problem in problems[:MAX_QUOTED_PROBLEMS]:
        assert f"  - {problem}" in backend.prompts[1]
    surplus = problems[MAX_QUOTED_PROBLEMS]
    assert surplus == "chunk #7 (spiral_7) is not a word in this game's grammar"
    assert surplus not in backend.prompts[1]
    assert backend.prompts[1].count("  - ") == MAX_QUOTED_PROBLEMS


async def test_design_chunks_hands_back_a_column_complaint_re_anchored_on_its_own_chunk(
    tmp_path: Path,
) -> None:
    """The translation is not a side exhibit: it is what the model is actually shown.

    ``translate`` is exercised in isolation elsewhere. Here the whole path runs -- expand, check,
    translate, quote -- so the chunk suffix has to survive into the retry prompt verbatim, in the
    vocabulary the model itself wrote rather than the validator's grid coordinates.
    """

    backend = _ScriptedComposerBackend([_TOO_DEEP_SENTENCE, _SOUND_SENTENCE])

    attempts = await design_chunks(
        _service(backend),
        GROUND_FOOTED_PROFILE,
        DesignBrief(intent="a shrine approach that starts too deep"),
        artifact_dir=tmp_path,
    )

    assert attempts[0].problems[0] == (
        "column 0 floor is 10 tiles, outside the profile's 1..8 [inside chunk #1: run(len=10)]"
    )
    assert "[inside chunk #1: run(len=10)]" in backend.prompts[1]
    assert f"  - {attempts[0].problems[0]}" in backend.prompts[1]
    assert attempts[1].problems == []


async def test_design_chunks_gives_up_after_max_attempts_and_returns_every_attempt(
    tmp_path: Path,
) -> None:
    backend = _ScriptedComposerBackend([_OVERFLOWING_SENTENCE])

    attempts = await design_chunks(
        _service(backend),
        GROUND_FOOTED_PROFILE,
        DesignBrief(intent="a map this composer will never get right"),
        seed=7,
        max_attempts=3,
        artifact_dir=tmp_path,
    )

    assert [attempt.attempt for attempt in attempts] == [1, 2, 3]
    assert all(attempt.problems for attempt in attempts)
    assert all(attempt.designed is not None for attempt in attempts)
    assert len(backend.prompts) == 3
    assert backend.seeds == [701, 702, 703]
    assert _attempt_artifacts(tmp_path) == [
        "attempt-01.json",
        "attempt-02.json",
        "attempt-03.json",
    ]
