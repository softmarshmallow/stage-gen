"""Provider-free command line authoring, inspection and local content packaging."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from .catalog import empty_catalog, read_catalog
from .compiler import Compilation, canonical_json, compile_scenario
from .content import build_content_package, read_json, verify_content_package
from .program import admit_program
from .validation import ScenarioError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scenario-authoring")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "compile", "inspect", "preview-input"):
        command = commands.add_parser(name)
        command.add_argument("input", type=Path)
        command.add_argument("--catalog", type=Path)
        command.add_argument("--capabilities", type=Path)
        command.add_argument(
            "--compiled", action="store_true", help="Read compiled JSON explicitly"
        )
        if name in {"compile", "preview-input"}:
            command.add_argument("--output", type=Path, required=True)
        if name == "compile":
            command.add_argument("--source-map", type=Path)
    package = commands.add_parser("pack")
    package.add_argument("--source-root", type=Path, required=True)
    package.add_argument("--output", type=Path, required=True)
    package.add_argument("--package-id", required=True)
    package.add_argument("--revision", type=int, required=True)
    package.add_argument("--catalog", required=True, help="Member path below source-root")
    package.add_argument("--program", action="append", default=[], metavar="ID=MEMBER")
    package.add_argument("--asset", action="append", default=[], metavar="MEMBER")
    package.add_argument("--capabilities", type=Path)
    verify = commands.add_parser("check-package")
    verify.add_argument("input", type=Path)
    verify.add_argument("--capabilities", type=Path)
    return parser


def _json_file(path: Path | None, default: Any) -> Any:
    return default if path is None else read_json(path.read_bytes(), path.name)


def _write(path: Path, value: Any) -> None:
    if path.is_symlink():
        raise ScenarioError("output file must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".scenario-write-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_json(value))
            stream.write(b"\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _compile(args: argparse.Namespace) -> tuple[dict[str, Any], Compilation | None]:
    catalog = _json_file(args.catalog, empty_catalog())
    capabilities = _json_file(args.capabilities, {})
    if args.compiled:
        return admit_program(
            _json_file(args.input, None), read_catalog(catalog, capabilities)
        ), None
    compilation = compile_scenario(
        args.input.read_text(encoding="utf-8"),
        catalog=catalog,
        capabilities=capabilities,
        source_name=args.input.name,
    )
    return compilation.program, compilation


def _report(program: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "scenario_id": program["scenario_id"],
        "entry": program["entry"],
        "nodes": len(program["nodes"]),
        "required_capabilities": program["required_capabilities"],
        "outcomes": sorted({node["outcome"] for node in program["nodes"] if node["kind"] == "end"}),
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "pack":
            programs: dict[str, str] = {}
            for value in args.program:
                name, separator, path = value.partition("=")
                if not separator or not name or not path or name in programs:
                    raise ScenarioError("--program requires distinct ID=MEMBER mappings")
                programs[name] = path
            manifest = build_content_package(
                args.source_root,
                args.output,
                package_id=args.package_id,
                revision=args.revision,
                catalog_path=args.catalog,
                programs=programs,
                assets=args.asset,
                capabilities=_json_file(args.capabilities, {}),
            )
            print(
                json.dumps(
                    {
                        "ok": True,
                        "package_id": manifest["package_id"],
                        "files": len(manifest["files"]),
                    }
                )
            )
            return 0
        if args.command == "check-package":
            manifest = verify_content_package(
                args.input, capabilities=_json_file(args.capabilities, {})
            )
            print(
                json.dumps(
                    {
                        "ok": True,
                        "package_id": manifest["package_id"],
                        "revision": manifest["revision"],
                    }
                )
            )
            return 0
        program, compilation = _compile(args)
        if args.command in {"compile", "preview-input"}:
            if args.input.resolve() == args.output.resolve():
                raise ScenarioError("output must not overwrite the authored input")
            if args.command == "preview-input":
                _write(
                    args.output,
                    {
                        "kind": "scenario-preview-input",
                        "schema_version": 1,
                        "program": program,
                        "catalog": _json_file(args.catalog, empty_catalog()),
                        "required_capabilities": program["required_capabilities"],
                        "source_map": {} if compilation is None else compilation.source_map,
                    },
                )
            else:
                _write(args.output, program)
                if args.source_map:
                    if args.source_map.resolve() in {args.input.resolve(), args.output.resolve()}:
                        raise ScenarioError(
                            "source-map output must be separate from source and program"
                        )
                    _write(args.source_map, {} if compilation is None else compilation.source_map)
        report = _report(program)
        if args.command == "inspect":
            report["instructions"] = [
                {
                    key: node[key]
                    for key in ("id", "kind", "next", "target", "outcome")
                    if key in node
                }
                for node in program["nodes"]
            ]
        if compilation:
            report["source_sha256"] = compilation.source_sha256
            report["program_sha256"] = compilation.program_sha256
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ScenarioError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
