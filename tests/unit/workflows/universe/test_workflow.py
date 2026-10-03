"""Universe through gnode, offline: every paid call answered by a stand-in, the world admitted,
one reviewed image per entity, and the gallery packaged and viewed."""

from __future__ import annotations

import io
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from gnode import (
    CallRecord,
    FileValue,
    HostServices,
    Plan,
    Route,
    RunOutcome,
    WorkflowRun,
    plan_async,
    project_run,
    verify_run,
    view_contexts,
)
from stage_gen.workflows.universe import models
from tests.unit.workflows.universe._universe_fixture import entity_direction

REPOSITORY = Path(__file__).resolve().parents[4]
LANTERN = REPOSITORY / "src/stage_gen/workflows/universe/inputs/lantern_ferry/inputs.yaml"
ADMITTED = json.loads(
    (
        REPOSITORY / "tests/contract/fixtures/universe/lantern_ferry.admitted-universe.json"
    ).read_text(encoding="utf-8")
)


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("_STAGE_GEN_DISABLE_DOTENV", "1")


def _grammar() -> dict[str, Any]:
    return models.GlobalDirection(
        universe_id="lantern_ferry",
        medium_id="anime_2d",
        world_silhouette_language="low hulls and tall lantern posts against flat banks",
        architecture_grammar="timber landings on piles",
        costume_grammar="oilcloth and wool",
        material_language="tarred timber, glass, rope",
        palette_by_region=[
            models.RegionPalette(region="Tallow Landing", palette="ochre and grey"),
            models.RegionPalette(region="Kestwick", palette="slate and moss"),
        ],
        scale_anchors="a person beside a lantern post",
        technology_and_ecology_rules="no engines; the river moves its bed",
        forbidden_substitutions=["stone bridge", "steamboat", "harbour crane"],
        poster_observation_ids_used=["poster_hung_lantern"],
    ).model_dump(mode="json")


def _review(entity_id: str, verdict: str) -> dict[str, Any]:
    grade = "fail" if verdict == "reject" else "pass"
    return models.ImageReview(
        review_id="universe_independent_image_review",
        entity_id=entity_id,
        verdict=verdict,
        entity_identity=grade,
        action_legibility="pass",
        medium_fidelity="pass",
        register_fidelity="pass",
        readable_text_absent="pass",
        explanatory_form_absent="pass",
        technical_quality="pass",
        blocking_findings=["the subject reads as generic"] if verdict == "reject" else [],
        advisory_findings=[],
        what_the_image_teaches="how the ferry crosses",
    ).model_dump(mode="json")


SEMANTIC_REVIEW = models.SemanticReview(
    review_id="universe_independent_semantic_review",
    reviewer_role="independent_semantic_reviewer",
    verdict="pass",
    checks=[
        models.ReviewCheck(check_id=f"check_{n}", status="pass", finding="holds") for n in range(6)
    ],
    blocking_findings=[],
    advisory_findings=[],
    conclusion="explorable",
).model_dump(mode="json")


def _schema_title(schema: FileValue) -> str:
    assert schema.location is not None
    return str(json.loads(Path(schema.location).read_text(encoding="utf-8"))["title"])


class Stand_in:
    """Answers each structured call by the schema it names, and draws flat pictures."""

    def __init__(self, *, rejected: frozenset[str] = frozenset()) -> None:
        self.rejected = rejected
        self.calls: list[tuple[str, str]] = []

    def services(self, plan: Plan) -> HostServices:
        store = plan.planner.store

        async def structured(route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
            schema = request["schema"]
            assert isinstance(schema, FileValue)
            title = _schema_title(schema)
            prompt = str(request["prompt"])
            self.calls.append(("structured.generate", title))
            bound = re.search(r"(?:Bound|Required) entity_id: (\w+)", prompt)
            answer = {
                "UniverseProposal": ADMITTED["proposal"],
                "GalleryPlan": ADMITTED["plan"],
                "SemanticReview": SEMANTIC_REVIEW,
                "GlobalDirection": _grammar(),
            }.get(title)
            if title == "EntityDirection":
                assert bound is not None
                answer = entity_direction(bound[1], "a clear dry day on the landing").model_dump(
                    mode="json"
                )
            if title == "ImageReview":
                assert bound is not None
                answer = _review(bound[1], "reject" if bound[1] in self.rejected else "admit")
            assert answer is not None, title
            return CallRecord({}, {"json": answer}, 0.01)

        async def image(route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
            self.calls.append(("image.generate", str(request["size"])))
            width, height = (int(n) // 16 for n in str(request["size"]).split("x"))
            buffer = io.BytesIO()
            Image.new("RGB", (width, height), (90, 110, 140 + take)).save(buffer, "PNG")
            return CallRecord(
                {"image": store.put_bytes(buffer.getvalue(), kind="image/png", name="image")},
                None,
                0.2,
            )

        return HostServices(
            store=store,
            capabilities={"structured.generate": structured, "image.generate": image},
            live=True,
        )


async def _run(tmp_path: Path, stand_in: Stand_in) -> tuple[Plan, RunOutcome]:
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    (project / "gnode.yaml").write_text("gnode: project/v1\n", encoding="utf-8")
    plan = await plan_async("universe", input_files=[LANTERN], cwd=project)
    assert plan.ok, plan.problems
    run = WorkflowRun(plan, run_dir=project / "runs/one", services=stand_in.services(plan))
    return plan, await run.run()


async def test_the_world_is_admitted_and_each_entity_gets_one_reviewed_image(
    tmp_path: Path,
) -> None:
    rejected = frozenset({ADMITTED["plan"]["plans"][0]["entity_id"]})
    stand_in = Stand_in(rejected=rejected)
    _plan, outcome = await _run(tmp_path, stand_in)

    assert outcome.ok, outcome.failed
    entities = [entry["entity_id"] for entry in ADMITTED["plan"]["plans"]]
    images = [size for capability, size in stand_in.calls if capability == "image.generate"]
    assert len(images) == len(entities)
    manifest = json.loads((outcome.run_dir / "outputs/manifest.json").read_text())
    assert manifest["publication_authorized"] is False
    statuses = {key: facts["status"] for key, facts in manifest["entities"].items()}
    assert statuses == {e: "rejected" if e in rejected else "admitted" for e in entities}
    gallery = outcome.run_dir / "outputs/gallery"
    for entity_id in entities:
        assert (gallery / f"entities/{entity_id}.png").is_file()
        assert (gallery / f"entities/{entity_id}.md").read_text().startswith("# ")
    assert verify_run(outcome.run_dir) == []

    (whole,) = [c for c in view_contexts(outcome.run_dir) if c["scope"] == "workflow"]
    keys = [instance["key"] for instance in whole["steps"]["entity"]["instances"]]
    assert keys == entities
    assert whole["outputs"]["universe"]["value"]["universe_id"] == "lantern_ferry"


async def test_a_second_run_is_answered_from_the_cache(tmp_path: Path) -> None:
    first = Stand_in()
    await _run(tmp_path, first)
    again = Stand_in()
    project = tmp_path / "project"
    plan = await plan_async("universe", input_files=[LANTERN], cwd=project)
    outcome = await WorkflowRun(
        plan, run_dir=project / "runs/two", services=again.services(plan)
    ).run()

    assert outcome.ok and again.calls == []
    # ``source`` runs while planning (``at: plan``), so the run itself never starts it.
    ran = [
        node
        for node in project_run(outcome.run_dir).nodes
        if node.state == "succeeded" and node.node_id != "world.source#1"
    ]
    assert {node.cache for node in ran} == {"hit"}
