"""A stand-in for Blender behind the character worker's command line, for offline tests.

It is invoked exactly as Blender is (``--background ... --python <entry> -- --request R
--input-root I --output-root O``) and answers the worker operations the character workflow
uses: ``normalize``, ``render``, ``inspect``, ``assemble`` and ``provider_rig``. Its models
are binary glTF containers whose JSON chunk holds a small document saying what the model is
(an export lists its clips as glTF animations); a model that says ``"untextured"`` is
refused by normalize, and one that says ``"damaged"`` fails the provider rig's
preservation audit, both the way the real worker refuses: one ``WORKER_ERROR`` line and a
nonzero exit.

The test writes this file out with a shebang naming its own Python, and sets ``CLIPS`` to
the diagnostic clips the profiles ask for, ``PRESERVATION_MESSAGE`` to the worker's own
refusal, and ``HOLD`` to a file that, while it exists, keeps the provider rig waiting.
"""

from __future__ import annotations

import hashlib
import json
import struct
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

CLIPS: list[str] = []
PRESERVATION_MESSAGE = ""
#: While this file exists, the provider rig waits here, so a test can kill the run mid-step.
HOLD = ""


def refuse(error_type: str, message: str) -> None:
    print("WORKER_ERROR " + json.dumps({"error_type": error_type, "message": message}))
    raise SystemExit(3)


def glb(document: dict[str, Any]) -> bytes:
    """A binary glTF holding only a JSON chunk: ``document``."""

    chunk = json.dumps(document, sort_keys=True).encode()
    chunk += b" " * (-len(chunk) % 4)
    header = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(chunk))
    return header + struct.pack("<I4s", len(chunk), b"JSON") + chunk


def unglb(data: bytes) -> dict[str, Any]:
    if data[:4] != b"glTF":
        refuse("ValueError", "not a binary glTF")
    length = struct.unpack("<I", data[12:16])[0]
    document: dict[str, Any] = json.loads(data[20 : 20 + length])
    return document


def model(root: Path, source: dict[str, Any]) -> dict[str, Any]:
    data = (root / source["path"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != source["sha256"]:
        refuse("ValueError", "source digest differs")
    return unglb(data)


def write_model(path: Path, document: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = glb(document)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def inventory(document: dict[str, Any]) -> dict[str, Any]:
    height = float(document.get("height", 1.0))
    meshes = document.get("meshes") or [document.get("role", "character")]
    return {
        "bounds": {
            "min": [-0.3, 0.0, -0.2],
            "max": [0.3, height, 0.2],
            "dimensions": [0.6, height, 0.4],
        },
        "meshes": [{"name": name, "triangles": 1200} for name in meshes],
        "images": [
            {"name": "albedo", "width": 64, "height": 64, "packed": True, "packed_sha256": "0" * 64}
        ],
        "triangles": 1200 * len(meshes),
    }


def picture(path: Path, size: int, height: int | None) -> None:
    image = Image.new("RGB", (size, size), (200, 200, 205))
    figure = height or size // 2
    top = (size - figure) // 2
    ImageDraw.Draw(image).rectangle(
        (size // 2 - figure // 6, top, size // 2 + figure // 6, top + figure - 1), fill=(90, 70, 50)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def main() -> None:
    arguments = sys.argv[sys.argv.index("--") + 1 :]
    values = dict(zip(arguments[::2], arguments[1::2], strict=True))
    request = json.loads(Path(values["--request"]).read_text())
    inputs, outputs = Path(values["--input-root"]), Path(values["--output-root"])
    out = outputs / request["output_dir"]
    operation = request["operation"]
    options = request.get("options", {})
    report: dict[str, Any] = {"schema_version": 1, "operation": operation}
    if operation == "normalize":
        document = model(inputs, request["source"])
        if document.get("untextured"):
            refuse("ValueError", "Imported mesh has no packed texture")
        normalized = {**document, "kind": "normalized"}
        write_model(out / "model.glb", normalized)
        report["result"] = {"after_reimport": inventory(normalized)}
    elif operation == "render":
        model(inputs, request["source"])
        height = options.get("character_height_pixels")
        size = options["resolution"][0]
        images = []
        for view in options["views"]:
            name = view if isinstance(view, str) else view["name"]
            picture(out / f"{name}.png", size, height)
            entry: dict[str, Any] = {"name": name, "image": f"{name}.png"}
            if height is not None:
                entry["projected_geometry"] = {"height_pixels": height, "fully_in_frame": True}
                entry["requested_character_height_pixels"] = height
            images.append(entry)
        report["pose"] = options.get("pose")
        report["result"] = {"images": images, "framing_bounds": {"min": [0, 0, 0], "max": [1] * 3}}
    elif operation == "inspect":
        report["result"] = inventory(model(inputs, request["source"]))
    elif operation == "assemble":
        parts = [model(inputs, part["source"]) for part in request["parts"]]
        roles = {part["role"]: part["role"] for part in request["parts"]}
        assembled = {
            "kind": "assembly",
            "height": max(float(part.get("height", 1.0)) for part in parts),
            "meshes": sorted(roles),
            "damaged": any(part.get("damaged") for part in parts),
            "draws": [part["draw"] for part in parts if "draw" in part],
        }
        write_model(out / "model.glb", assembled)
        report["export"] = {"after_reimport": inventory(assembled)}
        report["part_roles"] = roles
        report["seams"] = {"policy": "preserve"}
    elif operation == "provider_rig":
        if HOLD and Path(HOLD).exists():
            Path(HOLD + ".reached").write_text("")
            time.sleep(60)
        rigged = model(inputs, request["source"])
        if rigged.get("damaged"):
            refuse("ValueError", PRESERVATION_MESSAGE)
        exported = {
            **rigged,
            "kind": "export",
            "height": options["target_height"],
            "animations": [{"name": name} for name in ["rest", *CLIPS]],
        }
        sha = write_model(out / "rig.glb", exported)
        report["output"] = {"path": "rig.glb", "sha256": sha}
        report["external_rig"] = {"unsupported_control_semantics": []}
        report["clips"] = [{"name": name, "duration_seconds": 1.0} for name in CLIPS]
        report["preservation"] = {"appearance_preserved": True}
    else:
        refuse("ValueError", f"the stand-in does not do {operation}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report))


if __name__ == "__main__":
    main()
