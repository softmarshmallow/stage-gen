"""Maintained Godot consumers own gameplay; shared source has a closed dependency graph.

The deterministic simulations retain their engine boundary and replay guarantees.
A game's ordinary scene code is free to use Godot; it does not inherit a universal
scene shape or genre registry. Private support is shared only by actual callers.
"""

from __future__ import annotations

import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GODOT_TREE = REPOSITORY_ROOT / "godot"
GAMES = GODOT_TREE / "games"
GAME_NAMES = ("bellweather", "iron_petal_unit", "ember_hollow", "the_grain")
SHARED_ROOT = GAMES / "_shared" / "runtime"
SHARED_ADDON = SHARED_ROOT / "addons" / "demo_support"
ENGINE_DENY = (
    ("the wall clock", re.compile(r"\bTime\.")),
    ("the operating system", re.compile(r"\bOS\.")),
    ("an unseeded draw", re.compile(r"\brand[fi]\b|\bRandomNumberGenerator\b|\brandi_range\b")),
    ("an engine tween", re.compile(r"\bTween\b|\bcreate_tween\b")),
    ("an engine timer", re.compile(r"\bTimer\b(?!s)")),
    ("an animation player", re.compile(r"\bAnimationPlayer\b")),
    ("the filesystem", re.compile(r"\bFileAccess\b|\bDirAccess\b|\bResourceLoader\b")),
    ("a resource path", re.compile(r"res://|user://")),
    ("a script load", re.compile(r"\bpreload\s*\(|(?<![A-Za-z_])load\s*\(")),
    ("an engine vector", re.compile(r"\bVector[234]i?\s*\(|\bTransform[23]D\s*\(")),
    ("a scene node", re.compile(r"^extends\s+(Node|Control|Canvas|Camera|Audio|Sprite|Mesh)")),
)
# Ember Hollow's decoded masks and world still receive its run loader directly.
# Preserve these visible exceptions while retaining every other simulation rule.
ENGINE_EXEMPT = {"ember_hollow/gameplay/masks.gd"}
DIRECTION_EXEMPT = ENGINE_EXEMPT | {"ember_hollow/gameplay/world.gd"}


def _scripts() -> list[Path]:
    roots = [SHARED_ROOT, *(GAMES / name for name in GAME_NAMES)]
    return [
        path for root in roots for path in sorted(root.rglob("*.gd")) if ".godot" not in path.parts
    ]


def _code(path: Path) -> str:
    return "\n".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def _classes() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in _scripts():
        if match := re.search(r"^class_name\s+(\w+)", _code(path), re.MULTILINE):
            name = match.group(1)
            assert name not in found, f"duplicate class {name}: {path} and {found[name]}"
            found[name] = path
    return found


def _owner(path: Path) -> str:
    return path.relative_to(GAMES).parts[0]


def _simulation(path: Path) -> bool:
    return "gameplay" in path.relative_to(GAMES).parts or path.is_relative_to(
        SHARED_ADDON / "simulation"
    )


def _dependencies(classes: dict[str, Path]) -> dict[Path, set[Path]]:
    return {
        path: {classes[token] for token in re.findall(r"\b\w+\b", _code(path)) if token in classes}
        - {path}
        for path in _scripts()
    }


def test_each_game_is_a_real_independent_project() -> None:
    for name in GAME_NAMES:
        root = GAMES / name
        for required in (
            "project.godot",
            "main.gd",
            "main.tscn",
            "gameplay",
            "scenes",
            "tests/run_tests.gd",
        ):
            assert (root / required).exists(), f"{name} does not own {required}"
        assert 'run/main_scene="res://main.tscn"' in (root / "project.godot").read_text()
        assert not (root / "main.gd").is_symlink()
        assert not (root / "gameplay").is_symlink()


def test_shared_code_is_closed_and_games_do_not_import_each_other() -> None:
    failures: list[str] = []
    for path, targets in _dependencies(_classes()).items():
        for target in targets:
            if _owner(target) not in {_owner(path), "_shared"}:
                failures.append(f"{path.relative_to(GAMES)} names {target.relative_to(GAMES)}")
    assert not failures, "cross-game dependencies:\n  " + "\n  ".join(failures)


def test_shared_production_classes_have_multiple_game_consumers() -> None:
    dependencies = _dependencies(_classes())
    callers: dict[Path, set[str]] = {}
    for owner in GAME_NAMES:
        pending = [
            path
            for path in dependencies
            if _owner(path) == owner and "tests" not in path.parts and "tools" not in path.parts
        ]
        seen: set[Path] = set()
        while pending:
            path = pending.pop()
            if path in seen:
                continue
            seen.add(path)
            callers.setdefault(path, set()).add(owner)
            pending.extend(dependencies[path])
    orphaned = [
        str(path.relative_to(SHARED_ADDON))
        for path in _classes().values()
        if path.is_relative_to(SHARED_ADDON)
        and "testing" not in path.parts
        and len(callers.get(path, set())) < 2
    ]
    assert not orphaned, (
        f"private support that belongs to one game or has no game caller: {orphaned}"
    )


def test_deterministic_simulation_dependencies_stay_inward() -> None:
    failures: list[str] = []
    for path, targets in _dependencies(_classes()).items():
        if not _simulation(path) or path.relative_to(GAMES).as_posix() in DIRECTION_EXEMPT:
            continue
        for target in targets:
            if not _simulation(target):
                failures.append(
                    f"{path.relative_to(GAMES)} names scene code {target.relative_to(GAMES)}"
                )
            elif path.is_relative_to(
                SHARED_ADDON / "simulation" / "kernel"
            ) and not target.is_relative_to(SHARED_ADDON / "simulation" / "kernel"):
                failures.append(f"kernel {path.name} names {target.relative_to(GAMES)}")
    assert not failures, "simulation dependencies must point inward:\n  " + "\n  ".join(failures)


def test_a_simulation_never_touches_the_engine() -> None:
    failures: list[str] = []
    for path in _scripts():
        relative = path.relative_to(GAMES).as_posix()
        if not _simulation(path) or relative in ENGINE_EXEMPT:
            continue
        for label, pattern in ENGINE_DENY:
            if pattern.search(_code(path)):
                failures.append(f"{relative}: a simulation reads {label}")
    assert not failures, "simulation must not touch the engine:\n  " + "\n  ".join(failures)


def test_every_script_carries_its_uid() -> None:
    missing = [
        str(path.relative_to(GAMES))
        for path in _scripts()
        if not path.with_suffix(".gd.uid").exists()
    ]
    assert not missing, f"scripts with no .uid sidecar: {missing}"


def test_a_project_links_only_closed_addon_payloads() -> None:
    offences: list[str] = []
    for tier in ("games", "templates"):
        for project in sorted(path for path in (GODOT_TREE / tier).iterdir() if path.is_dir()):
            addons = project / "addons"
            if not addons.is_dir():
                continue
            for entry in sorted(addons.iterdir()):
                if not entry.is_symlink():
                    continue
                expected = (
                    SHARED_ADDON
                    if entry.name == "demo_support" and project.name in GAME_NAMES
                    else GODOT_TREE / "packages" / entry.name / "addons" / entry.name
                )
                if entry.resolve() != expected.resolve() or not expected.is_dir():
                    offences.append(f"{entry.relative_to(GODOT_TREE)} -> {entry.readlink()}")
    assert not offences, f"links outside declared addon payloads: {offences}"


def test_a_package_carries_its_payload_and_project() -> None:
    missing: list[str] = []
    for package in sorted(path for path in (GODOT_TREE / "packages").iterdir() if path.is_dir()):
        for required in ("project.godot", f"addons/{package.name}"):
            if not (package / required).exists():
                missing.append(f"{package.name}/{required}")
    assert not missing, f"packages missing their project or payload: {missing}"
