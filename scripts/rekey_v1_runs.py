#!/usr/bin/env python3
"""Carry a v1 run's paid results into a ported workflow's call cache; refuse and price the rest.

The ported workflow runs offline in this project, with each paid call answered only by the
old provider result made from exactly the same request (see stage_gen.orchestration.rekey).
It prints every answer, every refusal with what a live run would bill, and every old result
nothing asked for. Exits 1 when anything was refused or left unpaired. Deleted in M9.

    uv run python scripts/rekey_v1_runs.py looping-parallax \\
        --from out/looping-parallax-sunpetal-v1 \\
        --inputs out/looping-parallax-inputs/sunpetal/inputs.yaml

A Python builder is planned from its project, with its arguments:

    cd godot/games/iron_petal_unit && uv run python ../../../scripts/rekey_v1_runs.py \\
        pipeline/workflow.py:build --arg package=inputs --from ../../../out/iron-petal-c1-parity
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gnode import plan_async
from stage_gen.orchestration.rekey import rekey


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("workflow", help="the ported workflow's id, or a builder file.py:name")
    parser.add_argument("--from", dest="runs", type=Path, action="append", required=True)
    parser.add_argument("--inputs", type=Path, action="append", default=[])
    parser.add_argument("--arg", action="append", default=[], help="a builder's NAME=VALUE")
    parser.add_argument("--run", type=Path, help="the run folder (default: a new one)")
    args = parser.parse_args(argv)

    arguments = dict(pair.split("=", 1) for pair in args.arg)
    plan = asyncio.run(plan_async(args.workflow, input_files=args.inputs, arguments=arguments))
    if not plan.ok:
        for problem in plan.problems:
            print(f"refused   {problem.where}: {problem.message}")
        return 1
    stamp = "rekey"
    run_dir = args.run or plan.planner.project.runs_dir / plan.planner.workflow.id / stamp
    outcome, report = asyncio.run(rekey(plan, args.runs, run_dir=run_dir))
    for answer in report.answers:
        where = f"{answer.capability} on {answer.route}, take {answer.take}"
        if answer.old is not None:
            print(f"answered  {where} <- {answer.old}")
        else:
            print(f"refused   {where}: a live run would bill up to ${answer.high_usd:.2f}")
    for old in report.unpaired:
        print(f"unpaired  {old.artifact}: no call of {args.workflow} asked for it")
    print(
        f"rekeyed   {len(report.answered)} calls now, {len(report.paired)} of "
        f"{len(report.old)} old results in {plan.planner.store.root}; "
        f"{len(report.refused)} refused (up to ${report.would_bill_usd:.2f}), "
        f"{len(report.unpaired)} old results unpaired; run {outcome.run_dir}"
    )
    return 1 if report.refused or report.unpaired else 0


if __name__ == "__main__":
    raise SystemExit(main())
