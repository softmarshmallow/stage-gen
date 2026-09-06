#!/usr/bin/env python3
"""Diff two parity digests and name the first step and field that parted company.

    python3 tools/parity_diff.py <godot jsonl> <web jsonl> [--limit 5] [--ignore a,b]

Both files are the JSONL `tools/parity.gd` and `tools/parity_web.js.txt` write for
the same input script: one world digest every N steps, then a summary line.
This walks them in lockstep and reports the divergences in step order, most
useful first, because the critique's D2 rule is that the first divergent field
names the system.

Tolerances, since the two runtimes are two floating-point engines:

  * integers, strings and booleans     exact
  * `rng_next_u32`                     exact: it is an integer, the generator's
                                       own 32-bit word, and the one field that
                                       says the two PRNGs stand on the same
                                       state rather than merely near it
  * `rng_next`                         1e-9 — the same value as a float, held
                                       far tighter than a position but not
                                       exactly, because Godot's JSON writer
                                       prints a double shorter than JavaScript's
                                       and the last bit does not survive the
                                       round trip
  * every other number                 1e-3 absolute

Exit code 0 when the two agree, 1 when they do not, 2 when a file cannot be
read. No dependencies.
"""

from __future__ import annotations

import argparse
import json
import sys

# Absolute tolerance by leaf field name. Anything not named here that is a
# number on both sides gets DEFAULT_TOL, unless both sides wrote an integer, in
# which case it must match exactly: a count is a count.
TOLERANCES = {
    "rng_next": 1e-9,
    "x": 1e-3,
    "z": 1e-3,
    "vx": 1e-3,
    "vz": 1e-3,
    "health": 1e-3,
    "hunger": 1e-3,
    "warmth": 1e-3,
    "time": 1e-3,
    "day_phase": 1e-3,
    "night": 1e-3,
    "rain": 1e-3,
    "snow": 1e-3,
    "torch": 1e-3,
    "warm": 1e-3,
    "uses": 1e-3,
}
DEFAULT_TOL = 1e-3


def load(path: str) -> list:
    """One JSON object per non-blank line."""
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as error:
        print(f"parity-diff: cannot read {path}: {error}", file=sys.stderr)
        raise SystemExit(2) from None
    lines = []
    for number, raw in enumerate(text.splitlines(), start=1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            lines.append(json.loads(raw))
        except json.JSONDecodeError as error:
            print(f"parity-diff: {path}:{number} is not JSON: {error}", file=sys.stderr)
            raise SystemExit(2) from None
    if not lines:
        print(f"parity-diff: {path} holds no digest lines", file=sys.stderr)
        raise SystemExit(2)
    return lines


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def tolerance(field: str, left, right) -> float:
    if isinstance(left, int) and isinstance(right, int) and not isinstance(left, bool):
        return 0.0
    return TOLERANCES.get(field, DEFAULT_TOL)


def compare(left, right, path: str, field: str, ignore: set, out: list) -> None:
    """Walk two parsed values together, appending `(path, left, right)` per gap."""
    if field in ignore or path in ignore:
        return
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            here = f"{path}.{key}" if path else key
            if key not in left:
                if key not in ignore and here not in ignore:
                    out.append((here, "<missing>", right[key]))
                continue
            if key not in right:
                if key not in ignore and here not in ignore:
                    out.append((here, left[key], "<missing>"))
                continue
            compare(left[key], right[key], here, key, ignore, out)
        return
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            out.append((f"{path}.length", len(left), len(right)))
        for index in range(min(len(left), len(right))):
            compare(left[index], right[index], f"{path}[{index}]", field, ignore, out)
        return
    if is_number(left) and is_number(right):
        tol = tolerance(field, left, right)
        if abs(float(left) - float(right)) > tol:
            out.append((path, left, right))
        return
    if left != right:
        out.append((path, left, right))


def label(line: dict, index: int) -> str:
    if line.get("summary"):
        return "summary"
    step = line.get("step")
    return f"step {step}" if step is not None else f"line {index + 1}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diff two parity digests (the host's and the web viewer's).",
    )
    parser.add_argument("godot", help="the JSONL tools/parity.gd wrote")
    parser.add_argument("web", help="the JSONL tools/parity_web.js.txt returned")
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="how many divergent digests to report (default 5); 0 for every one",
    )
    parser.add_argument(
        "--fields",
        type=int,
        default=8,
        help="how many divergent fields to print per digest (default 8)",
    )
    parser.add_argument(
        "--ignore",
        default="",
        help="comma-separated field names or dotted paths to skip",
    )
    args = parser.parse_args()

    ignore = {token.strip() for token in args.ignore.split(",") if token.strip()}
    left_lines = load(args.godot)
    right_lines = load(args.web)

    print(f"godot {args.godot}: {len(left_lines)} lines")
    print(f"web   {args.web}: {len(right_lines)} lines")
    if ignore:
        print(f"ignoring: {', '.join(sorted(ignore))}")

    failed = False
    if len(left_lines) != len(right_lines):
        print(
            f"FAIL  line counts differ ({len(left_lines)} vs {len(right_lines)}): "
            "the two sides did not run the same script"
        )
        failed = True

    reported = 0
    for index in range(min(len(left_lines), len(right_lines))):
        left = left_lines[index]
        right = right_lines[index]
        name = label(left, index)
        other = label(right, index)
        if name != other:
            print(f"FAIL  {name} on the host is {other} on the web: the lines are not aligned")
            failed = True
            break
        gaps: list = []
        compare(left, right, "", "", ignore, gaps)
        if not gaps:
            continue
        failed = True
        if args.limit and reported >= args.limit:
            continue
        reported += 1
        print(f"\nFAIL  {name}: {len(gaps)} field(s) differ")
        for path, a, b in gaps[: args.fields]:
            print(f"        {path or '<root>'}: godot {a!r} | web {b!r}")
        if len(gaps) > args.fields:
            print(f"        … and {len(gaps) - args.fields} more")

    if not failed:
        print(f"\nPASS  {len(left_lines)} lines agree")
        return 0
    print(
        "\nThe first divergent step and field name the system: bisect from there "
        "(maps/viewer-sim.md maps a field to the system that writes it)."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
