"""What the movie-sprite workflow states about itself, read from its workflow file."""

from __future__ import annotations

from stage_gen.workflows._gnode import gnode_workflow

from .example import import_example

CODE = gnode_workflow(
    "stage_gen.workflows.movie_sprite",
    make_inputs="inputs/supplied_clip/make_inputs.py",
    import_example=import_example,
)
