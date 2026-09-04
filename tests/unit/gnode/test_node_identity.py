"""A node type's cache identity is declared, so a rename is not a re-bill."""

from __future__ import annotations

import pytest

from gnode import LOCAL_OPERATION, NodeType, ViewArchetype


def _local(type_id: str, *, identity: str | None = None) -> NodeType:
    return NodeType(
        type_id=type_id,
        title="probe",
        archetype=ViewArchetype.TRANSFORM,
        operation=LOCAL_OPERATION,
        contract_version="probe-v1",
        identity=identity,
    )


def test_identity_defaults_to_the_type_id() -> None:
    node_type = _local("2d/probe/thing.make")
    assert node_type.cache_identity == "2d/probe/thing.make"


def test_a_renamed_type_keeps_its_identity_when_it_says_so() -> None:
    before = _local("2d/probe/thing.make")
    after = _local("2d/better/home.make", identity="2d/probe/thing.make")
    assert after.type_id != before.type_id
    assert after.cache_identity == before.cache_identity


def test_an_identity_must_be_a_well_formed_type_id() -> None:
    with pytest.raises(ValueError, match="cache identity"):
        _local("2d/probe/thing.make", identity="not a type id")
