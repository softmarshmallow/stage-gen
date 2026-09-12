"""Compatibility import for pipeline-owned route context helpers."""

import sys

from stage_gen.pipeline import route_context as _implementation
from stage_gen.pipeline.route_context import _CURRENT_RESOLVED_BINDING as _CURRENT_RESOLVED_BINDING
from stage_gen.pipeline.route_context import current_resolved_binding as current_resolved_binding
from stage_gen.pipeline.route_context import node_route_context as node_route_context

sys.modules[__name__] = _implementation
