"""Compatibility import for pipeline-owned node cache helpers."""

import sys

from stage_gen.pipeline import node_cache as _implementation
from stage_gen.pipeline.node_cache import _NODE_CACHE_RECORD_FIELDS as _NODE_CACHE_RECORD_FIELDS
from stage_gen.pipeline.node_cache import NODE_CACHE_SCHEMA_VERSION as NODE_CACHE_SCHEMA_VERSION
from stage_gen.pipeline.node_cache import NodeArtifactCache as NodeArtifactCache
from stage_gen.pipeline.node_cache import (
    _ArtifactRestoreRecoveryError as _ArtifactRestoreRecoveryError,
)
from stage_gen.pipeline.node_cache import _CacheBundleRecoveryError as _CacheBundleRecoveryError
from stage_gen.pipeline.node_cache import _replace_cache_path as _replace_cache_path
from stage_gen.pipeline.node_cache import _replace_path as _replace_path
from stage_gen.pipeline.node_cache import _RestoreState as _RestoreState

sys.modules[__name__] = _implementation
