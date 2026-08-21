"""Argparse CLI preserving the public stage-gen command contract."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Never, TextIO

from stage_gen.benchmarks import list_benchmark_suites, run_benchmark
from stage_gen.capabilities import (
    HeadlessRuntime,
    generate_image_artifact,
    generate_music,
    remove_background,
)
from stage_gen.components.character_profile import (
    ResolvedCharacterProfile,
    resolve_character_profile_binding,
)
from stage_gen.config import (
    ConfigError,
    StageGenConfig,
    TransparencyMode,
    load_config,
    parse_transparency_mode,
)
from stage_gen.orchestration.env_import import import_provider_env
from stage_gen.orchestration.service import GenerateRequest, generate
from stage_gen.recipes.registry import list_recipes

COMMANDS = {
    "generate",
    "serve",
    "recipes",
    "benchmark",
    "research",
    "generate-image",
    "remove-background",
    "generate-music",
    "import-env",
    "doctor",
    "character-profile",
}


class CliUsageError(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise CliUsageError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="stage-gen",
        description="headless 2D asset pipeline",
        epilog=(
            "Every generated artifact reports its output and provenance paths. "
            "A bare prompt is legacy-compatible scrolling-preview generation."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    generate_parser = commands.add_parser("generate")
    generate_parser.add_argument("--recipe", default="scrolling-preview")
    generate_parser.add_argument("--input", dest="input_file")
    generate_parser.add_argument(
        "--character-library-root",
        help="explicit workspace root containing library/characters",
    )
    generate_parser.add_argument("--transparency", choices=("ai", "chroma"))
    generate_parser.add_argument("prompt", nargs="*")

    profile_parser = commands.add_parser(
        "character-profile",
        description="Validate and inspect an authored character profile",
    )
    profile_commands = profile_parser.add_subparsers(
        dest="character_profile_command", required=True
    )
    for action in ("validate", "digest"):
        action_parser = profile_commands.add_parser(action)
        action_parser.add_argument("--input", required=True, dest="input_path")
        action_parser.add_argument(
            "--character-library-root",
            required=True,
            help="workspace root containing library/characters",
        )

    serve_parser = commands.add_parser("serve")
    serve_parser.add_argument("--host")
    serve_parser.add_argument("--port", type=int, default=4317)
    serve_parser.add_argument("--public", action="store_true", dest="allow_public")

    commands.add_parser("recipes")
    for name in ("benchmark", "research"):
        benchmark_parser = commands.add_parser(name)
        benchmark_parser.add_argument("suite", nargs="?", default="smoke")

    image_parser = commands.add_parser("generate-image")
    image_parser.add_argument("--output", required=True)
    image_parser.add_argument("--aspect-ratio", default="1:1")
    image_parser.add_argument("--reference", action="append", default=[])
    image_parser.add_argument("prompt", nargs="+")

    background_parser = commands.add_parser("remove-background")
    background_parser.add_argument("--input", required=True, dest="input_path")
    background_parser.add_argument("--output", required=True)

    music_parser = commands.add_parser("generate-music")
    music_parser.add_argument("--output", required=True)
    music_parser.add_argument("--format", choices=("mp3", "wav"), default="mp3")
    music_parser.add_argument("prompt", nargs="+")

    env_parser = commands.add_parser("import-env")
    env_parser.add_argument("--source", required=True)
    env_parser.add_argument("--destination", required=True)

    doctor_parser = commands.add_parser("doctor")
    doctor_parser.add_argument("--transparency", choices=("ai", "chroma"))
    doctor_parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def parse_generate_arguments(args: Sequence[str]) -> dict[str, object]:
    namespace = build_parser().parse_args(["generate", *args])
    return {
        "recipe": namespace.recipe,
        "inputFile": namespace.input_file,
        "prompt": " ".join(namespace.prompt).strip(),
        "transparencyMode": namespace.transparency,
    }


def parse_doctor_arguments(args: Sequence[str]) -> dict[str, object]:
    namespace = build_parser().parse_args(["doctor", *args])
    return {
        "json": namespace.json_output,
        "transparencyMode": namespace.transparency,
    }


def create_doctor_report(
    config: StageGenConfig, requested_mode: TransparencyMode | None = None
) -> dict[str, object]:
    mode = requested_mode or config.transparency_mode
    requires_background = mode == "ai"
    ready = bool(config.open_router_api_key and (not requires_background or config.fal_key))
    return {
        "ok": ready,
        "transparencyMode": mode,
        "requirements": {
            "openrouter": True,
            "backgroundRemoval": requires_background,
        },
        "capabilities": {
            "openrouter": bool(config.open_router_api_key),
            "fal": bool(config.fal_key),
        },
        "models": {
            "image": config.image_model,
            "text": config.text_model,
            "music": config.music_model,
            "backgroundRemoval": config.background_removal_model,
        },
        "outDir": str(config.out_dir),
    }


def main(
    argv: Sequence[str] | None = None,
    *,
    runtime: HeadlessRuntime | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output = stdout or sys.stdout
    errors = stderr or sys.stderr
    args = list(sys.argv[1:] if argv is None else argv)
    while args and args[0] == "--":
        args.pop(0)
    parser = build_parser()
    if not args:
        parser.print_help(output)
        return 0
    if args[0] in {"help", "-h", "--help"}:
        parser.print_help(output)
        return 0
    if args[0] not in COMMANDS:
        args.insert(0, "generate")
    try:
        namespace = parser.parse_args(args)
        return _dispatch(namespace, runtime=runtime, stdout=output)
    except ConfigError as error:
        errors.write(f"stage-gen: configuration: {error}\n")
        return 2
    except Exception as error:
        errors.write(f"stage-gen: error: {error}\n")
        return 1
    except KeyboardInterrupt:
        return 130


def entrypoint() -> None:
    raise SystemExit(main())


def _dispatch(
    args: argparse.Namespace,
    *,
    runtime: HeadlessRuntime | None,
    stdout: TextIO,
) -> int:
    command: str = args.command
    if command == "recipes":
        stdout.write(f"{json.dumps({'recipes': list_recipes()}, indent=2)}\n")
        return 0
    if command == "character-profile":
        resolved = _resolve_cli_character_profile(
            input_path=Path(args.input_path),
            character_library_root=Path(args.character_library_root),
        )
        if args.character_profile_command == "digest":
            stdout.write(f"{resolved.source_sha256}\n")
        else:
            report = {"valid": True, **resolved.identity()}
            stdout.write(f"{json.dumps(report, sort_keys=True, separators=(',', ':'))}\n")
        return 0
    if command == "doctor":
        config = load_config()
        mode = (
            parse_transparency_mode(args.transparency, "--transparency")
            if args.transparency is not None
            else None
        )
        report = create_doctor_report(config, mode)
        if args.json_output:
            stdout.write(f"{json.dumps(report, separators=(',', ':'))}\n")
        else:
            requirements = report["requirements"]
            capabilities = report["capabilities"]
            assert isinstance(requirements, dict) and isinstance(capabilities, dict)
            fal = (
                ("configured" if capabilities["fal"] else "missing")
                if requirements["backgroundRemoval"]
                else "not-required"
            )
            stdout.write(
                f"stage-gen: {'ready' if report['ok'] else 'incomplete'}; "
                f"transparency={report['transparencyMode']}; "
                f"openrouter={'configured' if capabilities['openrouter'] else 'missing'}; "
                f"fal={fal}\n"
            )
        return 0 if report["ok"] else 2
    if command in {"benchmark", "research"}:
        if args.suite == "list":
            stdout.write(f"{json.dumps({'suites': list_benchmark_suites()}, indent=2)}\n")
            return 0
        result = run_benchmark(args.suite, load_config())
        stdout.write(f"{json.dumps(result, indent=2)}\n")
        return 0 if result["ok"] else 1
    if command == "import-env":
        imported = import_provider_env(args.source, args.destination)
        stdout.write(f"{json.dumps(imported, separators=(',', ':'))}\n")
        return 0
    if command == "serve":
        from stage_gen.interfaces.api import create_app, resolve_server_binding

        try:
            import uvicorn
        except ImportError as error:
            raise ValueError("serve requires the server extra: uv sync --extra server") from error
        hostname = "0.0.0.0" if args.allow_public and not args.host else args.host
        host, port = resolve_server_binding(
            hostname=hostname, port=args.port, allow_public=args.allow_public
        )
        uvicorn.run(create_app(load_config(), runtime=runtime), host=host, port=port)
        return 0
    return asyncio.run(_dispatch_async(args, runtime=runtime, stdout=stdout))


async def _dispatch_async(
    args: argparse.Namespace,
    *,
    runtime: HeadlessRuntime | None,
    stdout: TextIO,
) -> int:
    config = load_config()
    if args.command == "generate":
        if args.character_library_root is not None:
            config = config.model_copy(
                update={"character_library_root": Path(args.character_library_root)}
            )
        prompt = " ".join(args.prompt).strip()
        if args.input_file:
            input_path = Path(args.input_file)
            input_text = await asyncio.to_thread(input_path.read_text, encoding="utf-8")
            input_value = _parse_input_document(input_text, suffix=input_path.suffix.lower())
        else:
            input_value = {"prompt": prompt}
        summary = await generate(
            GenerateRequest(
                recipe=args.recipe,
                input=input_value,
                transparency_mode=args.transparency,
            ),
            config,
            runtime=runtime,
        )
        if not summary.ok:
            failed = next((stage for stage in summary.stages if not stage.ok), None)
            raise ValueError(
                f"stage failed - {failed.stage if failed else 'unknown'}: "
                f"{failed.error if failed else 'unknown'}"
            )
        stdout.write(
            f"stage-gen: done recipe={summary.recipe} tag={summary.tag} "
            f"stages={len(summary.stages)} duration={summary.duration_ms}ms\n"
        )
        return 0
    if args.command == "generate-image":
        aspect_ratio: str = args.aspect_ratio
        if aspect_ratio != "auto":
            pieces = aspect_ratio.split(":")
            if len(pieces) != 2 or not all(piece.isdigit() and int(piece) > 0 for piece in pieces):
                raise ValueError("--aspect-ratio must be auto or positive <width>:<height>")
        result = await generate_image_artifact(
            prompt=" ".join(args.prompt).strip(),
            output_path=args.output,
            aspect_ratio=aspect_ratio,
            reference_paths=args.reference,
            config=config,
            runtime=runtime,
        )
    elif args.command == "remove-background":
        result = await remove_background(
            input_path=args.input_path,
            output_path=args.output,
            config=config,
            runtime=runtime,
        )
    elif args.command == "generate-music":
        result = await generate_music(
            prompt=" ".join(args.prompt).strip(),
            output_path=args.output,
            output_format=args.format,
            config=config,
            runtime=runtime,
        )
    else:
        raise ValueError(f"unsupported command: {args.command}")
    stdout.write(f"{json.dumps(result.to_dict(), separators=(',', ':'))}\n")
    return 0


def _parse_input_document(text: str, *, suffix: str) -> object:
    if suffix == ".toml":
        return tomllib.loads(text)
    return json.loads(text)


def _resolve_cli_character_profile(
    *, input_path: Path, character_library_root: Path
) -> ResolvedCharacterProfile:
    root = character_library_root.absolute()
    source = input_path.absolute()
    try:
        relative = source.relative_to(root)
    except ValueError as error:
        raise ValueError("character profile input must be inside character library root") from error
    parts = relative.parts
    if len(parts) != 4 or parts[:2] != ("library", "characters") or parts[3] != "profile.toml":
        raise ValueError(
            "character profile input must equal ROOT/library/characters/<profile_id>/profile.toml"
        )
    try:
        source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    except OSError as error:
        raise ValueError("character profile input is unreadable") from error
    return resolve_character_profile_binding(
        {
            "schema_version": 1,
            "kind": "character-profile-binding-v1",
            "ref": relative.as_posix(),
            "source_sha256": source_sha256,
        },
        character_library_root=root,
    )
