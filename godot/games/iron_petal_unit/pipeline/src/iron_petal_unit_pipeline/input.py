"""Iron Petal Unit owns selection and admission of its input package."""

from pathlib import Path

from demo_game_tools.input_formats.game_contract import RunnerGenreMember
from demo_game_tools.input_formats.prepared_package import GenreResolver, ResolvedPreparedPackage
from demo_game_tools.input_formats.prepared_package import resolve_prepared_package as read_package
from iron_petal_unit_pipeline.validation import resolve_runner_member


def resolve_prepared_package(input_path: str | Path) -> ResolvedPreparedPackage:
    return read_package(
        input_path, resolvers=(GenreResolver("runner", RunnerGenreMember, resolve_runner_member),)
    )
