from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any, Literal, cast

import pytest
from PIL import Image, ImageChops, ImageDraw

from scripts.build_tileset_wireframe import DESTINATIONS, build_wireframe, main
from stage_gen.recipes.scrolling_preview import tileset_materials as tileset_materials_module
from stage_gen.recipes.scrolling_preview.raster_contracts import (
    contract_for_stage,
    grid_semantic_role,
    tileset_alpha_mask,
    tileset_cell_mask,
    validate_canonical_grid,
)
from stage_gen.recipes.scrolling_preview.tileset_materials import (
    CAP_FILL_GLOBAL_GAMUT_VERSION,
    CAP_FILL_LIGHTNESS_VERSION,
    TILESET_MATERIAL_SYNTHESIS_VERSION,
    MaterialRole,
    canonicalize_tileset_material,
    flatten_tileset_to_background,
    synthesize_tileset_from_materials,
    tileset_material_dependency_evidence,
    tileset_material_prompt,
    validate_tileset_material_swatch,
    validate_tileset_wireframe,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_WIREFRAME = _REPOSITORY_ROOT / "fixtures/image_gen_templates/wireframe.png"


def test_wireframe_builder_matches_both_canonical_copies() -> None:
    derived = build_wireframe()

    assert tuple(destination.read_bytes() for destination in DESTINATIONS) == (
        derived,
        derived,
    )
    assert main([]) == 0


@pytest.mark.parametrize(
    ("role", "role_direction"),
    [
        ("fill", "two-axis-repeatable ground-body material"),
        ("cap", "horizontally repeatable living walkable-cover material"),
        ("edge", "vertically repeatable air-facing cut-shadow material"),
    ],
)
def test_material_prompt_is_texture_only_and_role_specific(
    role: MaterialRole,
    role_direction: str,
) -> None:
    prompt = tileset_material_prompt(
        role,
        world_description="A warm hand-painted forest crossing.",
        layer_description="Mossy ochre stone beside quiet roots.",
        theme_directive="Keep the whimsical storybook palette restrained.",
    )

    assert role_direction in prompt
    for exclusion in (
        "no terrain silhouette",
        "scene",
        "sky",
        "horizon",
        "platform",
        "character",
        "focal object",
        "text",
        "logo",
        "watermark",
        "border",
    ):
        assert exclusion in prompt
    assert "fully opaque square image" in prompt
    assert "material continuing through every edge" in prompt
    assert "wireframe" not in prompt.lower()
    assert "12 x 4" not in prompt.lower()


def test_material_validation_rejects_transparency_flatness_and_horizon() -> None:
    wrong_size = Image.new("RGB", (512, 512), (120, 90, 60))
    with pytest.raises(ValueError, match="exactly 1024x1024"):
        canonicalize_tileset_material(_png(wrong_size), role="fill")

    transparent = Image.new("RGBA", (1024, 1024), (120, 90, 60, 254))
    with pytest.raises(ValueError, match="fully opaque"):
        canonicalize_tileset_material(_png(transparent), role="fill")

    flat = Image.new("RGB", (1024, 1024), (120, 90, 60))
    with pytest.raises(ValueError, match="luminance variance is too low"):
        canonicalize_tileset_material(_png(flat), role="fill")

    horizon = Image.new("RGB", (1024, 1024))
    draw = ImageDraw.Draw(horizon)
    for row in range(16):
        base = 180 if row < 8 else 75
        for column in range(16):
            offset = (-12, -4, 5, 13)[(row * 3 + column) % 4]
            value = base + offset
            draw.rectangle(
                (column * 64, row * 64, column * 64 + 63, row * 64 + 63),
                fill=(value + 8, value, value - 7),
            )
    with pytest.raises(ValueError, match="horizon-like luminance gradient"):
        canonicalize_tileset_material(_png(horizon), role="fill")


def test_material_validation_rejects_flat_regions_and_salient_motifs() -> None:
    with Image.open(BytesIO(_material("fill"))) as opened:
        dominant_flat = opened.convert("RGB")
    ImageDraw.Draw(dominant_flat).rectangle((80, 80, 780, 780), fill=(132, 90, 48))
    with pytest.raises(ValueError, match=r"dominant flat|large flat"):
        canonicalize_tileset_material(_png(dominant_flat), role="fill")

    with Image.open(BytesIO(_material("fill"))) as opened:
        salient = opened.convert("RGB")
    ImageDraw.Draw(salient).ellipse((250, 250, 774, 774), fill=(250, 250, 245))
    with pytest.raises(ValueError, match=r"salient motif|center-weighted focal subject"):
        canonicalize_tileset_material(_png(salient), role="fill")


def test_dependent_material_validation_rejects_palette_and_scale_drift() -> None:
    fill = _material("fill")
    alien_cap = _pattern_material(
        (
            (20, 220, 230),
            (40, 240, 250),
            (10, 190, 210),
            (60, 210, 255),
        ),
        block=64,
    )
    with pytest.raises(ValueError, match=r"palette is not linked|shared FILL palette"):
        canonicalize_tileset_material(alien_cap, role="cap", fill_anchor=fill)

    high_frequency_cap = _pattern_material(
        (
            (180, 190, 76),
            (145, 162, 55),
            (214, 214, 112),
            (130, 148, 61),
            (190, 174, 88),
            (162, 202, 70),
            (222, 188, 96),
            (142, 183, 82),
        ),
        block=16,
    )
    with pytest.raises(ValueError, match=r"frequency band|mark scale"):
        canonicalize_tileset_material(high_frequency_cap, role="cap", fill_anchor=fill)


def test_cap_fill_lightness_recovery_is_deterministic_hash_bound_and_periodic() -> None:
    fill = _material("fill")

    first, first_evidence = canonicalize_tileset_material(
        fill,
        role="cap",
        fill_anchor=fill,
    )
    second, second_evidence = canonicalize_tileset_material(
        fill,
        role="cap",
        fill_anchor=fill,
    )

    assert first == second
    assert first_evidence == second_evidence
    recovery = cast(dict[str, object], first_evidence["cap_fill_lightness_recovery"])
    assert recovery["version"] == CAP_FILL_LIGHTNESS_VERSION
    assert recovery["input_sha256"] != recovery["output_sha256"]
    assert recovery["fill_anchor_sha256"] == sha256(fill).hexdigest()
    assert recovery["output_sha256"] == sha256(first).hexdigest()
    payload = {key: value for key, value in recovery.items() if key != "sha256"}
    assert recovery["sha256"] == tileset_materials_module._json_digest(payload)
    relationship = cast(dict[str, object], recovery["output_relationship"])
    assert (
        tileset_materials_module.DEFAULT_MATERIAL_THRESHOLDS.minimum_cap_fill_luminance_delta
        <= abs(cast(float, relationship["luminance_delta"]))
        <= tileset_materials_module._CAP_MAX_RECOVERED_LUMINANCE_DELTA
    )
    assert cast(float, relationship["delta_e00"]) >= 10.0
    assert recovery["periodic_edges_preserved"] is True
    assert recovery["opacity_preserved"] is True
    validation = validate_tileset_material_swatch(first, role="cap", fill_anchor=fill)
    assert validation["tileset_material_source_valid"] is True
    recanonicalized, recanonicalized_evidence = canonicalize_tileset_material(
        first,
        role="cap",
        fill_anchor=fill,
    )
    assert recanonicalized == first
    assert "cap_fill_lightness_recovery" not in recanonicalized_evidence
    _normal, normal_evidence = canonicalize_tileset_material(
        _material("cap"),
        role="cap",
        fill_anchor=fill,
    )
    assert "cap_fill_lightness_recovery" not in normal_evidence


@pytest.mark.parametrize(
    (
        "fill_palette",
        "cap_palette",
        "expected_failures",
        "expected_direction",
        "expected_factor",
    ),
    [
        (
            ((39, 113, 236), (52, 100, 210), (52, 146, 254), (54, 85, 190)),
            ((54, 111, 252), (67, 101, 227), (65, 137, 255), (69, 88, 207)),
            ("gamut-chroma-retention", "gamut-chroma-retention"),
            "lighter",
            0.65,
        ),
        (
            ((225, 225, 10), (188, 200, 25), (243, 223, 21), (158, 180, 30)),
            ((203, 217, 6), (168, 192, 20), (235, 231, 16), (139, 171, 25)),
            ("target-shift-headroom", "gamut-chroma-retention"),
            "darker",
            0.85,
        ),
    ],
)
def test_cap_fill_global_gamut_recovery_is_bounded_and_preserves_material(
    fill_palette: tuple[tuple[int, int, int], ...],
    cap_palette: tuple[tuple[int, int, int], ...],
    expected_failures: tuple[str, str],
    expected_direction: str,
    expected_factor: float,
) -> None:
    fill_raw = _pattern_material(fill_palette, block=64)
    fill, _fill_evidence = canonicalize_tileset_material(fill_raw, role="fill")
    cap = _pattern_material(cap_palette, block=64)
    source = tileset_materials_module._periodicize(
        _rgb_image(cap),
        horizontal=True,
        vertical=False,
        band=tileset_materials_module.DEFAULT_MATERIAL_THRESHOLDS.periodic_blend_band,
    )
    preflight = tileset_materials_module._validate_material_pixels(
        source,
        role="cap",
        fill_anchor=fill,
        thresholds=tileset_materials_module.DEFAULT_MATERIAL_THRESHOLDS,
        enforce_cap_fill_separation=False,
    )
    evaluations = [
        tileset_materials_module._cap_lightness_candidate(
            source,
            fill_anchor=fill,
            preflight=preflight,
            thresholds=tileset_materials_module.DEFAULT_MATERIAL_THRESHOLDS,
            direction=direction,
        )
        for direction in cast(tuple[Literal["lighter", "darker"], ...], ("lighter", "darker"))
    ]
    assert tuple(evaluation.failure_code for evaluation in evaluations) == expected_failures
    first, first_evidence = canonicalize_tileset_material(
        cap,
        role="cap",
        fill_anchor=fill,
    )
    second, second_evidence = canonicalize_tileset_material(
        cap,
        role="cap",
        fill_anchor=fill,
    )

    assert first == second
    assert first_evidence == second_evidence
    recovery = cast(dict[str, object], first_evidence["cap_fill_lightness_recovery"])
    assert recovery["version"] == CAP_FILL_LIGHTNESS_VERSION
    assert recovery["global_gamut_version"] == CAP_FILL_GLOBAL_GAMUT_VERSION
    assert recovery["direction"] == expected_direction
    assert recovery["global_chroma_factor"] == expected_factor
    assert recovery["selection_order"] == [
        "minimum-absolute-lightness-shift",
        "maximum-global-chroma-retention",
        "maximum-directional-headroom",
        "lighter-tie-break",
    ]
    relationship = cast(dict[str, object], recovery["output_relationship"])
    assert (
        tileset_materials_module.DEFAULT_MATERIAL_THRESHOLDS.minimum_cap_fill_luminance_delta
        <= abs(cast(float, relationship["luminance_delta"]))
        <= tileset_materials_module._CAP_MAX_RECOVERED_LUMINANCE_DELTA
    )
    assert cast(float, relationship["delta_e00"]) >= 10.0
    gamut = cast(dict[str, object], recovery["gamut"])
    assert gamut["global_chroma_factor"] == expected_factor
    assert cast(float, gamut["maximum_hue_drift_degrees"]) <= 2.0
    assert gamut["prequantized_out_of_gamut_pixels"] == 0
    assert gamut["lightness_clipped_pixels"] == 0
    assert 0.85 <= cast(float, gamut["luminance_std_ratio"]) <= 1.15
    assert 0.85 <= cast(float, gamut["spatial_frequency_ratio"]) <= 1.15
    assert recovery["input_sha256"] != recovery["output_sha256"]
    assert recovery["fill_anchor_sha256"] == sha256(fill).hexdigest()
    assert recovery["output_sha256"] == sha256(first).hexdigest()
    payload = {key: value for key, value in recovery.items() if key != "sha256"}
    assert recovery["sha256"] == tileset_materials_module._json_digest(payload)
    with Image.open(BytesIO(first)) as opened:
        output = opened.convert("RGB")
    assert output.crop((0, 0, 1, 1024)).tobytes() == output.crop((1023, 0, 1024, 1024)).tobytes()


def test_cap_fill_global_gamut_rejects_chroma_below_reviewed_floor() -> None:
    saturated = _rgb_image(
        _pattern_material(
            ((20, 240, 20), (30, 220, 25), (40, 250, 30), (15, 210, 20)),
            block=64,
        )
    )

    _at_floor, facts = tileset_materials_module._shift_material_global_lch(
        saturated,
        signed_shift=-12.0,
        chroma_factor=0.60,
    )
    assert facts["global_chroma_factor"] == 0.60
    with pytest.raises(ValueError, match="outside the reviewed range"):
        tileset_materials_module._shift_material_global_lch(
            saturated,
            signed_shift=-12.0,
            chroma_factor=0.55,
        )


@pytest.mark.parametrize(
    ("lighter_failure", "darker_failure", "expected_failure"),
    [
        ("delta-e00-contract", "delta-e00-contract", "delta-e00-contract"),
        ("gamut-chroma-retention", "texture-contract", "texture-contract"),
    ],
    ids=["non-headroom", "mixed-headroom-and-non-headroom"],
)
def test_cap_fill_global_gamut_never_runs_after_non_headroom_failure(
    monkeypatch: pytest.MonkeyPatch,
    lighter_failure: str,
    darker_failure: str,
    expected_failure: str,
) -> None:
    failures = {"lighter": lighter_failure, "darker": darker_failure}
    fallback_calls: list[bool] = []

    def typed_failure(
        _image: Image.Image,
        *,
        direction: str,
        **_kwargs: object,
    ) -> object:
        return tileset_materials_module._CapLightnessEvaluation(
            None,
            cast(Any, failures[direction]),
        )

    def forbidden_global_fallback(*_args: object, **_kwargs: object) -> object:
        fallback_calls.append(True)
        raise AssertionError("global fallback must not run")

    monkeypatch.setattr(tileset_materials_module, "_cap_lightness_candidate", typed_failure)
    monkeypatch.setattr(
        tileset_materials_module,
        "_recover_cap_fill_global_gamut",
        forbidden_global_fallback,
    )
    fill = _material("fill")

    with pytest.raises(ValueError, match=expected_failure):
        canonicalize_tileset_material(fill, role="cap", fill_anchor=fill)

    assert fallback_calls == []


def test_cap_fill_lightness_recovery_uses_unrounded_threshold_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fill = _png(Image.new("RGB", (64, 64), (0, 0, 0)))
    cap_image = Image.new("RGB", (64, 64))
    floor = tileset_materials_module.DEFAULT_MATERIAL_THRESHOLDS.minimum_cap_fill_luminance_delta
    cap_image.putdata([(144, 0, 0)] * 3818 + [(143, 0, 0)] * 278)
    exact_delta = tileset_materials_module._material_fill_luminance_delta(cap_image, fill)
    assert exact_delta < floor
    assert round(exact_delta, 6) == floor
    assert tileset_materials_module._mean_luminance(cap_image) >= floor
    recovered_deltas: list[float] = []

    def validate_without_unrounded_evidence(
        _image: Image.Image,
        **_kwargs: object,
    ) -> dict[str, object]:
        return {"fill_luminance_delta": round(exact_delta, 6)}

    def record_recovery(
        image: Image.Image,
        *,
        fill_anchor: bytes,
        **_kwargs: object,
    ) -> tuple[Image.Image, dict[str, object]]:
        recovered_deltas.append(
            tileset_materials_module._material_fill_luminance_delta(image, fill_anchor)
        )
        return image, {"version": CAP_FILL_LIGHTNESS_VERSION}

    def preserve_source(image: Image.Image, **_kwargs: object) -> Image.Image:
        return image

    monkeypatch.setattr(tileset_materials_module, "_SWATCH_SIZE", 64)
    monkeypatch.setattr(tileset_materials_module, "_periodicize", preserve_source)
    monkeypatch.setattr(
        tileset_materials_module,
        "_validate_material_pixels",
        validate_without_unrounded_evidence,
    )
    monkeypatch.setattr(
        tileset_materials_module,
        "_recover_cap_fill_lightness",
        record_recovery,
    )

    _canonical, evidence = canonicalize_tileset_material(
        _png(cap_image),
        role="cap",
        fill_anchor=fill,
    )

    assert recovered_deltas == [exact_delta]
    assert evidence["cap_fill_lightness_recovery"] == {"version": CAP_FILL_LIGHTNESS_VERSION}


@pytest.mark.parametrize(
    ("fill_palette", "cap_palette", "expected_direction"),
    [
        (
            ((245, 235, 220), (230, 220, 200), (255, 245, 225), (220, 210, 190)),
            ((220, 245, 215), (205, 230, 195), (230, 255, 220), (195, 220, 185)),
            "darker",
        ),
        (
            ((32, 28, 22), (42, 35, 26), (22, 20, 18), (52, 43, 30)),
            ((32, 28, 22), (42, 35, 26), (22, 20, 18), (52, 43, 30)),
            "lighter",
        ),
    ],
)
def test_cap_fill_lightness_recovery_chooses_direction_from_headroom(
    fill_palette: tuple[tuple[int, int, int], ...],
    cap_palette: tuple[tuple[int, int, int], ...],
    expected_direction: str,
) -> None:
    fill = _pattern_material(fill_palette, block=64)
    cap = _pattern_material(cap_palette, block=64)

    _canonical, evidence = canonicalize_tileset_material(
        cap,
        role="cap",
        fill_anchor=fill,
    )

    recovery = cast(dict[str, object], evidence["cap_fill_lightness_recovery"])
    assert recovery["direction"] == expected_direction
    assert expected_direction in cast(list[str], recovery["feasible_directions"])
    assert recovery["selection_order"] == [
        "minimum-absolute-lightness-shift",
        "maximum-directional-headroom",
        "lighter-tie-break",
    ]


def test_cap_fill_lightness_recovery_never_rescues_invalid_or_unsafe_material() -> None:
    fill = _material("fill")
    flat = _png(Image.new("RGB", (1024, 1024), (142, 99, 54)))
    with pytest.raises(ValueError, match="luminance variance is too low"):
        canonicalize_tileset_material(flat, role="cap", fill_anchor=fill)

    saturated = _pattern_material(
        ((240, 20, 20), (220, 30, 25), (250, 40, 30), (210, 15, 20)),
        block=64,
    )
    with pytest.raises(ValueError, match="non-headroom contract: delta-e00-contract"):
        canonicalize_tileset_material(saturated, role="cap", fill_anchor=saturated)

    near_white = _pattern_material(
        ((245, 235, 220), (230, 220, 200), (255, 245, 225), (220, 210, 190)),
        block=64,
    )
    with pytest.raises(ValueError, match="non-headroom contract: delta-e00-contract"):
        canonicalize_tileset_material(near_white, role="cap", fill_anchor=near_white)


@pytest.mark.parametrize(
    ("role", "periodic_axes"),
    [
        ("fill", ("horizontal", "vertical")),
        ("cap", ("horizontal",)),
        ("edge", ("vertical",)),
    ],
)
def test_material_canonicalization_is_deterministic_and_exactly_periodic(
    role: MaterialRole,
    periodic_axes: tuple[str, ...],
) -> None:
    fill = _material("fill")
    source = _material(role)
    anchor = None if role == "fill" else fill

    first, first_evidence = canonicalize_tileset_material(
        source,
        role=role,
        fill_anchor=anchor,
    )
    second, second_evidence = canonicalize_tileset_material(
        source,
        role=role,
        fill_anchor=anchor,
    )

    assert first == second
    assert first_evidence == second_evidence
    assert first_evidence["periodic_axes"] == list(periodic_axes)
    assert first_evidence["output_sha256"] == sha256(first).hexdigest()
    with Image.open(BytesIO(first)) as opened:
        canonical = opened.convert("RGBA")
    assert canonical.size == (1024, 1024)
    assert canonical.getchannel("A").getextrema() == (255, 255)
    if "horizontal" in periodic_axes:
        assert (
            canonical.crop((0, 0, 1, 1024)).tobytes()
            == canonical.crop((1023, 0, 1024, 1024)).tobytes()
        )
    if "vertical" in periodic_axes:
        assert (
            canonical.crop((0, 0, 1024, 1)).tobytes()
            == canonical.crop((0, 1023, 1024, 1024)).tobytes()
        )


def test_material_dependency_digest_binds_every_exact_swatch() -> None:
    fill = _canonical_material("fill")
    cap = _canonical_material("cap")
    edge = _canonical_material("edge")

    first = tileset_material_dependency_evidence(fill=fill, cap=cap, edge=edge)
    second = tileset_material_dependency_evidence(fill=fill, cap=cap, edge=edge)
    with Image.open(BytesIO(edge)) as opened:
        tampered_image = opened.convert("RGB")
    tampered_image.putpixel((17, 29), (1, 2, 3))
    tampered_edge = _png(tampered_image)
    tampered = tileset_material_dependency_evidence(
        fill=fill,
        cap=cap,
        edge=tampered_edge,
    )

    assert first == second
    assert first["version"] == TILESET_MATERIAL_SYNTHESIS_VERSION
    assert first["role_order"] == ["fill", "cap", "edge"]
    assert first["dag"] == [
        {"role": "fill", "depends_on": []},
        {"role": "cap", "depends_on": ["fill"]},
        {"role": "edge", "depends_on": ["fill"]},
    ]
    assert tampered["sha256"] != first["sha256"]
    first_artifacts = cast(dict[str, object], first["artifacts"])
    tampered_artifacts = cast(dict[str, object], tampered["artifacts"])
    assert tampered_artifacts["fill"] == first_artifacts["fill"]
    assert tampered_artifacts["cap"] == first_artifacts["cap"]
    assert tampered_artifacts["edge"] != first_artifacts["edge"]


def test_wireframe_validator_binds_exact_bytes_and_rgb_class_inventory() -> None:
    wireframe = _WIREFRAME.read_bytes()

    evidence = validate_tileset_wireframe(wireframe)

    assert evidence == {
        "version": "packaged-tileset-wireframe-v2",
        "role": "version-locked-tileset-layout-prior",
        "sha256": "8af51ddb6796a242916b7c38974fd324202756a8c3fe9b91c6998766c34e149a",
        "bytes": 12_471,
        "dimensions": [2400, 800],
        "rgb_class_count": 4,
        "rgb_classes": [
            {"name": "layout_separator", "rgb": [26, 26, 26], "pixels": 38_208},
            {"name": "surface_cover", "rgb": [40, 180, 60], "pixels": 102_858},
            {"name": "underground_fill", "rgb": [60, 60, 60], "pixels": 921_129},
            {"name": "strategy_background", "rgb": [255, 0, 255], "pixels": 857_805},
        ],
        "content_identity_valid": True,
        "class_inventory_valid": True,
        "material_classes_bound": ["surface_cover", "underground_fill"],
        "geometry_usage": "identity-only",
        "canonical_topology_source": "tileset-12x4-v1",
        "sent_to_provider": False,
    }

    with Image.open(BytesIO(wireframe)) as opened:
        forged_image = opened.convert("RGB")
    # Reassign one pixel to a different packaged class; a same-palette mutation must still be
    # caught. The target is located rather than fixed because the border is already separator.
    forged_target = next(
        (x, y)
        for y in range(forged_image.height)
        for x in range(forged_image.width)
        if forged_image.getpixel((x, y)) != (26, 26, 26)
    )
    forged_image.putpixel(forged_target, (26, 26, 26))
    with pytest.raises(ValueError, match="RGB class inventory"):
        validate_tileset_wireframe(_png(forged_image))

    with Image.open(BytesIO(wireframe)) as opened:
        reencoded_image = opened.convert("RGB")
    reencoded_output = BytesIO()
    reencoded_image.save(reencoded_output, format="PNG", compress_level=0)
    reencoded = reencoded_output.getvalue()
    assert reencoded != wireframe
    with pytest.raises(ValueError, match="bytes do not match"):
        validate_tileset_wireframe(reencoded)


def test_material_synthesis_is_deterministic_and_matches_runtime_contract() -> None:
    fill = _canonical_material("fill")
    cap = _canonical_material("cap")
    edge = _canonical_material("edge")
    wireframe = _WIREFRAME.read_bytes()

    first, first_evidence = synthesize_tileset_from_materials(
        fill=fill,
        cap=cap,
        edge=edge,
        wireframe=wireframe,
    )
    second, second_evidence = synthesize_tileset_from_materials(
        fill=fill,
        cap=cap,
        edge=edge,
        wireframe=wireframe,
    )

    assert first == second
    assert first_evidence == second_evidence
    assert first_evidence["version"] == TILESET_MATERIAL_SYNTHESIS_VERSION
    assert first_evidence["canvas"] == [2400, 800]
    assert first_evidence["gutter_pixels"] == 2
    assert first_evidence["gutter_pixels_painted"] == 0
    assert first_evidence["canonical_fill_fully_opaque"] is True
    assert first_evidence["failed_sheet_pixels_used"] is False
    assert first_evidence["independent_role_cell_calls"] == 0
    assert first_evidence["output_sha256"] == sha256(first).hexdigest()
    wireframe_evidence = cast(dict[str, object], first_evidence["wireframe"])
    assert wireframe_evidence["sha256"] == sha256(wireframe).hexdigest()
    assert wireframe_evidence["sent_to_provider"] is False

    contract = contract_for_stage("tileset")
    assert contract is not None
    validation = validate_canonical_grid(first, contract)
    assert validation["layout_rows"] == 4
    assert validation["layout_columns"] == 12
    assert validation["cell_width"] == 200
    assert validation["cell_height"] == 200
    assert validation["cells_nonempty"] == 48
    assert validation["canonical_fill_opaque"] is True
    expected_roles = [
        grid_semantic_role(contract, row, column) for row in range(4) for column in range(12)
    ]
    assert first_evidence["role_order"] == expected_roles
    assert len(cast(list[object], first_evidence["cell_material_bands"])) == 48
    band_records = cast(list[dict[str, object]], first_evidence["cell_material_bands"])
    for record in band_records:
        row = cast(int, record["row"])
        column = cast(int, record["column"])
        role = cast(str, record["semantic_role"])
        solid = tileset_cell_mask(row, column % 4, 200, 200, contract.gutter)
        cap_mask = tileset_materials_module._cap_material_band_for_role(
            solid,
            semantic_role=role,
            thickness=12,
        )
        edge_mask = tileset_materials_module._edge_material_band_for_role(
            solid,
            semantic_role=role,
            thickness=10,
        )
        edge_mask = ImageChops.subtract(edge_mask, cap_mask)
        assert record["solid_pixels"] == sum(solid.histogram()[1:])
        assert record["cap_pixels"] == sum(cap_mask.histogram()[1:])
        assert record["edge_pixels"] == sum(edge_mask.histogram()[1:])
    attribution = cast(dict[str, object], first_evidence["source_attribution"])
    assert attribution["unattributed_opaque_pixels"] == 0
    assert attribution["rgb_source_reconstruction_mismatches"] == 0
    assert attribution["exact_alpha_coverage"] is True
    corridors = cast(dict[str, object], first_evidence["representative_corridors"])
    assert corridors["all_fully_opaque"] is True
    assert corridors["all_expected_material"] is True
    assert corridors["all_representative"] is True
    corridor_records = cast(list[dict[str, object]], corridors["corridors"])
    assert [record["name"] for record in corridor_records] == [
        "top-cap",
        "left-edge",
        "right-edge",
    ]
    variants = cast(dict[str, object], first_evidence["variant_validation"])
    assert variants["role_groups_validated"] == 16
    assert variants["all_hashes_non_identical"] is True
    adjacency = cast(dict[str, object], first_evidence["adjacency_validation"])
    assert adjacency["joins_validated"] == 12
    assert adjacency["transitions_validated"] == 24
    assert adjacency["join_local_patches_validated"] == 48
    assert adjacency["transition_categories"] == {
        "slope-to-flat": 6,
        "inner-corner": 6,
        "inward-side-fill": 12,
    }
    assert adjacency["all_geometry_continuous"] is True
    assert adjacency["all_material_sequences_compatible"] is True
    assert all(
        cast(list[dict[str, object]], transition["join_local_patches"])
        for transition in cast(list[dict[str, object]], adjacency["transitions"])
    )
    geometry = cast(dict[str, object], first_evidence["role_geometry"])
    assert geometry["anchor_tolerance_pixels"] == 1
    assert geometry["all_anchor_tolerances_valid"] is True

    with Image.open(BytesIO(first)) as opened:
        alpha = opened.convert("RGBA").getchannel("A")
    expected_alpha = tileset_alpha_mask(2400, 800, contract)
    assert ImageChops.difference(alpha, expected_alpha).getbbox() is None
    for column in (0, 4, 8):
        fill_inset = alpha.crop((column * 200 + 2, 602, column * 200 + 198, 798))
        assert fill_inset.getextrema() == (255, 255)

    top_corridor = alpha.crop((602, 2, 798, 7))
    left_corridor = alpha.crop((2, 402, 7, 598))
    right_corridor = alpha.crop((393, 402, 398, 598))
    assert top_corridor.getbbox() is not None
    assert left_corridor.getbbox() is not None
    assert right_corridor.getbbox() is not None


@pytest.mark.parametrize(
    "category",
    ["slope-to-flat", "inner-corner", "inward-side-fill"],
)
def test_join_local_validator_rejects_each_tampered_transition_family(category: str) -> None:
    canonical, fill, cap, edge = _synthesized_tileset_fixture()
    contract = contract_for_stage("tileset")
    assert contract is not None
    attribution = tileset_materials_module._canonical_material_attribution(
        contract,
        width=2400,
        height=800,
    )
    specs = tileset_materials_module._material_join_patch_specs(attribution, contract)
    spec = next(value for value in specs if value.category == category)
    targets = tileset_materials_module._join_patch_coordinates(
        attribution,
        spec.target_box,
        source=spec.source,
    )
    assert targets
    with Image.open(BytesIO(canonical)) as opened:
        tampered = opened.convert("RGBA")
    for point in targets:
        tampered.putpixel(point, (255, 0, 255, 255))

    with pytest.raises(ValueError, match=rf"{category}.*join-local"):
        tileset_materials_module._validate_tileset_adjacency(
            tampered,
            attribution,
            contract,
            fill_material=_rgb_image(fill),
            cap_material=_rgb_image(cap),
            edge_material=_rgb_image(edge),
            thresholds=tileset_materials_module.DEFAULT_MATERIAL_THRESHOLDS,
        )


def test_flattened_raw_has_truthful_local_processing_evidence() -> None:
    contract = contract_for_stage("tileset")
    assert contract is not None
    canonical_image = Image.new("RGBA", (2400, 800), (12, 34, 56, 255))
    canonical_image.putalpha(tileset_alpha_mask(2400, 800, contract))
    canonical = _png(canonical_image)

    flattened, evidence = flatten_tileset_to_background(
        canonical,
        background_rgb=(201, 17, 99),
    )

    assert evidence == {
        "version": "tileset-strategy-background-flatten-v1",
        "processor": "local-strategy-background-flatten",
        "input_sha256": sha256(canonical).hexdigest(),
        "input_bytes": len(canonical),
        "output_sha256": sha256(flattened).hexdigest(),
        "output_bytes": len(flattened),
        "background_rgb": [201, 17, 99],
        "dimensions": [2400, 800],
        "ai_background_removal": False,
        "chroma_key_applied": False,
    }
    with Image.open(BytesIO(flattened)) as opened:
        raw = opened.convert("RGB")
    assert raw.size == (2400, 800)
    assert raw.getpixel((0, 0)) == (201, 17, 99)
    assert raw.getpixel((2, 602)) == (12, 34, 56)


@lru_cache(maxsize=3)
def _material(role: MaterialRole) -> bytes:
    palettes: dict[MaterialRole, tuple[tuple[int, int, int], ...]] = {
        "fill": (
            (142, 99, 54),
            (126, 84, 46),
            (156, 112, 66),
            (112, 76, 50),
        ),
        "cap": (
            (180, 190, 76),
            (156, 170, 62),
            (204, 205, 102),
            (139, 153, 66),
        ),
        "edge": (
            (20, 35, 30),
            (30, 50, 40),
            (70, 90, 65),
            (45, 65, 50),
        ),
    }
    palette = palettes[role]
    image = Image.new("RGB", (1024, 1024))
    draw = ImageDraw.Draw(image)
    for row in range(16):
        for column in range(16):
            colour = palette[(column + row * 3 + column // 4) % len(palette)]
            draw.rectangle(
                (column * 64, row * 64, column * 64 + 63, row * 64 + 63),
                fill=colour,
            )
    return _png(image)


@lru_cache(maxsize=3)
def _canonical_material(role: MaterialRole) -> bytes:
    fill = _material("fill")
    canonical, _evidence = canonicalize_tileset_material(
        _material(role),
        role=role,
        fill_anchor=None if role == "fill" else fill,
    )
    return canonical


@lru_cache(maxsize=1)
def _synthesized_tileset_fixture() -> tuple[bytes, bytes, bytes, bytes]:
    fill = _canonical_material("fill")
    cap = _canonical_material("cap")
    edge = _canonical_material("edge")
    canonical, _evidence = synthesize_tileset_from_materials(
        fill=fill,
        cap=cap,
        edge=edge,
        wireframe=_WIREFRAME.read_bytes(),
    )
    return canonical, fill, cap, edge


def _rgb_image(data: bytes) -> Image.Image:
    with Image.open(BytesIO(data)) as opened:
        return opened.convert("RGB")


def _pattern_material(
    palette: tuple[tuple[int, int, int], ...],
    *,
    block: int,
) -> bytes:
    image = Image.new("RGB", (1024, 1024))
    draw = ImageDraw.Draw(image)
    for top in range(0, 1024, block):
        row = top // block
        for left in range(0, 1024, block):
            column = left // block
            colour = palette[(column + row * 3 + column // 4) % len(palette)]
            draw.rectangle(
                (left, top, min(1023, left + block - 1), min(1023, top + block - 1)),
                fill=colour,
            )
    return _png(image)


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
