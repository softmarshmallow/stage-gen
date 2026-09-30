"""An index of a run folder for the record: every file and folder with its size, nothing else.

Keys are run-relative POSIX paths; folders carry their total bytes, every file below them, and
their immediate entries. Symlinks are skipped, so nothing outside the run is ever counted.
"""

from __future__ import annotations

from pathlib import Path


def index(root: Path) -> dict[str, dict]:
    root = root.resolve()
    tree: dict[str, dict] = {"": {"kind": "dir", "bytes": 0, "files": 0, "entries": 0}}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            continue
        rel = path.relative_to(root).as_posix()
        parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
        if path.is_dir():
            tree[rel] = {"kind": "dir", "bytes": 0, "files": 0, "entries": 0}
        elif path.is_file():
            tree[rel] = {"kind": "file", "bytes": path.stat().st_size}
            ancestor = rel
            while ancestor:
                ancestor = ancestor.rsplit("/", 1)[0] if "/" in ancestor else ""
                tree[ancestor]["bytes"] += tree[rel]["bytes"]
                tree[ancestor]["files"] += 1
        else:
            continue
        tree[parent]["entries"] += 1
    return tree
