"""``stage-gen run character-3d``: the frozen character launcher, with its own argv.

The launcher at ``stage_gen.orchestration.character_3d.launch`` parses ``sys.argv`` itself,
and its path and bytes are bound into every character run's lineage, so it is not wrapped:
everything after ``run character-3d`` reaches it verbatim, including ``--help``. A character
run is prepared inside that launcher, so ``plan`` refuses and says what to run instead.
"""

from __future__ import annotations

import argparse
import sys
from typing import TextIO

PROGRAM = "stage-gen run character-3d"
#: ``stage-gen`` gives this workflow's run parser no options of its own, not even ``--help``,
#: and hands every argument after ``run character-3d`` to the handler as ``forwarded``.
FORWARDS_RUN_ARGUMENTS = True


def register_plan(parser: argparse.ArgumentParser) -> None:
    parser.set_defaults(handler=_plan)


def register_run(parser: argparse.ArgumentParser) -> None:
    parser.set_defaults(handler=_run)


def _plan(args: argparse.Namespace, stdout: TextIO) -> int:
    from stage_gen.workflows.character_3d.workflow import CODE

    del args, stdout
    raise ValueError(f"character-3d cannot be planned: {CODE.plan_refusal}")


def _run(args: argparse.Namespace, stdout: TextIO) -> int:
    from stage_gen.orchestration.character_3d import launch

    del stdout
    previous = sys.argv
    sys.argv = [PROGRAM, *args.forwarded]
    try:
        launch.main()
    except SystemExit as exit_:
        if exit_.code is None or isinstance(exit_.code, int):
            return exit_.code or 0
        raise
    finally:
        sys.argv = previous
    return 0
