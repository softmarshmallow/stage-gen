"""Every workflow describes itself, and drift between code, manifest, prose and examples fails.

The catalog's drift checks (decision 0071, section 8) run here over the installed workflows
in clean-clone mode, and each check is shown to fail on the drift it names. The example store
is local and ignored: its pinned examples are verified when it is present.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import io
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import cast

import pytest

from stage_gen.examples import ExamplePin, WorkflowExample, display_names, verify
from stage_gen.workflows import _checks as checks
from stage_gen.workflows._catalog import build, load_workflow
from stage_gen.workflows._checks import CheckContext, LoadedWorkflow
from stage_gen.workflows._registry import (
    OutputNote,
    Step,
    TryIt,
    discover,
    folder_of,
    repository_root,
)

REPOSITORY = Path(__file__).resolve().parents[2]
STORE = REPOSITORY / "out" / "examples"


def _script(name: str) -> ModuleType:
    """One of the repository's maintainer scripts, loaded as a module."""
    path = REPOSITORY / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"stage_gen_script_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GOLDEN = json.loads(
    (REPOSITORY / "tests/contract/fixtures/workflow-identity.json").read_text(encoding="utf-8")
)
WORKFLOWS = {
    "character-3d",
    "looping-parallax",
    "movie-sprite",
    "portrait-motion",
    "universe",
}


@pytest.fixture(autouse=True)
def _no_application_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for name in list(os.environ):
        if name.startswith("STAGE_GEN_"):
            monkeypatch.delenv(name)


@pytest.fixture(scope="module")
def loaded(tmp_path_factory: pytest.TempPathFactory) -> dict[str, LoadedWorkflow]:
    scratch = tmp_path_factory.mktemp("workflows")
    return {
        found.id: load_workflow(
            found,
            scratch,
            examples_dir=STORE if STORE.is_dir() else None,
            repository=REPOSITORY,
            allow_missing=True,
        )
        for found in discover()
    }


def _context() -> CheckContext:
    return CheckContext(names=display_names(), golden=GOLDEN)


def test_the_installed_workflows_have_no_drift() -> None:
    """Clean-clone mode: code-derived facts, declared facts and the library characters."""
    catalog, problems = build(examples_dir=None, allow_missing_examples=True)
    assert problems == []
    assert {w["id"] for w in catalog["workflows"]} == WORKFLOWS
    assert catalog["kind"] == "stage-gen-catalog-v1"
    assert [card["order"] for card in catalog["cards"]] == [5, 6, 7, 8]
    library = {
        e["id"]: e["currency"]
        for w in catalog["workflows"]
        for e in w["examples"]
        if e["source"].startswith("library:")
    }
    assert library == {"nami": "current", "riko": "current", "helix": "current"}


@pytest.mark.skipif(not STORE.is_dir(), reason="the local example store is absent")
def test_pinned_store_examples_verify_and_carry_their_currency() -> None:
    catalog, problems = build(examples_dir=STORE, allow_missing_examples=True)
    assert problems == []
    present = {
        e["id"]: e["currency"] for w in catalog["workflows"] for e in w["examples"] if e["present"]
    }
    expected = {
        "yuzu-idle": "earlier_version",
        "yuzu-face": "earlier_version",
        "wren-brief": "earlier_version",
        "tavi-parts": "earlier_version",
    }
    for example_id, state in expected.items():
        if example_id in present:
            assert present[example_id] == state


def test_folder_names_are_ids_and_ids_are_kebab_case() -> None:
    found = discover()
    assert {w.id for w in found} == WORKFLOWS
    for workflow in found:
        assert workflow.folder == folder_of(workflow.id)
    assert repository_root() == REPOSITORY


# ---------------------------------------------------------------- each check fails on its drift


def _with_manifest(workflow: LoadedWorkflow, **update: object) -> LoadedWorkflow:
    manifest = workflow.discovered.manifest.model_copy(update=update)
    found = dataclasses.replace(workflow.discovered, manifest=manifest)
    return dataclasses.replace(workflow, discovered=found)


def _with_steps(workflow: LoadedWorkflow, steps: tuple[Step, ...]) -> LoadedWorkflow:
    return dataclasses.replace(workflow, code=dataclasses.replace(workflow.code, steps=steps))


def test_a_type_in_no_step_or_in_two_steps_fails(loaded: dict[str, LoadedWorkflow]) -> None:
    movie = loaded["movie-sprite"]
    steps = movie.code.steps
    dropped = _with_steps(movie, steps[:-1])
    assert any("types in no step" in p for p in checks.structure(dropped))
    doubled = _with_steps(movie, (*steps, Step("Again", "Placed twice.", steps[0].members)))
    assert any("placed in two steps" in p for p in checks.structure(doubled))


def test_an_output_note_without_a_port_fails(loaded: dict[str, LoadedWorkflow]) -> None:
    parallax = _with_manifest(
        loaded["looping-parallax"],
        outputs=[OutputNote(artifact_ref="parallax/missing.png", description="Nothing")],
    )
    assert checks.outputs(parallax) == [
        "looping-parallax: output parallax/missing.png is in neither the sample plan nor the cover"
    ]
    assert checks.outputs(loaded["looping-parallax"]) == []


def test_a_page_that_restates_the_manifest_fails(loaded: dict[str, LoadedWorkflow]) -> None:
    movie = loaded["movie-sprite"]
    copied = _with_manifest(
        movie,
        summary="Stage Gen holds that as one graph",
        outputs=[OutputNote(artifact_ref="body/source.mp4", description="The take you chose")],
    )
    assert checks.structure(copied) == [
        "movie-sprite: page.mdx restates the workflow.toml summary",
        "movie-sprite: page.mdx restates the [[outputs]] note of body/source.mp4; "
        'write <File path="body/source.mp4" /> instead',
    ]
    assert checks.structure(movie) == []


def test_a_try_command_must_parse_with_the_real_parser(loaded: dict[str, LoadedWorkflow]) -> None:
    good = TryIt(
        input="inputs",
        commands=[
            "gnode inspect universe --verify",
            "GNODE_LIVE=1 gnode plan universe --inputs inputs.yaml",
        ],
    )
    bad = TryIt(input="inputs", commands=["gnode inspect --no-such-flag"])
    assert checks.try_commands(_with_manifest(loaded["universe"], try_=good)) == []
    [problem] = checks.try_commands(_with_manifest(loaded["universe"], try_=bad))
    assert "does not parse" in problem
    retired = TryIt(input="inputs", commands=["stage-gen show universe"])
    [problem] = checks.try_commands(_with_manifest(loaded["universe"], try_=retired))
    assert "does not start with gnode" in problem


def test_every_workflow_says_how_to_try_it_with_its_own_verbs() -> None:
    """Each [try] names its input and uses the workflow's own id with plan or run; the drift
    check above parses every command with the real parser."""
    for workflow in discover():
        assert workflow.manifest.try_ is not None, workflow.id
        assert workflow.manifest.try_.input.strip()
        commands = workflow.manifest.try_.commands
        assert 1 <= len(commands) <= 3, workflow.id
        verbs = ("gnode plan", "gnode run")
        assert any(
            command.startswith(tuple(f"{verb} {workflow.id} " for verb in verbs))
            for command in commands
        ), workflow.id


def test_related_must_name_a_known_workflow(loaded: dict[str, LoadedWorkflow]) -> None:
    others = [w for key, w in loaded.items() if key != "universe"]
    universe = _with_manifest(loaded["universe"], related=["no-such-workflow"])
    problems = checks.examples([universe, *others], _context())
    assert "universe: related names unknown workflow no-such-workflow" in problems


def test_a_store_example_that_differs_from_its_pin_fails(
    loaded: dict[str, LoadedWorkflow], tmp_path: Path
) -> None:
    from stage_gen.examples import MadeBy, Media, WorkflowExample, write_example
    from stage_gen.workflows._catalog import load_example

    movie = loaded["movie-sprite"]
    entry = movie.discovered.manifest.examples[0]
    directory = tmp_path / "movie-sprite" / entry.id
    media = Media(directory / "media", tmp_path)
    document = WorkflowExample.model_validate(
        {
            "example_id": entry.id,
            "made_by": MadeBy(kind="workflow", id="movie-sprite"),
            "importer": "test",
            "delivered_run": "runs/x",
            "source_runs": [{"path": "runs/x", "anchor": "graph.json", "anchor_sha256": "0" * 64}],
            "source_files": None,
            "status": None,
            "graph_kind": None,
            "graph_sha256": None,
            "inputs": {},
            "outputs": {},
            "metrics": {},
            "models": [],
            "tree": {},
            "nodes": {},
        }
    )
    pin = write_example(directory, document, media.figures("runs/x"))
    pinned = entry.model_copy(
        update={"example_sha256": pin.example_sha256, "figures_sha256": pin.figures_sha256}
    )
    found = load_example(
        "movie-sprite",
        pinned,
        movie.code,
        examples_dir=tmp_path,
        repository=REPOSITORY,
        allow_missing=False,
    )
    assert found.problems == () and found.currency == "current"
    stale = load_example(
        "movie-sprite",
        entry.model_copy(update={"example_sha256": "f" * 64}),
        movie.code,
        examples_dir=tmp_path,
        repository=REPOSITORY,
        allow_missing=False,
    )
    assert stale.problems and "differs from its pin" in stale.problems[0]
    assert verify(directory, ExamplePin(pin.example_sha256, pin.figures_sha256)) == []
    missing = load_example(
        "movie-sprite",
        entry,
        movie.code,
        examples_dir=tmp_path / "absent",
        repository=REPOSITORY,
        allow_missing=False,
    )
    assert missing.problems == ("is pinned but missing from the example store",)


def test_a_library_pin_that_differs_from_the_build_fails(loaded: dict[str, LoadedWorkflow]) -> None:
    from stage_gen.workflows._catalog import load_example

    character = loaded["character-3d"]
    [nami] = [e for e in character.discovered.manifest.examples if e.id == "nami"]
    stale = load_example(
        "character-3d",
        nami.model_copy(update={"figures_sha256": "0" * 64}),
        character.code,
        examples_dir=None,
        repository=REPOSITORY,
        allow_missing=True,
    )
    assert stale.problems and "differs from its pin" in stale.problems[0]


def test_a_model_without_a_display_name_fails(loaded: dict[str, LoadedWorkflow]) -> None:
    names = display_names()
    unnamed = dataclasses.replace(
        names, models={k: v for k, v in names.models.items() if k != "openai/gpt-5.6-sol"}
    )
    problems = checks.examples(list(loaded.values()), CheckContext(names=unnamed))
    assert "universe: route model openai/gpt-5.6-sol has no name" in problems


def test_a_title_that_is_empty_or_its_raw_slug_fails(loaded: dict[str, LoadedWorkflow]) -> None:
    raw = _with_manifest(loaded["universe"], title="universe")
    assert "universe: title 'universe' is empty or its raw slug" in checks.structure(raw)


def test_labels_title_only_the_types_an_example_ran(
    loaded: dict[str, LoadedWorkflow],
) -> None:
    compose = "looping_parallax/compose"
    editable = _with_manifest(loaded["looping-parallax"], labels={compose: "Compose"})
    assert checks.labels(editable) == [
        f"looping-parallax: [labels] retitles {compose}, whose title is in the workflow file"
    ]
    for workflow in loaded.values():
        assert checks.labels(workflow) == []
    unknown = _with_manifest(loaded["universe"], labels={"universe/no.such": "Nothing"})
    assert checks.labels(unknown) == [
        "universe: [labels] names universe/no.such, which no type or example has"
    ]


def test_a_folder_that_differs_from_its_id_fails(loaded: dict[str, LoadedWorkflow]) -> None:
    movie = loaded["movie-sprite"]
    renamed = dataclasses.replace(
        movie, discovered=dataclasses.replace(movie.discovered, folder="movie_sprites")
    )
    assert "movie-sprite: folder movie_sprites differs from its id" in checks.structure(renamed)


def test_the_readme_table_must_match_the_manifests(loaded: dict[str, LoadedWorkflow]) -> None:
    workflows = list(loaded.values())
    readme = (REPOSITORY / "README.md").read_text(encoding="utf-8")
    assert checks.readme(workflows, readme) == []
    edited = readme.replace("| [Movie sprite](", "| [Movie sprites](")
    [problem] = checks.readme(workflows, edited)
    assert problem.startswith("README.md workflow table differs from workflow.toml")


def test_identity_must_agree_with_the_identity_golden(loaded: dict[str, LoadedWorkflow]) -> None:
    for workflow in loaded.values():
        assert checks.identity(workflow, GOLDEN) == []
    moved = json.loads(json.dumps(GOLDEN))
    moved["identities"]["node_types"] = [
        entry
        for entry in moved["identities"]["node_types"]
        if entry[0] not in {"looping_parallax/compose", "movie_sprite/take", "universe/close"}
    ]
    assert checks.identity(loaded["universe"], moved) == [
        "universe: identity node type universe/close is not in the golden inventory"
    ]
    assert checks.identity(loaded["movie-sprite"], moved) == [
        "movie-sprite: identity node type movie_sprite/take is not in the golden inventory"
    ]
    assert checks.identity(loaded["looping-parallax"], moved) == [
        "looping-parallax: identity node type looping_parallax/compose is not in the golden "
        "inventory"
    ]


def test_landing_order_and_covers_are_one_each(loaded: dict[str, LoadedWorkflow]) -> None:
    portrait = loaded["portrait-motion"]
    entry = portrait.discovered.manifest.examples[0]
    clash = _with_manifest(portrait, examples=[entry.model_copy(update={"order": 6})])
    others = [w for key, w in loaded.items() if key != "portrait-motion"]
    problems = checks.examples([clash, *others], _context())
    assert any(
        p.startswith("landing order 6 is claimed by") and "portrait-motion/yuzu-face" in p
        for p in problems
    )
    draft = _with_manifest(portrait, examples=[entry.model_copy(update={"status": "draft"})])
    problems = checks.examples([draft, *others], _context())
    assert "portrait-motion: the cover example must be approved" in problems


def test_an_examples_own_steps_place_each_node_once_and_labels_name_its_nodes() -> None:
    character = next(w for w in discover() if w.id == "character-3d").manifest
    tavi = next(e for e in character.examples if e.id == "tavi-parts")
    assert [s.label for s in tavi.steps][:2] == ["Three meshes", "Before the agent is paid"]
    assert tavi.labels["generate_body"] == "Generate the body" and tavi.footer
    nodes = {member: None for step in tavi.steps for member in step.members}
    document = cast(WorkflowExample, SimpleNamespace(nodes=nodes))
    assert checks._own_steps(tavi, document) == []
    first, *rest = tavi.steps
    moved = first.model_copy(update={"members": [*first.members, "runtime_admit", "nope"]})
    broken = tavi.model_copy(update={"steps": [moved, *rest], "labels": {"ghost": "Ghost"}})
    assert checks._own_steps(broken, document) == [
        "labels names ghost, which is not a node of it",
        "steps must place every node once: unplaced [], unknown ['nope'], "
        "doubled ['runtime_admit']",
    ]


def _sample_plans(loaded: dict[str, LoadedWorkflow]) -> Iterator[tuple[str, LoadedWorkflow]]:
    yield from ((key, w) for key, w in loaded.items() if w.sample is not None)


def test_sample_plans_are_offline_and_every_planned_type_sits_in_a_step(
    loaded: dict[str, LoadedWorkflow],
) -> None:
    planned = dict(_sample_plans(loaded))
    assert set(planned) == WORKFLOWS
    for workflow in planned.values():
        assert workflow.sample is not None
        assert {node.type_id for node in workflow.sample.nodes} <= set(workflow.code.type_ids())


def test_the_script_exports_and_checks_the_catalog(tmp_path: Path) -> None:
    main = _script("catalog").main

    output = io.StringIO()
    argv = ["--out", str(tmp_path / "site")]
    argv += ["--examples", str(tmp_path / "absent"), "--allow-missing-examples"]
    assert main([*argv, "--check"], stdout=output) == 0
    assert json.loads(output.getvalue()) == {
        "workflows": 5,
        "catalog": None,
        "cli": None,
        "problems": [],
    }
    assert not (tmp_path / "site").exists()
    output = io.StringIO()
    assert main(argv, stdout=output) == 0
    written = json.loads((tmp_path / "site/catalog.json").read_text(encoding="utf-8"))
    assert written["kind"] == "stage-gen-catalog-v1" and len(written["workflows"]) == 5
    reference = json.loads((tmp_path / "site/cli.json").read_text(encoding="utf-8"))
    assert reference["kind"] == "gnode-cli-v1" and reference["prog"] == "gnode"
    assert json.loads(output.getvalue())["cli"] == str(tmp_path / "site/cli.json")
    strict = ["--out", str(tmp_path / "strict")]
    strict += ["--examples", str(tmp_path / "absent")]
    output = io.StringIO()
    assert main(strict, stdout=output) == 1
    assert (
        "movie-sprite/yuzu-idle: is pinned but missing from the example store"
        in (json.loads(output.getvalue())["problems"])
    )


def test_a_malformed_game_example_is_a_named_problem_not_a_crash(tmp_path: Path) -> None:
    main = _script("catalog").main

    store = tmp_path / "store"
    (store / "somegame/demo").mkdir(parents=True)
    (store / "somegame/demo/example.json").write_text("{}", encoding="utf-8")
    output = io.StringIO()
    argv = ["--out", str(tmp_path / "site"), "--examples", str(store)]
    assert main([*argv, "--check"], stdout=output) == 1
    problems = json.loads(output.getvalue())["problems"]
    assert any(
        problem.startswith("somegame/demo: unreadable example documents: ") for problem in problems
    )
    assert "movie-sprite/yuzu-idle: is pinned but missing from the example store" in problems


def test_the_script_verifies_library_examples_without_a_store(tmp_path: Path) -> None:
    main = _script("examples").main

    output = io.StringIO()
    argv = ["verify", "character-3d", "--examples", str(tmp_path)]
    assert main(argv, stdout=output, stderr=io.StringIO()) == 0
    assert output.getvalue().splitlines() == [
        "character-3d/wren-brief: missing",
        "character-3d/tavi-parts: missing",
        "character-3d/nami: ok",
        "character-3d/riko: ok",
        "character-3d/helix: ok",
    ]


def _game_store(tmp_path: Path, **entry: object) -> Path:
    """A store holding one example a game made, exported with its entry and page."""
    from stage_gen.examples import (
        FiguresLedger,
        GameExampleEntry,
        MadeBy,
        WorkflowExample,
        document_bytes,
        figures_bytes,
        sha256_bytes,
        write_example,
    )

    made_by = MadeBy(kind="game", id="some-game")
    example = WorkflowExample.model_validate(
        {
            "example_id": "made-in-game",
            "made_by": made_by,
            "importer": "game_importer",
            "delivered_run": "out/game-run",
            "source_runs": [
                {"path": "out/game-run", "anchor": "execution-plan.json", "anchor_sha256": "0" * 64}
            ],
            "source_files": {},
            "status": "succeeded",
            "graph_kind": None,
            "graph_sha256": None,
            "inputs": {},
            "outputs": {},
            "metrics": {},
            "models": [],
            "tree": {},
            "nodes": {},
        }
    )
    ledger = FiguresLedger(run="out/game-run", files=[])
    fields: dict[str, object] = {
        "made_by": made_by,
        "game_title": "Some Game",
        "title": "Made in a game",
        "promise": "A whole game package in. One example out.",
        "order": 1,
        "related": ["looping-parallax"],
        "command": "demo-games generate --input my-game",
        "currency": "earlier_version",
        "example_sha256": sha256_bytes(document_bytes(example)),
        "figures_sha256": sha256_bytes(figures_bytes(ledger)),
        **entry,
    }
    directory = tmp_path / "store" / "some-game" / "made-in-game"
    write_example(directory, example, ledger, entry=GameExampleEntry.model_validate(fields))
    (directory / "page.mdx").write_text("The game's page.\n", encoding="utf-8")
    return tmp_path / "store"


def test_examples_a_game_wrote_are_listed_generically_with_their_entry(tmp_path: Path) -> None:
    catalog, problems = build(examples_dir=_game_store(tmp_path), allow_missing_examples=True)
    assert problems == []
    (game,) = catalog["game_examples"]
    assert (game["owner"], game["id"], game["page"]) == ("some-game", "made-in-game", "page.mdx")
    assert game["currency"] == "earlier_version" and game["entry"]["game_title"] == "Some Game"
    assert [card["order"] for card in catalog["cards"]] == [1, 5, 6, 7, 8]
    card = catalog["cards"][0]
    assert (card["made_inside"], card["workflow"], card["example"]) == (
        "Some Game",
        None,
        "made-in-game",
    )
    assert {card["made_inside"] for card in catalog["cards"][1:]} == {None}


def test_a_game_entry_is_held_to_its_pins_relations_and_landing_order(tmp_path: Path) -> None:
    store = _game_store(tmp_path, related=["no-such-workflow"], order=5, example_sha256="1" * 64)
    _, problems = build(examples_dir=store, allow_missing_examples=True)
    prefix = "some-game/made-in-game: "
    assert f"{prefix}related names unknown workflow no-such-workflow" in problems
    assert any(p.startswith(f"{prefix}example.json sha256") for p in problems)
    assert "landing order 5 is claimed by some-game/made-in-game, portrait-motion/yuzu-face" in (
        problems
    )

    main = _script("examples").main

    output = io.StringIO()
    argv = ["verify", "some-game", "--examples", str(store)]
    assert main(argv, stdout=output, stderr=io.StringIO()) == 1
    assert "differs from its pin" in output.getvalue()
