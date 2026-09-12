#!/usr/bin/env python3
"""Run maintained game and private support regressions, one file per process.

Each project is imported separately before its tests run, proving that no game's
class discovery depends on another project's editor cache. --run selects an
existing or authored Ember Hollow fixture; the other suites own their fixtures.
Use --project to run one owner, and --only to debug one test filename.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

GAMES = Path(__file__).resolve().parents[1] / "games"
PROJECTS = {
    "demo_support": GAMES / "_shared" / "runtime",
    "bellweather": GAMES / "bellweather",
    "iron_petal_unit": GAMES / "iron_petal_unit",
    "ember_hollow": GAMES / "ember_hollow",
    "the_grain": GAMES / "the_grain",
}
QUIT_AFTER = 30000
DEFAULT_TIMEOUT = 180.0
SUMMARY = re.compile(r"^(\d+) checks in (\d+) files passed", re.MULTILINE)
PINNED = re.compile(r"^\d+ pinned to a real run, not read here:\n((?:  .*\n)*)", re.MULTILINE)


def engine() -> str:
    return (
        os.environ.get("GODOT")
        or shutil.which("godot")
        or "/Applications/Godot.app/Contents/MacOS/Godot"
    )


def import_project(project: Path, timeout: float) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [engine(), "--headless", "--editor", "--path", str(project), "--quit"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    output = result.stdout + result.stderr
    return result.returncode == 0 and "SCRIPT ERROR:" not in output, output


def run_one(
    project: Path,
    name: str,
    run_dir: str | None,
    timeout: float,
) -> tuple[str, bool, int, str, float, list[str]]:
    command = [
        engine(),
        "--headless",
        "--path",
        str(project),
        "-s",
        "res://tests/run_tests.gd",
        "--quit-after",
        str(QUIT_AFTER),
        "--",
        "--only",
        name,
    ]
    if run_dir and project == PROJECTS["ember_hollow"]:
        command += ["--run", run_dir]
    started = time.monotonic()
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return name, False, 0, f"hung: killed after {timeout:.0f}s", time.monotonic() - started, []
    except OSError as exc:
        return name, False, 0, str(exc), time.monotonic() - started, []
    seconds = time.monotonic() - started
    output = done.stdout + done.stderr
    pinned = [
        line.strip() for block in PINNED.findall(output) for line in block.splitlines() if line
    ]
    summary = SUMMARY.search(output)
    # Exit zero alone is insufficient: an engine crash or a parse-aborted runner
    # must never masquerade as an empty successful test file.
    passed = done.returncode == 0 and summary is not None and int(summary.group(1)) > 0
    count = int(summary.group(1)) if summary else 0
    return name, passed, count, output, seconds, pinned


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", choices=tuple(PROJECTS), action="append")
    parser.add_argument("--run", dest="run_dir", default=None)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--only", help="one test filename")
    args = parser.parse_args(argv)
    if not shutil.which(engine()):
        print(f"run_native_suite: no Godot at {engine()} (set GODOT=<path>)")
        return 1
    started = time.monotonic()
    work: list[tuple[str, Path, str]] = []
    for owner in args.project or PROJECTS:
        project = PROJECTS[owner]
        imported, note = import_project(project, args.timeout)
        if not imported:
            print(f"run_native_suite: {owner} import failed\n{note}")
            return 1
        names = sorted(path.name for path in (project / "tests").glob("test_*.gd"))
        if args.only:
            names = [name for name in names if name == args.only]
        work.extend((owner, project, name) for name in names)
    if not work:
        print("run_native_suite: no matching test files")
        return 1
    checks = 0
    failures: list[str] = []
    pinned: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {
            pool.submit(run_one, project, name, args.run_dir, args.timeout): owner
            for owner, project, name in work
        }
        for future in concurrent.futures.as_completed(futures):
            owner = futures[future]
            name, passed, count, output, seconds, skipped = future.result()
            label = f"{owner}/{name}"
            print(
                f"   {'ok' if passed else 'FAILED':6s} {label:64s} {count} checks ({seconds:.1f}s)",
                flush=True,
            )
            checks += count
            pinned.extend(f"{owner}/{entry}" for entry in skipped)
            if not passed:
                failures.append(label)
                print(output, flush=True)
    if pinned:
        print(f"   {len(pinned)} pinned to a real run, not read here:")
        for entry in pinned:
            print(f"     {entry}")
    seconds = time.monotonic() - started
    if failures:
        print(f"run_native_suite: {len(failures)} of {len(work)} files failed in {seconds:.1f}s")
        return 1
    print(f"   {checks} checks in {len(work)} files passed ({seconds:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
