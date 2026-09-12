"""Private collection adapter for scenario."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import TextIO

from stage_gen.components.scenario import (
    ResolvedScenario,
    read_scenario_catalog,
    read_scenario_declarations,
    resolve_scenario,
    script_digest,
)


def _dispatch_scenario(args: argparse.Namespace, *, stdout: TextIO) -> int:
    """Admission with no event loop, no config, and no provider - it never needs one."""

    root = Path(args.input_path)
    catalog = read_scenario_catalog(root)
    ids = catalog.scenario_ids if args.scenario is None else (args.scenario,)
    if args.scenario is not None and args.scenario not in catalog.scenario_ids:
        raise ValueError(f"scenario `{args.scenario}` is not in {root}/scenarios/index.toml")
    if args.write_digest:
        return _write_scenario_digests(root, ids, stdout=stdout)
    report = {
        "game_id": catalog.game_id,
        "scenarios": [_scenario_report(resolve_scenario(root, entry)) for entry in ids],
    }
    stdout.write(f"{json.dumps(report, sort_keys=True, separators=(',', ':'))}\n")
    return 0


def _scenario_report(resolved: ResolvedScenario) -> dict[str, object]:
    return {
        "admitted": resolved.admission.admitted,
        "scenario_id": resolved.declarations.scenario_id,
        "blocks": len(resolved.program.blocks),
        "reachable_states": resolved.admission.reachable_states,
        "program_sha256": resolved.program_sha256,
        "endings": {
            witness.outcome_id: list(witness.path) for witness in resolved.admission.witnesses
        },
    }


def _write_scenario_digests(root: Path, scenario_ids: tuple[str, ...], *, stdout: TextIO) -> int:
    """Repair `script_sha256` after a prose edit.

    Every save of the script invalidates the hand-copied digest, so leaving the
    author to run `sha256sum` and paste the result is a needless way to make the
    contract feel hostile. The rewrite is a single line in place: nothing else in
    the document is touched, and the scenario is still proven afterwards.
    """

    written: dict[str, str] = {}
    for scenario_id in scenario_ids:
        declarations = read_scenario_declarations(root, scenario_id)
        actual = script_digest(root, declarations)
        document = root / f"scenarios/{scenario_id}.toml"
        text = document.read_text(encoding="utf-8")
        updated = re.sub(
            r'^script_sha256 = "[0-9a-f]{64}"$',
            f'script_sha256 = "{actual}"',
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if updated == text and declarations.script_sha256 != actual:
            raise ValueError(f"could not locate script_sha256 in {document}")
        document.write_text(updated, encoding="utf-8")
        resolve_scenario(root, scenario_id)
        written[scenario_id] = actual
    stdout.write(f"{json.dumps(written, sort_keys=True, separators=(',', ':'))}\n")
    return 0
