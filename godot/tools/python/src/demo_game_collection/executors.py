"""Collection regression adapters for inputs holding both sideview members.

Named games default to their own input readers. This developer-tool composition
retains mixed-member input support by explicitly injecting the collection reader.
"""

from pathlib import Path

from bellweather_pipeline.package_executor import PreparedPackageExecutor as BellweatherExecutor
from demo_game_collection.game_package import (
    GamePackageValidationError,
    resolve_game_package,
    resolve_prepared_package,
)
from iron_petal_unit_pipeline.runner_executor import SideviewRunnerExecutor as IronPetalExecutor
from iron_petal_unit_pipeline.runner_request import ResolvedRunnerPackage
from iron_petal_unit_pipeline.validation import ResolvedRunnerMember
from stage_gen.config import StageGenConfig


def resolve_runner_package(input_path: Path) -> ResolvedRunnerPackage:
    package = resolve_prepared_package(input_path)
    runner = package.member("runner", ResolvedRunnerMember)
    if runner is None:
        raise GamePackageValidationError(
            "missing_genre_member", "prepared package declares no runner genre member"
        )
    return ResolvedRunnerPackage(package=package, runner=runner)


class PreparedPackageExecutor(BellweatherExecutor):
    """Run the maintained platformer builder against collection input formats."""

    def __init__(self, config: StageGenConfig) -> None:
        super().__init__(config, input_resolver=resolve_game_package)


class SideviewRunnerExecutor(IronPetalExecutor):
    """Run the maintained runner builder against collection input formats."""

    def __init__(self, config: StageGenConfig) -> None:
        super().__init__(config, input_resolver=resolve_runner_package)
