"""Every workflow describes itself, and drift between code, manifest, prose and examples fails.

The catalog's drift checks (decision 0071, section 8) run here over the installed workflows
in clean-clone mode, and each check is shown to fail on the drift it names. The example store
is local and ignored: its pinned examples are verified when it is present.
"""

from __future__ import annotations

import ast
import dataclasses
import io
import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

import stage_gen.recipes.character_3d.runner as frozen_runner
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
    load_code,
    repository_root,
)

REPOSITORY = Path(__file__).resolve().parents[2]
STORE = REPOSITORY / "out" / "examples"
GOLDEN = json.loads(
    (REPOSITORY / "tests/contract/fixtures/workflow-identity.json").read_text(encoding="utf-8")
)
WORKFLOWS = {
    "character-3d",
    "looping-parallax",
    "movie-sprite",
    "portrait-motion",
    "storefront",
    "universe",
}
FROZEN_CHARACTER_ROOT = REPOSITORY / "src/stage_gen/recipes/character_3d"
#: The namespace the frozen runner builds every character type id with.
NODE_TYPE_NAMESPACE: str = vars(frozen_runner)["NODE_TYPE_NAMESPACE"]


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
        "yuzu-idle": "current",
        "yuzu-face": "current",
        "wren-brief": "current",
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


def _frozen_node_type_literals() -> set[str]:
    literals: set[str] = set()
    for path in sorted(FROZEN_CHARACTER_ROOT.glob("*.py")):
        for call in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(call, ast.Call)
                and call.args
                and getattr(call.func, "id", getattr(call.func, "attr", None)) == "node_type"
            ):
                literals |= {
                    item.value
                    for item in ast.walk(call.args[0])
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                }
    return literals


def _declared_slugs() -> set[str]:
    code = load_code("character-3d")
    return {m for step in code.steps for m in step.members if isinstance(m, str)}


def test_character_steps_cover_every_slug_the_frozen_source_declares() -> None:
    literals = _frozen_node_type_literals()
    assert {"runtime_admit", "rig_admit", "rig_select", "assembly_select"} <= literals
    assert _declared_slugs() >= literals
    assert load_code("character-3d").member_namespace == NODE_TYPE_NAMESPACE


@pytest.mark.skipif(
    not (STORE / "character-3d/wren-brief/example.json").is_file(),
    reason="the local example store is absent",
)
def test_character_steps_cover_every_type_the_cover_example_ran() -> None:
    example = json.loads((STORE / "character-3d/wren-brief/example.json").read_text())
    ran = {node["type_id"].removeprefix(NODE_TYPE_NAMESPACE) for node in example["nodes"].values()}
    assert all(not slug.startswith(("3d/", "spike/")) for slug in ran)
    assert _declared_slugs() >= ran


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


def test_a_try_command_must_parse_with_the_real_parser(loaded: dict[str, LoadedWorkflow]) -> None:
    good = TryIt(input="inputs", commands=["stage-gen catalog export --out site --check"])
    bad = TryIt(input="inputs", commands=["stage-gen catalog export --no-such-flag"])
    assert checks.try_commands(_with_manifest(loaded["universe"], try_=good)) == []
    [problem] = checks.try_commands(_with_manifest(loaded["universe"], try_=bad))
    assert "does not parse" in problem


def test_every_workflow_says_how_to_try_it_with_its_own_verbs() -> None:
    """Each [try] names its input and uses the workflow's own id with plan or run; the drift
    check above parses every command with the real parser."""
    for workflow in discover():
        assert workflow.manifest.try_ is not None, workflow.id
        assert workflow.manifest.try_.input.strip()
        commands = workflow.manifest.try_.commands
        assert 1 <= len(commands) <= 3, workflow.id
        assert any(
            command.startswith((f"stage-gen plan {workflow.id} ", f"stage-gen run {workflow.id} "))
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
    raw = _with_manifest(loaded["storefront"], title="storefront")
    assert "storefront: title 'storefront' is empty or its raw slug" in checks.structure(raw)
    character = loaded["character-3d"]
    labels = dict(character.discovered.manifest.labels)
    del labels["3d/character/rig_select"]
    unlabelled = _with_manifest(character, labels=labels)
    assert any(
        "3d/character/rig_select has no reader title" in p for p in checks.structure(unlabelled)
    )


def test_labels_only_retitle_types_whose_titles_are_frozen(
    loaded: dict[str, LoadedWorkflow],
) -> None:
    editable = _with_manifest(loaded["looping-parallax"], labels={"parallax.compose": "Compose"})
    assert checks.labels(editable, checks.frozen_files(GOLDEN)) == [
        "looping-parallax: [labels] retitles parallax.compose, whose title is editable in code"
    ]
    frozen = checks.frozen_files(GOLDEN)
    for workflow_id in ("movie-sprite", "portrait-motion", "character-3d"):
        assert set(loaded[workflow_id].code.titles_frozen_in) <= frozen
        assert checks.labels(loaded[workflow_id], frozen) == []
    unknown = _with_manifest(loaded["universe"], labels={"universe/no.such": "Nothing"})
    assert checks.labels(unknown, frozen) == [
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
    edited = readme.replace("| Movie sprite |", "| Movie sprites |")
    [problem] = checks.readme(workflows, edited)
    assert problem.startswith("README.md workflow table differs from workflow.toml")


def test_identity_must_agree_with_the_identity_golden(loaded: dict[str, LoadedWorkflow]) -> None:
    for workflow in loaded.values():
        assert checks.identity(workflow, GOLDEN) == []
    moved = json.loads(json.dumps(GOLDEN))
    moved["identities"]["cache"]["universe_namespace"] = "universe-nodes-v2"
    moved["identities"]["pipelines"]["looping-parallax"]["namespace"] = "pipeline-0"
    assert checks.identity(loaded["universe"], moved) == [
        "universe: identity cache constant universe_namespace differs from the golden"
    ]
    assert checks.identity(loaded["looping-parallax"], moved) == [
        "looping-parallax: identity pipeline looping-parallax differs from the golden"
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
    assert set(planned) == {"looping-parallax", "movie-sprite", "storefront", "universe"}
    for workflow in planned.values():
        assert workflow.sample is not None
        assert {node.type_id for node in workflow.sample.nodes} <= set(workflow.code.type_ids())
    for key in ("portrait-motion", "character-3d"):
        assert loaded[key].sample is None and loaded[key].code.no_sample_plan
    assert loaded["character-3d"].code.plan_refusal is not None
    assert "stage-gen run character-3d --prepare-only" in str(
        loaded["character-3d"].code.plan_refusal
    )


def test_the_cli_exports_and_checks_the_catalog(tmp_path: Path) -> None:
    from stage_gen.interfaces.cli import main

    output, errors = io.StringIO(), io.StringIO()
    argv = ["catalog", "export", "--out", str(tmp_path / "site")]
    argv += ["--examples", str(tmp_path / "absent"), "--allow-missing-examples"]
    assert main([*argv, "--check"], stdout=output, stderr=errors) == 0, errors.getvalue()
    assert json.loads(output.getvalue()) == {
        "workflows": 6,
        "catalog": None,
        "cli": None,
        "problems": [],
    }
    assert not (tmp_path / "site").exists()
    output = io.StringIO()
    assert main(argv, stdout=output, stderr=errors) == 0
    written = json.loads((tmp_path / "site/catalog.json").read_text(encoding="utf-8"))
    assert written["kind"] == "stage-gen-catalog-v1" and len(written["workflows"]) == 6
    reference = json.loads((tmp_path / "site/cli.json").read_text(encoding="utf-8"))
    assert reference["kind"] == "stage-gen-cli-v1" and reference["prog"] == "stage-gen"
    assert json.loads(output.getvalue())["cli"] == str(tmp_path / "site/cli.json")
    strict = ["catalog", "export", "--out", str(tmp_path / "strict")]
    strict += ["--examples", str(tmp_path / "absent")]
    output = io.StringIO()
    assert main(strict, stdout=output, stderr=errors) == 1
    assert (
        "movie-sprite/yuzu-idle: is pinned but missing from the example store"
        in (json.loads(output.getvalue())["problems"])
    )


def test_the_cli_verifies_library_examples_without_a_store(tmp_path: Path) -> None:
    from stage_gen.interfaces.cli import main

    output = io.StringIO()
    argv = ["example", "verify", "character-3d", "--examples", str(tmp_path)]
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

    from stage_gen.interfaces.cli import main

    output = io.StringIO()
    argv = ["example", "verify", "some-game", "--examples", str(store)]
    assert main(argv, stdout=output, stderr=io.StringIO()) == 1
    assert "differs from its pin" in output.getvalue()
