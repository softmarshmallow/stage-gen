"""Copy one supplied image into this consumer's own binding, without generating.

The content directory is owned entirely by this preparation script. An adjacent
canonical provenance sidecar is checked and copied unchanged when present.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import tempfile
from pathlib import Path

from PIL import Image


def prepare_asset(source: Path, project: Path) -> None:
    data = source.read_bytes()
    with Image.open(io.BytesIO(data)) as image:
        if image.format != "PNG":
            raise ValueError("asset must be a PNG")
        if not all(1 <= size <= 16384 for size in image.size):
            raise ValueError("asset dimensions must be between 1 and 16384 pixels")
        image.verify()
    sidecar = Path(f"{source}.meta.json")
    metadata: bytes | None = None
    if sidecar.exists():
        metadata = sidecar.read_bytes()
        record = json.loads(metadata)
        artifact = record.get("artifact", {}) if isinstance(record, dict) else {}
        if not isinstance(artifact, dict):
            raise ValueError("asset provenance must contain an artifact record")
        if (
            artifact.get("sha256") != hashlib.sha256(data).hexdigest()
            or artifact.get("bytes") != len(data)
            or artifact.get("media_type") != "image/png"
        ):
            raise ValueError("asset provenance does not match the supplied PNG")

    project = project.resolve(strict=True)
    if not (project / "project.godot").is_file():
        raise ValueError("destination must be an asset consumer project")
    target = project / "content"
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise ValueError("consumer content must be a real directory")
    with tempfile.TemporaryDirectory(prefix=".asset-consumer-", dir=project) as scratch:
        staging = Path(scratch) / "content"
        staging.mkdir()
        (staging / "preview.png").write_bytes(data)
        if metadata is not None:
            (staging / "preview.png.meta.json").write_bytes(metadata)
        backup = Path(scratch) / "previous"
        if target.exists():
            target.rename(backup)
        try:
            staging.rename(target)
        except BaseException:
            if backup.exists():
                backup.rename(target)
            raise
        if backup.exists():
            shutil.rmtree(backup)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", type=Path, required=True)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    prepare_asset(args.asset, args.project)
    print("Prepared content/preview.png for the asset consumer.")


if __name__ == "__main__":
    main()
