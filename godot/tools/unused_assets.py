"""List the assets of a Godot project that nothing reaches.

A file is in use when a scene, script, resource or the project file names it,
directly or through a catalog: a JSON file that a script reads binds the media
it names. Anything else the project tracks, media or JSON, is dead weight and
is listed. Working directories (art/, captures/, .godot/, build/, tests/) and
game authoring sources (inputs/, pipeline/) are not runtime payloads and are
not searched. Imported records and Markdown never count as a use.

    python3 godot/tools/unused_assets.py godot/games/afterlight [more projects]
    python3 godot/tools/unused_assets.py --check godot/games/*

`--check` exits 1 when anything is listed.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import deque
from pathlib import Path

ROOT_SUFFIXES = {".gd", ".tscn", ".tres", ".godot", ".gdshader"}
CATALOG_SUFFIXES = {".json"}
ASSET_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".svg",
    ".mp3",
    ".ogg",
    ".wav",
    ".flac",
    ".ogv",
    ".mp4",
    ".webm",
    ".ttf",
    ".otf",
    ".glb",
}
WORKING_DIRECTORIES = {"art", "captures", ".godot", "build", "tests", "__pycache__"}
AUTHORING_DIRECTORIES = {"inputs", "pipeline"}


def tracked_files(project: Path) -> list[Path]:
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--", "."], cwd=project, capture_output=True, check=True
    ).stdout
    files = []
    for item in listing.split(b"\0"):
        if not item:
            continue
        relative = Path(item.decode("utf-8"))
        if relative.parts[0] in WORKING_DIRECTORIES | AUTHORING_DIRECTORIES:
            continue
        files.append(relative)
    return files


def unused(project: Path) -> list[Path]:
    files = tracked_files(project)
    candidates = [f for f in files if f.suffix.lower() in ASSET_SUFFIXES | CATALOG_SUFFIXES]
    texts = {
        f: (project / f).read_text(errors="ignore")
        for f in files
        if f.suffix.lower() in ROOT_SUFFIXES | CATALOG_SUFFIXES
    }

    # A candidate is named by its project-relative path or by its bare name; the
    # second catches catalogs that bind a file relative to their own directory.
    # A directory a script loads from by pattern, as in "text/" + language +
    # ".json", is named by a string literal ending in that directory's slash,
    # and reaches every candidate directly inside it.
    def named_in(text: str, candidate: Path) -> bool:
        if candidate.as_posix() in text or candidate.name in text:
            return True
        directory = candidate.parent.as_posix()
        return directory != "." and (f'"{directory}/"' in text or f'"res://{directory}/"' in text)

    reached: set[Path] = set()
    queue: deque[Path] = deque(f for f in texts if f.suffix.lower() in ROOT_SUFFIXES)
    seen = set(queue)
    while queue:
        source = queue.popleft()
        text = texts[source]
        for candidate in candidates:
            if candidate == source or candidate in reached:
                continue
            if named_in(text, candidate):
                reached.add(candidate)
                if candidate in texts and candidate not in seen:
                    seen.add(candidate)
                    queue.append(candidate)
    return sorted(c for c in candidates if c not in reached)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("projects", nargs="+", type=Path)
    parser.add_argument("--check", action="store_true", help="exit 1 when anything is listed")
    arguments = parser.parse_args()
    found = 0
    for project in arguments.projects:
        if not (project / "project.godot").is_file():
            print(f"{project}: not a Godot project", file=sys.stderr)
            return 2
        for relative in unused(project):
            found += 1
            print(f"{project.as_posix()}/{relative.as_posix()}")
    if arguments.check and found:
        print(f"{found} unused asset(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
