from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path


def test_external_fixture_uses_only_the_declared_gnode_surface_and_executes(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).resolve().parents[2]
    fixture = repository / "tests/contract/fixtures/external_image_consumer"
    package_root = fixture / "src"
    sources = sorted(package_root.rglob("*.py"))
    assert sources

    violations: list[str] = []
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("gnode.") or alias.name.startswith("stage_gen"):
                        violations.append(f"{path.name}:{node.lineno} imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith("gnode.") or module.startswith("stage_gen"):
                    violations.append(f"{path.name}:{node.lineno} imports {module}")
    assert not violations, "external fixture bypasses declared imports:\n" + "\n".join(violations)

    environment = os.environ.copy()
    for name in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "FAL_KEY"):
        environment.pop(name, None)
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(package_root), existing_pythonpath) if part
    )
    completed = subprocess.run(
        [sys.executable, "-m", "external_image_consumer", str(tmp_path / "output")],
        cwd=fixture,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(completed.stdout)
    assert report["ok"] is True
    assert report["provider_operations"] == {"image_generation": 1}
    assert report["backend_calls"] == 1
    assert report["node_provider"] == "fixture-provider"
    assert report["provenance_route_id"] == "fixture.image.generation"
    assert len(report["binding_ref"]) == len(report["artifact_sha256"]) == 64
