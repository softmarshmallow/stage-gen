"""Collection regression adapters for inputs holding both sideview members.

Named games default to their own input readers. This developer-tool composition
retains mixed-member input support by explicitly injecting the collection reader.
"""

from bellweather_pipeline.package_executor import PreparedPackageExecutor as BellweatherExecutor
from demo_game_collection.game_package import resolve_game_package
from stage_gen.config import StageGenConfig


class PreparedPackageExecutor(BellweatherExecutor):
    """Run the maintained platformer builder against collection input formats."""

    def __init__(self, config: StageGenConfig) -> None:
        super().__init__(config, input_resolver=resolve_game_package)


#: The runner is built with gnode from its own project; this collection no longer runs it.
RUNNER_BUILD = (
    "the runner builds with gnode from its game folder: cd godot/games/iron_petal_unit && "
    "gnode plan pipeline/workflow.py:build --arg package=inputs"
)
