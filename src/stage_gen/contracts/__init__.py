"""Legacy recipe run-summary contract.

Persisted contract bases and provenance records live in the engine; import them
from ``gnode``.
"""

from .run_summary import (
    MAX_JSON_SAFE_INTEGER,
    RUN_SUMMARY_KIND,
    RUN_SUMMARY_SCHEMA_VERSION,
    RecipeRunStage,
    RecipeRunSummary,
    RecipeRunSummaryLoadError,
    load_recipe_run_summary,
    parse_recipe_run_summary,
    validate_run_artifact_ref,
)

__all__ = [
    "MAX_JSON_SAFE_INTEGER",
    "RUN_SUMMARY_KIND",
    "RUN_SUMMARY_SCHEMA_VERSION",
    "RecipeRunStage",
    "RecipeRunSummary",
    "RecipeRunSummaryLoadError",
    "load_recipe_run_summary",
    "parse_recipe_run_summary",
    "validate_run_artifact_ref",
]
