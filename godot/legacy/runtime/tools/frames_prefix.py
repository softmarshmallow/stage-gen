#!/usr/bin/env python3
"""How many frames two hash files agree on, from the first, and whether that is enough.

    python3 tools/frames_prefix.py <host frames> <web frames> --at-least <n>

The whole-file `diff` every other genre's parity gate runs is the right check
once a port is finished. While one is being derived it is the wrong check: it
answers "no" for six hundred frames on the day the first fifty-nine are right,
and a gate that says nothing until the last day protects nothing on any of the
others.

So this asks the question a derivation can actually answer — how far does the
run agree, counting from the first frame — and fails when the answer is smaller
than the pin. A unit that ports another system raises the pin; a change that
breaks a frame already earned turns the gate red the same day it happens.

Counting from the first frame is what makes the number mean something. A count
of matching frames anywhere would let a port that diverges at frame 2 and
re-converges at 400 report a large number, and re-convergence after a divergence
is coincidence rather than correctness.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def rows(path: Path) -> list[tuple[str, str]]:
    made: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2:
            made.append((parts[0], parts[1]))
    return made


def prefix(host: list[tuple[str, str]], web: list[tuple[str, str]]) -> int:
    """Frames the two agree on, counting from the first.

    Walked by index rather than zipped, for two reasons that are the same
    reason. `zip(strict=)` needs Python 3.10 and `validate.sh` runs the system
    `python3`, which is 3.9 on the machine this is developed on; and a plain
    `zip` would silently stop at the shorter file, which is exactly the case
    this tool exists to notice — a host that wrote fewer frames than the
    reference has not agreed with the tail it never reached.
    """
    count = 0
    while count < len(host) and count < len(web):
        if host[count] != web[count]:
            break
        count += 1
    return count


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", type=Path, help="the host's per-frame hashes")
    parser.add_argument("web", type=Path, help="the browser's per-frame hashes")
    parser.add_argument("--at-least", type=int, required=True, help="the pin this must reach")
    args = parser.parse_args(argv)

    host, web = rows(args.host), rows(args.web)
    if not host or not web:
        print(f"   FAIL: {args.host} or {args.web} carries no frame hashes")
        return 2
    matched = prefix(host, web)
    total = len(web)
    if matched < args.at_least:
        first = matched + 1
        print(f"   FAIL: {matched} of {total} frames identical from the first, and the pin is")
        print(f"         {args.at_least}. Frame {first} is where they part company.")
        return 1
    if matched > args.at_least:
        print(f"   {matched} of {total} frames identical from the first, past the pin of")
        print(f"   {args.at_least} — raise the pin here and in tests/test_platformer.gd.")
        return 0
    print(f"   {matched} of {total} frames identical from the first, which is the pin")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
