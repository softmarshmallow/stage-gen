"""The runner recipe: plan shape, dry-run execution, and the exported view."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from stage_gen.config import StageGenConfig
from stage_gen.recipes.sideview_runner.prepared_runner import (
    _json_normalize_provider_identity,
    _validate_catalog_candidate,
    _validate_layer_candidate,
    _validate_motion_candidate,
    _validate_motion_source,
    _validate_transparent_sprite,
    canonicalize_runner_catalog_sprite,
    manifest_ground,
    manifest_rebase_multipliers,
)
from stage_gen.recipes.sideview_runner.runner_executor import SideviewRunnerExecutor
from stage_gen.recipes.sideview_runner.runner_graph import runner_graph_profile
from stage_gen.recipes.sideview_runner.runner_view import build_sideview_runner_view

from ..._runner_fixture import two_genre_package


def _executor() -> SideviewRunnerExecutor:
    return SideviewRunnerExecutor(StageGenConfig())


def test_provider_identity_is_exactly_json_round_trip_stable() -> None:
    normalized = _json_normalize_provider_identity(
        {
            "validation": {
                "visible_bbox": (12, 24, 96, 128),
                "nested": {"anchors": ((1, 2), (3, 4))},
            }
        }
    )

    assert normalized == json.loads(json.dumps(normalized))
    assert normalized["validation"] == {
        "visible_bbox": [12, 24, 96, 128],
        "nested": {"anchors": [[1, 2], [3, 4]]},
    }


def _select_structural_ground(package: Path) -> Path:
    track = package / "runner" / "track.toml"
    source = track.read_text(encoding="utf-8")
    track.write_text(
        source.replace(
            'mode = "terrain-atlas-3x3-minimal-v1"',
            'mode = "runner-structural-ground-v1"',
            1,
        ),
        encoding="utf-8",
    )
    return package


def test_plan_refuses_an_image_model_without_verified_native_alpha(tmp_path: Path) -> None:
    executor = SideviewRunnerExecutor(StageGenConfig(openai_image_model="gpt-image-1"))

    with pytest.raises(ValueError, match="native transparent-background support"):
        executor.plan(two_genre_package(tmp_path))


def test_plan_accepts_a_dated_gpt_image_2_native_alpha_route(tmp_path: Path) -> None:
    executor = SideviewRunnerExecutor(StageGenConfig(openai_image_model="gpt-image-2-2026-04-21"))

    plan = executor.plan(two_genre_package(tmp_path))

    assert plan.graph.node("track-ground-generate").model == "gpt-image-2-2026-04-21"


def test_runner_image_profile_declares_the_masked_edit_capability() -> None:
    binding = runner_graph_profile(StageGenConfig()).require("image_generation", "masked_edit")

    assert binding.model.model == "gpt-image-2"


def test_generative_layer_loop_keys_the_declared_fallback(tmp_path: Path) -> None:
    package = two_genre_package(tmp_path)
    track = package / "runner" / "track.toml"
    track.write_text(
        track.read_text().replace(
            'loop_construction = "mirror_repeat"',
            'loop_construction = "generated_bridge"',
        )
    )

    node = _executor().plan(package).graph.node("layer-meadow_sky-loop")

    assert hashlib.sha256(b"mirror_repeat").hexdigest() in node.input_sha256


def test_persisted_track_identity_rekeys_provider_nodes(tmp_path: Path) -> None:
    first_package = two_genre_package(tmp_path / "first")
    second_package = two_genre_package(tmp_path / "second")
    for package in (first_package, second_package):
        track = package / "runner" / "track.toml"
        track.write_text(
            track.read_text().replace(
                'loop_construction = "mirror_repeat"',
                'loop_construction = "generated_bridge"',
            )
        )
    for relative in ("runner/track.toml", "runner/gameplay.toml"):
        path = second_package / relative
        path.write_text(
            path.read_text().replace('track_id = "meadow-dash"', 'track_id = "new-dash"')
        )

    first = _executor().plan(first_package).graph
    second = _executor().plan(second_package).graph
    identity_digest = hashlib.sha256(b"new-dash").hexdigest()
    for node_id in (
        "track-ground-generate",
        "layer-meadow_sky-generate",
        "layer-meadow_sky-loop",
    ):
        assert first.node(node_id).cache_key != second.node(node_id).cache_key
        assert identity_digest in second.node(node_id).input_sha256

    first_structural = (
        _executor()
        .plan(_select_structural_ground(two_genre_package(tmp_path / "first-structural")))
        .graph
    )
    second_structural_package = _select_structural_ground(
        two_genre_package(tmp_path / "second-structural")
    )
    for relative in ("runner/track.toml", "runner/gameplay.toml"):
        path = second_structural_package / relative
        path.write_text(
            path.read_text().replace('track_id = "meadow-dash"', 'track_id = "new-dash"')
        )
    second_structural = _executor().plan(second_structural_package).graph
    structural_id = "track-ground-warmup_flat-generate"
    assert (
        first_structural.node(structural_id).cache_key
        != second_structural.node(structural_id).cache_key
    )
    assert identity_digest in second_structural.node(structural_id).input_sha256


def test_persisted_avatar_identity_rekeys_provider_nodes(tmp_path: Path) -> None:
    first_package = two_genre_package(tmp_path / "first")
    second_package = two_genre_package(tmp_path / "second")
    for relative in ("runner/content/avatar.toml", "game.toml"):
        path = second_package / relative
        path.write_text(
            path.read_text().replace(
                'avatar_id = "wayfarer_sprinter"', 'avatar_id = "renamed_sprinter"'
            )
        )

    first = _executor().plan(first_package).graph
    second = _executor().plan(second_package).graph
    identity_digest = hashlib.sha256(b"renamed_sprinter").hexdigest()
    for node_id in (
        "avatar-concept-generate",
        "avatar-run-generate",
        "avatar-rebase-judge",
        "avatar-rebase-verify",
    ):
        assert first.node(node_id).cache_key != second.node(node_id).cache_key
        assert identity_digest in second.node(node_id).input_sha256


def test_soundtrack_generation_keys_the_complete_provider_prompt(tmp_path: Path) -> None:
    first_package = two_genre_package(tmp_path / "first")
    second_package = two_genre_package(tmp_path / "second")
    soundtrack = second_package / "runner" / "soundtrack.toml"
    source = soundtrack.read_text()
    marker = "target_duration_seconds = "
    start = source.index(marker) + len(marker)
    end = source.index("\n", start)
    duration = int(source[start:end])
    soundtrack.write_text(f"{source[:start]}{duration + 1}{source[end:]}")

    first = _executor().plan(first_package).graph.node("soundtrack-sunpetal_sprint-generate")
    second = _executor().plan(second_package).graph.node("soundtrack-sunpetal_sprint-generate")

    assert first.cache_key != second.cache_key


def test_soundtrack_generation_adds_runner_specific_kinetic_staging(tmp_path: Path) -> None:
    node = (
        _executor()
        .plan(two_genre_package(tmp_path))
        .graph.node("soundtrack-sunpetal_sprint-generate")
    )

    assert node.card is not None and node.card.prompt is not None
    assert "Endless-runner staging" in node.card.prompt
    assert "full rhythmic engine on the first beat" in node.card.prompt
    assert "Do not drift into RPG exploration" in node.card.prompt


def test_ground_validation_keys_the_topology_lookup_resource(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from stage_gen.recipes.sideview_runner import runner_graph

    package = two_genre_package(tmp_path / "package")
    lookup = tmp_path / "lookup.json"
    monkeypatch.setattr(runner_graph, "terrain_atlas_lookup_path", lambda: lookup)
    lookup.write_text('{"version": 1}')
    first = _executor().plan(package).graph
    lookup.write_text('{"version": 2}')
    second = _executor().plan(package).graph

    assert (
        first.node("track-ground-generate").cache_key
        == second.node("track-ground-generate").cache_key
    )
    assert (
        first.node("track-ground-validate").cache_key
        != second.node("track-ground-validate").cache_key
    )


def test_the_plan_states_the_exact_graph_the_member_implies(tmp_path: Path) -> None:
    plan = _executor().plan(two_genre_package(tmp_path))

    graph = plan.graph
    assert graph.kind == "sideview-runner-execution-graph-v1"
    assert graph.recipe == "sideview-runner"
    assert graph.track_id == "meadow-dash"
    assert graph.terminal_node_id == "manifest-assemble"
    operations = Counter(node.operation for node in graph.nodes)
    # 1 ground + 1 layer + 1 concept + 4 motion strips (the declared duck
    # profile obligates a slide) + 2 catalog assets = 9 images; the two rebase
    # judges are the only structured calls; no design node exists - segments
    # are authored. The canonical fixture declares two BGM tracks and realizes
    # one audio effect as a generated clip, which is one sound-effect draw
    # plus its local admission.
    assert operations == {
        "local": 14,
        "image_generation": 9,
        "structured_generation": 2,
        "music_generation": 2,
        "sound_effect_generation": 1,
    }
    # The package node is a barrier: provider roots order behind it without
    # carrying it in cache lineage.
    for node in graph.nodes:
        if node.operation == "image_generation" and "package-resolve" in node.depends_on:
            assert "package-resolve" in node.barrier_only
    assert graph.node("avatar-rebase-judge").port("reading").sidecar_ref == (
        "avatar/rebase-reading.json.meta.json"
    )
    assert graph.node("avatar-rebase-verify").port("verification").sidecar_ref == (
        "avatar/rebase-verification.json.meta.json"
    )
    for node in graph.nodes:
        attempt_ports = [port for port in node.ports if port.kind == "attempt-ledger-v2"]
        if node.operation == "local":
            assert attempt_ports == []
        else:
            assert len(attempt_ports) == 1, node.node_id


def test_the_motion_vocabulary_is_declared_exactly_once() -> None:
    """The states that validate, the tuple that fans out nodes, and the plate
    band order are all one declaration; editing one without the others emits
    strips no contract admits, or refuses avatars no node serves."""

    from stage_gen.components.runner_content import (
        RUNNER_AVATAR_BASE_MOTION_STATES,
        RUNNER_AVATAR_MOTION_STATES,
        RUNNER_MOTION_ORDER,
    )
    from stage_gen.recipes.sideview_runner.runner_graph import RUNNER_MOTION_STATES

    assert RUNNER_MOTION_STATES is RUNNER_MOTION_ORDER
    assert frozenset(RUNNER_MOTION_ORDER) == RUNNER_AVATAR_MOTION_STATES
    assert RUNNER_AVATAR_BASE_MOTION_STATES < RUNNER_AVATAR_MOTION_STATES
    # The runtime's copy (web/lib/sideview-runner/contract.ts) pins the same
    # order in its own suite; a drift there fails the web gate.
    assert RUNNER_MOTION_ORDER == ("run", "jump", "slide", "fly", "hurt", "death")


def test_motion_source_requires_meaningful_alpha_in_every_declared_cell() -> None:
    source = Image.new("RGBA", (1536, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(source)
    for column in range(4):
        left = column * 384 + 20
        draw.rectangle((left, 300, left + 300, 700), fill=(80, 140, 220, 17))
    for left in (30, 90, 150, 210):
        draw.rectangle((left, 400, left + 40, 500), fill=(80, 140, 220, 255))
    encoded = BytesIO()
    source.save(encoded, format="PNG", optimize=False)

    with pytest.raises(ValueError, match="missing a required visible cell"):
        _validate_motion_source(encoded.getvalue())


def test_motion_provider_gate_includes_decisive_component_repacking() -> None:
    source = Image.new("RGBA", (1536, 1024), (0, 0, 0, 0))
    ImageDraw.Draw(source).rectangle((20, 300, 1515, 700), fill=(80, 140, 220, 255))
    encoded = BytesIO()
    source.save(encoded, format="PNG", optimize=False)

    assert _validate_motion_source(encoded.getvalue())["cell_visible_fractions"]
    with pytest.raises(ValueError, match="principal components for 4 required cells"):
        _validate_motion_candidate(encoded.getvalue(), anchor="bottom")


def test_motion_provider_gate_refuses_disconnected_rider_components() -> None:
    source = Image.new("RGBA", (1536, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(source)
    for column in range(4):
        left = column * 384 + 90
        draw.rectangle((left, 450, left + 200, 750), fill=(80, 140, 220, 255))
        draw.rectangle((left + 80, 330, left + 110, 380), fill=(240, 180, 90, 255))
    encoded = BytesIO()
    source.save(encoded, format="PNG", optimize=False)

    with pytest.raises(ValueError, match="refuses unassigned meaningful alpha components"):
        _validate_motion_candidate(encoded.getvalue(), anchor="bottom")


def test_manifest_reads_the_admitted_rebase_states_and_fails_closed_on_shape_drift() -> None:
    states = ("run", "jump", "slide", "death")
    assert manifest_rebase_multipliers(
        {"states": {"death": 0.95, "jump": 1.01, "run": 1, "slide": 0.99}},
        published_states=states,
    ) == {"run": 1.0, "jump": 1.01, "slide": 0.99, "death": 0.95}

    with pytest.raises(ValueError, match="must publish a states object"):
        manifest_rebase_multipliers({"multipliers_by_state": {"run": 1.0}}, published_states=states)
    with pytest.raises(ValueError, match="states differ from published motions"):
        manifest_rebase_multipliers(
            {"states": {"run": 1.0, "jump": 1.0, "slide": 1.0}},
            published_states=states,
        )
    with pytest.raises(ValueError, match="multiplier for death must be positive"):
        manifest_rebase_multipliers(
            {
                "states": {
                    "run": 1.0,
                    "jump": 1.0,
                    "slide": 1.0,
                    "death": float("nan"),
                }
            },
            published_states=states,
        )


def test_catalog_canonicalization_trims_only_a_short_sparse_terminal_prop_tail() -> None:
    source = Image.new("RGBA", (400, 1000), (0, 0, 0, 0))
    draw = ImageDraw.Draw(source)
    draw.rectangle((100, 100, 299, 899), fill=(240, 210, 170, 255))
    draw.rectangle((195, 900, 204, 949), fill=(80, 150, 80, 255))
    encoded = BytesIO()
    source.save(encoded, format="PNG", optimize=False)

    prop, _trim, report = canonicalize_runner_catalog_sprite(encoded.getvalue(), family="prop")
    with Image.open(BytesIO(prop)) as opened:
        assert opened.size == (400, 800)
    assert report["applied"] is True
    assert report["tail_rows"] == 50
    assert report["removed_rows"] == 50

    item, _item_trim, item_report = canonicalize_runner_catalog_sprite(
        encoded.getvalue(), family="item"
    )
    with Image.open(BytesIO(item)) as opened:
        assert opened.size == (400, 850)
    assert item_report["applied"] is False
    assert item_report["reason"] == "family_is_not_prop"

    long_tail = source.copy()
    ImageDraw.Draw(long_tail).rectangle((195, 950, 204, 999), fill=(80, 150, 80, 255))
    long_encoded = BytesIO()
    long_tail.save(long_encoded, format="PNG", optimize=False)
    untrimmed, _long_trim, long_report = canonicalize_runner_catalog_sprite(
        long_encoded.getvalue(), family="prop"
    )
    with Image.open(BytesIO(untrimmed)) as opened:
        assert opened.size == (400, 900)
    assert long_report["applied"] is False


def test_catalog_provider_gate_rejects_effectively_invisible_cutouts() -> None:
    source = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    ImageDraw.Draw(source).rectangle((100, 100, 900, 900), fill=(80, 140, 220, 1))
    encoded = BytesIO()
    source.save(encoded, format="PNG", optimize=False)

    with pytest.raises(ValueError, match="meaningful visible alpha"):
        _validate_catalog_candidate(encoded.getvalue(), family="prop")

    weak = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    ImageDraw.Draw(weak).rectangle((100, 100, 900, 900), fill=(80, 140, 220, 32))
    encoded = BytesIO()
    weak.save(encoded, format="PNG", optimize=False)
    with pytest.raises(ValueError, match="no pixels above painted alpha threshold"):
        _validate_catalog_candidate(encoded.getvalue(), family="prop")


def test_native_alpha_gates_reject_an_opaque_canvas_with_one_transparent_corner() -> None:
    cutout = Image.new("RGBA", (1024, 1024), (80, 140, 220, 255))
    cutout.putpixel((0, 0), (0, 0, 0, 0))
    encoded = BytesIO()
    cutout.save(encoded, format="PNG", optimize=False)

    with pytest.raises(ValueError, match="transparent negative space"):
        _validate_transparent_sprite(encoded.getvalue())
    with pytest.raises(ValueError, match="transparent negative space"):
        _validate_catalog_candidate(encoded.getvalue(), family="item")

    layer = Image.new("RGBA", (1536, 1024), (80, 140, 220, 255))
    layer.putpixel((0, 0), (0, 0, 0, 0))
    layer_encoded = BytesIO()
    layer.save(layer_encoded, format="PNG", optimize=False)
    with pytest.raises(ValueError, match="transparent negative space"):
        _validate_layer_candidate(layer_encoded.getvalue(), transparent=True)


def test_native_alpha_gates_reject_near_opaque_canvases_below_the_negative_space_floor() -> None:
    cutout = Image.new("RGBA", (1024, 1024), (80, 140, 220, 255))
    ImageDraw.Draw(cutout).rectangle((0, 0, 80, 1023), fill=(0, 0, 0, 0))
    encoded = BytesIO()
    cutout.save(encoded, format="PNG", optimize=False)
    with pytest.raises(ValueError, match="transparent negative space"):
        _validate_transparent_sprite(encoded.getvalue())

    layer = Image.new("RGBA", (1536, 1024), (80, 140, 220, 255))
    ImageDraw.Draw(layer).rectangle((0, 0, 60, 1023), fill=(0, 0, 0, 0))
    layer_encoded = BytesIO()
    layer.save(layer_encoded, format="PNG", optimize=False)
    with pytest.raises(ValueError, match="transparent negative space"):
        _validate_layer_candidate(layer_encoded.getvalue(), transparent=True)


def test_native_alpha_gates_require_negative_space_to_reach_the_canvas_edge() -> None:
    cutout = Image.new("RGBA", (1024, 1024), (80, 140, 220, 255))
    ImageDraw.Draw(cutout).rectangle((300, 250, 723, 773), fill=(0, 0, 0, 0))
    encoded = BytesIO()
    cutout.save(encoded, format="PNG", optimize=False)
    with pytest.raises(ValueError, match="transparent edge separation"):
        _validate_transparent_sprite(encoded.getvalue())

    layer = Image.new("RGBA", (1536, 1024), (80, 140, 220, 255))
    ImageDraw.Draw(layer).rectangle((500, 250, 1035, 773), fill=(0, 0, 0, 0))
    layer_encoded = BytesIO()
    layer.save(layer_encoded, format="PNG", optimize=False)
    with pytest.raises(ValueError, match="transparent edge separation"):
        _validate_layer_candidate(layer_encoded.getvalue(), transparent=True)


def test_a_slide_free_avatar_fans_out_no_slide_nodes(tmp_path: Path) -> None:
    """The node census is a function of what the member declares."""

    from ..._runner_fixture import (
        RUNNER_AVATAR_NO_SLIDE,
        RUNNER_GAMEPLAY_NO_DUCK,
        WIDE_FLAT_ROWS,
        chunk_toml,
    )

    package = two_genre_package(
        tmp_path,
        chunks=chunk_toml("warmup_flat", WIDE_FLAT_ROWS),
        gameplay=RUNNER_GAMEPLAY_NO_DUCK,
        avatar=RUNNER_AVATAR_NO_SLIDE,
    )
    plan = _executor().plan(package)
    node_ids = {node.node_id for node in plan.graph.nodes}
    assert "avatar-run-generate" in node_ids
    assert "avatar-slide-generate" not in node_ids
    assert "avatar-slide-validate" not in node_ids


def test_every_provider_node_states_its_full_prompt_on_its_card(tmp_path: Path) -> None:
    plan = _executor().plan(two_genre_package(tmp_path))

    for node in plan.graph.nodes:
        if node.operation != "local":
            assert node.card is not None and node.card.prompt, node.node_id


def test_avatar_v3_facts_and_whole_silhouette_semantics_are_generation_identity(
    tmp_path: Path,
) -> None:
    plan = _executor().plan(two_genre_package(tmp_path))
    concept_card = plan.graph.node("avatar-concept-generate").card
    motion_card = plan.graph.node("avatar-run-generate").card
    assert concept_card is not None and motion_card is not None
    prompts = [concept_card.prompt, motion_card.prompt]
    for prompt in prompts:
        assert prompt is not None
        assert "age 19" in prompt
        assert "body_kind human" in prompt
        assert "silhouette_mode single_character_v1" in prompt
        assert "proportion_basis character_head_v1" in prompt
        assert "whole character silhouette" in prompt


def test_visible_rider_machine_slide_keeps_the_combined_actor_secure(tmp_path: Path) -> None:
    from ..._runner_fixture import RUNNER_AVATAR, runner_only_package

    combined_avatar = (
        RUNNER_AVATAR.replace('body_kind = "human"', 'body_kind = "piloted_machine"')
        .replace(
            'silhouette_mode = "single_character_v1"',
            'silhouette_mode = "visible_rider_machine_v1"',
        )
        .replace(
            'proportion_basis = "character_head_v1"',
            'proportion_basis = "visible_rider_head_v1"',
        )
    )
    package = runner_only_package(
        tmp_path,
        avatar=combined_avatar,
        piloted_heads_tall=4.2,
    )
    plan = _executor().plan(package)
    slide = plan.graph.node("avatar-slide-generate").card
    assert slide is not None and slide.prompt is not None
    assert "fully-low held skid" in slide.prompt
    assert "held indefinitely while the player ducks" in slide.prompt
    assert "below 45 percent of standing run height" in slide.prompt
    assert "keeps both hands on the controls" in slide.prompt
    assert "baseball-style" not in slide.prompt

    death = plan.graph.node("avatar-death-generate").card
    assert death is not None and death.prompt is not None
    assert "height strictly descends" in death.prompt
    assert "lowest compact powered-down failure pose" in death.prompt
    assert "reactor and headlamp visibly dark" in death.prompt
    assert "Never recover, rise, reset, smile, celebrate" in death.prompt


def test_death_strip_prompt_requires_disconnected_zero_alpha_cells(tmp_path: Path) -> None:
    plan = _executor().plan(two_genre_package(tmp_path))
    card = plan.graph.node("avatar-death-generate").card
    assert card is not None and card.prompt is not None
    assert "fully disconnected" in card.prompt
    assert "zero-alpha transparent pixels" in card.prompt
    assert "no glow, aura" in card.prompt.lower()


def test_structural_ground_fans_out_one_guide_generate_validate_pipeline_per_segment(
    tmp_path: Path,
) -> None:
    plan = _executor().plan(_select_structural_ground(two_genre_package(tmp_path)))
    graph = plan.graph
    node_ids = {node.node_id for node in graph.nodes}
    assert "track-ground-generate" not in node_ids
    bridge_id = "track-ground-shared-seam-bridge"
    assert bridge_id in node_ids
    bridge = graph.node(bridge_id)
    assert bridge.depends_on == (
        "track-ground-warmup_flat-guide",
        "track-ground-warmup_flat-generate",
    )
    for segment_id in ("warmup_flat", "first_gap"):
        guide_id = f"track-ground-{segment_id}-guide"
        generate_id = f"track-ground-{segment_id}-generate"
        validate_id = f"track-ground-{segment_id}-validate"
        assert {guide_id, generate_id, validate_id} <= node_ids
        guide = graph.node(guide_id)
        generated = graph.node(generate_id)
        validated = graph.node(validate_id)
        assert guide.barrier_only == ("package-resolve",)
        assert generated.depends_on == (guide_id,)
        assert validated.depends_on == (guide_id, generate_id, bridge_id)
        assert generated.card is not None
        assert generated.card.prompt is not None
        assert generated.card.reference_inputs[0].node_id == guide_id
        assert generated.card.authored_inputs[0].label == "cover_style"
        assert "fully transparent with true alpha" in generated.card.prompt
        assert validated.port("image").artifact_ref == f"world/ground/{segment_id}.png"

    assert manifest_ground(plan.resolved.runner.track) == {
        "mode": "runner-structural-ground-v1",
        "vertical_fit": "floor_to_screen_bottom",
        "cell_px": 64,
        "chunks": [
            {
                "segment_id": "warmup_flat",
                "image": "world/ground/warmup_flat.png",
                "columns": 24,
                "rows": 8,
            },
            {
                "segment_id": "first_gap",
                "image": "world/ground/first_gap.png",
                "columns": 28,
                "rows": 8,
            },
        ],
    }


def test_an_unrelated_segment_edit_rekeys_only_its_structural_ground_pipeline(
    tmp_path: Path,
) -> None:
    from ..._runner_fixture import WIDE_FLAT_ROWS, chunk_toml

    first_chunks = "\n".join(
        [chunk_toml("alpha", WIDE_FLAT_ROWS), chunk_toml("beta", WIDE_FLAT_ROWS)]
    )
    wider_rows = ["0" * 25] * 5 + ["1" * 25] * 3
    second_chunks = "\n".join([chunk_toml("alpha", WIDE_FLAT_ROWS), chunk_toml("beta", wider_rows)])
    first = _executor().plan(
        _select_structural_ground(two_genre_package(tmp_path / "first", chunks=first_chunks))
    )
    second = _executor().plan(
        _select_structural_ground(two_genre_package(tmp_path / "second", chunks=second_chunks))
    )
    for suffix in ("guide", "generate", "validate"):
        assert (
            first.graph.node(f"track-ground-alpha-{suffix}").cache_key
            == second.graph.node(f"track-ground-alpha-{suffix}").cache_key
        )
        assert (
            first.graph.node(f"track-ground-beta-{suffix}").cache_key
            != second.graph.node(f"track-ground-beta-{suffix}").cache_key
        )


def test_catalog_local_reference_ids_republish_one_port_per_unique_source(
    tmp_path: Path,
) -> None:
    package = two_genre_package(tmp_path)
    items = package / "runner/content/items.toml"
    source = items.read_text(encoding="utf-8")
    items.write_text(
        source.replace('reference_id = "cover_style"', 'reference_id = "item_cover"', 1).replace(
            'reference_ids = ["cover_style"]', 'reference_ids = ["item_cover"]', 1
        ),
        encoding="utf-8",
    )

    plan = _executor().plan(package)
    reference_ports = [
        port
        for port in plan.graph.node("manifest-assemble").ports
        if port.kind == "runner-reference-v1"
    ]
    assert [port.artifact_ref for port in reference_ports] == ["references/cover.png"]
    assert reference_ports[0].port_id.startswith("reference_")


@pytest.mark.asyncio
async def test_a_dry_run_executes_the_whole_graph_and_exports_a_view(tmp_path: Path) -> None:
    package = two_genre_package(tmp_path)
    run_dir = tmp_path / "run"
    result = await _executor().dry_run(
        package,
        run_dir=run_dir,
        cache_dir=tmp_path / "cache",
        invocation_id="dry-run-test",
    )

    assert result.summary.ok
    plan_document = json.loads((run_dir / "execution-plan.json").read_text(encoding="utf-8"))
    assert plan_document["kind"] == "sideview-runner-execution-graph-v1"
    view = build_sideview_runner_view(run_dir)
    assert view.recipe == "sideview-runner"
    assert view.track_id == "meadow-dash"
    assert len(view.nodes) == len(result.plan.graph.nodes)


@pytest.mark.asyncio
async def test_a_dry_run_failure_is_reported_rather_than_swallowed(tmp_path: Path) -> None:
    result = await _executor().dry_run(
        two_genre_package(tmp_path),
        run_dir=tmp_path / "run",
        cache_dir=tmp_path / "cache",
        invocation_id="dry-run-failure",
        failure_node_id="avatar-run-generate",
    )

    assert not result.summary.ok
