"""What the character-3d workflow states about itself, read from its workflow file."""

from __future__ import annotations

from stage_gen.workflows._gnode import gnode_workflow

from .example import import_example, read_library

CODE = gnode_workflow(
    "stage_gen.workflows.character_3d",
    sample_inputs="inputs/sample/inputs.yaml",
    import_example=import_example,
    read_library=read_library,
)
