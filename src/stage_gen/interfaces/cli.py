"""Argparse CLI preserving the public stage-gen command contract."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
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
    generate_sound_effect,
    remove_background,
)
from stage_gen.components._secure_fs import SecurePathError, read_absolute_regular_file
from stage_gen.components.case import ResolvedCase, read_case_catalog, resolve_case
from stage_gen.components.character_profile import (
    ResolvedCharacterProfile,
    resolve_character_profile_binding,
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
from stage_gen.components.scenario import (
    ResolvedScenario,
    read_scenario_catalog,
    read_scenario_declarations,
    resolve_scenario,
    script_digest,
)
from stage_gen.config import (
    ConfigError,
    StageGenConfig,
    TransparencyMode,
    load_config,
    parse_transparency_mode,
)
from stage_gen.orchestration.case_binding import BoundCase, bind_case
from stage_gen.orchestration.env_import import import_provider_env
from stage_gen.orchestration.game_package import resolve_prepared_package
from stage_gen.recipes.dialogue_scene.review import transition_dialogue_review
from stage_gen.recipes.dialogue_scene.scene_executor import DialogueSceneExecutor
from stage_gen.recipes.dialogue_scene.scene_view import build_dialogue_scene_view
from stage_gen.recipes.pointclick_room.room_executor import PointClickRoomExecutor
from stage_gen.recipes.pointclick_room.room_view import build_pointclick_room_view
from stage_gen.recipes.sideview_platformer.execution_view import build_execution_view
from stage_gen.recipes.sideview_platformer.package_executor import PreparedPackageExecutor
from stage_gen.recipes.sideview_platformer.view_annotations import (
    annotate_sideview_platformer_artifact,
)
from stage_gen.recipes.sideview_runner.runner_executor import SideviewRunnerExecutor
from stage_gen.recipes.sideview_runner.runner_view import build_sideview_runner_view
from stage_gen.recipes.universe import gallery_page as universe_gallery_page
from stage_gen.recipes.universe.universe_executor import UniverseExecutor
from stage_gen.recipes.universe.universe_view import build_universe_view


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
    generate_parser.add_argument(
        "--genre",
        help=(
            "which declared genre member to generate; optional when the package "
            "declares exactly one"
        ),
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

    universe_parser = commands.add_parser(
        "universe",
        description="Expand one authored universe package and draw its concept gallery",
    )
    universe_commands = universe_parser.add_subparsers(dest="universe_command", required=True)
    universe_semantic_parser = universe_commands.add_parser(
        "semantic",
        help="propose, plan, evaluate, review, and admit one universe as text",
    )
    universe_semantic_parser.add_argument(
        "--input",
        required=True,
        dest="input_path",
        help="authored universe package directory (universe.toml plus references/)",
    )
    universe_semantic_parser.add_argument("--output", required=True, dest="output_path")
    universe_semantic_parser.add_argument("--cache-dir", dest="cache_dir")
    universe_semantic_parser.add_argument("--dry-run", action="store_true", dest="dry_run")
    universe_semantic_parser.add_argument("--invocation-id")
    universe_semantic_parser.add_argument(
        "--failure-node", dest="failure_node", help="inject one dry-run node failure"
    )
    universe_gallery_parser = universe_commands.add_parser(
        "gallery",
        help="draw one concept image per admitted entity and close the package",
    )
    universe_gallery_parser.add_argument(
        "--input",
        required=True,
        dest="input_path",
        help="the same authored universe package the semantic run was planned from",
    )
    universe_gallery_parser.add_argument(
        "--semantic-run",
        required=True,
        dest="semantic_run",
        help="an admitted semantic run directory",
    )
    universe_gallery_parser.add_argument("--output", required=True, dest="output_path")
    universe_gallery_parser.add_argument("--cache-dir", dest="cache_dir")
    universe_gallery_parser.add_argument("--dry-run", action="store_true", dest="dry_run")
    universe_gallery_parser.add_argument("--invocation-id")
    universe_gallery_parser.add_argument(
        "--reroll",
        action="append",
        default=None,
        dest="rerolls",
        metavar="ENTITY_ID",
        help="redraw one entity's concept image; repeatable, everything else is a cache hit",
    )
    universe_gallery_parser.add_argument(
        "--sample-ledger",
        dest="sample_ledger",
        help="carry a prior run's sample-ledger.json forward before applying --reroll",
    )
    universe_gallery_parser.add_argument(
        "--failure-node", dest="failure_node", help="inject one dry-run node failure"
    )
    universe_page_parser = universe_commands.add_parser(
        "page",
        help="re-render the consumer page from a finished gallery run, provider-free",
    )
    universe_page_parser.add_argument("--run", required=True, dest="run_dir")

    scenario_parser = commands.add_parser(
        "scenario",
        description="Admit one authored scenario: parse the script, compile it, and prove it",
    )
    scenario_commands = scenario_parser.add_subparsers(dest="scenario_command", required=True)
    scenario_check_parser = scenario_commands.add_parser(
        "check",
        help="prove one authored scenario finishable, offline and before any spend",
    )
    scenario_check_parser.add_argument(
        "--input",
        required=True,
        dest="input_path",
        help="authored package directory holding scenarios/index.toml",
    )
    scenario_check_parser.add_argument(
        "--scenario",
        default=None,
        help="one scenario_id from the catalog; omit to check every scenario the game holds",
    )
    scenario_check_parser.add_argument(
        "--write-digest",
        action="store_true",
        dest="write_digest",
        help="rewrite script_sha256 in each scenario document to match its script",
    )

    case_parser = commands.add_parser(
        "case",
        description=(
            "Admit one authored case: prove the beat graph, then bind every beat to "
            "the scenario or room it plays"
        ),
    )
    case_commands = case_parser.add_subparsers(dest="case_command", required=True)
    case_check_parser = case_commands.add_parser(
        "check",
        help="prove one authored case playable end to end, offline and before any spend",
    )
    case_check_parser.add_argument(
        "--input",
        required=True,
        dest="input_path",
        help="authored package directory holding cases/index.toml",
    )
    case_check_parser.add_argument(
        "--case",
        default=None,
        dest="case_id",
        help="one case_id from the catalog; omit to check every case the game holds",
    )
    case_check_parser.add_argument(
        "--structure-only",
        action="store_true",
        dest="structure_only",
        help=(
            "prove the beat graph and the fact discipline without resolving the leaves; "
            "for authoring a case before every scenario and room it names exists"
        ),
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
        if action == "plan":
            package_action_parser.add_argument(
                "--genre",
                help=(
                    "which declared genre member to plan; optional when the package "
                    "declares exactly one"
                ),
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

    sound_effect_parser = commands.add_parser("generate-sound-effect")
    sound_effect_parser.add_argument("--output", required=True)
    sound_effect_parser.add_argument("--duration", required=True, type=float, dest="duration")
    sound_effect_parser.add_argument(
        "--prompt-influence", type=float, default=None, dest="prompt_influence"
    )
    sound_effect_parser.add_argument("--loop", action="store_true")
    sound_effect_parser.add_argument("prompt", nargs="+")

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
    if declared == "sideview-runner-execution-graph-v1":
        return build_sideview_runner_view(run_dir)
    if declared == "universe-execution-graph-v1":
        return build_universe_view(run_dir)
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
            "elevenlabs": bool(config.elevenlabs_api_key),
        },
        "models": {
            "nativeImage": config.openai_image_model,
            "image": config.image_model,
            "text": config.text_model,
            "music": config.music_model,
            "soundEffect": config.sound_effect_model,
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


def _resolve_cli_genre(declared: Sequence[str], requested: str | None) -> str:
    """Pick the genre member one run addresses.

    One run serves one genre member. With a single declared member the flag is
    noise, so it defaults; with several, defaulting would silently choose a
    genre, which is exactly the kind of decision a spend-adjacent command must
    not make on its own.
    """

    if requested is not None:
        if requested not in declared:
            raise ValueError(
                f"genre {requested!r} is not declared by this package; declared: "
                + ", ".join(declared)
            )
        return requested
    if len(declared) == 1:
        return declared[0]
    raise ValueError("--genre is required for a package declaring several: " + ", ".join(declared))


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
    if command == "universe" and args.universe_command == "page":
        # Re-rendering a finished gallery reads the run and nothing else: no
        # config, no provider, no event loop.
        page_path = universe_gallery_page.render(Path(args.run_dir))
        stdout.write(
            f"{json.dumps({'page': page_path}, sort_keys=True, separators=(',', ':'))}\n"
        )
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
        resolved_package = resolve_prepared_package(Path(args.input_path))
        if args.package_command == "digest":
            stdout.write(f"{resolved_package.closure_sha256}\n")
        elif args.package_command == "plan":
            declared_genres = [entry.genre for entry in resolved_package.game.genres]
            genre = _resolve_cli_genre(declared_genres, getattr(args, "genre", None))
            # The genre dispatch point: each genre member plans through its own
            # recipe executor.
            if genre == "runner":
                runner_plan = SideviewRunnerExecutor(load_config()).plan(Path(args.input_path))
                plan_report = {
                    "genre": genre,
                    "graph": runner_plan.graph.model_dump(mode="json"),
                    "projection": runner_plan.projection.model_dump(mode="json"),
                }
                stdout.write(f"{json.dumps(plan_report, sort_keys=True, separators=(',', ':'))}\n")
                return 0
            if genre != "platformer":
                raise ValueError(f"no recipe is registered for genre {genre!r}")
            plan = PreparedPackageExecutor(load_config()).plan(Path(args.input_path))
            plan_report = {
                "genre": genre,
                "graph": plan.graph.model_dump(mode="json"),
                "projection": plan.projection.model_dump(mode="json"),
            }
            stdout.write(f"{json.dumps(plan_report, sort_keys=True, separators=(',', ':'))}\n")
        else:
            package_report = {"valid": True, **resolved_package.identity()}
            stdout.write(f"{json.dumps(package_report, sort_keys=True, separators=(',', ':'))}\n")
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
    if command == "scenario":
        return _dispatch_scenario(args, stdout=stdout)
    if command == "case":
        return _dispatch_case(args, stdout=stdout)
    return asyncio.run(_dispatch_async(args, runtime=runtime, stdout=stdout))


def _dispatch_case(args: argparse.Namespace, *, stdout: TextIO) -> int:
    """Admission with no event loop, no config, and no provider - it never needs one."""

    root = Path(args.input_path)
    catalog = read_case_catalog(root)
    if args.case_id is not None and args.case_id not in catalog.case_ids:
        raise ValueError(f"case `{args.case_id}` is not in {root}/cases/index.toml")
    ids = catalog.case_ids if args.case_id is None else (args.case_id,)
    report = {
        "game_id": catalog.game_id,
        "cases": [
            _case_report(root, case_id, structure_only=bool(args.structure_only))
            for case_id in ids
        ],
    }
    stdout.write(f"{json.dumps(report, sort_keys=True, separators=(',', ':'))}\n")
    return 0


def _case_report(root: Path, case_id: str, *, structure_only: bool) -> dict[str, object]:
    if structure_only:
        return _case_structure_report(resolve_case(root, case_id))
    return _bound_case_report(bind_case(root, case_id))


def _case_structure_report(resolved: ResolvedCase) -> dict[str, object]:
    admission = resolved.admission
    return {
        "admitted": admission.admitted,
        "case_id": admission.case_id,
        "beats": admission.beat_count,
        "bound": False,
        "case_sha256": resolved.case_sha256,
        "reachable_beats": list(admission.reachable_beats),
        "terminals": {
            witness.beat_id: list(witness.path) for witness in admission.witnesses
        },
        "facts": {
            entry.fact_id: {
                "establishment": entry.establishment,
                "exported_by": list(entry.exported_by),
                "read_by": list(entry.read_by),
            }
            for entry in admission.facts
        },
    }


def _bound_case_report(bound: BoundCase) -> dict[str, object]:
    report = _case_structure_report(bound.resolved)
    report["bound"] = True
    report["leaves"] = {
        beat.beat_id: {
            "kind": beat.kind,
            "member": beat.member,
            "outcomes": list(beat.outcomes),
            "exports": list(beat.exports),
            "imports": list(beat.imports),
            "reachable_states": beat.reachable_states,
        }
        for beat in bound.beats
    }
    return report


def _dispatch_scenario(args: argparse.Namespace, *, stdout: TextIO) -> int:
    """Admission with no event loop, no config, and no provider - it never needs one."""

    root = Path(args.input_path)
    catalog = read_scenario_catalog(root)
    ids = catalog.scenario_ids if args.scenario is None else (args.scenario,)
    if args.scenario is not None and args.scenario not in catalog.scenario_ids:
        raise ValueError(f"scenario `{args.scenario}` is not in {root}/scenarios/index.toml")
    if args.write_digest:
        return _write_scenario_digests(root, ids, stdout=stdout)
    report = {
        "game_id": catalog.game_id,
        "scenarios": [_scenario_report(resolve_scenario(root, entry)) for entry in ids],
    }
    stdout.write(f"{json.dumps(report, sort_keys=True, separators=(',', ':'))}\n")
    return 0


def _scenario_report(resolved: ResolvedScenario) -> dict[str, object]:
    return {
        "admitted": resolved.admission.admitted,
        "scenario_id": resolved.declarations.scenario_id,
        "blocks": len(resolved.program.blocks),
        "reachable_states": resolved.admission.reachable_states,
        "program_sha256": resolved.program_sha256,
        "endings": {
            witness.outcome_id: list(witness.path) for witness in resolved.admission.witnesses
        },
    }


def _write_scenario_digests(root: Path, scenario_ids: tuple[str, ...], *, stdout: TextIO) -> int:
    """Repair `script_sha256` after a prose edit.

    Every save of the script invalidates the hand-copied digest, so leaving the
    author to run `sha256sum` and paste the result is a needless way to make the
    contract feel hostile. The rewrite is a single line in place: nothing else in
    the document is touched, and the scenario is still proven afterwards.
    """

    written: dict[str, str] = {}
    for scenario_id in scenario_ids:
        declarations = read_scenario_declarations(root, scenario_id)
        actual = script_digest(root, declarations)
        document = root / f"scenarios/{scenario_id}.toml"
        text = document.read_text(encoding="utf-8")
        updated = re.sub(
            r'^script_sha256 = "[0-9a-f]{64}"$',
            f'script_sha256 = "{actual}"',
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if updated == text and declarations.script_sha256 != actual:
            raise ValueError(f"could not locate script_sha256 in {document}")
        document.write_text(updated, encoding="utf-8")
        resolve_scenario(root, scenario_id)
        written[scenario_id] = actual
    stdout.write(f"{json.dumps(written, sort_keys=True, separators=(',', ':'))}\n")
    return 0


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


async def _dispatch_universe(
    args: argparse.Namespace,
    *,
    config: StageGenConfig,
    stdout: TextIO,
) -> int:
    executor = UniverseExecutor(config)
    input_path = Path(args.input_path)
    output_path = Path(args.output_path)
    cache_dir = Path(args.cache_dir) if args.cache_dir else output_path.parent / ".universe-cache"
    phase = str(args.universe_command)
    invocation_id = args.invocation_id or f"universe-{phase}-{uuid.uuid4().hex}"
    if not args.dry_run and args.failure_node is not None:
        raise ValueError("--failure-node is available only with --dry-run")
    if phase == "semantic":
        if args.dry_run:
            run = await executor.dry_run_semantic(
                input_path,
                run_dir=output_path,
                cache_dir=cache_dir,
                invocation_id=invocation_id,
                failure_node_id=args.failure_node,
            )
        else:
            run = await executor.run_semantic(
                input_path,
                run_dir=output_path,
                cache_dir=cache_dir,
                invocation_id=invocation_id,
            )
    else:
        semantic_run = Path(args.semantic_run)
        rerolls = tuple(args.rerolls or ())
        sample_ledger = Path(args.sample_ledger) if args.sample_ledger else None
        if args.dry_run:
            run = await executor.dry_run_gallery(
                input_path,
                semantic_run=semantic_run,
                run_dir=output_path,
                cache_dir=cache_dir,
                invocation_id=invocation_id,
                rerolls=rerolls,
                sample_ledger=sample_ledger,
                failure_node_id=args.failure_node,
            )
        else:
            run = await executor.run_gallery(
                input_path,
                semantic_run=semantic_run,
                run_dir=output_path,
                cache_dir=cache_dir,
                invocation_id=invocation_id,
                rerolls=rerolls,
                sample_ledger=sample_ledger,
            )
    report: dict[str, object] = {
        "ok": run.summary.ok,
        "recipe": "universe",
        "phase": phase,
        "universe_id": run.plan.resolved.universe_id,
        "run_dir": str(output_path),
        "graph_sha256": run.plan.graph.graph_sha256,
        "topology_sha256": run.plan.graph.topology_sha256,
        "node_count": len(run.plan.graph.nodes),
        "provider_operation_counts": run.summary.provider_operation_counts,
        "duration_ms": run.summary.duration_ms,
    }
    if run.manifest is not None:
        report["counts"] = run.manifest["counts"]
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
    if args.command == "universe":
        return await _dispatch_universe(args, config=config, stdout=stdout)
    if args.command == "generate":
        if args.output_path is None:
            raise ValueError("generate requires --output")
        generate_package = resolve_prepared_package(Path(args.input_path))
        declared_genres = [entry.genre for entry in generate_package.game.genres]
        genre = _resolve_cli_genre(declared_genres, getattr(args, "genre", None))
        output_path = Path(args.output_path)
        # The genre dispatch point: each genre member executes through its own
        # recipe executor. The runner runs single-shot; the platformer keeps its
        # bounded checkpoints below.
        if genre == "runner":
            runner_cache = (
                Path(args.cache_dir)
                if args.cache_dir is not None
                else output_path.parent / ".stage-gen-cache"
            )
            if args.checkpoint is not None:
                raise ValueError(
                    "the runner genre runs single-shot; --checkpoint is platformer-only"
                )
            if args.artifact_roots or args.replace_output:
                raise ValueError(
                    "--artifact-root/--replace-output are platformer integration flags"
                )
            runner_executor = SideviewRunnerExecutor(config)
            if args.dry_run:
                runner_invocation = args.invocation_id or f"dry-run-{uuid.uuid4().hex}"
                runner_result = await runner_executor.dry_run(
                    Path(args.input_path),
                    run_dir=output_path,
                    cache_dir=runner_cache,
                    invocation_id=runner_invocation,
                    failure_node_id=args.failure_node,
                )
            else:
                if args.failure_node is not None:
                    raise ValueError("--failure-node is available only with --dry-run")
                runner_invocation = args.invocation_id or f"runner-{uuid.uuid4().hex}"
                runner_result = await runner_executor.run(
                    Path(args.input_path),
                    run_dir=output_path,
                    cache_dir=runner_cache,
                    invocation_id=runner_invocation,
                )
            runner_report = {
                "ok": runner_result.summary.ok,
                "genre": genre,
                "invocation_id": runner_invocation,
                "graph_sha256": runner_result.plan.graph.graph_sha256,
                "topology_sha256": runner_result.plan.graph.topology_sha256,
                "node_count": len(runner_result.plan.graph.nodes),
                "provider_operation_counts": runner_result.summary.provider_operation_counts,
                "duration_ms": runner_result.summary.duration_ms,
                "run_dir": str(output_path),
            }
            stdout.write(f"{json.dumps(runner_report, sort_keys=True, separators=(',', ':'))}\n")
            return 0 if runner_result.summary.ok else 1
        if genre != "platformer":
            raise ValueError(f"no recipe is registered for genre {genre!r}")
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
                    "genre": genre,
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
                "genre": genre,
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
            "genre": genre,
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
    elif args.command == "generate-sound-effect":
        result = await generate_sound_effect(
            prompt=" ".join(args.prompt).strip(),
            output_path=args.output,
            duration_seconds=args.duration,
            prompt_influence=args.prompt_influence,
            loop=args.loop,
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
