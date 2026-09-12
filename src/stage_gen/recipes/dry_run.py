"""Compatibility import for pipeline-owned dry run helpers."""

import sys

from stage_gen.pipeline import dry_run as _implementation
from stage_gen.pipeline.dry_run import DRY_RUN_ARTIFACT_KIND as DRY_RUN_ARTIFACT_KIND
from stage_gen.pipeline.dry_run import DRY_RUN_CACHE_NAMESPACE as DRY_RUN_CACHE_NAMESPACE
from stage_gen.pipeline.dry_run import DRY_RUN_CACHE_RECORD_KIND as DRY_RUN_CACHE_RECORD_KIND
from stage_gen.pipeline.dry_run import PLACEHOLDER_PREFIX as PLACEHOLDER_PREFIX
from stage_gen.pipeline.dry_run import DryRunNodeHandler as DryRunNodeHandler
from stage_gen.pipeline.dry_run import _fake_bytes as _fake_bytes
from stage_gen.pipeline.dry_run import is_placeholder as is_placeholder

sys.modules[__name__] = _implementation
