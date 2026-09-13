"""Canonical 3D library representations retain portable, reviewed content bindings."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image

from stage_gen.components.character_3d.worker.rig_glb import read_glb
from tests.contract.test_packaged_resources import _worktree_files


def _regular_file(repository: Path, relative: str, tracked: set[str]) -> Path:
    assert isinstance(relative, str) and relative in tracked
    portable = PurePosixPath(relative)
    assert not portable.is_absolute() and portable.as_posix() == relative
    assert not any(part in {"", ".", ".."} for part in relative.split("/"))
    assert "\\" not in relative
    path = repository / portable
    for part in (portable, *portable.parents):
        assert not (repository / part).is_symlink(), relative
    assert path.is_file(), relative
    assert path.resolve().is_relative_to(repository.resolve()), relative
    return path


def _verified_file(repository: Path, record: dict[str, Any], tracked: set[str]) -> Path:
    path = _regular_file(repository, record["path"], tracked)
    assert type(record["bytes"]) is int and record["bytes"] > 0
    assert isinstance(record["sha256"], str)
    assert re.fullmatch(r"[a-f0-9]{64}", record["sha256"])
    payload = path.read_bytes()
    assert len(payload) == record["bytes"], record["path"]
    assert hashlib.sha256(payload).hexdigest() == record["sha256"], record["path"]
    return path


def test_character_library_3d_representations_are_content_bound() -> None:
    repository = Path(__file__).resolve().parents[2]
    tracked = _worktree_files(repository)
    representations = {
        PurePosixPath(name).parent
        for name in tracked
        if name.startswith("library/characters/")
        and PurePosixPath(name).name in {"sd_3d.json", "sd_3d.glb", "sd_3d.webp"}
    }
    for directory in sorted(representations):
        assert len(directory.parts) == 3
        character_id = directory.name
        manifest_path = _regular_file(repository, (directory / "sd_3d.json").as_posix(), tracked)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert type(manifest["schema_version"]) is int and manifest["schema_version"] == 1
        assert manifest["character_id"] == character_id
        assert manifest["representation_id"] == "sd_3d"

        source = manifest["source"]
        source_path = _verified_file(repository, source, tracked)
        assert source_path.parent == repository / directory
        assert source_path.suffix == ".webp" and source_path.name != "sd_3d.webp"
        assert isinstance(source["rights_basis"], str) and source["rights_basis"].strip()
        assert isinstance(manifest["generation"], dict) and manifest["generation"]

        artifacts = manifest["artifacts"]
        assert isinstance(artifacts, list) and len(artifacts) == 2
        expected = {
            (directory / "sd_3d.glb").as_posix(): "model/gltf-binary",
            (directory / "sd_3d.webp").as_posix(): "image/webp",
        }
        assert {artifact["path"] for artifact in artifacts} == set(expected)
        for artifact in artifacts:
            path = _verified_file(repository, artifact, tracked)
            assert artifact["media_type"] == expected[artifact["path"]]
            if path.suffix == ".glb":
                # The existing bounded decoder rejects external buffers/images, invalid
                # buffer ranges, nonfinite accessors and cyclic scene hierarchies.
                document, _ = read_glb(path)
                assert document.get("asset", {}).get("version") == "2.0"
                assert document.get("meshes") and document.get("scenes")
            else:
                assert type(artifact["width"]) is int and artifact["width"] > 0
                assert type(artifact["height"]) is int and artifact["height"] > 0
                with Image.open(path) as image:
                    assert image.format == "WEBP"
                    assert image.size == (artifact["width"], artifact["height"])
                    image.verify()

        review = manifest["visual_review"]
        assert review["independent"] is True and review["verdict"] == "pass"
        report = _verified_file(repository, review["report"], tracked)
        assert report.parent == repository / directory and report.suffix == ".md"
        report_text = report.read_text(encoding="utf-8")
        assert all(artifact["sha256"] in report_text for artifact in artifacts)

        rights = manifest["rights"]
        assert rights["status"] == "redistribution-approved"
        assert isinstance(rights["basis"], list) and rights["basis"]
        assert all(isinstance(basis, str) and basis.strip() for basis in rights["basis"])
        assert isinstance(rights["reviewed_at"], str) and rights["reviewed_at"].endswith("Z")
        assert datetime.fromisoformat(rights["reviewed_at"]).utcoffset() == UTC.utcoffset(None)
