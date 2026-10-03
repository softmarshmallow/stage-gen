"""Private collection adapter for parser."""

from __future__ import annotations

import argparse
from typing import Never

from stage_gen.application import (
    UsageError as CliUsageError,
)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise CliUsageError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="demo-games",
        description="repository game preparation and regression tooling",
        epilog=(
            "Every game's assets build with gnode from the game's own folder: "
            "cd godot/games/<game> && gnode plan pipeline/workflow.py:build ..."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    dialogue_parser = commands.add_parser(
        "dialogue-scene",
        description=(
            "Review one non-explicit visual-novel dialogue-scene bundle; the scene builds "
            "with gnode from its game folder (pipeline/workflow.py:scene)"
        ),
    )
    dialogue_commands = dialogue_parser.add_subparsers(dest="dialogue_command", required=True)
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

    case_bundle_parser = case_commands.add_parser(
        "bundle",
        help="publish one proven case as the `case.json` a consumer plays",
    )
    case_bundle_parser.add_argument(
        "--input",
        required=True,
        dest="input_path",
        help="authored package directory holding cases/index.toml",
    )
    case_bundle_parser.add_argument(
        "--case",
        required=True,
        dest="case_id",
        help="one case_id from the catalog",
    )
    case_bundle_parser.add_argument(
        "--beat-run",
        action="append",
        default=[],
        dest="beat_runs",
        metavar="BEAT_ID=RUN_TAG",
        help=(
            "which run each beat is played from; repeat once per beat. A run tag only "
            "exists after its leaf has been generated, so this cannot be authored"
        ),
    )
    case_bundle_parser.add_argument("--output", required=True, dest="output_path")
    case_bundle_parser.add_argument(
        "--runs-dir",
        dest="runs_dir",
        help="directory holding the named runs (default: the output's parent)",
    )

    example_parser = commands.add_parser(
        "example",
        description=(
            "Publish the examples a game made into the local example store, through the "
            "product's public example contract"
        ),
    )
    example_commands = example_parser.add_subparsers(dest="example_command", required=True)
    example_export_parser = example_commands.add_parser(
        "export",
        help=(
            "check each pinned example against its runs, then write its page and entry "
            "beside its frozen export"
        ),
    )
    example_export_parser.add_argument("game", choices=("bellweather",))
    example_export_parser.add_argument(
        "--store",
        dest="store",
        metavar="DIR",
        help="the example store (default: out/examples in the checkout)",
    )
    example_export_parser.add_argument(
        "--from-frozen",
        action="store_true",
        dest="from_frozen",
        help=(
            "trust the frozen export in the store without making each example again from "
            "its runs, for when a source run has moved on"
        ),
    )

    package_parser = commands.add_parser(
        "package",
        description="Validate and inspect one prepared game directory or ZIP",
    )
    package_commands = package_parser.add_subparsers(dest="package_command", required=True)
    for action in ("validate", "digest"):
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
            help="explicit root containing this game soundtrack input",
        )

    return parser
