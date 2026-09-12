"""Compatibility import for pipeline-owned node handler helpers."""

import sys

from stage_gen.pipeline import node_handler as _implementation
from stage_gen.pipeline.node_handler import CachedNodeHandler as CachedNodeHandler
from stage_gen.pipeline.node_handler import NodeMethod as NodeMethod
from stage_gen.pipeline.node_handler import RecipeNodeHandler as RecipeNodeHandler
from stage_gen.pipeline.node_handler import bind as bind

sys.modules[__name__] = _implementation
