"""The Grain's case: prove it, bind its leaves, and publish it over the leaves' runs.

The rooms and the scene build with gnode from the game's folder
(``pipeline/workflow.py:room`` and ``:scene``); this checks the case they are played in and,
with ``--bundle``, publishes ``case.json`` naming the delivered folder each beat plays.
Nothing here is generated and no provider is reached.
"""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from the_grain_pipeline.case_binding import bind_case
from the_grain_pipeline.case_bundle import publish_case


def main(default_input: Path, argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prove and publish The Grain's case")
    parser.add_argument(
        "--input", type=Path, dest="input_path", help="override this game's local inputs"
    )
    parser.add_argument("--case", default="episode_one", dest="case_id")
    parser.add_argument(
        "--bundle", action="store_true", help="publish case.json over the beats' delivered runs"
    )
    parser.add_argument("--beat-run", action="append", default=[], metavar="BEAT_ID=RUN_TAG")
    parser.add_argument("--runs-dir", type=Path)
    parser.add_argument("--output", type=Path, help="where case.json is published")
    args = parser.parse_args(argv)
    input_path = args.input_path or default_input
    bound = bind_case(input_path, args.case_id)
    if not args.bundle:
        print(
            json.dumps(
                {
                    "case_id": bound.resolved.case.case_id,
                    "valid": True,
                    "beats": [beat.beat_id for beat in bound.beats],
                },
                indent=2,
            )
        )
        return 0
    if args.output is None:
        parser.error("--bundle requires --output")
    beat_runs: dict[str, str] = {}
    for value in args.beat_run:
        beat_id, separator, run_tag = value.partition("=")
        if not separator or not beat_id or not run_tag or beat_id in beat_runs:
            parser.error("--beat-run requires a unique BEAT_ID=RUN_TAG")
        beat_runs[beat_id] = run_tag
    report = publish_case(
        input_path,
        args.case_id,
        run_tags=beat_runs,
        output=args.output,
        runs_root=args.runs_dir or args.output.parent,
    )
    print(json.dumps(report.runtime.model_dump(mode="json"), indent=2))
    return 0
