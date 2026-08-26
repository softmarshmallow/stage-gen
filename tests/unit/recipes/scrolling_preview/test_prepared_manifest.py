from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PIL import Image

from stage_gen.orchestration.game_package import resolve_game_package
from stage_gen.recipes.scrolling_preview.prepared_manifest import (
    PREPARED_RUNTIME_MANIFEST_KIND,
    PreparedManifestError,
    assemble_prepared_runtime,
    runtime_artifact_paths,
    verify_prepared_runtime,
)

REPOSITORY_ROOT = Path(__file__).parents[4]
BELLWEATHER = REPOSITORY_ROOT / "library/games/bellweather"


def _write_artifact(root: Path, relative_path: str, *, color: int = 40) -> None:
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix == ".mp3":
        target.write_bytes(b"ID3" + bytes([color]) * 32)
        return
    Image.new("RGBA", (16, 12), (color, 90, 180, 255)).save(target)


def test_runtime_manifest_is_stable_id_bound_and_portable(tmp_path: Path) -> None:
    package = resolve_game_package(BELLWEATHER)
    complete = tmp_path / "complete"
    correction = tmp_path / "correction"
    for relative_path in runtime_artifact_paths(package):
        _write_artifact(complete, relative_path)
    corrected_path = "content/players/wayfarer/states/idle.png"
    _write_artifact(correction, corrected_path, color=210)

    output = tmp_path / "runtime"
    result = assemble_prepared_runtime(
        package,
        artifact_roots=(correction, complete),
        output_dir=output,
    )

    assert result.manifest["kind"] == PREPARED_RUNTIME_MANIFEST_KIND
    assert result.artifact_count == len(runtime_artifact_paths(package))
    assert result.manifest["entry_map_id"] == "sunpetal-crossing"
    maps = result.manifest["maps"]
    assert isinstance(maps, list)
    assert [entry["map_id"] for entry in maps] == [
        "sunpetal-crossing",
        "crowncrag-road",
    ]
    corrected = output / corrected_path
    assert (
        hashlib.sha256(corrected.read_bytes()).hexdigest()
        == hashlib.sha256((correction / corrected_path).read_bytes()).hexdigest()
    )
    assert not any(str(output) in str(value) for value in result.manifest.values())
    closure = result.manifest["closure"]
    assert isinstance(closure, dict)
    assert verify_prepared_runtime(output) == {
        "schema_version": 1,
        "kind": "prepared-runtime-verification-v1",
        "valid": True,
        "game_id": "bellweather",
        "package_sha256": package.package_sha256,
        "artifact_count": len(runtime_artifact_paths(package)),
        "artifacts_sha256": closure["artifacts_sha256"],
    }


def test_runtime_manifest_missing_artifact_leaves_no_partial_output(tmp_path: Path) -> None:
    package = resolve_game_package(BELLWEATHER)
    incomplete = tmp_path / "incomplete"
    paths = runtime_artifact_paths(package)
    for relative_path in paths[:-1]:
        _write_artifact(incomplete, relative_path)
    output = tmp_path / "runtime"

    with pytest.raises(PreparedManifestError, match="missing accepted runtime artifact"):
        assemble_prepared_runtime(
            package,
            artifact_roots=(incomplete,),
            output_dir=output,
        )

    assert not output.exists()
    assert list(tmp_path.glob(".runtime.assembling-*")) == []
