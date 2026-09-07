#!/usr/bin/env python3
"""Diff two runner replay dumps and name the first field that parted company.

The frame hashes beside these files already answer *which* frame moved. This
answers *why*: it walks the two records in step and prints the path, the
browser's value and the host's, so a divergence is a field name rather than a
hash somebody has to bisect by hand.

Both sides serialise a float as a nine-decimal string, so the comparison here is
exact by construction. There is no tolerance to set, and that is deliberate: a
port that is close is a port that will drift.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[int, Any]:
    """One record per sampled frame, keyed by the frame it was taken on."""
    records: dict[int, Any] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        frame, _, rest = line.partition(" ")
        records[int(frame)] = json.loads(rest)
    return records


def walk(left: Any, right: Any, path: str = "") -> list[tuple[str, Any, Any]]:
    """Every leaf the two records disagree on, deepest name first."""
    if type(left) is not type(right):
        return [(path or "/", left, right)]
    if isinstance(left, dict):
        found: list[tuple[str, Any, Any]] = []
        for key in sorted(set(left) | set(right)):
            if key not in left:
                found.append((f"{path}/{key}", "<absent>", right[key]))
            elif key not in right:
                found.append((f"{path}/{key}", left[key], "<absent>"))
            else:
                found.extend(walk(left[key], right[key], f"{path}/{key}"))
        return found
    if isinstance(left, list):
        if len(left) != len(right):
            return [(f"{path} (length)", len(left), len(right))]
        found = []
        # The lengths matched above, so pairing by index is total.
        for index, entry in enumerate(left):
            found.extend(walk(entry, right[index], f"{path}[{index}]"))
        return found
    return [] if left == right else [(path or "/", left, right)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("web", type=Path, help="the browser's dump")
    parser.add_argument("host", type=Path, help="the host's dump")
    parser.add_argument("--limit", type=int, default=20, help="fields to print")
    args = parser.parse_args()

    web = load(args.web)
    host = load(args.host)
    if set(web) != set(host):
        missing = sorted(set(web) - set(host))
        extra = sorted(set(host) - set(web))
        print(f"   the two dumps sample different frames: missing {missing}, extra {extra}")
        return 1

    for frame in sorted(web):
        differences = walk(web[frame], host[frame])
        if not differences:
            continue
        print(f"   frame {frame}: {len(differences)} field(s) parted company")
        for where, left, right in differences[: args.limit]:
            print(f"     {where}\n       web:  {left!r}\n       host: {right!r}")
        return 1

    print(f"   {len(web)} of {len(web)} sampled digests identical, field for field")
    return 0


if __name__ == "__main__":
    sys.exit(main())
