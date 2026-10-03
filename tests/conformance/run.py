#!/usr/bin/env python3
"""Run every conformance case through the gnode command line and compare its output.

Never imports gnode: the command is the interface under test.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent


def _gnode() -> list[str]:
    found = shutil.which("gnode")
    if found is None:
        raise SystemExit("conformance: no gnode command on PATH")
    return [found]


def _run(case: Path, work: Path) -> dict[str, str]:
    spec = yaml.safe_load((case / "case.yaml").read_text(encoding="utf-8"))
    project = work / "project"
    shutil.copytree(case / "in", project)
    env = {**os.environ, "NO_COLOR": "1"}
    outputs: dict[str, str] = {}
    for step in spec["steps"]:
        argv = [*_gnode(), *step["argv"]]
        completed = subprocess.run(
            argv, cwd=project, env=env, capture_output=True, text=True, check=False
        )
        expected_status = step.get("status", 0)
        if completed.returncode != expected_status:
            raise AssertionError(
                f"{case.name}: {' '.join(step['argv'])} exited {completed.returncode}, "
                f"not {expected_status}\n{completed.stdout}{completed.stderr}"
            )
        if "save" in step:
            text = completed.stdout
            if step.get("json"):
                text = json.dumps(_normal(json.loads(text)), indent=1, sort_keys=True) + "\n"
            outputs[step["save"]] = text
    return outputs


def _normal(value: object) -> object:
    """Drop what differs between machines and invocations: offsets and invocation ids."""

    if isinstance(value, dict):
        return {
            key: _normal(item)
            for key, item in value.items()
            if key not in {"offset_ms", "invocation_id", "duration_ms"}
        }
    if isinstance(value, list):
        return [_normal(item) for item in value]
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="rewrite expected/ outputs")
    parser.add_argument("cases", nargs="*", help="case names (default: all)")
    args = parser.parse_args(argv)
    cases = sorted(path.parent for path in ROOT.glob("*/case.yaml"))
    if args.cases:
        cases = [case for case in cases if case.name in args.cases]
    failures = 0
    for case in cases:
        with tempfile.TemporaryDirectory(prefix=f"gnode-conformance-{case.name}-") as work:
            try:
                outputs = _run(case, Path(work))
            except AssertionError as error:
                print(f"FAIL {case.name}: {error}")
                failures += 1
                continue
        expected = case / "expected"
        if args.write:
            expected.mkdir(exist_ok=True)
            for name, text in outputs.items():
                (expected / name).write_text(text, encoding="utf-8")
            print(f"wrote {case.name}")
            continue
        for name, text in outputs.items():
            path = expected / name
            want = path.read_text(encoding="utf-8") if path.is_file() else ""
            if want != text:
                diff = "".join(
                    difflib.unified_diff(
                        want.splitlines(True), text.splitlines(True), f"expected/{name}", "actual"
                    )
                )
                print(f"FAIL {case.name}: {name} differs\n{diff[:4000]}")
                failures += 1
                break
        else:
            print(f"PASS {case.name}")
    print(f"conformance: {len(cases) - failures} of {len(cases)} cases pass")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
