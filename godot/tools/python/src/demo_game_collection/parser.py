"""Private collection adapter for parser."""

from __future__ import annotations

import argparse
from typing import Never

from ember_hollow_pipeline.scopes import SCOPES as SURVIVAL_SCOPES
from stage_gen.application import (
    UsageError as CliUsageError,
)
from stage_gen.capabilities import (
    VIDEO_RESOLUTIONS,
)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise CliUsageError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="demo-games",
        description="repository game preparation and regression tooling",
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
        choices=("world", "content", "soundtrack", "world-review", "content-review", "integration"),
        help=(
            "execute one explicitly bounded live checkpoint; the review checkpoints run the "
            "semantic reviews over a world or content closure the cache already holds"
        ),
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
        help=(
            "an accepted run root integration may read after the cache; repeat in priority "
            "order. The cache is the authority: a root supplies what it lacks, never overrides"
        ),
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

    storefront_parser = commands.add_parser(
        "storefront",
        description="Draw one game's storefront face: icon, preview stills, banner, listing",
    )
    storefront_commands = storefront_parser.add_subparsers(dest="storefront_command", required=True)
    storefront_generate_parser = storefront_commands.add_parser(
        "generate",
        help="draw every declared surface and write the store listing beside them",
    )
    storefront_generate_parser.add_argument(
        "--input",
        required=True,
        dest="input_path",
        help="authored storefront package directory (storefront.toml plus references/)",
    )
    storefront_generate_parser.add_argument("--output", required=True, dest="output_path")
    storefront_generate_parser.add_argument("--cache-dir", dest="cache_dir")
    storefront_generate_parser.add_argument("--dry-run", action="store_true", dest="dry_run")
    storefront_generate_parser.add_argument("--invocation-id")
    storefront_generate_parser.add_argument(
        "--reroll",
        action="append",
        default=None,
        dest="rerolls",
        metavar="SURFACE_ID",
        help="redraw one surface; repeatable, everything else stays a cache hit",
    )
    storefront_generate_parser.add_argument(
        "--draw-ledger",
        dest="draw_ledger",
        help="carry a prior run's draw-ledger.json forward before applying --reroll",
    )
    storefront_generate_parser.add_argument(
        "--failure-node", dest="failure_node", help="inject one dry-run node failure"
    )

    oblique_survival_parser = commands.add_parser(
        "oblique-survival",
        description="Generate one authored elevated-oblique survival world, scope by scope",
    )
    oblique_survival_commands = oblique_survival_parser.add_subparsers(
        dest="oblique_survival_command", required=True
    )
    oblique_survival_generate_parser = oblique_survival_commands.add_parser(
        "generate",
        help="draw, gate and publish one scope of one survival package",
    )
    oblique_survival_generate_parser.add_argument(
        "--input",
        required=True,
        dest="input_path",
        help="authored survival package directory (survival.toml plus its siblings)",
    )
    oblique_survival_generate_parser.add_argument("--output", required=True, dest="output_path")
    oblique_survival_generate_parser.add_argument("--cache-dir", dest="cache_dir")
    oblique_survival_generate_parser.add_argument(
        "--scope",
        choices=SURVIVAL_SCOPES,
        default="full",
        help="which rung of the ladder to draw; a narrower scope shares every node it keeps",
    )
    oblique_survival_generate_parser.add_argument("--dry-run", action="store_true", dest="dry_run")
    oblique_survival_generate_parser.add_argument("--invocation-id")
    oblique_survival_generate_parser.add_argument(
        "--failure-node", dest="failure_node", help="inject one dry-run node failure"
    )
    oblique_survival_plan_parser = oblique_survival_commands.add_parser(
        "plan",
        help="print the exact plan for one scope, offline, and what a cache would restore",
    )
    oblique_survival_plan_parser.add_argument("--input", required=True, dest="input_path")
    oblique_survival_plan_parser.add_argument("--scope", choices=SURVIVAL_SCOPES, default="full")
    oblique_survival_plan_parser.add_argument(
        "--cache-dir",
        dest="cache_dir",
        help="report which provider operations this cache would restore, before any spend",
    )
    oblique_survival_import_parser = oblique_survival_commands.add_parser(
        "import-run",
        help="replay a prior run's artifacts into the cache, key by key, provider-free",
    )
    oblique_survival_import_parser.add_argument("--run", required=True, dest="run_dir")
    oblique_survival_import_parser.add_argument("--input", required=True, dest="input_path")
    oblique_survival_import_parser.add_argument("--cache-dir", required=True, dest="cache_dir")
    oblique_survival_import_parser.add_argument("--scope", choices=SURVIVAL_SCOPES, default="full")
    oblique_survival_finalize_parser = oblique_survival_commands.add_parser(
        "finalize",
        help="rebuild one run's manifest from what it has on disk, provider-free",
    )
    oblique_survival_finalize_parser.add_argument("--run", required=True, dest="run_dir")
    oblique_survival_finalize_parser.add_argument("--input", required=True, dest="input_path")

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
            package_action_parser.add_argument(
                "--cache-dir",
                dest="cache_dir",
                help=(
                    "price the plan against this execution cache: the report gains a "
                    "`cache` block naming every provider node that would bill"
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
            help="explicit root containing this game soundtrack input",
        )

    image_parser = commands.add_parser("generate-image")
    image_parser.add_argument("--output", required=True)
    image_parser.add_argument("--aspect-ratio", default="1:1")
    image_parser.add_argument("--reference", action="append", default=[])
    image_parser.add_argument("prompt", nargs="+")
    image_parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm a paid provider call when stdin is not a terminal",
    )

    background_parser = commands.add_parser("remove-background")
    background_parser.add_argument("--input", required=True, dest="input_path")
    background_parser.add_argument("--output", required=True)
    background_parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm a paid provider call when stdin is not a terminal",
    )

    music_parser = commands.add_parser("generate-music")
    music_parser.add_argument("--output", required=True)
    music_parser.add_argument("--format", choices=("mp3", "wav"), default="mp3")
    music_parser.add_argument("prompt", nargs="+")
    music_parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm a paid provider call when stdin is not a terminal",
    )

    sound_effect_parser = commands.add_parser("generate-sound-effect")
    sound_effect_parser.add_argument("--output", required=True)
    sound_effect_parser.add_argument("--duration", required=True, type=float, dest="duration")
    sound_effect_parser.add_argument(
        "--prompt-influence", type=float, default=None, dest="prompt_influence"
    )
    sound_effect_parser.add_argument("--loop", action="store_true")
    sound_effect_parser.add_argument("prompt", nargs="+")
    sound_effect_parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm a paid provider call when stdin is not a terminal",
    )

    # The audition pair. Video is the most expensive route this CLI reaches and it takes
    # no seed, so drawing a brief twice costs twice and answers differently. These two
    # exist so the drawing and the choosing happen outside a run, where the frames can be
    # looked at and only the chosen file is carried into a package.
    video_parser = commands.add_parser("generate-video")
    video_parser.add_argument("--output", required=True)
    video_parser.add_argument("--duration", required=True, type=float, dest="duration")
    video_parser.add_argument("--resolution", choices=VIDEO_RESOLUTIONS, default="720p")
    video_parser.add_argument("--aspect-ratio", default="16:9", dest="aspect_ratio")
    video_parser.add_argument("--reference", action="append", default=[])
    video_parser.add_argument("prompt", nargs="+")
    video_parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm a paid provider call when stdin is not a terminal",
    )

    inspect_parser = commands.add_parser("inspect-video")
    inspect_parser.add_argument("--input", required=True, dest="input_path")
    inspect_parser.add_argument("--output", required=True, help="where to write the contact sheet")
    inspect_parser.add_argument(
        "--duration",
        type=float,
        default=None,
        dest="duration",
        help="the length to hold the clip to; defaults to the length it actually is",
    )

    speech_parser = commands.add_parser("generate-speech")
    speech_parser.add_argument("--output", required=True)
    speech_parser.add_argument("--voice", required=True)
    speech_parser.add_argument("--stability", type=float, default=None)
    speech_parser.add_argument("--language", default=None, dest="language_code")
    speech_parser.add_argument("text", nargs="+")
    speech_parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm a paid provider call when stdin is not a terminal",
    )

    env_parser = commands.add_parser("import-env")
    env_parser.add_argument("--source", required=True)
    env_parser.add_argument("--destination", required=True)

    doctor_parser = commands.add_parser("doctor")
    doctor_parser.add_argument("--transparency", choices=("native", "ai", "chroma"))
    doctor_parser.add_argument("--json", action="store_true", dest="json_output")

    models_parser = commands.add_parser(
        "models",
        description="Inspect checked-in model routes and policy changes entirely offline",
    )
    models_commands = models_parser.add_subparsers(dest="models_command", required=True)
    models_commands.add_parser(
        "routes",
        help="print the active route catalog, policy selections, and recipe summaries",
    )
    models_diff_parser = models_commands.add_parser(
        "diff",
        help="compare a prior model-policy snapshot with the active application snapshot",
    )
    models_diff_parser.add_argument(
        "--base",
        required=True,
        dest="base_path",
        help="prior stage-gen-model-policy-snapshot-v1 JSON document",
    )
    models_diff_parser.add_argument(
        "--recipe",
        default=None,
        dest="recipe_id",
        help="limit graph, cache, count, and cost analysis to one canonical recipe id",
    )
    models_diff_parser.add_argument(
        "--image-provider",
        choices=("openai", "fal", "openrouter"),
        default=None,
        help="replan canonical recipe graphs under this explicit provider policy",
    )
    return parser
