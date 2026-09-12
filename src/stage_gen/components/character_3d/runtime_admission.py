"""Bounded, credential-free admission of the selected local Blender runtime."""

from __future__ import annotations

import asyncio
import math
import os
import signal
from pathlib import Path
from typing import Any

from PIL import Image

from stage_gen.components.character_3d.io import confined, digest, read_json, write_json

CAPABILITIES = (
    "worker_modules",
    "glb_export",
    "glb_import",
    "embedded_texture_import",
    "fbx_import",
    "fbx_embedded_texture_import",
    "armature_auto_weights",
    "skin_deformation",
    "native_blend_save",
    "cycles_cpu_render",
    "calibrated_orthographic_render",
)
SUPPORTED_BLENDER = (5, 2)


class RuntimeAdmissionError(ValueError):
    """Safe diagnostic: never include child output or an environment value."""


def executable_identity(blender: Path) -> dict[str, Any]:
    path = Path(blender).resolve(strict=True)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise RuntimeAdmissionError("Selected Blender is not an executable regular file")
    return {"sha256": digest(path), "bytes": path.stat().st_size}


def validate_probe(report: dict[str, Any], output: Path) -> None:
    if report.get("schema_version") != 1 or report.get("status") != "probe_passed":
        raise RuntimeAdmissionError("Local runtime probe did not pass")
    runtime = report.get("runtime", {})
    version = runtime.get("blender_version", [])
    if (
        not isinstance(version, list)
        or len(version) != 3
        or any(type(value) is not int for value in version)
        or (tuple(version[:2]) != SUPPORTED_BLENDER)
    ):
        raise RuntimeAdmissionError("Only the measured Blender 5.2 runtime family is admitted")
    if any(
        not isinstance(runtime.get(key), str) or not runtime[key]
        for key in ("build_hash", "python_version", "numpy_version")
    ):
        raise RuntimeAdmissionError("Runtime build and dependency evidence is incomplete")
    capabilities = report.get("capabilities", {})
    if set(capabilities) != set(CAPABILITIES) or any(
        capabilities[name] is not True for name in CAPABILITIES
    ):
        raise RuntimeAdmissionError("Required local runtime capabilities are unavailable")
    projection = report.get("projection", {})
    height = projection.get("height_pixels")
    if (
        type(height) not in {int, float}
        or not math.isfinite(height)
        or abs(height - 64) > 0.001
        or (projection.get("fully_in_frame") is not True)
    ):
        raise RuntimeAdmissionError("The actual runtime failed calibrated image framing")
    image_path = confined(output, "positive_z.png")
    with Image.open(image_path) as image:
        if image.format != "PNG" or image.size != (128, 128):
            raise RuntimeAdmissionError("The runtime did not produce the required PNG")
        image.verify()
    for name in ("probe.glb", "probe.fbx", "probe.blend"):
        if confined(output, name).stat().st_size == 0:
            raise RuntimeAdmissionError("Runtime round-trip evidence is empty")


async def admit_runtime(
    *,
    blender: Path,
    package_root: Path,
    run_root: Path,
    output_dir: str = "runtime_admission",
    timeout_seconds: float = 90,
) -> dict[str, Any]:
    """Execute only our fixed probe, before model activity; retain a fresh receipt.

    This checks a tiny synthetic fixture, not arbitrary generated-model quality.
    The executable digest is suitable for inclusion in the host's resume identity.
    """
    if (
        type(timeout_seconds) not in {int, float}
        or not math.isfinite(timeout_seconds)
        or (not 0 < timeout_seconds <= 180)
    ):
        raise RuntimeAdmissionError("Runtime admission timeout must be within 180 seconds")
    executable = await asyncio.to_thread(Path(blender).resolve, strict=True)
    identity = await asyncio.to_thread(executable_identity, executable)
    script = confined(package_root, "worker/runtime_probe.py")
    output = confined(run_root, output_dir, must_exist=False)
    if output.exists():
        raise RuntimeAdmissionError("Runtime admission requires a fresh output directory")
    output.mkdir(parents=True, exist_ok=False)
    environment = {
        key: os.environ[key]
        for key in ("PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")
        if key in os.environ
    }
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [
        str(executable),
        "--background",
        "--factory-startup",
        "--disable-autoexec",
        "--python",
        str(script),
        "--",
        "--output",
        str(output),
    ]
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=environment,
            start_new_session=True,
        )
        assert process.stdout is not None
        async with asyncio.timeout(timeout_seconds):
            while await process.stdout.read(65536):
                pass
            await process.wait()
        if process.returncode != 0:
            raise RuntimeAdmissionError("The local runtime probe process failed")
        report = read_json(confined(output, "probe.json"))
        validate_probe(report, output)
        if await asyncio.to_thread(executable_identity, executable) != identity:
            raise RuntimeAdmissionError("Selected Blender changed during admission")
        artifacts = []
        for path in sorted(output.rglob("*")):
            if path.is_symlink():
                raise RuntimeAdmissionError("Runtime evidence must not contain symlinks")
            if not path.is_file():
                continue
            relative = path.relative_to(output).as_posix()
            safe = confined(output, relative)
            artifacts.append(
                {
                    "path": output_dir + "/" + relative,
                    "sha256": digest(safe),
                    "bytes": safe.stat().st_size,
                }
            )
        result = {
            "schema_version": 1,
            "status": "runtime_admitted",
            "executable": identity,
            "probe": {"path": "worker/runtime_probe.py", "sha256": digest(script)},
            "runtime": report["runtime"],
            "capabilities": report["capabilities"],
            "artifacts": artifacts,
            "scope": ("Synthetic local format, rig and render capability; not character quality"),
        }
        write_json(output / "admission.json", result)
        return result
    except BaseException as error:
        if process is not None and process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                async with asyncio.timeout(5):
                    await process.wait()
            except (ProcessLookupError, TimeoutError):
                if process.returncode is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    await process.wait()
        write_json(
            output / "failure.json",
            {
                "schema_version": 1,
                "status": "runtime_refused",
                "error_type": type(error).__name__,
                "live_provider_dispatches": 0,
            },
        )
        raise
