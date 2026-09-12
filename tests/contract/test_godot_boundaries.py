"""The runtime project's layers point inward, and only a host touches the engine.

`docs/spec/game/host-contract.md` states the rule; this is what makes it true. The
browser runtime it replaced called an equivalent test "the whole enforcement" and never
wrote one, so its rings were documentary and a ring inversion would have gone unnoticed.

Two rules, checked mechanically:

**Direction.** `kernel/` names nothing but itself. `families/` name the kernel and each
other. `genres/<recipe>/` name the kernel and families, never a host and never another
genre. `hosts/common/` names the kernel and families. `hosts/<recipe>/` names anything
inward plus `hosts/common/`, never another host. The check is by class-name prefix,
because that is how the inner layers reference each other: a path would be a `res://`,
and the inner layers may not carry one.

**The engine deny-list.** Only files under `hosts/`, `tests/` and `tools/` may extend a
scene-tree class, touch the filesystem, read the wall clock, draw an unseeded random
number, run an engine tween or timer, or use an engine vector type. Simulation state is
scalars, arrays and dictionaries: an engine's vector is single precision in the default
build, and a world that stores one cannot be compared against another implementation of
itself, which is what every promotion in this repository is proved by.
"""

from __future__ import annotations

import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
#: The run consumer. The tiers beside it (`packages/`, `templates/`, `games/`) are
#: separate projects; only the link rule below applies to them.
GODOT_TREE = REPOSITORY_ROOT / "godot"
GODOT_ROOT = GODOT_TREE / "legacy" / "runtime"

#: Directories that hold simulation, in the order they may be named from.
INNER_LAYERS = ("kernel", "families", "genres")

#: The prefix every class in a layer carries, so a reference is legible without a path.
LAYER_PREFIX = {"kernel": "Kernel", "families": "Family", "hosts/common": "Host"}

#: One recipe, one word. A genre and its host share it.
RECIPE_PREFIX = {
    "oblique_survival": "Survival",
    "sideview_runner": "Runner",
    "sideview_platformer": "Platformer",
    "pointclick_room": "Room",
    "dialogue_scene": "Dialogue",
    "case": "Case",
}

#: Names a test file may declare. Everything else in `tests/` is a `test_*.gd` with a
#: `run(h)` and no class of its own.
TEST_CLASS_NAMES = frozenset({"TestHarness", "TestFixtures"})

#: What a simulation may not touch, word-bound so a class named `PlatformerTimersSystem`
#: is not mistaken for `Timer`. Each entry is (label, pattern).
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

#: `genres/oblique_survival/masks.gd` reads the run's plates as images. It is the one
#: simulation file that holds decoded media, and it is on the list to be moved behind a
#: port when a second genre needs one; until then it is named here rather than silently
#: excluded, so the exception is visible in the diff that removes it.
DENY_EXEMPT = {"genres/oblique_survival/masks.gd"}

#: A genre that still names the shared run loader, because the loader has not been split
#: yet: `hosts/common/run_dir.gd` carries the survival document's kind, schema, layout
#: reference and field refusals, which belong in `genres/oblique_survival/parser.gd`, and
#: its raw media readers, which belong in `hosts/common/run_media.gd` behind a port the
#: genre asks through. Named here rather than quietly excluded, so removing the exception
#: is what the split's diff looks like.
DIRECTION_EXEMPT = {
    "genres/oblique_survival/masks.gd",
    "genres/oblique_survival/world.gd",
}


def _gd_files(*relative: str) -> list[Path]:
    assert GODOT_ROOT.is_dir(), "legacy Godot runtime root is missing"
    found: list[Path] = []
    for part in relative:
        root = GODOT_ROOT / part
        if not root.is_dir():
            continue
        found.extend(
            path
            for path in sorted(root.rglob("*.gd"))
            if ".godot" not in path.parts and not path.name.endswith(".uid")
        )
    return found


def _declared_classes() -> dict[str, str]:
    """Every `class_name` in the project, mapped to its path relative to `godot/`.

    Built from the tracked sources rather than from `.godot/global_script_class_cache.cfg`,
    which is gitignored and absent on a fresh clone.
    """

    found: dict[str, str] = {}
    for path in _gd_files("."):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("class_name "):
                found[line.split()[1]] = path.relative_to(GODOT_ROOT).as_posix()
                break
    return found


def _layer_of(relative: str) -> str:
    """Which layer a file belongs to, as a coarse word the rules are written in."""

    if relative.startswith("kernel/"):
        return "kernel"
    if relative.startswith("families/"):
        return "families"
    if relative.startswith("genres/"):
        return "genres"
    if relative.startswith("hosts/common/"):
        return "hosts/common"
    if relative.startswith("hosts/"):
        return "hosts"
    return "outside"


def _recipe_of(relative: str) -> str | None:
    parts = relative.split("/")
    if parts[0] in {"genres"} and len(parts) > 1:
        return parts[1]
    if parts[0] == "hosts" and len(parts) > 1 and parts[1] != "common":
        return parts[1]
    return None


def test_every_class_name_carries_its_layer_or_its_recipe() -> None:
    """One project means one global class-name space; a prefix is what keeps it legible
    and what stops a second genre colliding on `World`, `Hud` or `Music`."""

    failures: list[str] = []
    for name, relative in sorted(_declared_classes().items()):
        layer = _layer_of(relative)
        if relative.startswith("tests/"):
            if name not in TEST_CLASS_NAMES:
                failures.append(f"{relative}: a test declares `class_name {name}`")
            continue
        if layer in LAYER_PREFIX:
            prefix = LAYER_PREFIX[layer]
            if not name.startswith(prefix):
                failures.append(f"{relative}: `{name}` is in {layer} and needs the {prefix} prefix")
            continue
        recipe = _recipe_of(relative)
        if recipe is not None:
            expected = RECIPE_PREFIX.get(recipe)
            if expected is None:
                failures.append(f"{relative}: {recipe} has no prefix in RECIPE_PREFIX")
            elif not name.startswith(expected):
                failures.append(
                    f"{relative}: `{name}` is {recipe}'s and needs the {expected} prefix"
                )
    assert not failures, "class names must carry their layer:\n  " + "\n  ".join(failures)


def test_the_layers_point_inward() -> None:
    """A layer names what is inside it and never what is outside."""

    classes = _declared_classes()
    failures: list[str] = []
    for path in _gd_files("kernel", "families", "genres", "hosts"):
        relative = path.relative_to(GODOT_ROOT).as_posix()
        layer = _layer_of(relative)
        recipe = _recipe_of(relative)
        source = "\n".join(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        if relative in DIRECTION_EXEMPT:
            continue
        for name, home in classes.items():
            if not re.search(rf"\b{re.escape(name)}\b", source) or home == relative:
                continue
            target = _layer_of(home)
            target_recipe = _recipe_of(home)
            if layer == "kernel" and target != "kernel":
                failures.append(f"{relative}: the kernel names `{name}` in {target}")
            elif layer == "families" and target not in {"kernel", "families"}:
                failures.append(f"{relative}: a family names `{name}` in {target}")
            elif layer == "genres":
                if target in {"hosts", "hosts/common"}:
                    failures.append(f"{relative}: a genre names the host class `{name}`")
                elif target_recipe is not None and target_recipe != recipe:
                    failures.append(f"{relative}: a genre names `{name}` from {target_recipe}")
            elif layer == "hosts/common" and target in {"hosts"}:
                failures.append(f"{relative}: the shared host names `{name}` in a genre's host")
            elif layer == "hosts" and target_recipe is not None and target_recipe != recipe:
                failures.append(f"{relative}: a host names `{name}` from {target_recipe}")
    assert not failures, "the layers must point inward:\n  " + "\n  ".join(sorted(set(failures)))


def test_a_simulation_never_touches_the_engine() -> None:
    """The deny-list. What a replay depends on is that a step is the same twice."""

    failures: list[str] = []
    for path in _gd_files(*INNER_LAYERS):
        relative = path.relative_to(GODOT_ROOT).as_posix()
        if relative in DENY_EXEMPT:
            continue
        source = path.read_text(encoding="utf-8")
        # Comments explain the rule; the rule is about code.
        code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
        for label, pattern in ENGINE_DENY:
            if pattern.search(code):
                failures.append(f"{relative}: a simulation reads {label}")
    assert not failures, "simulation must not touch the engine:\n  " + "\n  ".join(failures)


def test_one_scene_per_host_and_none_anywhere_else() -> None:
    """Every other node is built with `.new()`, so a scene file is a decision rather than
    a habit: a `.tscn` nobody opens is a second place a wiring can live."""

    scenes = sorted(
        path.relative_to(GODOT_ROOT).as_posix()
        for path in GODOT_ROOT.rglob("*.tscn")
        if ".godot" not in path.parts
    )
    unexpected = [
        scene
        for scene in scenes
        if not re.fullmatch(r"hosts/[a-z_]+/main\.tscn", scene)
        and scene != "hosts/common/boot.tscn"
    ]
    assert not unexpected, f"unexpected scenes: {unexpected}"


def test_every_script_carries_its_uid() -> None:
    """A `.uid` is how the engine keeps a reference stable across a move; a script
    without one is a reference that breaks the next time something is renamed."""

    missing = [
        path.relative_to(GODOT_ROOT).as_posix()
        for path in _gd_files(".")
        if not path.with_suffix(".gd.uid").exists()
    ]
    assert not missing, f"scripts with no .uid sidecar: {missing}"


def test_a_project_links_only_package_payloads() -> None:
    """A game or template never contains a package. It links `addons/<name>` to
    `packages/<name>/addons/<name>`; anything else under `addons/` is either a real
    directory the project owns or a link that would smuggle one project into another."""

    offences: list[str] = []
    for tier in ("games", "templates"):
        tier_root = GODOT_TREE / tier
        if not tier_root.is_dir():
            continue
        for project in sorted(p for p in tier_root.iterdir() if p.is_dir()):
            addons = project / "addons"
            if not addons.is_dir():
                continue
            for entry in sorted(addons.iterdir()):
                if not entry.is_symlink():
                    continue
                expected = GODOT_TREE / "packages" / entry.name / "addons" / entry.name
                if entry.resolve() != expected.resolve() or not expected.is_dir():
                    offences.append(
                        f"{entry.relative_to(GODOT_TREE).as_posix()} -> {entry.readlink()}"
                    )
    assert not offences, f"links that do not point at a package payload: {offences}"


def test_a_package_carries_its_payload_and_project() -> None:
    """A package is an addon project: `project.godot` beside `addons/<name>/`, so the
    payload can be opened and checked without any game."""

    packages = GODOT_TREE / "packages"
    missing = []
    for package in sorted(p for p in packages.iterdir() if p.is_dir()):
        for required in ("project.godot", f"addons/{package.name}"):
            if not (package / required).exists():
                missing.append(f"{package.name}/{required}")
    assert not missing, f"packages missing their project or payload: {missing}"
