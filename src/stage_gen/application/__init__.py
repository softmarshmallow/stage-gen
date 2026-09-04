"""The application layer: what a command does, reachable without argparse.

The CLI parses; this package decides. A run report has one shape across every recipe
and checkpoint, a usage error is its own class so it can exit 2 rather than be
flattened with an internal failure, and the genre and path resolutions a command
makes are functions a test or a script calls directly.
"""

from stage_gen.application.runs import (
    UsageError,
    resolve_cache_dir,
    resolve_genre,
    resolve_output_path,
    run_report,
    write_report,
)

__all__ = [
    "UsageError",
    "resolve_cache_dir",
    "resolve_genre",
    "resolve_output_path",
    "run_report",
    "write_report",
]
