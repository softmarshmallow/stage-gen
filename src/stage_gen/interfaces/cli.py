"""Argparse CLI preserving the public stage-gen command contract."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import tomllib
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Never, TextIO, cast

from gnode import RunView, write_run_view
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
from stage_gen.components.game_soundtrack import (
    ResolvedGameSoundtrack,
    resolve_game_soundtrack_binding,
)
from stage_gen.components.platformer_map import (
    ResolvedGameMap,
    ResolvedGameMapBook,
    resolve_game_map_book_binding,
    resolve_game_map_source,
)
from stage_gen.config import (
    ConfigError,
    StageGenConfig,
    TransparencyMode,
    load_config,
    parse_transparency_mode,
)
from stage_gen.orchestration.env_import import import_provider_env
from stage_gen.orchestration.execution_view import build_execution_view
from stage_gen.orchestration.game_package import resolve_game_package
from stage_gen.recipes.dialogue_scene.character_bundle import (
    package_dialogue_character_spike,
    review_dialogue_character_bundle,
    sanitize_dialogue_character_spike,
)
from stage_gen.recipes.dialogue_scene.review import transition_dialogue_review
from stage_gen.recipes.dialogue_scene.scene_executor import DialogueSceneExecutor
from stage_gen.recipes.dialogue_scene.scene_view import build_dialogue_scene_view
from stage_gen.recipes.pointclick_room.room_executor import PointClickRoomExecutor
from stage_gen.recipes.pointclick_room.room_view import build_pointclick_room_view
from stage_gen.recipes.sideview_platformer.package_executor import PreparedPackageExecutor
from stage_gen.recipes.sideview_platformer.view_annotations import (
    annotate_sideview_platformer_artifact,
)


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
            "Prepared game generation requires a directory or ZIP containing game.toml."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    generate_parser = commands.add_parser("generate")
    generate_parser.add_argument(
        "--input",
        required=True,
        dest="input_path",
        help="prepared game directory or ZIP",
    )
    generate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="execute deterministic fake operations without provider access",
    )
    generate_parser.add_argument(
        "--output",
        dest="output_path",
        help="new immutable execution output directory",
    )
    generate_parser.add_argument(
        "--cache-dir",
        dest="cache_dir",
        help="content-and-lineage validated execution cache directory",
    )
    generate_parser.add_argument(
        "--checkpoint",
        choices=("world", "content", "integration"),
        help="execute one explicitly bounded live checkpoint",
    )
    generate_parser.add_argument(
        "--replace-output",
        action="store_true",
        help=(
            "permit integration to destroy an existing output directory whose content differs; "
            "republishing identical content never needs this"
        ),
    )
    generate_parser.add_argument(
        "--artifact-root",
        action="append",
        default=[],
        dest="artifact_roots",
        help="accepted run root searched for integration artifacts; repeat in priority order",
    )
    generate_parser.add_argument("--invocation-id")
    generate_parser.add_argument(
        "--failure-node",
        help="inject one deterministic node failure during a dry run",
    )

    dialogue_parser = commands.add_parser(
        "dialogue-scene",
        description=(
            "Plan, execute, and review one non-explicit visual-novel dialogue-scene bundle"
        ),
    )
    dialogue_commands = dialogue_parser.add_subparsers(dest="dialogue_command", required=True)
    dialogue_generate_parser = dialogue_commands.add_parser(
        "generate",
        help="execute one authored scene package as an asset graph",
    )
    dialogue_generate_parser.add_argument(
        "--input",
        required=True,
        dest="input_path",
        metavar="PACKAGE",
        help="authored scene package directory containing scene.toml",
    )
    dialogue_generate_parser.add_argument(
        "--output",
        required=True,
        dest="output_path",
        help="new immutable execution output directory",
    )
    dialogue_generate_parser.add_argument(
        "--cache-dir",
        dest="cache_dir",
        help="content-and-lineage validated execution cache directory",
    )
    dialogue_generate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="execute deterministic fake operations without provider access",
    )
    dialogue_generate_parser.add_argument("--invocation-id")
    dialogue_generate_parser.add_argument(
        "--failure-node",
        help="inject one deterministic node failure during a dry run",
    )
    dialogue_review_parser = dialogue_commands.add_parser(
        "review",
        help="apply a digest-bound independent review to one dialogue bundle",
    )
    dialogue_review_parser.add_argument("--bundle", required=True, dest="bundle_path")
    dialogue_review_parser.add_argument("--review", required=True, dest="review_path")
    dialogue_review_parser.add_argument(
        "--acceptance-spec", required=True, dest="acceptance_spec_path"
    )
    dialogue_review_parser.add_argument("--usage", required=True, choices=("local-demo",))

    room_parser = commands.add_parser(
        "pointclick-room",
        description="Plan and execute one authored point-and-click puzzle room",
    )
    room_commands = room_parser.add_subparsers(dest="room_command", required=True)
    room_generate_parser = room_commands.add_parser(
        "generate",
        help="execute one authored room document as an asset graph",
    )
    room_generate_parser.add_argument(
        "--input",
        required=True,
        dest="input_path",
        help="authored pointclick-room package directory (room.toml plus references/)",
    )
    room_generate_parser.add_argument("--output", required=True, dest="output_path")
    room_generate_parser.add_argument("--cache-dir", dest="cache_dir")
    room_generate_parser.add_argument("--dry-run", action="store_true", dest="dry_run")
    room_generate_parser.add_argument("--invocation-id")
    room_generate_parser.add_argument(
        "--failure-node", dest="failure_node", help="inject one dry-run node failure"
    )

    dialogue_character_parser = commands.add_parser(
        "dialogue-character",
        description="Sanitize, package, and review a four-state dialogue character bundle",
    )
    dialogue_character_commands = dialogue_character_parser.add_subparsers(
        dest="dialogue_character_command", required=True
    )
    sanitize_parser = dialogue_character_commands.add_parser(
        "sanitize", help="sanitize one pending local character spike in place"
    )
    sanitize_parser.add_argument("--spike", required=True, dest="spike_path")
    character_package_parser = dialogue_character_commands.add_parser(
        "package", help="package one validated spike at its canonical run path"
    )
    character_package_parser.add_argument("--spike", required=True, dest="spike_path")
    character_review_parser = dialogue_character_commands.add_parser(
        "review", help="apply an independent review to one pending character bundle"
    )
    character_review_parser.add_argument("--bundle", required=True, dest="bundle_path")
    character_review_parser.add_argument("--review", required=True, dest="review_path")
    character_review_parser.add_argument(
        "--acceptance-spec", required=True, dest="acceptance_spec_path"
    )

    export_view_parser = commands.add_parser(
        "export-view",
        description=(
            "Join one run directory's execution plan and trace into a derived "
            "execution-view.json for read-only rendering"
        ),
    )
    export_view_parser.add_argument(
        "--run",
        required=True,
        dest="run_dir",
        metavar="RUN_DIR",
        help="existing execution output directory holding execution-plan.json",
    )
    export_view_parser.add_argument(
        "--output",
        dest="output_path",
        help="view document destination (default: RUN_DIR/execution-view.json)",
    )

    package_parser = commands.add_parser(
        "package",
        description="Validate and inspect one prepared game directory or ZIP",
    )
    package_commands = package_parser.add_subparsers(dest="package_command", required=True)
    for action in ("validate", "digest", "plan"):
        package_action_parser = package_commands.add_parser(action)
        package_action_parser.add_argument(
            "--input",
            required=True,
            dest="input_path",
            help="prepared package directory or ZIP",
        )

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
            "--package-root",
            required=True,
            help="authored package directory the profile is a member of",
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


def _build_run_view_for(run_dir: Path) -> RunView:
    """Pick the view document by the kind the run's own plan declares.

    Two recipes emit two graph kinds, and hard-drop versioning means neither type may
    accept the other's document. Reading the declared kind first keeps the refusal a
    clear one instead of a validation error about the wrong contract.
    """

    plan_path = run_dir / "execution-plan.json"
    if not plan_path.is_file():
        raise ValueError(f"run directory has no execution-plan.json: {run_dir.name}")
    declared = json.loads(plan_path.read_text(encoding="utf-8")).get("kind")
    if declared == "dialogue-scene-execution-graph-v3":
        return build_dialogue_scene_view(run_dir)
    if declared == "pointclick-room-execution-graph-v1":
        return build_pointclick_room_view(run_dir)
    if declared == "sideview-platformer-execution-graph-v1":
        return build_execution_view(
            run_dir,
            annotators={"sideview-platformer": annotate_sideview_platformer_artifact},
        )
    raise ValueError(
        f"unsupported execution plan kind: {declared!r}; re-export this run with a current "
        "stage-gen"
    )


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
    if command == "character-profile":
        resolved = _resolve_cli_character_profile(
            input_path=Path(args.input_path),
            package_root=Path(args.package_root),
        )
        if args.character_profile_command == "digest":
            stdout.write(f"{resolved.source_sha256}\n")
        else:
            report = {"valid": True, **resolved.identity()}
            stdout.write(f"{json.dumps(report, sort_keys=True, separators=(',', ':'))}\n")
        return 0
    if command == "export-view":
        run_dir = Path(args.run_dir)
        view = _build_run_view_for(run_dir)
        view_path = Path(args.output_path) if args.output_path else run_dir / "execution-view.json"
        write_run_view(view_path, view)
        view_report = {
            "gaps": len(view.gaps),
            "nodes": len(view.nodes),
            "run_state": view.run_state,
            "output": str(view_path),
            "states": view.state_counts,
        }
        stdout.write(f"{json.dumps(view_report, sort_keys=True, separators=(',', ':'))}\n")
        return 0
    if command == "package":
        resolved_package = resolve_game_package(Path(args.input_path))
        if args.package_command == "digest":
            stdout.write(f"{resolved_package.closure_sha256}\n")
        elif args.package_command == "plan":
            plan = PreparedPackageExecutor(load_config()).plan(Path(args.input_path))
            plan_report = {
                "graph": plan.graph.model_dump(mode="json"),
                "projection": plan.projection.model_dump(mode="json"),
            }
            stdout.write(f"{json.dumps(plan_report, sort_keys=True, separators=(',', ':'))}\n")
        else:
            package_report = {"valid": True, **resolved_package.identity()}
            stdout.write(f"{json.dumps(package_report, sort_keys=True, separators=(',', ':'))}\n")
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
            character_result = sanitize_dialogue_character_spike(args.spike_path)
        elif args.dialogue_character_command == "package":
            character_result = package_dialogue_character_spike(args.spike_path)
        else:
            character_result = review_dialogue_character_bundle(
                args.bundle_path,
                review_path=args.review_path,
                acceptance_spec_path=args.acceptance_spec_path,
            )
        stdout.write(f"{json.dumps(character_result, sort_keys=True, separators=(',', ':'))}\n")
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
    if command == "import-env":
        imported = import_provider_env(args.source, args.destination)
        stdout.write(f"{json.dumps(imported, separators=(',', ':'))}\n")
        return 0
    return asyncio.run(_dispatch_async(args, runtime=runtime, stdout=stdout))


async def _dispatch_dialogue_scene(
    args: argparse.Namespace,
    *,
    config: StageGenConfig,
    stdout: TextIO,
) -> int:
    if args.dialogue_command == "review":
        review_result = await transition_dialogue_review(
            {
                "bundle_path": args.bundle_path,
                "review_path": args.review_path,
                "acceptance_spec_path": args.acceptance_spec_path,
                "usage": args.usage,
            }
        )
        stdout.write(f"{json.dumps(review_result, separators=(',', ':'))}\n")
        return 0
    executor = DialogueSceneExecutor(config)
    output_path = Path(args.output_path)
    cache_dir = Path(args.cache_dir) if args.cache_dir else output_path.parent / ".dialogue-cache"
    invocation_id = args.invocation_id or f"dialogue-{uuid.uuid4().hex}"
    if args.dry_run:
        run = await executor.dry_run(
            Path(args.input_path),
            run_dir=output_path,
            cache_dir=cache_dir,
            invocation_id=invocation_id,
            failure_node_id=args.failure_node,
        )
    else:
        if args.failure_node is not None:
            raise ValueError("--failure-node is available only with --dry-run")
        run = await executor.run(
            Path(args.input_path),
            run_dir=output_path,
            cache_dir=cache_dir,
            invocation_id=invocation_id,
        )
    report = {
        "ok": run.summary.ok,
        "recipe": "dialogue-scene",
        "scene_id": run.plan.scene.scene_id,
        "run_dir": str(output_path),
        "graph_sha256": run.plan.graph.graph_sha256,
        "topology_sha256": run.plan.graph.topology_sha256,
        "node_count": len(run.plan.graph.nodes),
        "provider_operation_counts": run.summary.provider_operation_counts,
        "duration_ms": run.summary.duration_ms,
    }
    stdout.write(f"{json.dumps(report, sort_keys=True, separators=(',', ':'))}\n")
    return 0 if run.summary.ok else 1


async def _dispatch_pointclick_room(
    args: argparse.Namespace,
    *,
    config: StageGenConfig,
    stdout: TextIO,
) -> int:
    executor = PointClickRoomExecutor(config)
    output_path = Path(args.output_path)
    cache_dir = Path(args.cache_dir) if args.cache_dir else output_path.parent / ".pointclick-cache"
    invocation_id = args.invocation_id or f"room-{uuid.uuid4().hex}"
    if args.dry_run:
        run = await executor.dry_run(
            Path(args.input_path),
            run_dir=output_path,
            cache_dir=cache_dir,
            invocation_id=invocation_id,
            failure_node_id=args.failure_node,
        )
    else:
        if args.failure_node is not None:
            raise ValueError("--failure-node is available only with --dry-run")
        run = await executor.run(
            Path(args.input_path),
            run_dir=output_path,
            cache_dir=cache_dir,
            invocation_id=invocation_id,
        )
    report = {
        "ok": run.summary.ok,
        "recipe": "pointclick-room",
        "room_id": run.plan.resolved.room.room_id,
        "run_dir": str(output_path),
        "graph_sha256": run.plan.graph.graph_sha256,
        "topology_sha256": run.plan.graph.topology_sha256,
        "node_count": len(run.plan.graph.nodes),
        "provider_operation_counts": run.summary.provider_operation_counts,
        "duration_ms": run.summary.duration_ms,
    }
    stdout.write(f"{json.dumps(report, sort_keys=True, separators=(',', ':'))}\n")
    return 0 if run.summary.ok else 1


async def _dispatch_async(
    args: argparse.Namespace,
    *,
    runtime: HeadlessRuntime | None,
    stdout: TextIO,
) -> int:
    config = load_config()
    if args.command == "dialogue-scene":
        return await _dispatch_dialogue_scene(args, config=config, stdout=stdout)
    if args.command == "pointclick-room":
        return await _dispatch_pointclick_room(args, config=config, stdout=stdout)
    if args.command == "generate":
        if args.output_path is None:
            raise ValueError("generate requires --output")
        output_path = Path(args.output_path)
        cache_dir = (
            Path(args.cache_dir)
            if args.cache_dir is not None
            else output_path.parent / ".stage-gen-cache"
        )
        if not args.dry_run:
            if args.checkpoint not in {"world", "content", "integration"}:
                raise ValueError(
                    "prepared-package execution requires --checkpoint "
                    "world, content, or integration"
                )
            if args.failure_node is not None:
                raise ValueError("--failure-node is available only with --dry-run")
            checkpoint = cast("str", args.checkpoint)
            invocation_id = args.invocation_id or f"{checkpoint}-{uuid.uuid4().hex}"
            prepared_executor = PreparedPackageExecutor(config)
            if checkpoint == "integration":
                if not args.artifact_roots:
                    raise ValueError("integration requires at least one --artifact-root")
                integration_result = prepared_executor.run_integration(
                    Path(args.input_path),
                    run_dir=output_path,
                    artifact_roots=tuple(Path(path) for path in args.artifact_roots),
                    replace_output=bool(args.replace_output),
                )
                integration_report: dict[str, object] = {
                    "ok": True,
                    "checkpoint": checkpoint,
                    "invocation_id": invocation_id,
                    "graph_sha256": integration_result.plan.graph.graph_sha256,
                    "topology_sha256": integration_result.plan.graph.topology_sha256,
                    "artifact_count": integration_result.result.artifact_count,
                    "package_sha256": integration_result.plan.package.package_sha256,
                    "provider_operation_counts": {},
                    "run_dir": str(output_path),
                    "disposition": integration_result.result.disposition,
                    "replaced_manifest_sha256": (
                        integration_result.result.replaced_manifest_sha256
                    ),
                }
                stdout.write(
                    f"{json.dumps(integration_report, sort_keys=True, separators=(',', ':'))}\n"
                )
                return 0
            if args.artifact_roots:
                raise ValueError("--artifact-root is available only with --checkpoint integration")
            if args.replace_output:
                raise ValueError("--replace-output is available only with --checkpoint integration")
            if checkpoint == "world":
                live_result = await prepared_executor.run_world(
                    Path(args.input_path),
                    run_dir=output_path,
                    cache_dir=cache_dir,
                    invocation_id=invocation_id,
                )
                live_summary = live_result.summary
                live_graph = live_result.plan.graph
            else:
                content_result = await prepared_executor.run_content(
                    Path(args.input_path),
                    run_dir=output_path,
                    cache_dir=cache_dir,
                    invocation_id=invocation_id,
                )
                live_summary = content_result.summary
                live_graph = content_result.plan.graph
            report = {
                "ok": live_summary.ok,
                "checkpoint": checkpoint,
                "invocation_id": invocation_id,
                "graph_sha256": live_graph.graph_sha256,
                "topology_sha256": live_graph.topology_sha256,
                "executed_node_count": len(live_summary.nodes),
                "provider_operation_counts": live_summary.provider_operation_counts,
                "duration_ms": live_summary.duration_ms,
                "run_dir": str(output_path),
            }
            stdout.write(f"{json.dumps(report, sort_keys=True, separators=(',', ':'))}\n")
            return 0 if live_summary.ok else 1
        if args.replace_output:
            raise ValueError("--replace-output is available only with --checkpoint integration")
        invocation_id = args.invocation_id or f"dry-run-{uuid.uuid4().hex}"
        dry_run_result = await PreparedPackageExecutor(config).dry_run(
            Path(args.input_path),
            run_dir=output_path,
            cache_dir=cache_dir,
            invocation_id=invocation_id,
            failure_node_id=args.failure_node,
        )
        dry_run_report = {
            "ok": dry_run_result.summary.ok,
            "invocation_id": invocation_id,
            "graph_sha256": dry_run_result.plan.graph.graph_sha256,
            "topology_sha256": dry_run_result.plan.graph.topology_sha256,
            "node_count": len(dry_run_result.plan.graph.nodes),
            "provider_operation_counts": dry_run_result.summary.provider_operation_counts,
            "duration_ms": dry_run_result.summary.duration_ms,
            "run_dir": str(output_path),
        }
        stdout.write(f"{json.dumps(dry_run_report, sort_keys=True, separators=(',', ':'))}\n")
        return 0 if dry_run_result.summary.ok else 1
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
    *, input_path: Path, package_root: Path
) -> ResolvedCharacterProfile:
    root = package_root.absolute()
    source = input_path.absolute()
    try:
        relative = source.relative_to(root)
    except ValueError as error:
        raise ValueError("character profile input must be inside the package root") from error
    if relative.suffix.lower() != ".toml":
        raise ValueError("character profile input must be a TOML member of the package")
    source_sha256 = _secure_cli_source_sha256(source, label="character profile input")
    return resolve_character_profile_binding(
        {
            "schema_version": 1,
            "kind": "character-profile-binding-v1",
            "ref": relative.as_posix(),
            "source_sha256": source_sha256,
        },
        package_root=root,
    )
