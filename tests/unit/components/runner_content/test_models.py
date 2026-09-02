from __future__ import annotations

import pytest

from stage_gen.components._game_input import AuthoredContractLoadError
from stage_gen.components.runner_content import (
    RUNNER_AVATAR_SCHEMA_VERSION,
    load_runner_avatar_bytes,
)

from ..._runner_fixture import RUNNER_AVATAR


def _combined_avatar() -> str:
    return RUNNER_AVATAR.replace(
        '''body_kind = "human"
age = 19
silhouette_mode = "single_character_v1"
proportion_basis = "character_head_v1"''',
        '''body_kind = "piloted_machine"
age = 11
silhouette_mode = "visible_rider_machine_v1"
proportion_basis = "visible_rider_head_v1"''',
    )


def test_exact_current_single_character_uses_character_head_proportion() -> None:
    catalog = load_runner_avatar_bytes(RUNNER_AVATAR.encode())

    assert RUNNER_AVATAR_SCHEMA_VERSION == catalog.schema_version == 3
    assert catalog.kind == "runner-avatar-v3"
    assert catalog.avatar.age == 19
    assert catalog.avatar.silhouette_mode == "single_character_v1"
    assert catalog.avatar.proportion_basis == "character_head_v1"


def test_visible_rider_machine_admits_the_riders_honest_child_age() -> None:
    avatar = load_runner_avatar_bytes(_combined_avatar().encode()).avatar

    assert avatar.age == 11
    assert avatar.body_kind == "piloted_machine"
    assert avatar.silhouette_mode == "visible_rider_machine_v1"
    assert avatar.proportion_basis == "visible_rider_head_v1"


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            'body_kind = "piloted_machine"',
            'body_kind = "human"',
            "requires body_kind piloted_machine",
        ),
        (
            'proportion_basis = "visible_rider_head_v1"',
            'proportion_basis = "character_head_v1"',
            "requires proportion_basis visible_rider_head_v1",
        ),
        (
            'silhouette_mode = "visible_rider_machine_v1"',
            'silhouette_mode = "single_character_v1"',
            "requires a non-piloted body_kind",
        ),
    ],
)
def test_silhouette_and_proportion_semantics_are_closed(old: str, new: str, message: str) -> None:
    with pytest.raises(AuthoredContractLoadError, match=message):
        load_runner_avatar_bytes(_combined_avatar().replace(old, new).encode())


def test_retired_runner_avatar_v2_is_not_inferred_or_migrated() -> None:
    retired = RUNNER_AVATAR.replace("schema_version = 3", "schema_version = 2").replace(
        'kind = "runner-avatar-v3"', 'kind = "runner-avatar-v2"'
    )

    with pytest.raises(AuthoredContractLoadError, match="runner avatar catalog"):
        load_runner_avatar_bytes(retired.encode())
