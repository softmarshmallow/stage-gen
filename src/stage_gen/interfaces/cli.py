"""Command adapters for user-authored asset pipelines and optional consumers."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Never, TextIO


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ValueError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="stage-gen", description="Author, run and inspect your own asset pipelines"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    pipeline = commands.add_parser("pipeline", help="run a Python-authored asset pipeline")
    actions = pipeline.add_subparsers(dest="action", required=True)
    for action in ("plan", "run"):
        command = actions.add_parser(action)
        command.add_argument(
            "definition", help="module:attribute or file.py:attribute (default: pipeline)"
        )
        command.add_argument("--input", type=Path, required=True, dest="input_root")
        command.add_argument("--output", type=Path, required=action == "run", dest="output_root")
        command.add_argument("--target", action="append", default=None, dest="targets")
        if action == "run":
            command.add_argument("--cache-dir", type=Path, required=True, dest="cache_root")
            command.add_argument("--invocation-id")
            command.add_argument(
                "--live",
                action="store_true",
                help="explicitly allow provider nodes configured by the pipeline author",
            )
    inspect_parser = actions.add_parser("inspect")
    inspect_parser.add_argument("run_dir", type=Path)
    commands.add_parser("universe", help="optional storyworld asset recipe; use universe --help")
    commands.add_parser(
        "storefront", help="optional promotional asset recipe; use storefront --help"
    )
    commands.add_parser("models", help="inspect the application-owned route catalog")
    catalog = commands.add_parser(
        "catalog", help="export the catalog of installed workflows and their examples"
    )
    catalog_actions = catalog.add_subparsers(dest="action", required=True)
    export = catalog_actions.add_parser("export", help="write catalog.json, or only check drift")
    export.add_argument("--out", type=Path, required=True, dest="out_dir")
    export.add_argument("--examples", type=Path, dest="examples_dir", help="the example store")
    export.add_argument(
        "--allow-missing-examples",
        action="store_true",
        help="build without pinned store examples that are absent; a mismatch still fails",
    )
    export.add_argument("--check", action="store_true", help="run the drift checks only")
    example = commands.add_parser("example", help="verify or promote pinned examples")
    example_actions = example.add_subparsers(dest="action", required=True)
    verify = example_actions.add_parser("verify", help="recompute every example pin")
    verify.add_argument("owner", nargs="?", help="a workflow or game id (default: all)")
    verify.add_argument("--examples", type=Path, dest="examples_dir", help="the example store")
    promote = example_actions.add_parser(
        "promote", help="export runs as a draft example and pin it in workflow.toml"
    )
    promote.add_argument("workflow")
    promote.add_argument("--run", type=Path, action="append", required=True, dest="runs")
    promote.add_argument("--id", required=True, dest="example_id")
    promote.add_argument("--title", help="the example's name (default: from its id)")
    promote.add_argument(
        "--option",
        action="append",
        default=[],
        dest="options",
        metavar="KEY=VALUE",
        help="an importer option, such as output_node=finish",
    )
    promote.add_argument("--examples", type=Path, dest="examples_dir", help="the example store")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output, errors = stdout or sys.stdout, stderr or sys.stderr
    arguments = list(sys.argv[1:] if argv is None else argv)
    while arguments and arguments[0] == "--":
        arguments.pop(0)
    parser = build_parser()
    if not arguments or arguments[0] in {"help", "-h", "--help"}:
        parser.print_help(output)
        return 0
    try:
        if arguments[0] in {"universe", "storefront"}:
            from stage_gen.interfaces.asset_recipes import main as recipe_main

            return recipe_main(arguments, stdout=output, stderr=errors)
        if arguments[0] == "models":
            from stage_gen.model_policy_maintenance import (
                load_active_model_policy_snapshot,
                model_route_report,
            )

            if arguments[1:] not in ([], ["routes"]):
                raise ValueError(
                    "use stage-gen models routes; game fixture projections belong to "
                    "demo-games models"
                )
            output.write(
                json.dumps(model_route_report(load_active_model_policy_snapshot()), indent=2) + "\n"
            )
            return 0
        args = parser.parse_args(arguments)
        if args.command == "catalog":
            return _catalog_export(args, output)
        if args.command == "example":
            return (
                _example_verify(args, output) if args.action == "verify" else _promote(args, output)
            )
        from stage_gen.pipeline import inspect, load_definition, plan, run, write_plan

        if args.action == "inspect":
            result = inspect(args.run_dir)
            output.write(result.model_dump_json(indent=2) + "\n")
            return 0
        try:
            definition = load_definition(args.definition)
        except (ImportError, AttributeError, TypeError, SyntaxError) as error:
            raise ValueError(f"cannot load pipeline definition: {error}") from error
        planned = plan(definition, input_root=args.input_root, targets=args.targets)
        if args.action == "plan":
            if args.output_root is not None:
                write_plan(planned, args.output_root)
            output.write(
                json.dumps(
                    {
                        "graph": planned.graph.model_dump(mode="json"),
                        "projection": planned.projection.model_dump(mode="json"),
                    },
                    indent=2,
                )
                + "\n"
            )
            return 0
        completed = asyncio.run(
            run(
                planned,
                output_root=args.output_root,
                cache_root=args.cache_root,
                invocation_id=args.invocation_id,
                allow_provider_calls=args.live,
            )
        )
        output.write(
            json.dumps(
                {
                    "ok": completed.summary.ok,
                    "pipeline_id": definition.pipeline_id,
                    "run_dir": str(completed.run_dir),
                    "summary": completed.summary.model_dump(mode="json"),
                },
                indent=2,
            )
            + "\n"
        )
        return 0 if completed.summary.ok else 1
    except (ValueError, FileNotFoundError, FileExistsError) as error:
        errors.write(f"stage-gen: {error}\n")
        return 2
    except KeyboardInterrupt:
        return 130


def _catalog_export(args: argparse.Namespace, output: TextIO) -> int:
    from stage_gen.workflows._catalog import default_examples_dir, export

    result = export(
        args.out_dir,
        examples_dir=args.examples_dir or default_examples_dir(),
        allow_missing_examples=args.allow_missing_examples,
        check=args.check,
    )
    output.write(
        json.dumps(
            {
                "workflows": result.workflows,
                "catalog": None if result.path is None else str(result.path),
                "problems": list(result.problems),
            },
            indent=2,
        )
        + "\n"
    )
    return 1 if result.problems else 0


def _example_verify(args: argparse.Namespace, output: TextIO) -> int:
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


def _promote(args: argparse.Namespace, output: TextIO) -> int:
    """Export runs as a draft example in the store and pin it in the workflow's manifest."""
    import shutil

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


def entrypoint() -> None:
    raise SystemExit(main())
