"""Installed resource closure and run-owned execution snapshots."""

from __future__ import annotations

import base64
import hashlib
import importlib.metadata
import importlib.resources
import json
import sys
from pathlib import Path
from typing import Any, TypedDict

from .io import confined, read_json, verified_input, write_bytes, write_json

DEPENDENCIES = ("jsonschema", "httpx", "pydantic", "Pillow", "numpy")


class PackageMap(TypedDict):
    schema_version: int
    aliases: dict[str, str]


def installed_root() -> Path:
    import stage_gen

    return Path(stage_gen.__file__).resolve().parent.parent


def package_map() -> PackageMap:
    path = Path(
        str(
            importlib.resources.files("stage_gen.resources.character_3d").joinpath(
                "package-map.json"
            )
        )
    )
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("Unsupported installed character resource map")
    aliases = value.get("aliases")
    if not isinstance(aliases, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in aliases.items()
    ):
        raise ValueError("Installed character resources require string mappings")
    return {"schema_version": 1, "aliases": aliases}


def resource(ref: str) -> Path:
    mapping = package_map()
    if ref not in mapping["aliases"]:
        raise ValueError("Undeclared installed character resource")
    return confined(installed_root(), mapping["aliases"][ref])


def _worker_bootstrap(module: str) -> bytes:
    # Blender must not import the host package's eager component facade and its
    # Python-ABI-specific dependencies. Create only the fixed namespace ancestry;
    # worker code then imports other verified worker modules normally.
    return (
        '''"""Fixed run-owned Blender entry point from installed package sources."""
import importlib.machinery
import runpy
import sys
import types
from pathlib import Path
root = Path(__file__).resolve().parents[1]
for name in (
    "stage_gen", "stage_gen.components", "stage_gen.components.character_3d",
    "stage_gen.components.character_3d.worker",
):
    module = types.ModuleType(name)
    module.__path__ = [str(root.joinpath(*name.split(".")))]
    module.__package__ = name
    module.__spec__ = importlib.machinery.ModuleSpec(name, loader=None, is_package=True)
    sys.modules[name] = module
runpy.run_module('''
        + repr("stage_gen.components.character_3d.worker." + module)
        + """, run_name="__main__")
"""
    ).encode()


def _installed_payloads() -> list[tuple[str, bytes]]:
    """Read only hash-verified wheel sources and the declared fixed entry aliases."""
    root = installed_root()
    distribution = importlib.metadata.distribution("stage-gen")
    payloads = []
    for item in sorted(distribution.files or (), key=str):
        ref = str(item)
        if not (ref.startswith("stage_gen/") or ref.startswith("gnode/")) or ref.endswith(".pyc"):
            continue
        source = confined(root, ref)
        data = source.read_bytes()
        if item.hash is None or item.hash.mode != "sha256":
            raise ValueError("Installed source lacks a wheel integrity record")
        if (
            base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            != item.hash.value
        ):
            raise ValueError("Installed source differs from its declared wheel")
        payloads.append((ref, data))
    if not any(ref.startswith("stage_gen/") for ref, _ in payloads):
        raise ValueError(
            "The character launcher requires a wheel installation of stage-gen; an editable "
            "checkout has no verifiable installed sources to freeze"
        )
    mapping = package_map()
    for alias, installed_ref in sorted(mapping["aliases"].items()):
        data = confined(root, installed_ref).read_bytes()
        if alias.startswith("worker/") and alias.endswith(".py"):
            data = _worker_bootstrap(Path(alias).stem)
        payloads.append((alias, data))
    if not payloads or len({ref for ref, _ in payloads}) != len(payloads):
        raise ValueError("An installed source closure is required")
    return payloads


def _inventory(payloads: list[tuple[str, bytes]]) -> dict[str, Any]:
    entries = [
        {"path": ref, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        for ref, data in payloads
    ]
    return {
        "code": entries,
        "python": sys.version.split()[0],
        "dependencies": {name: importlib.metadata.version(name) for name in DEPENDENCIES},
        "package_closure_sha256": hashlib.sha256(
            json.dumps(entries, sort_keys=True).encode()
        ).hexdigest(),
    }


def installed_inventory() -> dict[str, Any]:
    """Verify the installed closure before creating any writable run directory."""
    return _inventory(_installed_payloads())


def snapshot_code(
    _package_root: Path | None, run_root: Path, *, support_admission: dict[str, Any] | None = None
) -> Path:
    """Copy installed distribution bytes across a real immutable run boundary."""
    payloads = _installed_payloads()
    inventory = _inventory(payloads)
    if support_admission is not None and (
        support_admission["target"]["package_closure_sha256"] != inventory["package_closure_sha256"]
        or support_admission["target"]["python_version"] != inventory["python"]
        or support_admission["target"]["runtime_dependencies"] != inventory["dependencies"]
    ):
        raise ValueError("Installed source changed between admission and snapshot")
    destination = run_root / "code"
    destination.mkdir(parents=True, exist_ok=False)
    for ref, data in payloads:
        write_bytes(destination / ref, data)
    write_json(
        run_root / "runtime.json",
        {
            "schema_version": 2,
            "python": inventory["python"],
            "code": inventory["code"],
            "dependencies": inventory["dependencies"],
            **({"support_admission": support_admission} if support_admission is not None else {}),
            "package_closure_sha256": inventory["package_closure_sha256"],
            "policy": (
                "Installed package resources, public SDK and application dependencies execute "
                "from a verified run-owned snapshot; third-party Python and Blender runtimes "
                "remain declared external dependencies."
            ),
        },
    )
    return destination


def verify_snapshot(run_root: Path) -> dict[str, Any]:
    value = read_json(confined(run_root, "runtime.json"))
    if value.get("schema_version") != 2:
        raise ValueError("Unsupported installed-runtime snapshot version")
    if value["python"].split(".")[:2] != sys.version.split()[0].split(".")[:2]:
        raise ValueError("Python major/minor differs from the frozen runtime")
    for name, version in value["dependencies"].items():
        if importlib.metadata.version(name) != version:
            raise ValueError("A frozen runtime dependency changed")
    entries = value["code"]
    if not entries or len({item["path"] for item in entries}) != len(entries):
        raise ValueError("Runtime requires unique content-addressed resources")
    for item in entries:
        verified_input(run_root / "code", {key: item[key] for key in ("path", "sha256")})
    if (
        hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()
        != value["package_closure_sha256"]
    ):
        raise ValueError("Runtime source closure changed")
    return value
