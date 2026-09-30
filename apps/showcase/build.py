"""Build the showcase into out/showcase, or into the directory given with --out.

    uv run python apps/showcase/build.py [--out output-dir] [page ...]

Naming pages rebuilds only those, and leaves the index as it was.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from showcase.site import REPO, build

if __name__ == "__main__":
    args = sys.argv[1:]
    out = REPO / "out" / "showcase"
    if args[:1] == ["--out"]:
        out, args = Path(args[1]).resolve(), args[2:]
    build(out, frozenset(args))
