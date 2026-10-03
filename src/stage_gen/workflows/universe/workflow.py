"""What the universe workflow states about itself, read from its workflow file."""

from __future__ import annotations

from stage_gen.workflows._gnode import gnode_workflow

CODE = gnode_workflow(
    "stage_gen.workflows.universe",
    sample_inputs="inputs/lantern_ferry/inputs.yaml",
    no_importer="no example is pinned yet; one would be imported from a gnode run",
)
