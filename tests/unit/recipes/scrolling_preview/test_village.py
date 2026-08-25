"""Contract coverage for the optional village hub.

The village is purely additive: it adds artifacts and stages and changes nothing a run already
produced. Almost every test here exists to hold that claim to its literal meaning rather than its
spirit - the graph a village-less run resolves is asserted to be the *same object* the recipe has
always declared, and the manifest a village-less run writes is asserted byte-for-byte against the
manifest the same directory writes with the feature switched on. A regression in either would be
invisible from a village run, and would silently invalidate the cached artifacts of every run that
never asked for a village.

The second theme is that the village borrows rather than reimplements. Its grids, its facing
review, its scale reference and its per-cell fallback are the hunting run's, so those are asserted
against their hunting counterparts (`contract_for_stage("village-npc-0-idle") ==
contract_for_stage("mob-idle-0")`) instead of against transcribed literals. A transcribed literal
would keep passing after the two drifted apart, which is exactly the failure the shared branches in
`raster_contracts` were written to prevent.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

import stage_gen.recipes.scrolling_preview.executor as executor_module
import stage_gen.recipes.scrolling_preview.manifest as manifest_module
from stage_gen.recipes.base import StageContext, StageSpec, resolve_force_stage_plan
from stage_gen.recipes.scrolling_preview.models import ANATOMICAL_NOUNS, WorldSpec
from stage_gen.recipes.scrolling_preview.proportion import character_proportion_prompt
from stage_gen.recipes.scrolling_preview.raster_contracts import (
    contract_for_runtime_role,
    contract_for_stage,
)
from stage_gen.recipes.scrolling_preview.recipe import (
    parse_scrolling_preview_input,
    scrolling_preview_recipe,
    scrolling_preview_tag,
)
from stage_gen.recipes.scrolling_preview.review_criteria import reviews_facing
from stage_gen.recipes.scrolling_preview.scale_reference import (
    measures_scale_reference,
    scale_reference_frame,
)
from stage_gen.recipes.scrolling_preview.stages import STAGES, scrolling_preview_stages
from stage_gen.recipes.scrolling_preview.village import (
    RESIDENT_BODY_PLAN_NOUNS,
    VILLAGE_MANIFEST_SCHEMA_VERSION,
    VILLAGE_NPC_COUNT,
    VILLAGE_SPEC_SCHEMA_NAME,
    VillageSpec,
    npc_turnaround_subject,
    parse_village_opt_in,
    village_enabled,
    village_manifest_block,
)

VILLAGE_OPT_IN: dict[str, object] = {"schema_version": 1, "kind": "village_hub_v1"}

#: The graph the recipe has declared since before the village existed, transcribed rather than
#: derived. A test that rebuilt this from `STAGES` would agree with any change made to `STAGES`,
#: including one that reordered or re-wired the hunting run while a village was absent - which is
#: the single regression the village must never cause, because it would invalidate the cached
#: artifacts of every existing run.
LEGACY_GRAPH: tuple[tuple[str, float, tuple[str, ...]], ...] = (
    ("concept", 1, ()),
    ("world-spec", 1.5, ("concept",)),
    ("wave-a", 2, ("world-spec",)),
    ("wave-b", 3, ("wave-a",)),
    ("post-split", 4, ("wave-b",)),
    ("manifest", 5, ("post-split",)),
)

_NPC_BODY_PLANS = ("stocky humanoid", "tall bipedal", "winged avian", "reptilian lizard")
_NPC_ROLE_LABELS = ("Provisioner", "Toolwright", "Archivist", "Ferrier")
_NPC_NAMES = ("Bela Ash", "Oro Kem", "Sable Wren", "Tomas Reed")
_FIXTURE_NAMES = (
    "Awning stall",
    "Stone well",
    "Notice post",
    "Hand cart",
    "Drying rack",
    "Rope winch",
    "Grain bin",
    "Lamp post",
)


async def _village_concept_specs(run_dir: Path, **input_overrides: Any) -> list[Any]:
    """Capture the specs `village-concepts` would fan out, without calling a provider."""

    from PIL import Image

    from stage_gen.config import StageGenConfig, TransparencyMode

    tag = "kettle"
    (run_dir / f"village_spec_{tag}.json").write_text(
        json.dumps(village_payload()), encoding="utf-8"
    )
    Image.new("RGB", (16, 16), (10, 20, 30)).save(run_dir / f"concept_{tag}.png")

    # The services are never reached: `_fan_out` is replaced before any spec is generated, and
    # `_village_concepts` only reads the bible and assembles specs before calling it.
    executor = executor_module.ScrollingPreviewExecutor(
        image_service=cast(Any, object()),
        structured_service=cast(Any, object()),
    )
    captured: list[Any] = []

    async def capture(_self: Any, _context: Any, specs: Any) -> tuple[str, ...]:
        captured.extend(specs)
        return ()

    original = executor_module.ScrollingPreviewExecutor._fan_out
    executor_module.ScrollingPreviewExecutor._fan_out = capture  # type: ignore[assignment]
    try:
        await executor._village_concepts(
            StageContext(
                input={"prompt": "original ridge crossing", **input_overrides},
                tag=tag,
                run_dir=run_dir,
                config=StageGenConfig(out_dir=run_dir, transparency_mode=TransparencyMode.CHROMA),
            )
        )
    finally:
        executor_module.ScrollingPreviewExecutor._fan_out = original  # type: ignore[method-assign]
    return captured


def village_payload(**overrides: Any) -> dict[str, Any]:
    """A roster that satisfies every distinguishability rule, so a test can break exactly one."""

    payload: dict[str, Any] = {
        "name": "Kettlebrook",
        "one_liner": "A quiet crossing where nothing is hunted.",
        "narrative": "Four trades share one square between the ridges.",
        "fixtures_theme": "riverside market furniture",
        "npcs": [
            {
                "role_label": role_label,
                "name": name,
                "body_plan": body_plan,
                "brief": f"Original townsfolk direction for {name}.",
                "greeting": f"{name} greets you.",
                "remark": f"{name} mentions the weather.",
                "farewell": f"{name} says goodbye.",
            }
            for role_label, name, body_plan in zip(
                _NPC_ROLE_LABELS, _NPC_NAMES, _NPC_BODY_PLANS, strict=True
            )
        ],
        "fixtures": [
            {"name": name, "brief": f"A readable isolated {name.lower()}."}
            for name in _FIXTURE_NAMES
        ],
    }
    payload.update(overrides)
    return payload


def _npcs(**per_index: dict[str, Any]) -> list[dict[str, Any]]:
    """The canonical roster with named fields replaced on named residents."""

    npcs = [dict(npc) for npc in village_payload()["npcs"]]
    for index, changes in per_index.items():
        npcs[int(index)].update(changes)
    return npcs


def _graph(**opt_ins: Any) -> tuple[StageSpec, ...]:
    return scrolling_preview_stages({"prompt": "original ridge crossing", **opt_ins})


def _table(stages: tuple[StageSpec, ...]) -> tuple[tuple[str, float, tuple[str, ...]], ...]:
    return tuple((stage.name, stage.wave, stage.depends_on) for stage in stages)


def _without_village(stages: tuple[StageSpec, ...]) -> tuple[StageSpec, ...]:
    """The same graph with every village stage and the manifest's village edge removed.

    Composition is asserted by subtraction rather than by transcribing an expected table per
    combination, because the point being proved is that the village is additive under *every*
    branch of `scrolling_preview_stages` - a transcribed table proves only that one combination
    produces the constant it was written against. Whole `StageSpec`s are compared rather than a
    projection of them, so a village splice that rewrote a hunting stage's description or swapped
    its `run` callable is caught as readily as one that changed its wave.
    """

    return tuple(
        replace(
            stage,
            depends_on=tuple(name for name in stage.depends_on if name != "village-strips"),
        )
        if stage.name == "manifest"
        else stage
        for stage in stages
        if not stage.name.startswith("village-")
    )


class TestVillageSchema:
    """Every rule here refuses a roster that would render as one resident repeated four times."""

    def test_a_distinguishable_roster_parses_and_pins_the_locked_constants(self) -> None:
        spec = VillageSpec.model_validate(village_payload())

        assert VILLAGE_SPEC_SCHEMA_NAME == "scrolling_preview_village_v1"
        assert VILLAGE_NPC_COUNT == 4
        assert VILLAGE_MANIFEST_SCHEMA_VERSION == 2
        assert len(spec.npcs) == VILLAGE_NPC_COUNT
        assert len(spec.fixtures) == 8
        assert [npc.role_label for npc in spec.npcs] == list(_NPC_ROLE_LABELS)

    def test_duplicate_resident_names_are_rejected_case_insensitively(self) -> None:
        with pytest.raises(ValidationError, match="village npc names must be unique"):
            VillageSpec.model_validate(
                village_payload(npcs=_npcs(**{"2": {"name": _NPC_NAMES[0].upper()}}))
            )

    def test_duplicate_role_labels_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="village npc role labels must be unique"):
            VillageSpec.model_validate(
                village_payload(npcs=_npcs(**{"3": {"role_label": _NPC_ROLE_LABELS[1]}}))
            )

    @pytest.mark.parametrize(
        "body_plan",
        [
            "elderly human baker",
            "stout dwarf smith",
            "young girl scribe",
            "small mouse child",
            "broad badger smith",
            "weathered elf forager",
            "plump hedgehog cook",
            "old woman weaver",
        ],
    )
    def test_ordinary_people_are_accepted_as_bodies(self, body_plan: str) -> None:
        """The vocabulary must describe a census, not only a bestiary.

        `ANATOMICAL_NOUNS` was written to stop a *mob* roster collapsing into vague masses, so it
        names `humanoid`, `insectoid` and `draconic` but no `human`, `dwarf`, `child`, `mouse` or
        `badger`. Reused unchanged for townsfolk it rejected every plausible answer, and the first
        live village spent all six provider attempts failing schema validation before it reached a
        single image call. Residents validate against the widened union; mobs do not.
        """

        roster = village_payload()
        roster["npcs"][0]["body_plan"] = body_plan
        assert VillageSpec.model_validate(roster).npcs[0].body_plan == body_plan

    def test_widening_the_resident_vocabulary_left_the_mob_rule_alone(self) -> None:
        """The mob contract is working and is not what failed, so it must not have moved."""

        assert RESIDENT_BODY_PLAN_NOUNS > ANATOMICAL_NOUNS
        for people_noun in ("human", "dwarf", "child", "mouse", "badger", "woman"):
            assert people_noun in RESIDENT_BODY_PLAN_NOUNS
            assert people_noun not in ANATOMICAL_NOUNS

    def test_a_body_plan_naming_no_anatomy_is_rejected(self) -> None:
        # "cheerful and weathered" is prose about mood and profession: an image model answers it
        # with a generic human, which is how a roster collapses into one repeated resident.
        # Still rejected after the vocabulary was widened for people - widening added nouns a
        # census uses, it did not stop requiring that a body be named at all.
        with pytest.raises(ValidationError, match="must name a body"):
            VillageSpec.model_validate(
                village_payload(npcs=_npcs(**{"1": {"body_plan": "cheerful and weathered"}}))
            )

    def test_consecutive_residents_may_not_share_a_body_plan(self) -> None:
        with pytest.raises(
            ValidationError, match=r"npcs\[2\]\.body_plan must differ from npcs\[1\]\.body_plan"
        ):
            VillageSpec.model_validate(
                village_payload(npcs=_npcs(**{"2": {"body_plan": _NPC_BODY_PLANS[1]}}))
            )

    def test_a_repeated_body_plan_two_entries_apart_is_allowed(self) -> None:
        # Deliberately the weaker half of the check, kept identical to the mob rule: a generator
        # that has just written "humanoid" writes it again far more readily than it repeats it
        # two entries later, and the uniqueness rules above carry the rest.
        spec = VillageSpec.model_validate(
            village_payload(npcs=_npcs(**{"2": {"body_plan": _NPC_BODY_PLANS[0]}}))
        )
        assert spec.npcs[2].body_plan == _NPC_BODY_PLANS[0]

    def test_duplicate_fixture_names_are_rejected(self) -> None:
        fixtures = [dict(fixture) for fixture in village_payload()["fixtures"]]
        fixtures[5]["name"] = _FIXTURE_NAMES[0].lower()
        with pytest.raises(ValidationError, match="village fixture names must be unique"):
            VillageSpec.model_validate(village_payload(fixtures=fixtures))

    @pytest.mark.parametrize("count", [3, 5])
    def test_the_resident_count_is_exact(self, count: int) -> None:
        npcs = _npcs()
        roster = npcs[:count] if count < len(npcs) else [*npcs, {**npcs[0], "name": "Extra"}]
        with pytest.raises(ValidationError):
            VillageSpec.model_validate(village_payload(npcs=roster))

    @pytest.mark.parametrize("count", [7, 9])
    def test_the_fixture_count_is_exact_because_the_sheet_has_eight_cells(self, count: int) -> None:
        # The grid contract rejects an empty cell outright, so a roster that does not fill the
        # 2-row x 4-column sheet cannot produce a passing asset at all.
        fixtures = [dict(fixture) for fixture in village_payload()["fixtures"]]
        roster = (
            fixtures[:count]
            if count < len(fixtures)
            else [*fixtures, {"name": "Spare", "brief": "One cell too many."}]
        )
        with pytest.raises(ValidationError):
            VillageSpec.model_validate(village_payload(fixtures=roster))

    @pytest.mark.parametrize("field", ["greeting", "remark", "farewell"])
    def test_a_spoken_line_longer_than_the_dialogue_box_is_rejected(self, field: str) -> None:
        # A layout fact, not a style preference: the runtime dialogue box is one screen-fixed line
        # across the bottom of the viewport, and an overflowing line is one the player cannot read.
        with pytest.raises(ValidationError):
            VillageSpec.model_validate(village_payload(npcs=_npcs(**{"0": {field: "x" * 161}})))
        VillageSpec.model_validate(village_payload(npcs=_npcs(**{"0": {field: "x" * 160}})))

    def test_unknown_keys_and_camel_case_aliases_are_refused(self) -> None:
        with pytest.raises(ValidationError):
            VillageSpec.model_validate(village_payload(unexpected="value"))
        with pytest.raises(ValidationError):
            VillageSpec.model_validate(
                village_payload(npcs=_npcs(**{"0": {"roleLabel": "Provisioner"}}))
            )


class TestOptIn:
    def test_the_exact_versioned_object_is_accepted_and_copied(self) -> None:
        parsed = parse_village_opt_in(dict(VILLAGE_OPT_IN))
        assert parsed == VILLAGE_OPT_IN
        parsed["kind"] = "mutated"
        assert parse_village_opt_in(dict(VILLAGE_OPT_IN)) == VILLAGE_OPT_IN

    @pytest.mark.parametrize(
        "value",
        [
            True,
            "village_hub_v1",
            {},
            {"schema_version": 1},
            {"kind": "village_hub_v1"},
            {"schema_version": 2, "kind": "village_hub_v1"},
            {"schema_version": 1, "kind": "village_hub_v2"},
            {"schema_version": 1, "kind": "village_hub_v1", "npcs": 8},
            {"schemaVersion": 1, "kind": "village_hub_v1"},
        ],
        ids=[
            "bare-true",
            "bare-string",
            "empty",
            "missing-kind",
            "missing-version",
            "wrong-version",
            "later-kind",
            "superset",
            "camel-case",
        ],
    )
    def test_near_misses_are_rejected_rather_than_coerced(self, value: object) -> None:
        # A silently ignored key here would mean a run that generated something other than what
        # was asked for, so a superset is refused exactly as firmly as a wrong kind.
        with pytest.raises(ValueError, match="scrolling-preview village must equal"):
            parse_village_opt_in(value)
        with pytest.raises(ValueError):
            parse_scrolling_preview_input({"prompt": "original ridge crossing", "village": value})

    def test_recipe_input_echoes_the_opt_in_and_leaves_a_village_less_input_untouched(self) -> None:
        legacy = parse_scrolling_preview_input({"prompt": "original ridge crossing"})
        assert legacy == {"prompt": "original ridge crossing"}
        assert village_enabled(legacy) is False

        parsed = parse_scrolling_preview_input(
            {"prompt": "original ridge crossing", "village": dict(VILLAGE_OPT_IN)}
        )
        assert parsed == {"prompt": "original ridge crossing", "village": VILLAGE_OPT_IN}
        assert village_enabled(parsed) is True

    def test_the_village_is_the_one_opt_in_that_does_not_fork_the_run_directory(self) -> None:
        # Deliberate, and the reason enabling the village on an existing run costs one structured
        # call plus nine image calls instead of a regeneration: the village only ever adds
        # artifacts, so a suffix would fork the directory and leave the same world in two places.
        legacy = parse_scrolling_preview_input({"prompt": "original ridge crossing"})
        villaged = parse_scrolling_preview_input(
            {"prompt": "original ridge crossing", "village": dict(VILLAGE_OPT_IN)}
        )
        assert scrolling_preview_tag(villaged) == scrolling_preview_tag(legacy)


class TestStageGraph:
    def test_a_village_less_run_resolves_the_identical_legacy_graph_object(self) -> None:
        # The strongest available statement of "purely additive": not an equal graph, the same
        # object the recipe has always declared, still wired exactly as transcribed above.
        legacy = _graph()
        assert legacy is STAGES
        assert _table(legacy) == LEGACY_GRAPH
        assert scrolling_preview_recipe.stages_for({"prompt": "original ridge crossing"}) is STAGES

    def test_the_village_stages_run_after_the_whole_mandatory_graph(self) -> None:
        """An optional feature must not be able to abort the mandatory one.

        `orchestration/runner.py` walks this tuple strictly sequentially and breaks on the first
        failure, so wave numbers order execution rather than overlapping it. Placing the village
        stages between the hunting waves - where their dependencies alone would allow them - buys
        no concurrency and lets a failed village bible destroy a run before Wave A draws anything.
        Last-but-one is the only placement whose blast radius is "no village".
        """

        stages = _graph(village=dict(VILLAGE_OPT_IN))

        assert _table(stages) == (
            ("concept", 1, ()),
            ("world-spec", 1.5, ("concept",)),
            ("wave-a", 2, ("world-spec",)),
            ("wave-b", 3, ("wave-a",)),
            ("post-split", 4, ("wave-b",)),
            ("village-spec", 4.1, ("concept", "post-split")),
            ("village-concepts", 4.2, ("village-spec",)),
            ("village-strips", 4.3, ("village-concepts",)),
            ("manifest", 5, ("post-split", "village-strips")),
        )

    def test_every_village_stage_follows_the_last_mandatory_artifact_stage(self) -> None:
        """Stated as a property, so a future wave edit cannot quietly reintroduce the defect."""

        stages = _graph(village=dict(VILLAGE_OPT_IN))
        order = [stage.name for stage in stages]
        last_mandatory = order.index("post-split")
        for name in ("village-spec", "village-concepts", "village-strips"):
            assert order.index(name) > last_mandatory, f"{name} precedes post-split"
        assert order.index("manifest") == len(order) - 1

    def test_the_manifest_gains_its_village_edge_only_when_the_village_is_enabled(self) -> None:
        # The manifest enumerates published artifacts, so a village stage running after it would
        # leave its artwork out of the very file the runtime reads to find it.
        by_name = {stage.name: stage for stage in _graph()}
        assert by_name["manifest"].depends_on == ("post-split",)
        villaged = {stage.name: stage for stage in _graph(village=dict(VILLAGE_OPT_IN))}
        assert villaged["manifest"].depends_on == ("post-split", "village-strips")

    @pytest.mark.parametrize(
        "opt_ins",
        [
            {},
            {"theme": {"hostile_action": 3}},
            {"style_anchor": {"schema_version": 1, "kind": "automatic_style_anchor_v1"}},
            {
                "character_profile": {
                    "schema_version": 1,
                    "kind": "character-profile-binding-v1",
                    "ref": "library/characters/mira-vale-cartographer/profile.toml",
                    "source_sha256": "a" * 64,
                }
            },
            {
                "theme": {"hostile_action": 3},
                "style_anchor": {"schema_version": 1, "kind": "automatic_style_anchor_v1"},
            },
            {
                "theme": {"hostile_action": 3},
                "style_anchor": {"schema_version": 1, "kind": "automatic_style_anchor_v1"},
                "character_profile": {
                    "schema_version": 1,
                    "kind": "character-profile-binding-v1",
                    "ref": "library/characters/mira-vale-cartographer/profile.toml",
                    "source_sha256": "a" * 64,
                },
            },
        ],
        ids=["bare", "theme", "style", "profile", "theme-style", "theme-style-profile"],
    )
    def test_the_village_composes_over_every_other_branch_without_disturbing_it(
        self, opt_ins: dict[str, Any]
    ) -> None:
        # `scrolling_preview_stages` branches on theme, style and profile before it splices the
        # village in, so each branch is a separate opportunity for the splice to reorder or
        # re-wire a hunting stage. Subtracting the village back out must return the exact graph
        # the same input resolves without it.
        without = _graph(**opt_ins)
        with_village = _graph(**opt_ins, village=dict(VILLAGE_OPT_IN))

        assert _without_village(with_village) == without
        assert [stage.name for stage in with_village if stage.name.startswith("village-")] == [
            "village-spec",
            "village-concepts",
            "village-strips",
        ]

    @pytest.mark.parametrize(
        "opt_ins",
        [
            {},
            {"theme": {"hostile_action": 3}},
            {"style_anchor": {"schema_version": 1, "kind": "automatic_style_anchor_v1"}},
        ],
        ids=["bare", "theme", "style"],
    )
    def test_the_composed_graph_is_a_valid_dag_in_execution_order(
        self, opt_ins: dict[str, Any]
    ) -> None:
        # The runner executes the tuple in order, so a village stage sorted ahead of a dependency
        # would deadlock the run rather than fail it. `resolve_force_stage_plan` refuses an
        # undeclared dependency and a cycle, and the wave order must already be topological.
        stages = _graph(**opt_ins, village=dict(VILLAGE_OPT_IN))
        resolve_force_stage_plan(stages, ())
        seen: set[str] = set()
        for stage in stages:
            assert set(stage.depends_on) <= seen
            seen.add(stage.name)

    def test_forcing_the_village_bible_regenerates_only_the_village_and_the_manifest(self) -> None:
        stages = _graph(village=dict(VILLAGE_OPT_IN))
        plan = resolve_force_stage_plan(stages, ("village-spec",))

        assert plan.affected == {
            "village-spec",
            "village-concepts",
            "village-strips",
            "manifest",
        }


class TestStageNameSwitchSites:
    """Every switch keyed on a stage or runtime-role name has to have learned the new names.

    Asserted against the hunting counterparts rather than against transcribed geometry, because
    the village stages are folded into those branches precisely so the two cannot drift: a village
    grid that quietly stopped matching a mob grid would break per-cell isolation and the camera
    check in a way only a generated sheet would reveal.
    """

    @pytest.mark.parametrize("slot", range(VILLAGE_NPC_COUNT))
    def test_a_resident_turnaround_is_contracted_as_a_creature_turnaround(self, slot: int) -> None:
        contract = contract_for_stage(f"village-npc-concept-{slot}")
        assert contract == contract_for_stage(f"mob-concept-{slot}")
        assert contract is not None
        assert (contract.rows, contract.columns, contract.gutter) == (1, 3, 8)
        assert contract.anchor == "bottom"
        assert contract_for_runtime_role(f"village-npc-concept-{slot}") == contract

    @pytest.mark.parametrize("slot", range(VILLAGE_NPC_COUNT))
    def test_a_resident_idle_strip_is_contracted_as_a_mob_idle_strip(self, slot: int) -> None:
        contract = contract_for_stage(f"village-npc-{slot}-idle")
        assert contract == contract_for_stage(f"mob-idle-{slot}")
        assert contract is not None
        assert (contract.rows, contract.columns, contract.gutter) == (1, 4, 8)
        assert contract.anchor == "bottom"
        # The strip prompt asks for one side view held across four frames, and nothing else in
        # the contract can tell whether the provider honoured that.
        assert contract.fixed_side_view_frames is True
        published = contract_for_runtime_role(f"village-npc-{slot}-idle")
        assert published == contract_for_runtime_role(f"mob-{slot}-idle")
        assert published is not None
        assert (published.rows, published.columns, published.gutter) == (1, 4, 8)
        assert published.anchor == "bottom"
        # The published role describes cell geometry only: the runtime loads an NPC strip through
        # the identical frame-strip path it loads a mob strip through, and the camera constraint
        # is a producer-side check that has already run by then.
        assert published.fixed_side_view_frames is False

    def test_the_fixture_sheet_is_contracted_as_an_obstacle_sheet(self) -> None:
        contract = contract_for_stage("village-fixtures")
        assert contract == contract_for_stage("obstacles-0")
        assert contract is not None
        assert (contract.rows, contract.columns, contract.gutter) == (2, 4, 8)
        assert contract.anchor == "bottom"
        assert contract_for_runtime_role("village-fixtures") == contract_for_runtime_role(
            "obstacles-0"
        )

    def test_only_the_idle_strips_carry_a_facing_contract(self) -> None:
        # A turnaround shows every side by definition, so reviewing one for a single facing would
        # reject the artwork for doing exactly what it was asked to do.
        assert all(
            reviews_facing(f"village-npc-{slot}-idle") is True for slot in range(VILLAGE_NPC_COUNT)
        )
        assert not any(
            reviews_facing(stage)
            for stage in (
                *(f"village-npc-concept-{slot}" for slot in range(VILLAGE_NPC_COUNT)),
                "village-fixtures",
                "village-spec",
                "village-concepts",
                "village-strips",
            )
        )

    def test_only_the_idle_strips_are_head_matched_to_the_player(self) -> None:
        # This is what stops a resident rendering at half or twice the player's height while the
        # two stand side by side in the hub - the first thing anyone sees on entering it.
        for slot in range(VILLAGE_NPC_COUNT):
            stage = f"village-npc-{slot}-idle"
            assert measures_scale_reference(stage) is True
            assert measures_scale_reference(stage) == measures_scale_reference(f"mob-idle-{slot}")
            # The first frame of a loop is its rest pose, where a head is least obscured.
            assert scale_reference_frame(stage) == 0
        assert not any(
            measures_scale_reference(stage)
            for stage in (
                *(f"village-npc-concept-{slot}" for slot in range(VILLAGE_NPC_COUNT)),
                "village-fixtures",
            )
        )

    @pytest.mark.parametrize(
        ("stage", "asset_kind"),
        [
            ("village-npc-concept-0", "concept_art"),
            ("village-npc-concept-3", "concept_art"),
            ("village-npc-0-idle", "character_sprite"),
            ("village-npc-3-idle", "character_sprite"),
            ("village-fixtures", "asset_sheet"),
        ],
    )
    def test_the_asset_kind_branches_order_concept_art_ahead_of_the_sprite_prefix(
        self, stage: str, asset_kind: str
    ) -> None:
        assert executor_module._asset_kind_for_image_stage(stage) == asset_kind

    def test_no_village_stage_is_ever_treated_as_a_player_asset(self) -> None:
        # A resident is not the player and must never pull in the authored character profile.
        assert not any(
            executor_module._is_player_asset_stage(stage)
            for stage in (
                "village-spec",
                "village-concepts",
                "village-strips",
                "village-npc-concept-0",
                "village-npc-0-idle",
                "village-npc-isolated-view-0",
                "village-fixtures",
            )
        )

    def test_a_resident_is_reviewed_as_a_game_character_not_as_a_creature(self) -> None:
        assert executor_module._review_subject("village-npc-0-idle") == "a game character"
        assert executor_module._review_subject("mob-idle-0") == "a creature"

    def test_the_fixture_sheet_reuses_the_obstacle_prop_adapter(self) -> None:
        assert executor_module._uses_prop_sheet_adapter("village-fixtures") is True
        assert executor_module._uses_prop_sheet_adapter("village-npc-concept-0") is False

    def test_a_resident_turnaround_can_degrade_into_separately_generated_views(self) -> None:
        # Without this the difference from the hunting turnarounds would stay invisible until a
        # village run exhausted one, and then the run would fail where a hunting run recovers.
        assert executor_module._is_turnaround_concept_stage("village-npc-concept-0") is True
        assert executor_module._isolated_view_family("village-npc-concept-0") == "village-npc"
        assert executor_module._isolated_view_family("mob-concept-0") == "mob"


class TestManifestProjection:
    def test_only_what_the_runtime_draws_or_speaks_crosses_into_the_manifest(self) -> None:
        spec = VillageSpec.model_validate(village_payload())
        block = village_manifest_block(spec)

        assert block == {
            "schema_version": 2,
            "name": "Kettlebrook",
            "one_liner": "A quiet crossing where nothing is hunted.",
            "fixtures_theme": "riverside market furniture",
            # An undirected run's residents are the strip profile, and the block says so rather
            # than leaving a consumer to infer it from the absence of a field. `frames` is what
            # the web runtime slices the sheet by, so it is never allowed to be a default.
            "render": {
                "frames": 4,
                "orientation": "side",
                "animation": "strip",
                "state": "idle",
            },
            "npcs": [
                {
                    "slot": slot,
                    "name": _NPC_NAMES[slot],
                    "role_label": _NPC_ROLE_LABELS[slot],
                    "lines": [
                        f"{_NPC_NAMES[slot]} greets you.",
                        f"{_NPC_NAMES[slot]} mentions the weather.",
                        f"{_NPC_NAMES[slot]} says goodbye.",
                    ],
                }
                for slot in range(VILLAGE_NPC_COUNT)
            ],
        }
        # Direction for the image model is already spent by the time the artwork exists, and
        # publishing it would invite a consumer to render prompt text as if it were content.
        serialized = json.dumps(block)
        assert "narrative" not in serialized and spec.narrative not in serialized
        assert all(npc.brief not in serialized for npc in spec.npcs)
        assert all(npc.body_plan not in serialized for npc in spec.npcs)

    def test_every_published_key_is_lower_snake_case(self) -> None:
        block = village_manifest_block(VillageSpec.model_validate(village_payload()))

        def assert_snake(value: object) -> None:
            if isinstance(value, dict):
                assert all(not any(char.isupper() for char in key) for key in value)
                for item in value.values():
                    assert_snake(item)
            elif isinstance(value, list):
                for item in value:
                    assert_snake(item)

        assert_snake(block)

    @pytest.mark.parametrize("heads_tall", [2, 2.5, 6])
    async def test_residents_are_drawn_to_the_runs_own_build(
        self, tmp_path: Path, heads_tall: float
    ) -> None:
        """A resident off the run's build is the wrong size, not merely off-style.

        The runtime scales every actor until their heads agree, so proportion decides rendered
        height outright. Measured on the first live village, whose residents did not carry this
        directive: a seven-head elf beside this run's two-head player renders about three and a
        half times the player's height.
        """

        specs = await _village_concept_specs(tmp_path, character_heads_tall=heads_tall)
        expected = character_proportion_prompt(heads_tall)
        residents = [spec for spec in specs if spec.stage.startswith("village-npc-concept-")]

        assert len(residents) == VILLAGE_NPC_COUNT
        for spec in residents:
            assert expected in spec.prompt

    async def test_an_unset_build_leaves_the_residents_to_the_image_model(
        self, tmp_path: Path
    ) -> None:
        """Unset stays exactly the plain turnaround, as it does for the player."""

        specs = await _village_concept_specs(tmp_path)
        for spec in specs:
            if spec.stage.startswith("village-npc-concept-"):
                assert "heads tall" not in spec.prompt

    def test_the_turnaround_subject_carries_the_trade_and_the_anatomy_to_the_image_model(
        self,
    ) -> None:
        # The trade, not the name, is what makes two residents read as different people in a
        # three-view sheet: a trade puts an apron or a ledger into the silhouette.
        spec = VillageSpec.model_validate(village_payload())
        subject = npc_turnaround_subject(spec.npcs[0])

        assert subject == (
            f"Village resident {_NPC_NAMES[0]}, {_NPC_ROLE_LABELS[0]}, {_NPC_BODY_PLANS[0]}. "
            f"Original townsfolk direction for {_NPC_NAMES[0]}."
        )


class TestRuntimeRequirements:
    def test_a_village_less_run_demands_exactly_the_roles_it_always_demanded(
        self, minimal_world: WorldSpec
    ) -> None:
        assert manifest_module._runtime_requirements("t", minimal_world, None) == (
            manifest_module._runtime_requirements("t", minimal_world)
        )
        assert not any(
            requirement.role.startswith("village-")
            for requirement in manifest_module._runtime_requirements("t", minimal_world)
        )

    def test_a_village_appends_nine_sheets_and_moves_nothing_ahead_of_them(
        self, minimal_world: WorldSpec
    ) -> None:
        village = VillageSpec.model_validate(village_payload())
        legacy = manifest_module._runtime_requirements("kettle", minimal_world)
        requirements = manifest_module._runtime_requirements("kettle", minimal_world, village)

        assert requirements[: len(legacy)] == legacy
        added = requirements[len(legacy) :]
        assert len(added) == 9
        assert [
            (item.role, item.path, item.width, item.height, item.alpha, item.metadata)
            for item in added
        ] == [
            *(
                entry
                for slot in range(VILLAGE_NPC_COUNT)
                for entry in (
                    (
                        f"village-npc-concept-{slot}",
                        f"npc_concept_kettle_{slot}.png",
                        2400,
                        800,
                        "transparent",
                        {"slot": slot},
                    ),
                    (
                        f"village-npc-{slot}-idle",
                        f"npc_kettle_{slot}_idle.png",
                        2400,
                        800,
                        "transparent",
                        {"slot": slot, "state": "idle"},
                    ),
                )
            ),
            # One sheet for the whole settlement, so it carries no slot: fixture cells are
            # addressed positionally out of the sheet the way obstacle cells are.
            ("village-fixtures", "village_fixtures_kettle.png", 2400, 800, "transparent", None),
        ]

    def test_every_village_role_publishes_a_grid_the_runtime_already_knows_how_to_load(
        self, minimal_world: WorldSpec
    ) -> None:
        village = VillageSpec.model_validate(village_payload())
        requirements = manifest_module._runtime_requirements("kettle", minimal_world, village)

        for requirement in requirements:
            if not requirement.role.startswith("village-"):
                continue
            contract = contract_for_runtime_role(requirement.role)
            assert contract is not None
            # A published sheet whose declared cells do not divide its canvas cannot be sliced.
            assert requirement.width % contract.columns == 0
            assert requirement.height % contract.rows == 0


class TestSpecOnDisk:
    def test_a_bible_round_trips_through_the_artifact_the_manifest_reads(
        self, tmp_path: Path
    ) -> None:
        # The manifest re-reads and re-validates the artifact rather than trusting the opt-in, so
        # the block it publishes and the nine sheets it demands can never disagree.
        spec = VillageSpec.model_validate(village_payload())
        path = tmp_path / "village_spec_kettle.json"
        path.write_text(spec.model_dump_json(indent=2) + "\n", encoding="utf-8")

        assert manifest_module._read_village_spec(tmp_path, "kettle") == spec

    def test_a_declared_absent_or_unparseable_bible_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="missing or unreadable"):
            manifest_module._read_village_spec(tmp_path, "kettle")

        path = tmp_path / "village_spec_kettle.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(ValueError, match="declared village specification is invalid"):
            manifest_module._read_village_spec(tmp_path, "kettle")

        # A bible that parses as JSON but no longer satisfies the distinguishability rules is
        # refused for the same reason a hand-edited one is: it was never validated.
        path.write_text(
            json.dumps(village_payload(npcs=_npcs(**{"1": {"body_plan": _NPC_BODY_PLANS[0]}}))),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="declared village specification is invalid"):
            manifest_module._read_village_spec(tmp_path, "kettle")


@pytest.fixture
def minimal_world() -> WorldSpec:
    return WorldSpec.model_validate(
        {
            "world": {"name": "Ridge", "one_liner": "A quiet ridge.", "narrative": "Rain falls."},
            "mobs": [
                {
                    "tier_label": "scout",
                    "body_plan": "winged avian",
                    "name": "Mote",
                    "brief": "A pale bird.",
                }
            ],
            "obstacles": [
                {
                    "sheet_theme": "ridge set",
                    "props": [
                        {"name": f"Prop {index}", "brief": "Readable broken cover."}
                        for index in range(8)
                    ],
                }
            ],
            "items": [
                {"kind": kind, "name": kind.title(), "brief": "A distinct collectible."}
                for kind in (
                    "sun-coin",
                    "spore-vial",
                    "rune-shard",
                    "gate-key",
                    "bone-charm",
                    "signal-map",
                    "flint-tool",
                    "thorn-blade",
                )
            ],
            "layers": [
                {
                    "id": "backdrop",
                    "title": "Backdrop",
                    "z_index": 0,
                    "parallax": 0.0,
                    "opaque": True,
                    "paint_region": "full frame",
                    "description": "Ridge architecture.",
                },
                {
                    "id": "near_ridge",
                    "title": "Near Ridge",
                    "z_index": 1,
                    "parallax": 1.8,
                    "opaque": False,
                    "paint_region": "screen edges",
                    "description": "Sparse silhouettes.",
                },
            ],
        }
    )
