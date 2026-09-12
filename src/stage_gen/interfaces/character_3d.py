"""Console entry point for the contained 3D character recipe.

The launcher itself is the composition root under orchestration; this module only
gives the console script the same home as the other ``stage-gen`` entry points.
"""

from stage_gen.orchestration.character_3d.launch import main

__all__ = ["main"]
