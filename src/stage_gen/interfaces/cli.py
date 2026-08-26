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
from stage_gen.components._secure_fs import SecurePathError, read_absolute_regular_file
from stage_gen.components.character_profile import (
    ResolvedCharacterProfile,
    resolve_character_profile_binding,
)
from stage_gen.components.game_contract import (
    ResolvedGameContract,
    resolve_game_contract_binding,
)
from stage_gen.components.game_map import (
    ResolvedGameMap,
    ResolvedGameMapBook,
    resolve_game_map_book_binding,
    resolve_game_map_source,
)
from stage_gen.components.game_soundtrack import (
    ResolvedGameSoundtrack,
    resolve_game_soundtrack_binding,
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
from stage_gen.recipes.dialogue_scene.character_bundle import (
    package_dialogue_character_spike,
    review_dialogue_character_bundle,
    sanitize_dialogue_character_spike,
)
from stage_gen.recipes.registry import list_recipes, run_recipe_action
from stage_gen.recipes.scrolling_preview.dialogue_character import (
    bind_dialogue_character_to_scrolling_manifest,
)

COMMANDS = {
    "generate",
    "serve",
    "recipes",
    "benchmark",
    "research",
    "review",
    "generate-image",
    "remove-background",
    "generate-music",
    "import-env",
    "doctor",
    "character-profile",
    "game",
    "map",
    "map-book",
    "soundtrack",
    "dialogue-character",
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
            "A bare prompt is the current shorthand for scrolling-preview generation."
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
    generate_parser.add_argument(
        "--game-library-root",
        help="explicit workspace root containing library/games",
    )
    generate_parser.add_argument("--transparency", choices=("native", "ai", "chroma"))
    generate_parser.add_argument(
        "--force-stage",
        action="append",
        default=[],
        dest="force_stages",
        metavar="STAGE_ID",
        help="rerun one recipe stage; repeat to select multiple stages",
    )
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

    game_parser = commands.add_parser(
        "game",
        description="Validate and inspect an authored game contract",
    )
    game_commands = game_parser.add_subparsers(dest="game_command", required=True)
    for action in ("validate", "digest"):
        game_action_parser = game_commands.add_parser(action)
        game_action_parser.add_argument("--input", required=True, dest="input_path")
        game_action_parser.add_argument(
            "--game-library-root",
            required=True,
            help="workspace root containing library/games",
        )

    soundtrack_parser = commands.add_parser(
        "soundtrack",
        description="Validate and inspect an authored game soundtrack",
    )
    soundtrack_commands = soundtrack_parser.add_subparsers(dest="soundtrack_command", required=True)
    for action in ("validate", "digest"):
        soundtrack_action_parser = soundtrack_commands.add_parser(action)
        soundtrack_action_parser.add_argument("--input", required=True, dest="input_path")
        soundtrack_action_parser.add_argument(
            "--game-library-root",
            required=True,
            help="workspace root containing library/games",
        )

    dialogue_character_parser = commands.add_parser(
        "dialogue-character",
        description="Sanitize, package, review, and bind a four-state dialogue character",
    )
    dialogue_character_commands = dialogue_character_parser.add_subparsers(
        dest="dialogue_character_command", required=True
    )
    sanitize_parser = dialogue_character_commands.add_parser(
        "sanitize",
        help="sanitize one pending local character spike in place",
    )
    sanitize_parser.add_argument(
        "--spike",
        required=True,
        dest="spike_path",
        metavar="RUN/spike-assets/character-only.json",
        help="pending character-only spike to sanitize in place",
    )
    package_parser = dialogue_character_commands.add_parser(
        "package",
        help="package one validated spike at its canonical run path",
    )
    package_parser.add_argument(
        "--spike",
        required=True,
        dest="spike_path",
        metavar="RUN/spike-assets/character-only.json",
        help="validated character-only spike to package",
    )
    character_review_parser = dialogue_character_commands.add_parser(
        "review",
        help="apply an independent review to one pending character bundle",
    )
    character_review_parser.add_argument(
        "--bundle",
        required=True,
        dest="bundle_path",
        metavar="RUN/dialogue-character.bundle.json",
        help="pending character bundle to review",
    )
    character_review_parser.add_argument(
        "--review",
        required=True,
        dest="review_path",
        metavar="REVIEW.json",
        help="independent digest-bound review input",
    )
    character_review_parser.add_argument(
        "--acceptance-spec",
        required=True,
        dest="acceptance_spec_path",
        metavar="ACCEPTANCE.json",
        help="acceptance specification bound by the review",
    )
    bind_parser = dialogue_character_commands.add_parser(
        "bind",
        help="bind one reviewed character bundle into a current scrolling manifest",
    )
    bind_parser.add_argument(
        "--bundle",
        required=True,
        dest="bundle_path",
        metavar="RUN/dialogue-character.bundle.reviewed.json",
        help="reviewed local-demo character bundle to bind",
    )
    bind_parser.add_argument(
        "--manifest",
        required=True,
        dest="manifest_path",
        metavar="RUN/manifest_TAG.json",
        help="current scrolling manifest to update in place",
    )
    bind_parser.add_argument(
        "--npc-slot",
        required=True,
        type=int,
        choices=range(4),
        dest="npc_slot",
        help="verified scrolling NPC slot",
    )

    map_parser = commands.add_parser(
        "map",
        description="Validate and inspect one authored game map",
    )
    map_commands = map_parser.add_subparsers(dest="map_command", required=True)
    for action in ("validate", "digest"):
        map_action_parser = map_commands.add_parser(action)
        map_action_parser.add_argument("--input", required=True, dest="input_path")
        map_action_parser.add_argument(
            "--game-library-root",
            required=True,
            help="workspace root containing library/games",
        )

    map_book_parser = commands.add_parser(
        "map-book",
        description="Validate and inspect an authored ordered game map book",
    )
    map_book_commands = map_book_parser.add_subparsers(dest="map_book_command", required=True)
    for action in ("validate", "digest"):
        map_book_action_parser = map_book_commands.add_parser(action)
        map_book_action_parser.add_argument("--input", required=True, dest="input_path")
        map_book_action_parser.add_argument(
            "--game-library-root",
            required=True,
            help="workspace root containing library/games",
        )

    review_parser = commands.add_parser(
        "review", description="Apply a digest-bound independent recipe review"
    )
    review_parser.add_argument("--recipe", required=True)
    review_parser.add_argument("--bundle", required=True, dest="bundle_path")
    review_parser.add_argument("--review", required=True, dest="review_path")
    review_parser.add_argument("--acceptance-spec", required=True, dest="acceptance_spec_path")
    review_parser.add_argument("--usage", required=True, choices=("local-demo",))

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
    doctor_parser.add_argument("--transparency", choices=("native", "ai", "chroma"))
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
    requires_openai = mode is TransparencyMode.NATIVE
    requires_background = mode is TransparencyMode.AI
    ready = bool(
        config.open_router_api_key
        and (not requires_openai or config.openai_api_key)
        and (not requires_background or config.fal_key)
    )
    return {
        "ok": ready,
        "transparencyMode": mode,
        "requirements": {
            "openai": requires_openai,
            "openrouter": True,
            "backgroundRemoval": requires_background,
        },
        "capabilities": {
            "openai": bool(config.openai_api_key),
            "openrouter": bool(config.open_router_api_key),
            "fal": bool(config.fal_key),
        },
        "models": {
            "nativeImage": config.openai_image_model,
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
    if command == "game":
        resolved_game = _resolve_cli_game_contract(
            input_path=Path(args.input_path),
            game_library_root=Path(args.game_library_root),
        )
        if args.game_command == "digest":
            stdout.write(f"{resolved_game.source_sha256}\n")
        else:
            game_report = {"valid": True, **resolved_game.identity()}
            stdout.write(f"{json.dumps(game_report, sort_keys=True, separators=(',', ':'))}\n")
        return 0
    if command == "soundtrack":
        resolved_soundtrack = _resolve_cli_game_soundtrack(
            input_path=Path(args.input_path),
            game_library_root=Path(args.game_library_root),
        )
        if args.soundtrack_command == "digest":
            stdout.write(f"{resolved_soundtrack.source_sha256}\n")
        else:
            soundtrack_report = {"valid": True, **resolved_soundtrack.identity()}
            stdout.write(
                f"{json.dumps(soundtrack_report, sort_keys=True, separators=(',', ':'))}\n"
            )
        return 0
    if command == "dialogue-character":
        if args.dialogue_character_command == "sanitize":
            dialogue_character_result = sanitize_dialogue_character_spike(args.spike_path)
        elif args.dialogue_character_command == "package":
            dialogue_character_result = package_dialogue_character_spike(args.spike_path)
        elif args.dialogue_character_command == "review":
            dialogue_character_result = review_dialogue_character_bundle(
                args.bundle_path,
                review_path=args.review_path,
                acceptance_spec_path=args.acceptance_spec_path,
            )
        elif args.dialogue_character_command == "bind":
            dialogue_character_result = bind_dialogue_character_to_scrolling_manifest(
                args.bundle_path,
                manifest_path=args.manifest_path,
                npc_slot=args.npc_slot,
            )
        else:
            raise CliUsageError(
                f"unsupported dialogue-character command: {args.dialogue_character_command}"
            )
        stdout.write(
            f"{json.dumps(dialogue_character_result, sort_keys=True, separators=(',', ':'))}\n"
        )
        return 0
    if command == "map":
        resolved_map = _resolve_cli_game_map(
            input_path=Path(args.input_path),
            game_library_root=Path(args.game_library_root),
        )
        if args.map_command == "digest":
            stdout.write(f"{resolved_map.source_sha256}\n")
        else:
            map_report = {"valid": True, **resolved_map.identity()}
            stdout.write(f"{json.dumps(map_report, sort_keys=True, separators=(',', ':'))}\n")
        return 0
    if command == "map-book":
        resolved_map_book = _resolve_cli_game_map_book(
            input_path=Path(args.input_path),
            game_library_root=Path(args.game_library_root),
        )
        if args.map_book_command == "digest":
            stdout.write(f"{resolved_map_book.source_sha256}\n")
        else:
            map_book_report = {"valid": True, **resolved_map_book.identity()}
            stdout.write(f"{json.dumps(map_book_report, sort_keys=True, separators=(',', ':'))}\n")
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
    if args.command == "review":
        action_result = await run_recipe_action(
            args.recipe,
            "review",
            {
                "bundle_path": args.bundle_path,
                "review_path": args.review_path,
                "acceptance_spec_path": args.acceptance_spec_path,
                "usage": args.usage,
            },
        )
        stdout.write(f"{json.dumps(action_result, separators=(',', ':'))}\n")
        return 0
    config = load_config()
    if args.command == "generate":
        if args.character_library_root is not None:
            config = config.model_copy(
                update={"character_library_root": Path(args.character_library_root)}
            )
        if args.game_library_root is not None:
            config = config.model_copy(update={"game_library_root": Path(args.game_library_root)})
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
                force_stages=tuple(args.force_stages),
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


def _secure_cli_source_sha256(source: Path, *, label: str) -> str:
    """Digest one regular authored source without following any path symlink."""

    try:
        source_bytes = read_absolute_regular_file(source, label=label)
    except SecurePathError as error:
        raise ValueError(str(error)) from error
    return hashlib.sha256(source_bytes).hexdigest()


def _resolve_cli_game_contract(
    *, input_path: Path, game_library_root: Path
) -> ResolvedGameContract:
    """Digest an authored game in place and resolve it exactly as a run would.

    Shaped identically to `_resolve_cli_character_profile`, including computing the digest from
    the file rather than asking for one: this command exists so an author can find out whether
    what they wrote is valid, and requiring them to already know its digest to ask would make it
    useless for the case it is for.
    """

    root = game_library_root.absolute()
    source = input_path.absolute()
    try:
        relative = source.relative_to(root)
    except ValueError as error:
        raise ValueError("game contract input must be inside game library root") from error
    parts = relative.parts
    if len(parts) != 4 or parts[:2] != ("library", "games") or parts[3] != "game.toml":
        raise ValueError("game contract input must equal ROOT/library/games/<game_id>/game.toml")
    source_sha256 = _secure_cli_source_sha256(source, label="game contract input")
    return resolve_game_contract_binding(
        {
            "schema_version": 1,
            "kind": "game-contract-binding-v1",
            "ref": relative.as_posix(),
            "source_sha256": source_sha256,
        },
        game_library_root=root,
    )


def _resolve_cli_game_soundtrack(
    *, input_path: Path, game_library_root: Path
) -> ResolvedGameSoundtrack:
    """Digest one authored soundtrack in place and resolve its exact source bytes."""

    root = game_library_root.absolute()
    source = input_path.absolute()
    try:
        relative = source.relative_to(root)
    except ValueError as error:
        raise ValueError("game soundtrack input must be inside game library root") from error
    parts = relative.parts
    if len(parts) != 4 or parts[:2] != ("library", "games") or parts[3] != "soundtrack.toml":
        raise ValueError(
            "game soundtrack input must equal ROOT/library/games/<game_id>/soundtrack.toml"
        )
    source_sha256 = _secure_cli_source_sha256(source, label="game soundtrack input")
    return resolve_game_soundtrack_binding(
        {
            "schema_version": 1,
            "kind": "game-soundtrack-binding-v1",
            "ref": relative.as_posix(),
            "source_sha256": source_sha256,
        },
        game_library_root=root,
    )


def _resolve_cli_game_map(*, input_path: Path, game_library_root: Path) -> ResolvedGameMap:
    """Validate one fixed-path map and report its exact authored source digest."""

    return resolve_game_map_source(
        input_path,
        game_library_root=game_library_root,
    )


def _resolve_cli_game_map_book(*, input_path: Path, game_library_root: Path) -> ResolvedGameMapBook:
    """Digest an ordered map index and validate every map digest it locks."""

    root = game_library_root.absolute()
    source = input_path.absolute()
    try:
        relative = source.relative_to(root)
    except ValueError as error:
        raise ValueError("game map book input must be inside game library root") from error
    parts = relative.parts
    if (
        len(parts) != 5
        or parts[:2] != ("library", "games")
        or parts[3:]
        != (
            "maps",
            "index.toml",
        )
    ):
        raise ValueError(
            "game map book input must equal ROOT/library/games/<game_id>/maps/index.toml"
        )
    source_sha256 = _secure_cli_source_sha256(source, label="game map book input")
    return resolve_game_map_book_binding(
        {
            "schema_version": 1,
            "kind": "game-map-book-binding-v1",
            "ref": relative.as_posix(),
            "source_sha256": source_sha256,
        },
        game_library_root=root,
    )


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
    source_sha256 = _secure_cli_source_sha256(source, label="character profile input")
    return resolve_character_profile_binding(
        {
            "schema_version": 1,
            "kind": "character-profile-binding-v1",
            "ref": relative.as_posix(),
            "source_sha256": source_sha256,
        },
        character_library_root=root,
    )
