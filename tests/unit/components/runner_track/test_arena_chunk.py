"""The arena chunk role: the flat floor an encounter is fought over.

An endless run's seam rule says any chunk may follow any chunk, which is
exactly what forbids a multi-screen scripted sequence. An arena sidesteps that
rather than weakening it: it holds the seam profile in *every* column, not just
its two edges, so it may be entered, left, and repeated back to back, and one
authored chunk can hold an encounter of any length.

These tests hold what the role refuses. What an encounter then requires of it -
that one exists, that exactly one is named - is a cross-member obligation and
lives with the package validator.
"""

from __future__ import annotations

import pytest

from stage_gen.components._game_input import AuthoredContractLoadError
from stage_gen.components.runner_track import load_runner_track_bytes, seam_profile
from tests.unit._runner_fixture import chunk_toml, runner_track_toml

#: The fixture grid: eight rows, walk surface at row five.
FLAT_ARENA = ["0" * 24] * 5 + ["1" * 24] * 3
RUN_CHUNK = chunk_toml("meadow_flat", FLAT_ARENA)


def test_a_chunk_that_says_nothing_is_a_run_chunk() -> None:
    track = load_runner_track_bytes(runner_track_toml(RUN_CHUNK).encode())

    assert track.segments.chunks[0].role == "run"
    assert track.segments.arena_chunks() == []


def test_an_arena_is_admitted_and_reported() -> None:
    document = runner_track_toml(RUN_CHUNK + chunk_toml("boss_arena", FLAT_ARENA, role="arena"))

    track = load_runner_track_bytes(document.encode())

    assert [chunk.segment_id for chunk in track.segments.arena_chunks()] == ["boss_arena"]


def test_the_arena_profile_is_the_seam_profile_in_every_column() -> None:
    document = runner_track_toml(RUN_CHUNK + chunk_toml("boss_arena", FLAT_ARENA, role="arena"))

    arena = load_runner_track_bytes(document.encode()).segments.arena_chunks()[0]

    expected = seam_profile(8, 5)
    for column in range(len(arena.occupancy[0])):
        assert [row[column] for row in arena.occupancy] == expected


def test_an_arena_with_a_pit_is_refused() -> None:
    pitted = ["0" * 24] * 5 + ["1" * 10 + "0" * 4 + "1" * 10] + ["1" * 24] * 2
    document = runner_track_toml(RUN_CHUNK + chunk_toml("boss_arena", pitted, role="arena"))

    with pytest.raises(AuthoredContractLoadError, match="every column must be empty"):
        load_runner_track_bytes(document.encode())


def test_an_arena_with_a_step_is_refused() -> None:
    stepped = ["0" * 24] * 4 + ["0" * 10 + "1" * 4 + "0" * 10] + ["1" * 24] * 3
    document = runner_track_toml(RUN_CHUNK + chunk_toml("boss_arena", stepped, role="arena"))

    with pytest.raises(AuthoredContractLoadError, match="every column must be empty"):
        load_runner_track_bytes(document.encode())


def test_an_arena_carrying_a_hazard_is_refused() -> None:
    hazard = (
        '[[segments.chunks.hazards]]\nprop_id = "meadow_stump"\ncolumn = 8\nanchor = "surface"\n'
    )
    document = runner_track_toml(
        RUN_CHUNK + chunk_toml("boss_arena", FLAT_ARENA, role="arena", extra=hazard)
    )

    with pytest.raises(AuthoredContractLoadError, match="is an arena and carries no hazards"):
        load_runner_track_bytes(document.encode())


def test_an_arena_carrying_a_pickup_is_refused() -> None:
    pickup = '[[segments.chunks.pickups]]\nitem_id = "meadow_penny"\ncolumn = 8\nrow = 2\n'
    document = runner_track_toml(
        RUN_CHUNK + chunk_toml("boss_arena", FLAT_ARENA, role="arena", extra=pickup)
    )

    with pytest.raises(AuthoredContractLoadError, match="is an arena and carries no pickups"):
        load_runner_track_bytes(document.encode())


def test_an_unknown_role_is_refused() -> None:
    document = runner_track_toml(RUN_CHUNK + chunk_toml("boss_arena", FLAT_ARENA, role="lobby"))

    with pytest.raises(AuthoredContractLoadError):
        load_runner_track_bytes(document.encode())
