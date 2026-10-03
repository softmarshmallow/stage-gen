"""What the looping-parallax workflow states about itself, read from its workflow file."""

from __future__ import annotations

from stage_gen.workflows._gnode import gnode_workflow

CODE = gnode_workflow(
    "stage_gen.workflows.looping_parallax",
    make_inputs="inputs/supplied_layers/make_inputs.py",
    no_importer=(
        "no example is pinned; examples are imported from gnode runs once the run importer "
        "lands with movie-sprite's port"
    ),
)
