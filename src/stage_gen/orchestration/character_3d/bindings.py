"""Application composition bindings: one reviewed table for every provider operation."""

from gnode import BindingTable
from stage_gen.orchestration.character_3d.policy_defaults import default_bindings


def application_bindings() -> BindingTable:
    return default_bindings()
