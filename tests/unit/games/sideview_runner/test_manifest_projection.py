"""The game manifest projects admitted assets without generation or filesystem writes."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Never

from PIL import Image, ImageDraw

from demo_game_collection.executors import SideviewRunnerExecutor
from iron_petal_unit_pipeline.content import declared_motion_states
from iron_petal_unit_pipeline.manifest import build_manifest
from stage_gen.canonical import canonical_sha256
from stage_gen.config import StageGenConfig
from tests.unit._runner_fixture import two_genre_package


def _unexpected_material_identity() -> Never:
    raise AssertionError("atlas ground must not request a structural material identity")


def test_complete_manifest_projection_preserves_the_pre_extraction_document(tmp_path: Path) -> None:
    plan = SideviewRunnerExecutor(StageGenConfig()).plan(two_genre_package(tmp_path / "input"))
    runner = plan.resolved.runner
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((32, 16, 95, 111), fill=(160, 90, 50, 255))
    output = BytesIO()
    image.save(output, format="PNG")
    png = output.getvalue()

    def put(ref: str, data: bytes) -> None:
        path = run_dir / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def put_json(ref: str, value: object) -> None:
        put(ref, json.dumps(value, sort_keys=True).encode())

    put("avatar/run.png", png)
    put_json(
        "avatar/rebase-verification.json",
        {"states": {state: 1.0 for state in declared_motion_states(runner.avatar.avatar)}},
    )
    for prop in runner.props.props:
        put(f"catalog/props/{prop.prop_id}.png", png)
    for item in runner.items.items:
        put(f"catalog/items/{item.item_id}.png", png)
    for layer in runner.track.layers:
        put_json(
            f"world/layers/{layer.layer_id}.validation.json",
            {
                "width": 1536,
                "height": 1024,
                "placement": {"vertical_offset": 12.0, "vertical_offset_source": "source"},
            },
        )
    for effect in runner.audio.effects:
        put_json(f"audio/{effect.effect_id}.validation.json", {"duration_seconds": 2.5})
    before = {
        path.relative_to(run_dir): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    }

    manifest = build_manifest(
        plan.resolved,
        run_dir=run_dir,
        read_artifact=lambda ref: (run_dir / ref).read_bytes(),
        structural_material_identity=_unexpected_material_identity,
    )

    # Recorded from the previous handler using these exact admitted assets. This
    # pins the entire runtime document, including nulls, block versions and calibration.
    assert (
        canonical_sha256(manifest)
        == "e9a372a526f1cc539c90e6534a6276e011d34a1bc369d481e9c6b6e67e5d4053"
    )
    assert {
        path.relative_to(run_dir): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    } == before
