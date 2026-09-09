#!/usr/bin/env python3
"""Run the Godot suite one file per process, with a timeout on each.

    python3 tools/run_suite.py [--run <run dir>] [--timeout 180] [--jobs 4]

The suite used to be one process over forty-two files, and two failures were
invisible to it. A file that dies hard — a segfault, an engine abort — takes the
whole run down and every file after it goes unreported, so the suite says
nothing rather than saying which file. And a file that *hangs* is
indistinguishable from a slow one: `--quit-after` kills the process at some
iteration count and the output ends mid-sentence, naming nothing.

A process per file fixes both, because the supervisor is outside the thing that
died. A crash costs that file's result and no one else's; a hang is killed at its
own timeout and named. That is what decision 0061's plan means by the suite
entering the locked gate: a gate that cannot tell a hang from a slow test is not
one.

`--run` names the world the suite reads. Without one it reads the promoted run
under `out/`, which a fresh clone does not have; `tools/make_fixture_run.py`
writes the small authored package the locked gate points it at instead. An
assertion pinned to a producer's own counts is read only on the promoted run,
and every guarded block the run could not answer is listed at the end — a tier
that is invisible under the supervisor is a tier that empties unnoticed.

`GODOT` overrides the engine binary; the default is the macOS app bundle. A
missing engine is a failure and says so — never a silent skip, because a gate
that quietly does nothing is worse than one that is red.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import re
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
TESTS = PROJECT / "tests"

#: The engine's own hang guard, in main-loop iterations. Kept well above what any
#: file needs: the supervisor's wall-clock timeout is the one that decides.
QUIT_AFTER = 30000

#: How long one file may take before it is called hung. The slowest file in the
#: suite today is `test_ui_layers.gd` at about 0.6 s of checks on top of roughly
#: two seconds of engine start, so this is two orders of magnitude of headroom
#: and still finite.
DEFAULT_TIMEOUT = 180.0

SUMMARY = re.compile(r"^(\d+) checks in (\d+) files passed", re.MULTILINE)
FAILURES = re.compile(r"^(\d+) of (\d+) checks failed", re.MULTILINE)
#: The runner's own header for the assertions it did not read, and the lines
#: under it. A process per file means each child prints its own list, and only
#: the supervisor's output is read, so it gathers them.
PINNED = re.compile(r"^\d+ pinned to a real run, not read here:\n((?:  .*\n)*)", re.MULTILINE)


def engine() -> str:
    return os.environ.get("GODOT", "/Applications/Godot.app/Contents/MacOS/Godot")


def test_files() -> list[str]:
    return sorted(path.name for path in TESTS.glob("test_*.gd"))


def run_one(
    name: str, run_dir: str | None, timeout: float
) -> tuple[str, bool, str, float, list[str]]:
    """One file in its own process. Returns (name, passed, note, seconds, pinned)."""
    command = [
        engine(),
        "--headless",
        "--path",
        str(PROJECT),
        "-s",
        "res://tests/run_tests.gd",
        "--quit-after",
        str(QUIT_AFTER),
        "--",
        "--only",
        name,
    ]
    if run_dir:
        command += ["--run", run_dir]
    started = time.monotonic()
    try:
        done = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return (name, False, f"hung: killed after {timeout:.0f}s", time.monotonic() - started, [])
    except FileNotFoundError:
        return (name, False, f"no engine at {engine()}", time.monotonic() - started, [])
    seconds = time.monotonic() - started
    output = done.stdout + done.stderr
    pinned = [
        line.strip() for block in PINNED.findall(output) for line in block.splitlines() if line
    ]
    if done.returncode != 0:
        failed = FAILURES.search(output)
        if failed:
            lines = [
                line.strip()
                for line in output.splitlines()
                if line.startswith("  ") and ": " in line
            ]
            first = lines[0] if lines else "see the output"
            return (name, False, f"{failed.group(1)} checks failed — {first}", seconds, pinned)
        # No summary line at all: the process did not reach the end of the suite.
        # That is the crash case, and naming the file is the whole point.
        return (name, False, f"died with exit {done.returncode}", seconds, pinned)
    passed = SUMMARY.search(output)
    return (name, True, f"{passed.group(1)} checks" if passed else "ok", seconds, pinned)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", dest="run_dir", default=None)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--only", default=None, help="one file, for debugging the supervisor")
    args = parser.parse_args(argv[1:])

    binary = Path(engine())
    if not binary.exists() or not os.access(binary, os.X_OK):
        print(f"run_suite: no Godot at {binary} (set GODOT=<path>)")
        return 1

    names = [args.only] if args.only else test_files()
    if not names:
        print(f"run_suite: no test files under {TESTS}")
        return 1

    started = time.monotonic()
    results: list[tuple[str, bool, str, float]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {pool.submit(run_one, name, args.run_dir, args.timeout): name for name in names}
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda entry: entry[0])

    checks = 0
    failures = []
    pinned: list[str] = []
    for name, passed, note, seconds, skipped in results:
        mark = "ok    " if passed else "FAILED"
        print(f"   {mark} {name:34s} {note}  ({seconds:.1f}s)")
        if passed and note.endswith("checks"):
            checks += int(note.split()[0])
        if not passed:
            failures.append(name)
        pinned.extend(skipped)
    seconds = time.monotonic() - started
    if pinned:
        print(f"   {len(pinned)} pinned to a real run, not read here:")
        for entry in pinned:
            print(f"     {entry}")
    if failures:
        print(
            f"run_suite: {len(failures)} of {len(results)} files failed "
            f"({', '.join(failures)}) in {seconds:.1f}s"
        )
        return 1
    print(f"   {checks} checks in {len(results)} files passed ({seconds:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
