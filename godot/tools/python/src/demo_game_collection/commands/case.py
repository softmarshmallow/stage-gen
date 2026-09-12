"""Private collection adapter for case."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TextIO

from stage_gen.application import (
    UsageError as CliUsageError,
)
from the_grain_pipeline.case import ResolvedCase, read_case_catalog, resolve_case
from the_grain_pipeline.case_binding import BoundCase, bind_case
from the_grain_pipeline.case_bundle import publish_case


def _bundle_case(args: argparse.Namespace, *, stdout: TextIO) -> int:
    """Join the authored beats to the runs they were generated into, and publish."""

    published = publish_case(
        Path(args.input_path),
        args.case_id,
        run_tags=_beat_run_tags(args.beat_runs),
        output=Path(args.output_path),
        runs_root=Path(args.runs_dir) if args.runs_dir else None,
    )
    report = {
        "case_id": published.runtime.case_id,
        "kind": published.runtime.kind,
        "output": published.output.as_posix(),
        "document_sha256": published.document_sha256,
        "beats": {
            beat.beat_id: {
                "run_tag": beat.run_tag,
                **({} if beat.scenario_id is None else {"scenario_id": beat.scenario_id}),
            }
            for beat in published.runtime.beats
        },
    }
    stdout.write(f"{json.dumps(report, sort_keys=True, separators=(',', ':'))}\n")
    return 0


def _beat_run_tags(values: list[str]) -> dict[str, str]:
    """Parse `--beat-run beat_id=run_tag`, refusing a repeat rather than taking one."""

    tags: dict[str, str] = {}
    for value in values:
        beat_id, separator, run_tag = value.partition("=")
        if not separator or not beat_id or not run_tag:
            raise CliUsageError(f"--beat-run expects BEAT_ID=RUN_TAG; found `{value}`")
        if beat_id in tags:
            raise CliUsageError(f"--beat-run names beat `{beat_id}` twice")
        tags[beat_id] = run_tag
    return tags


def _dispatch_case(args: argparse.Namespace, *, stdout: TextIO) -> int:
    """Admission with no event loop, no config, and no provider - it never needs one."""

    if args.case_command == "bundle":
        return _bundle_case(args, stdout=stdout)
    root = Path(args.input_path)
    catalog = read_case_catalog(root)
    if args.case_id is not None and args.case_id not in catalog.case_ids:
        raise ValueError(f"case `{args.case_id}` is not in {root}/cases/index.toml")
    ids = catalog.case_ids if args.case_id is None else (args.case_id,)
    report = {
        "game_id": catalog.game_id,
        "cases": [
            _case_report(root, case_id, structure_only=bool(args.structure_only)) for case_id in ids
        ],
    }
    stdout.write(f"{json.dumps(report, sort_keys=True, separators=(',', ':'))}\n")
    return 0


def _case_report(root: Path, case_id: str, *, structure_only: bool) -> dict[str, object]:
    if structure_only:
        return _case_structure_report(resolve_case(root, case_id))
    return _bound_case_report(bind_case(root, case_id))


def _case_structure_report(resolved: ResolvedCase) -> dict[str, object]:
    admission = resolved.admission
    return {
        "admitted": admission.admitted,
        "case_id": admission.case_id,
        "beats": admission.beat_count,
        "bound": False,
        "case_sha256": resolved.case_sha256,
        "reachable_beats": list(admission.reachable_beats),
        "terminals": {witness.beat_id: list(witness.path) for witness in admission.witnesses},
        "facts": {
            entry.fact_id: {
                "establishment": entry.establishment,
                "exported_by": list(entry.exported_by),
                "read_by": list(entry.read_by),
            }
            for entry in admission.facts
        },
    }


def _bound_case_report(bound: BoundCase) -> dict[str, object]:
    report = _case_structure_report(bound.resolved)
    report["bound"] = True
    report["leaves"] = {
        beat.beat_id: {
            "kind": beat.kind,
            "member": beat.member,
            "outcomes": list(beat.outcomes),
            "exports": list(beat.exports),
            "imports": list(beat.imports),
            "reachable_states": beat.reachable_states,
        }
        for beat in bound.beats
    }
    return report
