"""Every renamed command reaches the same internal call with the same arguments.

The fixture was recorded once from the old console scripts and ``demo-games`` commands,
before they were deleted (decision 0071, section 13). Each case ran its old argv with the
final internal calls replaced by recorders, so no provider, service, budget or run folder
was ever reached. This test replays each case's new ``stage-gen`` argv under the same
recorders and requires the same calls, in the same order, with the same arguments: a spend
opt-in, a budget, a candidate or a cache root that moved would show here, offline.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import io
import json
import os
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from enum import Enum
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any, Literal

import pytest
from pydantic import BaseModel

from gnode import BindingTable

FIXTURE = Path(__file__).parent / "fixtures" / "cli-equivalence.json"
FIXTURE_KIND = "stage-gen-cli-equivalence-v1"

#: What a recorder does after it records: stop the command there, hand back a stand-in so
#: the command reaches its next call, or call through to the real code.
type Behaviour = Literal["stop", "argv", "definition", "planned", "budget", "view", "empty", "pass"]

#: Module prefixes whose bindings a recorder replaces; any other module keeps the original.
PATCHED_PACKAGES = ("stage_gen", "demo_game_collection", "gnode")
#: Values that stand for a service or configuration object and are never serialised.
OPAQUE = frozenset({"StageGenConfig", "ConfiguredPortraitServices", "HeadlessRuntime"})
CREDENTIALS = ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "FAL_KEY", "ELEVENLABS_API_KEY")


class Stop(BaseException):
    """Raised by a final-call recorder, so nothing after the recorded call runs."""


@dataclasses.dataclass(frozen=True, slots=True)
class Probe:
    target: str
    behaviour: Behaviour


_UNIVERSE = "stage_gen.workflows.universe.universe_executor.UniverseExecutor"

#: The final internal calls of every renamed command, and the calls on the way to them.
PROBES: tuple[Probe, ...] = (
    Probe("stage_gen.pipeline.load_definition", "definition"),
    Probe("stage_gen.pipeline.plan", "planned"),
    Probe("stage_gen.pipeline.write_plan", "stop"),
    Probe("stage_gen.pipeline.run", "stop"),
    Probe("stage_gen.pipeline.inspect", "stop"),
    Probe("stage_gen.provider_env.load_provider_dotenv", "empty"),
    Probe("stage_gen.components.character_3d.budget_pool.BudgetPool", "budget"),
    Probe("stage_gen.workflows.portrait_motion.pipeline.prepare_run", "stop"),
    Probe("stage_gen.workflows.portrait_motion.pipeline.run_pipeline", "stop"),
    Probe("stage_gen.workflows.portrait_motion.pipeline.verify_run", "stop"),
    Probe("stage_gen.orchestration.character_3d.launch.main", "argv"),
    Probe(f"{_UNIVERSE}.dry_run_semantic", "stop"),
    Probe(f"{_UNIVERSE}.run_semantic", "stop"),
    Probe(f"{_UNIVERSE}.dry_run_gallery", "stop"),
    Probe(f"{_UNIVERSE}.run_gallery", "stop"),
    Probe("stage_gen.capabilities.generate_image_artifact", "stop"),
    Probe("stage_gen.capabilities.remove_background", "stop"),
    Probe("stage_gen.capabilities.generate_music", "stop"),
    Probe("stage_gen.capabilities.generate_sound_effect", "stop"),
    Probe("stage_gen.capabilities.generate_speech", "stop"),
    Probe("stage_gen.capabilities.generate_video", "stop"),
    Probe("stage_gen.capabilities.inspect_video", "stop"),
    Probe("stage_gen.orchestration.env_import.import_provider_env", "stop"),
    Probe("stage_gen.workflows.universe.universe_view.build_universe_view", "view"),
    Probe("gnode.write_run_view", "stop"),
)


@dataclasses.dataclass(frozen=True, slots=True)
class StandIn:
    """What a recorder hands back in place of a definition, a budget or a view."""

    label: str
    pipeline_id: str = "<definition>"


class _Dump:
    def model_dump(self, **_: object) -> dict[str, object]:
        return {}


@dataclasses.dataclass(frozen=True, slots=True)
class _Node:
    node_id: str = "generate"
    is_local: bool = False


class PlannedStandIn:
    """A planned pipeline with one provider node, so a live command reaches its services."""

    graph = _Dump()
    projection = _Dump()
    selected_nodes = (_Node(),)


def _resolve(target: str) -> tuple[object, str, Any]:
    """The owner (a module or a class), the attribute name and the original object."""
    parts = target.split(".")
    for cut in range(len(parts) - 1, 0, -1):
        try:
            owner: object = importlib.import_module(".".join(parts[:cut]))
        except ModuleNotFoundError:
            continue
        for name in parts[cut:-1]:
            owner = getattr(owner, name)
        return owner, parts[-1], getattr(owner, parts[-1])
    raise ValueError(f"cannot resolve {target}")


def _path(value: Path, root: Path) -> str:
    if not value.is_absolute():
        return PurePosixPath(*value.parts).as_posix()
    for base in (root, root.resolve()):
        if value.is_relative_to(base):
            return value.relative_to(base).as_posix() or "."
        if value.resolve().is_relative_to(base):
            return value.resolve().relative_to(base).as_posix() or "."
    raise ValueError(f"a recorded path lies outside the case folder: {value}")


def plain(value: object, root: Path) -> object:
    """A JSON value for one recorded argument; paths are written relative to the case."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if type(value).__name__ in OPAQUE:
        return f"<{type(value).__name__}>"
    if isinstance(value, StandIn):
        return f"<{value.label}>"
    if isinstance(value, PlannedStandIn):
        return "<planned>"
    if isinstance(value, Path):
        return _path(value, root)
    if isinstance(value, Enum):
        return plain(value.value, root)
    if isinstance(value, BaseModel):
        return plain(value.model_dump(mode="json"), root)
    if isinstance(value, BindingTable):
        # The routes' own terms are code, not argv; the binding call above records the
        # arguments they were built from, so a later route change does not fail this test.
        return [binding.resource_id for binding in value.bindings]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: plain(getattr(value, f.name), root) for f in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return {str(key): plain(item, root) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [plain(item, root) for item in value]
    if isinstance(value, set | frozenset):
        return sorted((plain(item, root) for item in value), key=json.dumps)
    raise TypeError(f"no recorded form for a {type(value).__qualname__}")


def _arguments(original: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    bound = inspect.signature(original).bind(*args, **kwargs)
    bound.apply_defaults()
    return {name: value for name, value in bound.arguments.items() if name != "self"}


def _stub(probe: Probe, original: Any, calls: list[dict[str, object]], root: Path) -> Any:
    def recorder(*args: Any, **kwargs: Any) -> Any:
        if probe.behaviour == "argv":
            calls.append({"target": probe.target, "kwargs": {"argv": list(sys.argv[1:])}})
            raise Stop
        recorded = _arguments(original, args, kwargs)
        calls.append({"target": probe.target, "kwargs": plain(recorded, root)})
        match probe.behaviour:
            case "stop":
                raise Stop
            case "pass":
                return original(*args, **kwargs)
            case "planned":
                return PlannedStandIn()
            case "empty":
                return {}
            case _:
                return StandIn(probe.behaviour)

    return recorder


def _modules() -> list[ModuleType]:
    return [
        module
        for name, module in list(sys.modules.items())
        if isinstance(module, ModuleType) and name.split(".")[0] in PATCHED_PACKAGES
    ]


@contextmanager
def recording(calls: list[dict[str, object]], root: Path) -> Iterator[None]:
    """Replace each probe's original wherever it is bound, then put every binding back.

    Classes get the recorder as an attribute. A function is replaced in every loaded module
    that binds it, and in any module-level frozen dataclass that holds it (a workflow's run
    readers keep their view builder that way).
    """
    undo: list[Callable[[], None]] = []
    try:
        for probe in PROBES:
            owner, name, original = _resolve(probe.target)
            stub = _stub(probe, original, calls, root)
            if isinstance(owner, type):
                previous = owner.__dict__.get(name, _ABSENT)
                setattr(owner, name, stub)
                undo.append(_restore_attribute(owner, name, previous))
                continue
            for module in _modules():
                for attribute, value in list(vars(module).items()):
                    if value is original:
                        setattr(module, attribute, stub)
                        undo.append(_restore_attribute(module, attribute, original))
                    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
                        for field in dataclasses.fields(value):
                            if getattr(value, field.name) is original:
                                object.__setattr__(value, field.name, stub)
                                undo.append(_restore_field(value, field.name, original))
        yield
    finally:
        for step in reversed(undo):
            step()


_ABSENT = object()


def _restore_attribute(owner: object, name: str, previous: object) -> Callable[[], None]:
    def restore() -> None:
        if previous is _ABSENT:
            delattr(owner, name)
        else:
            setattr(owner, name, previous)

    return restore


def _restore_field(owner: object, name: str, previous: object) -> Callable[[], None]:
    def restore() -> None:
        object.__setattr__(owner, name, previous)

    return restore


def prepare_case(root: Path, fixture: Mapping[str, Any]) -> None:
    """Write the small files the commands read before their final call."""
    from scripts.write_workflow_identity import materialize_inputs

    for relative, text in fixture["files"].items():
        target = root.joinpath(*PurePosixPath(relative).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    for name in fixture["identity_inputs"]:
        materialize_inputs(name, root)


def preload() -> None:
    """Import every module a command may bind a probe in, before any probe is applied, so a
    module imported mid-command cannot keep an original or record its own import-time
    calls."""
    from stage_gen.interfaces.cli import build_parser
    from stage_gen.workflows._registry import discover

    build_parser()
    for found in discover():
        importlib.import_module(f"{found.package}.workflow")
    for probe in PROBES:
        _resolve(probe.target)


def invoke(
    argv: Sequence[str],
    programs: Mapping[str, Callable[[list[str]], str]],
    root: Path,
) -> tuple[list[dict[str, object]], str]:
    """Run one argv under the recorders; return what they recorded and how the command
    ended when no final call stopped it."""
    calls: list[dict[str, object]] = []
    program = programs[argv[0]]
    with recording(calls, root):
        try:
            ending = program(list(argv[1:]))
        except Stop:
            ending = "stopped at its final call"
    return calls, ending


def _stage_gen(arguments: list[str]) -> str:
    from stage_gen.interfaces.cli import main

    errors = io.StringIO()
    status = main(arguments, stdout=io.StringIO(), stderr=errors)
    return f"returned {status}: {errors.getvalue()}"


def load_fixture() -> dict[str, Any]:
    fixture: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["kind"] == FIXTURE_KIND
    return fixture


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """No credential, configuration override or dotenv file reaches a replayed command."""
    for key in list(os.environ):
        if key.startswith("STAGE_GEN_") or key in CREDENTIALS:
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("_STAGE_GEN_DISABLE_DOTENV", "1")


def _cases() -> list[str]:
    return sorted(load_fixture()["cases"]) if FIXTURE.is_file() else []


@pytest.mark.parametrize("case_id", _cases())
def test_new_command_reaches_the_recorded_call(
    case_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = load_fixture()
    case = fixture["cases"][case_id]
    preload()
    monkeypatch.chdir(tmp_path)
    prepare_case(tmp_path, fixture)
    calls, ending = invoke(case["new_argv"], {"stage-gen": _stage_gen}, tmp_path)
    expected = [*case["before"], {"target": case["target"], "kwargs": case["kwargs"]}]
    assert calls == expected, (
        json.dumps({"recorded": expected, "replayed": calls}, indent=1) + f"\n{ending}"
    )


def _entry(argv: Sequence[str]) -> str:
    return argv[0] if argv[0] == "stage-gen-character" else " ".join(argv[:2])


def test_every_retired_entry_point_has_a_case() -> None:
    """Each deleted console script and each command that left demo-games is replayed."""
    cases = load_fixture()["cases"].values()
    old = {_entry(case["old_argv"]) for case in cases}
    for program in (
        "stage-gen pipeline",
        "stage-gen universe",
        "stage-gen-portrait-motion prepare",
        "stage-gen-portrait-motion run",
        "stage-gen-portrait-motion verify",
        "stage-gen-character",
        "demo-games generate-image",
        "demo-games generate-music",
        "demo-games generate-video",
        "demo-games generate-speech",
        "demo-games generate-sound-effect",
        "demo-games remove-background",
        "demo-games inspect-video",
        "demo-games import-env",
        "demo-games export-view",
    ):
        assert program in old, program
    assert all(case["new_argv"][0] == "stage-gen" for case in cases)
