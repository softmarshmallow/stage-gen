#!/usr/bin/env python3
"""Prepare the supplied local movie_sprite handoff for Afterlight, without generation.

This game-owned diagnostic adapter consumes final lossless bodies and independent
native face patches. It does not import or alter the repaint/generation pipeline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from PIL import __version__ as pillow_version

PROJECT = Path(__file__).resolve().parents[1]
REPOSITORY = PROJECT.parents[2]
SOURCE_ROOT = REPOSITORY / "spikes/movie_sprite"
FRAME_SIZE = (720, 1280)
NATIVE_SIZE = (2160, 3840)
FRAME_COUNT = 192
FPS = 16
COLUMNS, ROWS = 4, 2
SOURCE_SETS = {
    "yuzu": {
        "body": (
            "review/baseline-recovery/yuzu-4k-01-stabilization/pendant-repair/body-v2/rgba-720p.mkv"
        ),
        "canonical": "review/baseline-recovery/yuzu-4k-01-stabilization/prepared/canonical.png",
        "canonical_sha256": "591fda7e0756259000acc8be86bfde67b6d9ce4fc3dc1732f059ba30eaea5e08",
        "manifests": ["review/baseline-recovery/facial-yuzu4k-retry/run-01/render/manifest.json"],
        "reports": [
            "review/baseline-recovery/yuzu-4k-01-stabilization/pendant-repair/body-v2/report.json",
            "review/baseline-recovery/yuzu-4k-01-stabilization/pendant-repair/body-v2/independent-root-review.json",
            "review/baseline-recovery/yuzu-facial-v2/report.json",
        ],
        "eye_semantics": "bilateral_blink",
    },
    "riko": {
        "body": "review/baseline-recovery/riko-native-v2/body-alpha-720p.mkv",
        "canonical": "review/baseline-recovery/riko-native-v2/canonical.png",
        "canonical_sha256": "6c5f6ab184a3dc25b406ad5708acced3a0d62f3971e12ba8506292576ccae065",
        "manifests": [
            "review/facial-4k/riko-eye-left/run-01/render/manifest.json",
            "review/facial-4k/riko-a-retry/run-01/render/manifest.json",
            "review/facial-4k/riko-o/run-01/render/manifest.json",
        ],
        "reports": ["review/baseline-recovery/riko-native-v2/report.json"],
        "eye_semantics": "canvas_left_wink",
    },
}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def confined_file(root: Path, relative: str) -> Path:
    """Reject traversal and symlinks before touching an input or bound output."""
    if (
        not relative
        or relative.startswith("/")
        or ":" in relative
        or "\\" in relative
        or any(part in {"", ".", ".."} for part in relative.split("/"))
    ):
        raise ValueError(f"Invalid relative file: {relative}")
    path = root / relative
    if any(item.is_symlink() for item in [path, *path.parents] if item.is_relative_to(root)):
        raise ValueError(f"Symbolic link refused: {relative}")
    if (
        not path.resolve(strict=True).is_relative_to(root.resolve(strict=True))
        or not path.is_file()
    ):
        raise ValueError(f"File escapes root or is not regular: {relative}")
    return path


def checked_artifact(root: Path, relative: str) -> tuple[Path, dict[str, Any]]:
    path = confined_file(root, relative)
    sidecar = confined_file(root, relative + ".meta.json")
    origin = json.loads(sidecar.read_text())
    recorded = origin.get("artifact", {})
    if recorded.get("sha256") != digest(path) or recorded.get("bytes") != path.stat().st_size:
        raise ValueError(f"Artifact differs from provenance: {relative}")
    return path, origin


def resize_rgba(pixels: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Match the handoff's float premultiplied Lanczos and one final rounding."""
    if pixels.dtype != np.uint8 or pixels.ndim != 3 or pixels.shape[2] != 4:
        raise ValueError("Resampling requires uint8 straight RGBA.")
    alpha = pixels[..., 3].astype(np.float32) / 255
    sampled_alpha = np.asarray(Image.fromarray(alpha).resize(size, Image.Resampling.LANCZOS))
    sampled_alpha = sampled_alpha.clip(0, 1)
    channels = []
    for channel in range(3):
        premultiplied = pixels[..., channel].astype(np.float32) * alpha
        sampled = np.asarray(Image.fromarray(premultiplied).resize(size, Image.Resampling.LANCZOS))
        straight = np.divide(
            sampled, sampled_alpha, out=np.zeros_like(sampled), where=sampled_alpha > 0
        )
        channels.append(np.rint(straight).clip(0, 255).astype(np.uint8))
    channels.append(np.rint(sampled_alpha * 255).astype(np.uint8))
    result = np.stack(channels, axis=-1)
    result[result[..., 3] == 0, :3] = 0
    return result


def apply_patches(canonical: np.ndarray, patches: list[tuple[int, int, np.ndarray]]) -> np.ndarray:
    """Replace selected RGB at native integer offsets without changing source alpha."""
    result = canonical.copy()
    for x, y, patch in patches:
        height, width = patch.shape[:2]
        if x < 0 or y < 0 or x + width > result.shape[1] or y + height > result.shape[0]:
            raise ValueError("Native patch exceeds the canonical canvas.")
        if not np.isin(patch[..., 3], [0, 255]).all():
            raise ValueError("Native patch selection alpha must be binary.")
        region = result[y : y + height, x : x + width]
        selected = patch[..., 3] == 255
        if not selected.any() or not (region[..., 3][selected] == 255).all():
            raise ValueError("Facial support must be nonempty and inside opaque canonical anatomy.")
        region[..., :3][selected] = patch[..., :3][selected]
    return result


def replacement_texture(canonical: np.ndarray, painted: np.ndarray) -> np.ndarray:
    """The mask selects already composed RGB; it is not another feather weight."""
    if canonical.shape != painted.shape or not np.array_equal(canonical[..., 3], painted[..., 3]):
        raise ValueError("Face repaint must preserve canonical alpha.")
    result = painted.copy()
    result[..., 3] = np.any(canonical[..., :3] != painted[..., :3], axis=2).astype(np.uint8) * 255
    return result


def decode_frames(
    source: Path, size: tuple[int, int], count: int, fps: int
) -> Iterator[np.ndarray]:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(source)],
        check=True,
        capture_output=True,
        text=True,
    )
    streams = json.loads(probe.stdout)["streams"]
    if len(streams) != 1:
        raise ValueError("Body source must have one video stream and no audio.")
    stream = streams[0]
    if (
        stream.get("codec_name") != "ffv1"
        or stream.get("pix_fmt") != "bgra"
        or (stream.get("width"), stream.get("height")) != size
        or stream.get("r_frame_rate") != f"{fps}/1"
    ):
        raise ValueError("Body source does not match the lossless BGRA dimensions and timebase.")
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-fps_mode",
        "passthrough",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "pipe:1",
    ]
    frame_bytes = size[0] * size[1] * 4
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
        assert process.stdout is not None
        try:
            for index in range(count):
                raw = process.stdout.read(frame_bytes)
                if len(raw) != frame_bytes:
                    raise ValueError(f"Body source ended during frame {index}.")
                yield np.frombuffer(raw, dtype=np.uint8).reshape(size[1], size[0], 4).copy()
            if process.stdout.read(1):
                raise ValueError("Body source has more frames than its explicit contract.")
            if process.wait() != 0:
                raise ValueError("FFmpeg failed to decode the complete body.")
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.kill()
            process.wait()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def pack_frames(
    frames: Iterator[np.ndarray],
    output: Path,
    canonical: np.ndarray,
    support: np.ndarray,
    *,
    count: int = FRAME_COUNT,
    columns: int = COLUMNS,
    rows: int = ROWS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    height, width = canonical.shape[:2]
    page = Image.new("RGBA", (width * columns, height * rows))
    pages = []
    hashes = []
    bounds: tuple[int, int, int, int] | None = None
    first = last = None
    frame_index = -1
    for frame_index, frame in enumerate(frames):
        if frame_index >= count or frame.shape != canonical.shape:
            raise ValueError("Decoded body does not match the frame contract.")
        if not np.array_equal(frame[support], canonical[support]):
            raise ValueError(f"Facial registration differs from canonical at frame {frame_index}.")
        if not np.any(frame[..., 3] == 0) or not np.any(frame[..., 3] == 255):
            raise ValueError("Body requires both transparent and opaque pixels.")
        raw_hash = hashlib.sha256(frame.tobytes()).hexdigest()
        hashes.append(raw_hash)
        if first is None:
            first = frame.copy()
        last = frame
        image = Image.fromarray(frame)
        current = image.getbbox(alpha_only=True)
        assert current is not None
        bounds = (
            current
            if bounds is None
            else (
                min(bounds[0], current[0]),
                min(bounds[1], current[1]),
                max(bounds[2], current[2]),
                max(bounds[3], current[3]),
            )
        )
        local = frame_index % (columns * rows)
        page.paste(image, ((local % columns) * width, (local // columns) * height))
        if local == columns * rows - 1 or frame_index == count - 1:
            path = output / f"body_{len(pages):03d}.png"
            page.save(path, compress_level=6)
            with Image.open(path) as decoded:
                if decoded.tobytes() != page.tobytes():
                    raise ValueError("PNG atlas did not retain exact straight RGBA bytes.")
            pages.append({"file": path.name, "sha256": digest(path)})
            page = Image.new("RGBA", page.size)
    if frame_index + 1 != count or first is None or not np.array_equal(first, last):
        raise ValueError("Body must contain the expected count and identical endpoint frames.")
    assert bounds is not None
    return pages, {
        "decoded_frame_count": count,
        "endpoint_rgba_equal": True,
        "all_frame_registration_exact": True,
        "atlas_rgba_exact": True,
        "body_alpha_unchanged": True,
        "frame_rgba_sha256": hashes,
        "visible_alpha_bounds_xywh": [
            bounds[0],
            bounds[1],
            bounds[2] - bounds[0],
            bounds[3] - bounds[1],
        ],
    }


def prepare_character(source_root: Path, character_id: str, output: Path) -> dict[str, Any]:
    """Create a new actor directory atomically; never overwrite existing assets."""
    if character_id not in SOURCE_SETS:
        raise ValueError("Only the two explicitly handed-off characters are supported.")
    source_root = source_root.resolve(strict=True)
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Destination already exists; choose a new directory.")
    if any(parent.is_symlink() for parent in output.parents):
        raise ValueError("Destination cannot use symbolic links.")
    config = SOURCE_SETS[character_id]
    sources: dict[str, Path] = {}

    def source(relative: str, artifact: bool = True) -> Path:
        if artifact:
            path, _ = checked_artifact(source_root, relative)
            sources[relative + ".meta.json"] = confined_file(source_root, relative + ".meta.json")
        else:
            path = confined_file(source_root, relative)
        sources[relative] = path
        return path

    body = source(config["body"])
    canonical_path = source(config["canonical"])
    if digest(canonical_path) != config["canonical_sha256"]:
        raise ValueError("The final canonical does not match the selected handoff revision.")
    canonical = np.array(Image.open(canonical_path).convert("RGBA"))
    if canonical.shape != (NATIVE_SIZE[1], NATIVE_SIZE[0], 4):
        raise ValueError("Native canonical dimensions differ from the handoff.")
    patches: dict[str, list[tuple[int, int, np.ndarray]]] = {}
    geometry = []
    for relative in config["manifests"]:
        manifest_path = source(relative)
        manifest = json.loads(manifest_path.read_text())
        run_root = manifest_path.parent.parent
        if (
            manifest.get("kind") != "portrait-face-motion-v1"
            or manifest.get("patch_application") != "replace_selected_rgb_preserve_original_alpha"
            or manifest.get("feather_already_baked") is not True
            or manifest.get("source_size") != list(NATIVE_SIZE)
        ):
            raise ValueError("Facial manifest does not match the existing repaint contract.")
        offset = manifest["offset_xy"]
        if len(offset) != 2 or any(type(value) is not int for value in offset):
            raise ValueError("Native placement must use two integer coordinates.")
        for relative_input in [manifest["source_ref"], manifest["transform_ref"]]:
            path = confined_file(run_root, relative_input)
            source(path.relative_to(source_root).as_posix())
        source_canonical = np.array(
            Image.open(confined_file(run_root, manifest["source_ref"])).convert("RGBA")
        )
        if source_canonical.shape != canonical.shape:
            raise ValueError("Facial source canonical dimensions differ from final canonical.")
        for item in manifest["patches"]:
            path = confined_file(run_root, item["ref"])
            path = source(path.relative_to(source_root).as_posix())
            if digest(path) != item["sha256"]:
                raise ValueError("Facial patch differs from its render manifest.")
            state = item["state_id"]
            if state not in {"eyes_half", "eyes_closed", "mouth_a", "mouth_o"}:
                raise ValueError("Unsupported facial state in the diagnostic input.")
            pixels = np.array(Image.open(path).convert("RGBA"))
            if list(pixels.shape[1::-1]) != manifest["patch_size"]:
                raise ValueError("Patch size does not match its native placement manifest.")
            x, y = offset
            height, width = pixels.shape[:2]
            selected = pixels[..., 3] > 0
            if not np.array_equal(
                source_canonical[y : y + height, x : x + width][selected],
                canonical[y : y + height, x : x + width][selected],
            ):
                raise ValueError(
                    "Facial source differs from final canonical on native patch support."
                )
            patches.setdefault(state, []).append((*offset, pixels))
            geometry.append(
                {
                    "state_id": state,
                    "feature_id": item["feature_id"],
                    "offset_xy": offset,
                    "patch_size": manifest["patch_size"],
                }
            )
    for relative in config["reports"]:
        source(relative, artifact=(source_root / (relative + ".meta.json")).is_file())
    source("review/baseline-recovery/final-review.json", artifact=False)
    source("GAME_ASSET_HANDOFF.md", artifact=False)
    expected = {"eyes_closed", "mouth_a", "mouth_o"}
    if character_id == "yuzu":
        expected.add("eyes_half")
    if set(patches) != expected:
        raise ValueError("Supplied facial states differ from the diagnostic casting contract.")
    baseline = resize_rgba(canonical, FRAME_SIZE)
    painted = {
        state: resize_rgba(apply_patches(canonical, items), FRAME_SIZE)
        for state, items in patches.items()
    }
    textures = {state: replacement_texture(baseline, pixels) for state, pixels in painted.items()}
    support = np.zeros(baseline.shape[:2], dtype=bool)
    for pixels in textures.values():
        support |= pixels[..., 3] > 0
    combination_count = 0
    for eye in [state for state in textures if state.startswith("eyes")]:
        for mouth in [state for state in textures if state.startswith("mouth")]:
            eye_mask, mouth_mask = textures[eye][..., 3] > 0, textures[mouth][..., 3] > 0
            if np.any(eye_mask & mouth_mask):
                raise ValueError(
                    "Resampled eye and mouth support overlaps; do not overwrite sequentially."
                )
            sequential = baseline.copy()
            sequential[eye_mask] = painted[eye][eye_mask]
            sequential[mouth_mask] = painted[mouth][mouth_mask]
            joint = resize_rgba(apply_patches(canonical, patches[eye] + patches[mouth]), FRAME_SIZE)
            if not np.array_equal(joint, sequential):
                raise ValueError(
                    "Independent facial composition differs from native joint repaint."
                )
            combination_count += 1
    output.parent.mkdir(parents=True, exist_ok=True)
    ignore_marker = output.parent / ".gdignore"
    if ignore_marker.is_symlink():
        raise ValueError("Godot import marker cannot be a symbolic link.")
    if not ignore_marker.exists():
        ignore_marker.write_text("")
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    prefix = f"assets/movie_sprite/{character_id}/"
    try:
        pages, validation = pack_frames(
            decode_frames(body, FRAME_SIZE, FRAME_COUNT, FPS), temporary, baseline, support
        )
        for page in pages:
            page["file"] = prefix + page["file"]
        entries = {}
        for state, pixels in textures.items():
            path = temporary / f"{state}.png"
            Image.fromarray(pixels).save(path, compress_level=6)
            entries[state] = {"file": prefix + path.name, "sha256": digest(path)}
        Image.fromarray(baseline).save(temporary / "canonical_720.png", compress_level=6)
        provenance = temporary / "provenance"
        inventory = []
        for relative, path in sorted(sources.items()):
            target = provenance / "sources" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            sha = digest(path)
            if digest(target) != sha:
                raise ValueError("Copied provenance content differs from its source.")
            inventory.append(
                {
                    "source_ref": f"spikes/movie_sprite/{relative}",
                    "copied_ref": target.relative_to(temporary).as_posix(),
                    "sha256": sha,
                    "bytes": path.stat().st_size,
                }
            )
        validation.update(
            {
                "independent_face_combinations_exact": combination_count,
                "eye_mouth_selection_disjoint": True,
            }
        )
        preparation = {
            "schema_version": 1,
            "kind": "afterlight_local_movie_sprite_preparation",
            "character_id": character_id,
            "source_inventory": inventory,
            "tool_sha256": digest(Path(__file__)),
            "pillow_version": pillow_version,
            "numpy_version": np.__version__,
            "native_size": list(NATIVE_SIZE),
            "runtime_size": list(FRAME_SIZE),
            "canonical_runtime_rgba_sha256": hashlib.sha256(baseline.tobytes()).hexdigest(),
            "native_patch_geometry": geometry,
            "face_resampling": "native RGB replacement; float premultiplied Lanczos; one rint",
            "replacement_alpha": "binary changed-RGB selection, not anatomical opacity",
            "validation": validation,
            "rights": {
                "local_diagnostic_activation_authorized": True,
                "authorization": "User requested local diagnostic integration on 2026-09-14.",
                "publication_authorized": False,
                "redistribution_established": False,
                "source_rights": "Unchanged; original sidecars copied byte-for-byte.",
            },
            "limitations": [
                "Native edge softness remains.",
                "No viseme or audio synchronization claim.",
                "Riko supports canvas-left wink, not bilateral blinking.",
                "Generation-module promotion is deferred.",
            ],
        }
        write_json(provenance / "preparation.json", preparation)
        manifest = {
            "schema_version": 1,
            "character_id": character_id,
            "frame_size": list(FRAME_SIZE),
            "frame_count": FRAME_COUNT,
            "fps": FPS,
            "columns": COLUMNS,
            "rows": ROWS,
            "pages": pages,
            "eyes": {key: value for key, value in entries.items() if key.startswith("eyes")},
            "mouths": {key: value for key, value in entries.items() if key.startswith("mouth")},
            "eye_semantics": config["eye_semantics"],
            "patch_application": "replace_selected_rgb_preserve_original_alpha",
            "preparation_ref": prefix + "provenance/preparation.json",
        }
        write_json(temporary / "manifest.json", manifest)
        file_inventory = {
            path.relative_to(temporary).as_posix(): digest(path)
            for path in sorted(temporary.rglob("*"))
            if path.is_file()
        }
        write_json(temporary / "inventory.json", {"schema_version": 1, "files": file_inventory})
        if output.exists() or output.is_symlink():
            raise ValueError("Destination appeared during preparation.")
        temporary.rename(output)
        return manifest
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--output-root", type=Path, default=PROJECT / "assets/movie_sprite")
    parser.add_argument("--character", choices=sorted(SOURCE_SETS), action="append")
    args = parser.parse_args()
    try:
        for character_id in args.character or sorted(SOURCE_SETS):
            result = prepare_character(
                args.source_root, character_id, args.output_root / character_id
            )
            print(
                json.dumps(
                    {
                        "character_id": character_id,
                        "pages": len(result["pages"]),
                        "status": "prepared",
                    }
                ),
                flush=True,
            )
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Movie sprite preparation failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
