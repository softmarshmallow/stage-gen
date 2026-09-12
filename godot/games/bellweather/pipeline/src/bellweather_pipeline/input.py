"""Bellweather owns selection and admission of its input package."""

from pathlib import Path

from bellweather_pipeline.validation import ResolvedGamePackage, resolve_platformer_member
from demo_game_tools.input_formats.game_contract import PlatformerGenreMember
from demo_game_tools.input_formats.prepared_package import GenreResolver, ResolvedPreparedPackage
from demo_game_tools.input_formats.prepared_package import resolve_prepared_package as read_package


def resolve_prepared_package(input_path: str | Path) -> ResolvedPreparedPackage:
    return read_package(
        input_path,
        resolvers=(GenreResolver("platformer", PlatformerGenreMember, resolve_platformer_member),),
    )


def resolve_game_package(input_path: str | Path) -> ResolvedGamePackage:
    return ResolvedGamePackage.of(resolve_prepared_package(input_path))
