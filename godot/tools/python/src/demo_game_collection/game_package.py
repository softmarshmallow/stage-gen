"""Repository tooling that understands the maintained sideview input formats.

Game preparation uses its own resolver; this collection-level tool supports
historical packages containing both members for regression and inspection.
"""

from pathlib import Path

from bellweather_pipeline.validation import ResolvedGamePackage, resolve_platformer_member
from demo_game_tools.input_formats import prepared_package as reader
from demo_game_tools.input_formats.game_contract import PlatformerGenreMember, RunnerGenreMember
from demo_game_tools.input_formats.prepared_package import (
    GAME_PACKAGE_VALIDATION_KIND,
    GAME_PACKAGE_VALIDATION_SCHEMA_VERSION,
    RESOLVED_GAME_PACKAGE_KIND,
    GamePackageValidationError,
    GenreResolver,
    ResolvedPackageFile,
    ResolvedPreparedPackage,
    invalid_game_package_report,
)
from iron_petal_unit_pipeline.validation import resolve_runner_member

GENRE_RESOLVERS = (
    GenreResolver("platformer", PlatformerGenreMember, resolve_platformer_member),
    GenreResolver("runner", RunnerGenreMember, resolve_runner_member),
)


def resolve_prepared_package(input_path: str | Path) -> ResolvedPreparedPackage:
    return reader.resolve_prepared_package(input_path, resolvers=GENRE_RESOLVERS)


def resolve_game_package(input_path: str | Path) -> ResolvedGamePackage:
    return ResolvedGamePackage.of(resolve_prepared_package(input_path))


def validate_game_package(
    input_path: str | Path,
    *,
    repository_root: str | Path | None = None,
    require_tracked: bool = False,
    require_committed: bool = False,
) -> dict[str, object]:
    return reader.validate_game_package(
        input_path,
        resolvers=GENRE_RESOLVERS,
        repository_root=repository_root,
        require_tracked=require_tracked,
        require_committed=require_committed,
    )


__all__ = [
    "GAME_PACKAGE_VALIDATION_KIND",
    "GAME_PACKAGE_VALIDATION_SCHEMA_VERSION",
    "RESOLVED_GAME_PACKAGE_KIND",
    "GENRE_RESOLVERS",
    "GamePackageValidationError",
    "GenreResolver",
    "ResolvedGamePackage",
    "ResolvedPackageFile",
    "ResolvedPreparedPackage",
    "invalid_game_package_report",
    "resolve_game_package",
    "resolve_prepared_package",
    "validate_game_package",
]
