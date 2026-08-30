"""Exact-current prepared sequence catalog and linear dialogue sequence contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    GAME_ID_PATTERN,
    KEBAB_ID_PATTERN,
    SNAKE_ID_PATTERN,
    canonical_contract_json,
    normalized_text,
    parse_toml_contract,
    portable_relative_path,
    unique_values,
)

GAME_SEQUENCE_CATALOG_SCHEMA_VERSION = 2
GAME_SEQUENCE_SCHEMA_VERSION = 1


class SequenceSource(PersistedContractModel):
    sequence_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    source: str

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        return portable_relative_path(value, "sequence source")

    @model_validator(mode="after")
    def validate_filename(self) -> SequenceSource:
        if self.source != f"sequences/{self.sequence_id}.toml":
            raise ValueError("sequence source must equal sequences/<sequence_id>.toml")
        return self


class GameSequenceCatalog(PersistedContractModel):
    schema_version: Literal[2]
    kind: Literal["game-sequence-catalog-v2"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    sequences: list[SequenceSource] = Field(min_length=1, max_length=256)

    @field_validator("sequences")
    @classmethod
    def validate_sequences(cls, value: list[SequenceSource]) -> list[SequenceSource]:
        unique_values((entry.sequence_id for entry in value), "sequence_id")
        unique_values((entry.source for entry in value), "sequence source")
        return value


class SequenceAgency(PersistedContractModel):
    policy: Literal["dialogue_only"]
    back_navigation: Literal["history_only"]
    world_simulation: Literal["continues"]


class SequencePresentation(PersistedContractModel):
    map_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    subject_view: Literal["front_three_quarter"]
    soundtrack_policy: Literal["duck"]


class SequenceInterruption(PersistedContractModel):
    policy: Literal["restart_node"]


class SequenceSkip(PersistedContractModel):
    policy: Literal["skip_seen_only"]
    target_outcome_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)


class DialogueNode(PersistedContractModel):
    node_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    node_kind: Literal["dialogue"]
    speaker_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    visible_subject_ids: list[str] = Field(min_length=1, max_length=16)
    focus_subject_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    listener_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    expression: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    text: str
    advance_policy: Literal["manual"]
    next_node_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)

    @field_validator("visible_subject_ids")
    @classmethod
    def validate_visible_subjects(cls, value: list[str]) -> list[str]:
        unique_values(value, "visible subject_id")
        return value

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return normalized_text(value, "dialogue text")

    @model_validator(mode="after")
    def validate_focus(self) -> DialogueNode:
        if self.focus_subject_id not in self.visible_subject_ids:
            raise ValueError("focus_subject_id must be visible")
        if self.speaker_id not in self.visible_subject_ids:
            raise ValueError("dialogue speaker must be visible")
        return self


class OutcomeNode(PersistedContractModel):
    node_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    node_kind: Literal["outcome"]
    outcome_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    effect_ids: list[str] = Field(default_factory=list, max_length=64)

    @field_validator("effect_ids")
    @classmethod
    def validate_effect_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "outcome effect_id")
        return value


SequenceNode = Annotated[DialogueNode | OutcomeNode, Field(discriminator="node_kind")]


class GameSequence(PersistedContractModel):
    schema_version: Literal[1]
    kind: Literal["game-sequence-v1"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    sequence_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    display_name: str
    sequence_kind: Literal["dialogue_sequence"]
    entry_node_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    agency: SequenceAgency
    presentation: SequencePresentation
    interruption: SequenceInterruption
    skip: SequenceSkip
    nodes: list[SequenceNode] = Field(min_length=2, max_length=64)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalized_text(value, "sequence display_name")

    @model_validator(mode="after")
    def validate_graph(self) -> GameSequence:
        unique_values((node.node_id for node in self.nodes), "sequence node_id")
        by_id = {node.node_id: node for node in self.nodes}
        if self.entry_node_id not in by_id:
            raise ValueError("sequence entry_node_id does not resolve")
        outcomes = {node.outcome_id: node for node in self.nodes if isinstance(node, OutcomeNode)}
        unique_values(outcomes, "sequence outcome_id")
        if self.skip.target_outcome_id not in outcomes:
            raise ValueError("skip target_outcome_id does not resolve")

        reachable: set[str] = set()
        active: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in active:
                raise ValueError("sequence contains an unconditional cycle")
            if node_id in reachable:
                return
            node = by_id.get(node_id)
            if node is None:
                raise ValueError(f"sequence references unknown node_id: {node_id}")
            active.add(node_id)
            reachable.add(node_id)
            if isinstance(node, DialogueNode):
                visit(node.next_node_id)
            active.remove(node_id)

        visit(self.entry_node_id)
        unreachable = sorted(set(by_id) - reachable)
        if unreachable:
            raise ValueError("sequence contains unreachable nodes: " + ", ".join(unreachable))
        return self


def load_game_sequence_catalog_bytes(data: bytes) -> GameSequenceCatalog:
    return parse_toml_contract(data, model=GameSequenceCatalog, label="game sequence catalog")


def load_game_sequence_bytes(data: bytes) -> GameSequence:
    return parse_toml_contract(data, model=GameSequence, label="game sequence")


def canonical_game_sequence_json(contract: PersistedContractModel) -> bytes:
    return canonical_contract_json(contract)


__all__ = [
    "GAME_SEQUENCE_CATALOG_SCHEMA_VERSION",
    "GAME_SEQUENCE_SCHEMA_VERSION",
    "DialogueNode",
    "GameSequence",
    "GameSequenceCatalog",
    "OutcomeNode",
    "SequenceAgency",
    "SequenceInterruption",
    "SequenceNode",
    "SequencePresentation",
    "SequenceSkip",
    "SequenceSource",
    "canonical_game_sequence_json",
    "load_game_sequence_bytes",
    "load_game_sequence_catalog_bytes",
]
