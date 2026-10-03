"""Which games build with gnode from their own folder, and the command that plans each."""

#: Genre -> the game folder that builds it and the package its plan reads.
GNODE_BUILDS: dict[str, tuple[str, str]] = {
    "runner": ("godot/games/iron_petal_unit", "inputs"),
    "platformer": ("godot/games/bellweather", "inputs/default"),
}


def gnode_build(genre: str) -> str | None:
    """The notice for a genre that builds with gnode, or None for one this collection runs."""

    found = GNODE_BUILDS.get(genre)
    if found is None:
        return None
    folder, package = found
    return (
        f"the {genre} builds with gnode from its game folder: cd {folder} && "
        f"gnode plan pipeline/workflow.py:build --arg package={package}"
    )
