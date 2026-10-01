#!/usr/bin/env python3
"""Build or serve the static site in web/site from the catalog and the example store.

    uv run python scripts/site.py build [--allow-missing-examples] [--examples DIR] [--base-path P]
    uv run python scripts/site.py stage [--allow-missing-examples] [--examples DIR]
    uv run python scripts/site.py serve [--port 8790]

`stage` writes everything `next build` reads, all into gitignored folders:
- `stage-gen catalog export` into web/site/.catalog/: catalog.json, and cli.json, the command
  tree the CLI reference page is written from;
- the prose from the checkout into web/site/.catalog/pages/: each workflow's page.mdx,
  contract.md and examples/*.mdx, each game example's page.mdx from the store, and the
  SITE_DOCS markdown with docs/index.json, their slugs, titles and checkout paths in order;
- the example media into web/site/public/examples/<owner>/<id>/media/, from the store, or
  for a library example from the tracked files its figures ledger names.
`build` stages, then runs `bun run --cwd web/site build`, which writes web/site/out/.
Without `--allow-missing-examples` an approved example missing from the store fails the
export, which is the strict mode a release build uses; a clean clone builds with the flag.
`serve` serves web/site/out/ on 127.0.0.1 with the standard library file server.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SITE_ROOT = REPOSITORY_ROOT / "web" / "site"
CATALOG_ROOT = SITE_ROOT / ".catalog"
PAGES_ROOT = CATALOG_ROOT / "pages"
MEDIA_ROOT = SITE_ROOT / "public" / "examples"
OUT_ROOT = SITE_ROOT / "out"
DEFAULT_EXAMPLES = REPOSITORY_ROOT / "out" / "examples"

# Markdown the site shows under /docs/<slug>/, read from the checkout: (path, title), in the
# order the docs index lists them. The site resolves a doc's relative links by its path.
SITE_DOCS: Mapping[str, tuple[str, str]] = {
    "getting-started": ("docs/getting-started.md", "Getting started"),
    "glossary": ("docs/glossary.md", "Glossary"),
    "viewer": ("docs/viewer.md", "Run viewer"),
    "sdk": ("src/stage_gen/pipeline/README.md", "Pipeline SDK"),
}

SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class SiteError(RuntimeError):
    pass


def _slug(value: object, label: str) -> str:
    if not isinstance(value, str) or not SLUG.match(value):
        raise SiteError(f"{label} {value!r} is not a plain folder name")
    return value


def _inside(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise SiteError(f"{label} {path} escapes {root}")
    return resolved


def _stage_gen() -> str:
    beside = Path(sys.executable).parent / "stage-gen"
    if beside.is_file():
        return str(beside)
    found = shutil.which("stage-gen")
    if found is None:
        raise SiteError("stage-gen is not installed here; run this through `uv run`")
    return found


def export_catalog(examples: Path, *, allow_missing_examples: bool) -> dict[str, object]:
    if CATALOG_ROOT.exists():
        shutil.rmtree(CATALOG_ROOT)
    CATALOG_ROOT.mkdir(parents=True)
    command = [
        _stage_gen(),
        "catalog",
        "export",
        "--out",
        str(CATALOG_ROOT),
        "--examples",
        str(examples),
    ]
    if allow_missing_examples:
        command.append("--allow-missing-examples")
    completed = subprocess.run(command, cwd=REPOSITORY_ROOT, check=False)
    if completed.returncode != 0:
        raise SiteError(f"stage-gen catalog export failed with exit code {completed.returncode}")
    loaded: object = json.loads((CATALOG_ROOT / "catalog.json").read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise SiteError("catalog.json is not an object")
    if not (CATALOG_ROOT / "cli.json").is_file():
        raise SiteError("stage-gen catalog export wrote no cli.json; the CLI reference needs it")
    return loaded


def _copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def _entries(catalog: Mapping[str, object], key: str) -> list[dict[str, object]]:
    value = catalog.get(key)
    if not isinstance(value, list) or not all(isinstance(entry, dict) for entry in value):
        raise SiteError(f"catalog.{key} is not a list of objects")
    return value


def stage_pages(catalog: Mapping[str, object], examples: Path) -> list[Path]:
    """Copy every page source the site compiles into .catalog/pages/."""
    written: list[Path] = []
    for workflow in _entries(catalog, "workflows"):
        workflow_id = _slug(workflow.get("id"), "workflow id")
        folder = workflow.get("source_folder")
        if not isinstance(folder, str):
            raise SiteError(f"workflow {workflow_id} has no source folder; build from a checkout")
        source = _inside(REPOSITORY_ROOT / folder, REPOSITORY_ROOT, "workflow folder")
        target = PAGES_ROOT / "workflows" / workflow_id
        for name in ("page.mdx", "contract.md"):
            _copy_file(source / name, target / name)
            written.append(target / name)
        for page in sorted((source / "examples").glob("*.mdx")):
            _copy_file(page, target / "examples" / page.name)
            written.append(target / "examples" / page.name)
    for game_example in _entries(catalog, "game_examples"):
        owner = _slug(game_example.get("owner"), "game")
        example_id = _slug(game_example.get("id"), "game example id")
        page_name = game_example.get("page")
        if page_name is None:
            continue
        if page_name != "page.mdx":
            raise SiteError(
                f"game example {owner}/{example_id} names an unexpected page {page_name!r}"
            )
        target = PAGES_ROOT / "games" / owner / example_id / "page.mdx"
        _copy_file(examples / owner / example_id / "page.mdx", target)
        written.append(target)
    docs: list[dict[str, str]] = []
    for slug, (relative, title) in SITE_DOCS.items():
        target = PAGES_ROOT / "docs" / f"{_slug(slug, 'doc slug')}.md"
        _copy_file(_inside(REPOSITORY_ROOT / relative, REPOSITORY_ROOT, "doc"), target)
        written.append(target)
        docs.append({"slug": slug, "title": title, "path": relative})
    index = PAGES_ROOT / "docs" / "index.json"
    index.write_text(json.dumps(docs, indent=2) + "\n", encoding="utf-8")
    written.append(index)
    return written


def _figure_sources(figures: object, label: str) -> list[tuple[str, str]]:
    """(example-relative file, repository-relative source) for each ledger entry."""
    if not isinstance(figures, dict) or not isinstance(figures.get("files"), list):
        raise SiteError(f"{label} has no figures ledger")
    pairs: dict[str, str] = {}
    for entry in figures["files"]:
        if not isinstance(entry, dict):
            raise SiteError(f"{label} has a malformed ledger entry")
        file, sources = entry.get("file"), entry.get("sources")
        if not isinstance(file, str) or not isinstance(sources, list) or len(sources) != 1:
            raise SiteError(f"{label}: a library file must name exactly one source")
        source = sources[0]
        if not isinstance(source, dict) or not isinstance(source.get("path"), str):
            raise SiteError(f"{label}: ledger entry {file} has no source path")
        pairs[file] = source["path"]  # the last entry for a file wins, as in the ledger
    return list(pairs.items())


def stage_media(catalog: Mapping[str, object], examples: Path) -> int:
    """Copy each present example's media to public/examples/<owner>/<id>/; returns a count."""
    if MEDIA_ROOT.exists():
        shutil.rmtree(MEDIA_ROOT)
    MEDIA_ROOT.mkdir(parents=True)
    count = 0
    stores: list[tuple[str, str]] = []
    for workflow in _entries(catalog, "workflows"):
        workflow_id = _slug(workflow.get("id"), "workflow id")
        for example in _entries(workflow, "examples"):
            if not example.get("present"):
                continue
            example_id = _slug(example.get("id"), "example id")
            source = example.get("source")
            if source == "store":
                stores.append((workflow_id, example_id))
                continue
            label = f"{workflow_id}/{example_id}"
            target_root = MEDIA_ROOT / workflow_id / example_id
            for file, path in _figure_sources(example.get("figures"), label):
                origin = _inside(REPOSITORY_ROOT / path, REPOSITORY_ROOT, f"{label} source")
                target = _inside(target_root / file, target_root, f"{label} file")
                _copy_file(origin, target)
                count += 1
    for game_example in _entries(catalog, "game_examples"):
        stores.append(
            (
                _slug(game_example.get("owner"), "game"),
                _slug(game_example.get("id"), "game example id"),
            )
        )
    for owner, example_id in stores:
        media = examples / owner / example_id / "media"
        if not media.is_dir():
            raise SiteError(f"{owner}/{example_id} is in the catalog but {media} is missing")
        target = MEDIA_ROOT / owner / example_id / "media"
        shutil.copytree(media, target)
        count += sum(1 for path in target.rglob("*") if path.is_file())
    return count


def stage(examples: Path, *, allow_missing_examples: bool) -> None:
    catalog = export_catalog(examples, allow_missing_examples=allow_missing_examples)
    pages = stage_pages(catalog, examples)
    media = stage_media(catalog, examples)
    print(
        f"staged {len(pages)} page sources into {PAGES_ROOT.relative_to(REPOSITORY_ROOT)} "
        f"and {media} media files into {MEDIA_ROOT.relative_to(REPOSITORY_ROOT)}",
        flush=True,
    )


def build(examples: Path, *, allow_missing_examples: bool, base_path: str | None) -> None:
    stage(examples, allow_missing_examples=allow_missing_examples)
    bun = shutil.which("bun")
    if bun is None:
        raise SiteError("the site builds with Bun; install it (https://bun.sh) and run this again")
    environment = dict(os.environ)
    if base_path is not None:
        environment["SITE_BASE_PATH"] = base_path
    completed = subprocess.run(
        [bun, "run", "--cwd", str(SITE_ROOT), "build"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
    )
    if completed.returncode != 0:
        raise SiteError(f"next build failed with exit code {completed.returncode}")
    print(OUT_ROOT / "index.html", flush=True)


def serve(port: int) -> None:
    if not (OUT_ROOT / "index.html").is_file():
        raise SiteError(f"{OUT_ROOT} has no build; run `uv run python scripts/site.py build` first")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(OUT_ROOT))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"serving {OUT_ROOT} at http://127.0.0.1:{port}/", flush=True)
        with contextlib.suppress(KeyboardInterrupt):
            server.serve_forever()


def _base_path(value: str) -> str:
    if value and not re.fullmatch(r"(/[A-Za-z0-9._-]+)+", value):
        raise argparse.ArgumentTypeError("a base path looks like /showcase-site")
    return value


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0] if __doc__ else None)
    commands = root.add_subparsers(dest="command", required=True)
    for name, text in (
        ("stage", "export the catalog and stage page sources and media, without next build"),
        ("build", "stage, then run next build into web/site/out"),
    ):
        command = commands.add_parser(name, help=text)
        command.add_argument("--allow-missing-examples", action="store_true")
        command.add_argument("--examples", type=Path, default=DEFAULT_EXAMPLES)
        if name == "build":
            command.add_argument("--base-path", type=_base_path, default=None)
    served = commands.add_parser("serve", help="serve web/site/out on 127.0.0.1")
    served.add_argument("--port", type=int, default=8790)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "serve":
            serve(arguments.port)
        elif arguments.command == "stage":
            stage(
                arguments.examples.resolve(),
                allow_missing_examples=arguments.allow_missing_examples,
            )
        else:
            build(
                arguments.examples.resolve(),
                allow_missing_examples=arguments.allow_missing_examples,
                base_path=arguments.base_path,
            )
    except SiteError as error:
        print(f"site: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
