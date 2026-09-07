"""The game shell: the opening cinematic, the title screen and the loading screen.

One recipe-neutral component, consumed by every genre that has a host to show them in.
The composition of these screens is genre-neutral — a backdrop, a mark, a control stack,
a shot list — while their content is authored per package, which is the same split
``game_ui`` already makes and the reason this is a component rather than a recipe.

See ``docs/spec/game/shell.md``.
"""

from stage_gen.components.game_shell.layouts import (
    BACKDROP_DEPTHS,
    CUTOUT_ALPHA_POLICY,
    LOADING_SCREEN,
    LOADING_SCREEN_LAYOUT,
    OPAQUE_ALPHA_POLICY,
    OPENING_LAYOUT,
    OPENING_SHOT,
    SHELL_CANVAS,
    SHELL_LAYOUTS,
    SHOT_MOVES,
    SHOT_TRANSITIONS,
    TITLE_SCREEN,
    TITLE_SCREEN_LAYOUT,
    Rect,
    ShellLayout,
)
from stage_gen.components.game_shell.models import (
    FONT_SUFFIXES,
    GAME_SHELL_KIND,
    GAME_SHELL_SCHEMA_VERSION,
    REDISTRIBUTABLE_FONT_LICENSES,
    BackdropLayer,
    GameShell,
    LoadingBackdropBinding,
    LoadingScreen,
    Opening,
    OpeningShot,
    ShellPlate,
    ShellReference,
    ShellTypeface,
    TitleScreen,
    load_game_shell_bytes,
)

__all__ = [
    "BACKDROP_DEPTHS",
    "CUTOUT_ALPHA_POLICY",
    "FONT_SUFFIXES",
    "GAME_SHELL_KIND",
    "GAME_SHELL_SCHEMA_VERSION",
    "LOADING_SCREEN",
    "LOADING_SCREEN_LAYOUT",
    "OPAQUE_ALPHA_POLICY",
    "OPENING_LAYOUT",
    "OPENING_SHOT",
    "REDISTRIBUTABLE_FONT_LICENSES",
    "SHELL_CANVAS",
    "SHELL_LAYOUTS",
    "SHOT_MOVES",
    "SHOT_TRANSITIONS",
    "TITLE_SCREEN",
    "TITLE_SCREEN_LAYOUT",
    "BackdropLayer",
    "GameShell",
    "LoadingBackdropBinding",
    "LoadingScreen",
    "Opening",
    "OpeningShot",
    "Rect",
    "ShellLayout",
    "ShellPlate",
    "ShellReference",
    "ShellTypeface",
    "TitleScreen",
    "load_game_shell_bytes",
]
