"""Verify pinned examples, or promote runs to a new draft example.

    uv run python scripts/examples.py verify [OWNER] [--examples DIR]
    uv run python scripts/examples.py promote WORKFLOW --run RUN [--run RUN ...] --id ID
        [--title TITLE] [--option KEY=VALUE ...] [--examples DIR]

An example is a frozen export of real runs, pinned by digest in its owner's manifest.
``verify`` recomputes every pin and prints one line per example: ok, missing (from the local
store), or what differs. ``promote`` exports runs as a draft example into the store and pins
it in the workflow's ``workflow.toml``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts/examples.py", description="verify or promote pinned examples"
    )
    actions = parser.add_subparsers(dest="action", required=True)
    verify = actions.add_parser("verify", help="recompute every example pin")
    verify.add_argument("owner", nargs="?", help="a workflow or game id (default: all)")
    verify.add_argument("--examples", type=Path, dest="examples_dir", help="the example store")
    promote = actions.add_parser(
        "promote", help="export runs as a draft example and pin it in workflow.toml"
    )
    promote.add_argument("workflow", help="the workflow id the example belongs to")
    promote.add_argument(
        "--run",
        type=Path,
        action="append",
        required=True,
        dest="runs",
        help="a run folder to export; repeatable",
    )
    promote.add_argument("--id", required=True, dest="example_id", help="the new example's id")
    promote.add_argument("--title", help="the example's name (default: from its id)")
    promote.add_argument(
        "--option",
        action="append",
        default=[],
        dest="options",
        metavar="KEY=VALUE",
        help="an importer option, such as input_root=DIR, the folder the run was given as --input",
    )
    promote.add_argument("--examples", type=Path, dest="examples_dir", help="the example store")
    return parser


def verify(args: argparse.Namespace, output: TextIO) -> int:
    """One line per pinned example: ok, missing (from the local store), or what differs.

    Examples a game wrote into the store are checked against the pins the game wrote beside
    them in ``entry.json``, or only against their own ledger before the game exported them.
    """
    from stage_gen.examples import EXAMPLE_FILE, verify_game_example
    from stage_gen.workflows._catalog import default_examples_dir, load_example
    from stage_gen.workflows._registry import discover, load_code, repository_root

    store = args.examples_dir or default_examples_dir()
    repository = repository_root()
    lines: list[tuple[str, list[str], bool]] = []
    workflows = discover()
    for found in workflows:
        if args.owner not in (None, found.id):
            continue
        code = load_code(found.id)
        for entry in found.manifest.examples:
            loaded = load_example(
                found.id,
                entry,
                code,
                examples_dir=store,
                repository=repository,
                allow_missing=True,
            )
            lines.append((f"{found.id}/{entry.id}", list(loaded.problems), loaded.missing))
    owners = {found.id for found in workflows}
    if store.is_dir():
        for owner in sorted(p for p in store.iterdir() if p.is_dir() and p.name not in owners):
            if args.owner not in (None, owner.name):
                continue
            for directory in sorted(p for p in owner.iterdir() if (p / EXAMPLE_FILE).is_file()):
                lines.append(
                    (f"{owner.name}/{directory.name}", verify_game_example(directory), False)
                )
    if not lines:
        raise ValueError(f"no examples pinned or stored for {args.owner or 'any owner'}")
    for name, problems, missing in lines:
        state = "missing" if missing else "ok" if not problems else "; ".join(problems)
        output.write(f"{name}: {state}\n")
    return 1 if any(problems for _, problems, _ in lines) else 0


def promote(args: argparse.Namespace, output: TextIO) -> int:
    """Export runs as a draft example in the store and pin it in the workflow's manifest."""
    from stage_gen.examples import ImportRequest, MadeBy, store_directory, write_example
    from stage_gen.workflows._catalog import default_examples_dir
    from stage_gen.workflows._registry import (
        MANIFEST_FILE,
        find,
        load_code,
        read_manifest,
        repository_root,
    )

    found = find(args.workflow)
    code = load_code(found.id)
    if code.import_example is None:
        raise ValueError(f"{found.id} cannot promote examples: {code.no_importer}")
    if any(entry.id == args.example_id for entry in found.manifest.examples):
        raise ValueError(f"{found.id} already pins an example {args.example_id}")
    base = repository_root()
    manifest_path = Path(str(found.root)) / MANIFEST_FILE
    if base is None or not manifest_path.resolve().is_relative_to(base):
        raise ValueError("promote pins examples in a checkout's workflow.toml; run it from one")
    options: dict[str, str] = {}
    for option in args.options:
        key, sep, value = option.partition("=")
        if not sep or not key:
            raise ValueError(f"--option takes KEY=VALUE, not {option!r}")
        options[key] = value
    directory = store_directory(
        args.examples_dir or default_examples_dir(), found.id, args.example_id
    )
    if directory.exists():
        raise FileExistsError(f"the example store already holds {directory}")
    request = ImportRequest(
        example_id=args.example_id,
        made_by=MadeBy(kind="workflow", id=found.id),
        base=base,
        runs=tuple(run.resolve() for run in args.runs),
        out=directory,
        options=options,
    )
    try:
        example = code.import_example(request)
        pin = write_example(directory, example, request.figures(example))
    except BaseException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    title = args.title or args.example_id.replace("-", " ").capitalize()
    block = (
        "\n[[examples]]\n"
        f"id = {json.dumps(args.example_id)}\n"
        f"title = {json.dumps(title)}\n"
        'status = "draft"\n'
        'source = "store"\n'
        f'example_sha256 = "{pin.example_sha256}"\n'
        f'figures_sha256 = "{pin.figures_sha256}"\n'
    )
    text = manifest_path.read_text(encoding="utf-8").rstrip("\n") + "\n" + block
    read_manifest(text)
    manifest_path.write_text(text, encoding="utf-8")
    output.write(
        json.dumps(
            {
                "workflow": found.id,
                "example": args.example_id,
                "store": str(directory),
                "example_sha256": pin.example_sha256,
                "figures_sha256": pin.figures_sha256,
                "status": "draft",
            },
            indent=2,
        )
        + "\n"
    )
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output, errors = stdout or sys.stdout, stderr or sys.stderr
    args = build_parser().parse_args(argv)
    try:
        return verify(args, output) if args.action == "verify" else promote(args, output)
    except (ValueError, OSError) as error:
        errors.write(f"scripts/examples.py: {error}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
