"""Compatibility import for pipeline-owned cache report helpers."""

import sys

from stage_gen.pipeline import cache_report as _implementation
from stage_gen.pipeline.cache_report import _lineage_matches as _lineage_matches
from stage_gen.pipeline.cache_report import _record as _record
from stage_gen.pipeline.cache_report import cache_report as cache_report

sys.modules[__name__] = _implementation
