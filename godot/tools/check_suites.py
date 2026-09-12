"""Explicit execution contracts for maintained Godot checks, without game policy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Level = Literal["offline", "media", "rendered"]
Adapter = Literal["native", "script", "application", "asset_consumer", "python", "pytest"]
ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Owner:
    name: str
    directory: str
    convention: Literal["native", "checks", "explicit"]

    @property
    def project(self) -> Path:
        return ROOT / self.directory


@dataclass(frozen=True)
class Suite:
    owner: str
    name: str
    adapter: Adapter
    source: str
    level: Level = "offline"
    arguments: tuple[str, ...] = ()
    success: str = r"(?m)^PASS(?: |:)"
    prerequisite: str = ""
    members: tuple[str, ...] = ()


OWNERS = (
    Owner("demo_support", "games/_shared/runtime", "native"),
    Owner("bellweather", "games/bellweather", "native"),
    Owner("iron_petal_unit", "games/iron_petal_unit", "native"),
    Owner("ember_hollow", "games/ember_hollow", "native"),
    Owner("the_grain", "games/the_grain", "native"),
    Owner("afterlight", "games/afterlight", "checks"),
    Owner("command_link", "games/command_link", "checks"),
    Owner("game_presentation", "packages/game_presentation", "checks"),
    Owner("scenario_runtime", "packages/scenario_runtime", "explicit"),
    Owner("content_io", "packages/content_io", "explicit"),
    Owner("sideview_rendering", "packages/sideview_rendering", "explicit"),
    Owner("vn", "templates/vn", "checks"),
    Owner("asset_consumer", "templates/asset_consumer", "explicit"),
)

# These files contain only an extends declaration and comments. They remain
# supported entry points; running their base once avoids duplicating its episode.
ALIASES = {
    ("afterlight", name): "afterlight_ensemble_checks.gd"
    for name in (
        "afterlight_checks.gd",
        "afterlight_language_checks.gd",
        "afterlight_narrative_checks.gd",
        "eye_transition_integration_checks.gd",
    )
}


def _scripts(owner: str, names: str, level: Level = "offline") -> list[Suite]:
    return [Suite(owner, name, "script", f"tests/{name}.gd", level) for name in names.split()]


def declared_suites() -> list[Suite]:
    suites: list[Suite] = []
    for owner in OWNERS:
        if owner.convention == "native":
            suites.append(
                Suite(
                    owner.name,
                    "native_regressions",
                    "native",
                    "tests/run_tests.gd",
                    success=r"(?m)^\s*[1-9][0-9]* checks in [1-9][0-9]* files passed",
                )
            )
    suites += _scripts(
        "game_presentation",
        """actor_halo_checks ambient_particle_checks background_blackout_checks
        camera_drift_checks eye_transition_checks impact_shake_checks intertitle_checks
        layer_pan_checks local_content_checks one_shot_manpu_checks point_contact_checks
        sprite_burst_checks walking_approach_checks""",
    )
    suites += _scripts("game_presentation", "corruption_pattern_checks", "rendered")
    suites += _scripts(
        "afterlight",
        """actor_blocking_checks afterlight_cast_stage_checks afterlight_effect_study_checks
        afterlight_ensemble_checks afterlight_input_checks ambient_transmission_integration_checks
        ambient_voice_lab_checks autoplay_checks ominous_vfx_checks
        one_shot_manpu_integration_checks text_reveal_audio_checks voiceover_checks
        waking_eye_integration_checks walk_away_integration_checks""",
        "media",
    )
    suites += _scripts(
        "afterlight",
        """afterlight_contact_checks background_blackout_integration_checks
        cast_pan_integration_checks keeper_intensity_checks looping_manpu_integration_checks
        quick_approach_integration_checks sprite_burst_integration_checks
        transmission_audio_checks transmission_display_checks""",
        "rendered",
    )
    suites.append(
        Suite(
            "afterlight",
            "voiceover_policy",
            "script",
            "tests/voiceover_checks.gd",
            arguments=("--policy-only",),
        )
    )
    suites.append(
        Suite(
            "afterlight",
            "afterlight_external_content_checks",
            "script",
            "tests/afterlight_external_content_checks.gd",
            "media",
            prerequisite="--afterlight-content-root from tools/prepare_example_content.py",
        )
    )
    suites += _scripts(
        "command_link",
        """check_sample_bounds command_link_content_checks manpu_loop_checks
        walk_away_controller_checks scene_navigation_checks stage_seams_checks""",
    )
    suites += _scripts(
        "command_link",
        """composition_checks presentation_lab_checks route_option_checks
        one_shot_manpu_integration_checks walk_away_integration_checks""",
        "media",
    )
    suites += _scripts(
        "command_link", "hologram_defaults_checks looping_manpu_integration_checks", "rendered"
    )
    for name, option in (
        ("actor_focus_checks", "validate-focus"),
        ("cast_transition_checks", "validate-cast-transition"),
        ("character_exit_checks", "validate-character-exit"),
        ("dialogue_camera_checks", "validate-dialogue-camera"),
        ("establishing_shot_checks", "validate-establishing-shot"),
        ("manpu_animation_checks", "validate-manpu-animation"),
        ("route_checks", "validate-routes"),
        ("legacy_presentation", "validate"),
    ):
        suites.append(
            Suite(
                "command_link",
                name,
                "application",
                f"tests/{name}.gd",
                "media",
                arguments=(f"--{option}",),
            )
        )
    suites += _scripts("vn", "starter_checks")
    for name in ("scenario_runtime", "content_io", "sideview_rendering"):
        suites.append(
            Suite(
                name,
                "run_checks",
                "script",
                "tests/run_checks.gd",
                success=rf"(?m)^{name}: [1-9][0-9]* checks passed",
                members=("test_pixels.gd", "test_contract.gd")
                if name == "sideview_rendering"
                else (),
            )
        )
    suites.append(
        Suite(
            "asset_consumer",
            "consume",
            "asset_consumer",
            "tests/consume.gd",
            success=r"(?m)^asset consumer loaded 16 x 8$",
        )
    )
    suites.append(
        Suite("game_presentation", "package_dependencies", "python", "tools/check_sdk_package.py")
    )
    for owner_name, name, source in (
        ("game_presentation", "starter_assembly", "tests/python/test_starter_assembly.py"),
        ("afterlight", "content_preparation", "tests/python/test_example_content.py"),
        ("afterlight", "voice_preparation", "tests/python/test_afterlight_voice_preparation.py"),
    ):
        suites.append(Suite(owner_name, name, "pytest", source, success=r"\b[1-9][0-9]* passed\b"))
    return suites


def inventory_errors(owners: tuple[Owner, ...], suites: list[Suite]) -> list[str]:
    """A new, missing or reclassified suite must not disappear from coverage."""
    errors: list[str] = []
    if {owner.name for owner in owners} == {owner.name for owner in OWNERS}:
        found = {
            path.parent
            for tier in ("games", "packages", "templates")
            for path in (ROOT / tier).glob("*/project.godot")
        }
        found.add(ROOT / "games/_shared/runtime")
        declared_projects = {owner.project for owner in owners}
        for project in sorted(found - declared_projects):
            errors.append(f"project has no maintained-owner adapter: {project.relative_to(ROOT)}")
    for owner in owners:
        if not (owner.project / "project.godot").is_file():
            errors.append(f"{owner.name}: project.godot is absent")
        owned = [suite for suite in suites if suite.owner == owner.name]
        if not owned:
            errors.append(f"{owner.name}: no declared suites")
        for suite in owned:
            entry = owner.project / suite.source
            if not entry.is_file():
                errors.append(f"{owner.name}: declared source is absent: {suite.source}")
            for member in suite.members:
                if not (entry.parent / member).is_file():
                    errors.append(f"{owner.name}: bundled check is absent: {member}")
                elif entry.is_file() and f'preload("{member}")' not in entry.read_text():
                    errors.append(
                        f"{owner.name}: entry point does not preload bundled check: {member}"
                    )
        declared_python = {suite.source for suite in owned if suite.adapter == "pytest"}
        for path in sorted((owner.project / "tests").rglob("test_*.py")):
            if path.relative_to(owner.project).as_posix() not in declared_python:
                errors.append(f"{owner.name}: Python suite has no execution adapter: {path.name}")
        patterns = (
            ("test_*.gd",)
            if owner.convention == "native"
            else ("*_checks.gd", "test_*.gd", "check_*.gd")
        )
        discovered = {
            path.name for pattern in patterns for path in (owner.project / "tests").glob(pattern)
        }
        if owner.convention == "native":
            if not discovered:
                errors.append(f"{owner.name}: no test_*.gd files")
            continue
        declared = {Path(suite.source).name for suite in owned}
        declared.update(member for suite in owned for member in suite.members)
        aliases = {
            name: base for (name_owner, name), base in ALIASES.items() if name_owner == owner.name
        }
        for name, base in aliases.items():
            source = owner.project / "tests" / name
            if not source.is_file():
                errors.append(f"{owner.name}: compatibility entry point is absent: {name}")
                continue
            code = [
                line.strip()
                for line in source.read_text().splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
            if code != [f'extends "res://tests/{base}"'] or base not in declared:
                errors.append(f"{owner.name}: {name} is no longer a pure alias of {base}")
        for name in sorted(discovered - declared - aliases.keys()):
            errors.append(f"{owner.name}: suite has no execution adapter: {name}")
        for suite in owned:
            source = owner.project / suite.source
            if suite.adapter == "script" and source.is_file():
                first = source.read_text().splitlines()[0]
                if first == "extends RefCounted":
                    errors.append(
                        f"{owner.name}: RefCounted checks require application dispatch: "
                        f"{suite.name}"
                    )
    return errors
