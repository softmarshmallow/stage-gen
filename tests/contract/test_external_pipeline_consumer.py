"""An installed product executes arbitrary external Python without importing demo packages."""

# test-owner: product
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def _install_wheel(repository: Path, tmp_path: Path, environment: dict[str, str]) -> Path:
    wheels = tmp_path / "wheels"
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(wheels)],
        cwd=repository,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    # Materialize the built wheel into an external site-packages ownership root.
    installed = tmp_path / "site-packages"
    with zipfile.ZipFile(next(wheels.glob("*.whl"))) as archive:
        archive.extractall(installed)
    for module in (
        "stage_gen_legacy",
        "demo_game_tools",
        "demo_game_collection",
        "bellweather_pipeline",
        "iron_petal_unit_pipeline",
        "ember_hollow_pipeline",
        "the_grain_pipeline",
    ):
        assert not (installed / module).exists()
    assert not (installed / "concept_studio").exists()
    return installed


def test_installed_public_pipeline_cli_plan_run_cache_failure_and_inspect(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    for key in (
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "FAL_KEY",
        "ELEVENLABS_API_KEY",
        "PYTHONPATH",
    ):
        environment.pop(key, None)
    installed = _install_wheel(repository, tmp_path, environment)
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    definition = consumer / "my_assets.py"
    shutil.copyfile(repository / "examples/pipelines/local_media.py", definition)
    inputs = consumer / "inputs"
    inputs.mkdir()
    (inputs / "palette.json").write_text('{"color": [24, 48, 72]}')
    bootstrap = """
import importlib.abc
import sys
from pathlib import Path
sys.path.insert(0, sys.argv.pop(1))
class NoOptionalConsumers(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {
            'concept_studio',
            'demo_game_collection',
            'demo_game_tools',
            'iron_petal_unit_pipeline',
            'bellweather_pipeline',
            'stage_gen_legacy',
            'ember_hollow_pipeline',
            'the_grain_pipeline',
        }:
            raise AssertionError('Public pipeline imported an optional consumer: ' + fullname)
sys.meta_path.insert(0, NoOptionalConsumers())
from stage_gen.interfaces.cli import main
import stage_gen.pipeline
assert Path(stage_gen.pipeline.__file__).is_relative_to(Path(sys.path[0]))
raise SystemExit(main())
"""

    def cli(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-I", "-c", bootstrap, str(installed), *arguments],
            cwd=consumer,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    planned = cli("pipeline", "plan", str(definition), "--input", str(inputs), "--target", "swatch")
    assert planned.returncode == 0, planned.stderr
    assert json.loads(planned.stdout)["projection"]["operation_counts"] == {"local": 1}
    cache = consumer / "cache"
    first = cli(
        "pipeline",
        "run",
        str(definition),
        "--input",
        str(inputs),
        "--output",
        str(consumer / "first"),
        "--cache-dir",
        str(cache),
    )
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)["ok"]
    second = cli(
        "pipeline",
        "run",
        str(definition),
        "--input",
        str(inputs),
        "--output",
        str(consumer / "second"),
        "--cache-dir",
        str(cache),
    )
    assert second.returncode == 0, second.stderr
    assert all(node["cache"] == "hit" for node in json.loads(second.stdout)["summary"]["nodes"])
    inspected = cli("pipeline", "inspect", str(consumer / "second"))
    assert inspected.returncode == 0, inspected.stderr
    assert json.loads(inspected.stdout)["pipeline_id"] == "local-media"
    (inputs / "palette.json").write_text('{"color": [999, 0, 0]}')
    failed = cli(
        "pipeline",
        "run",
        str(definition),
        "--input",
        str(inputs),
        "--output",
        str(consumer / "failed"),
        "--cache-dir",
        str(cache),
    )
    assert failed.returncode == 1, failed.stderr
    failure_view = cli("pipeline", "inspect", str(consumer / "failed"))
    assert failure_view.returncode == 0
    assert json.loads(failure_view.stdout)["run_state"] == "failed"
    refused = cli(
        "pipeline", "plan", str(definition), "--input", str(inputs), "--target", "unknown"
    )
    assert refused.returncode == 2
    assert "undeclared" in refused.stderr
    missing = cli("pipeline", "plan", "missing_external_pipeline", "--input", str(inputs))
    assert missing.returncode == 2 and "cannot load pipeline definition" in missing.stderr
    invalid = consumer / "invalid.py"
    invalid.write_text("pipeline = object()\n")
    rejected = cli("pipeline", "plan", str(invalid), "--input", str(inputs))
    assert rejected.returncode == 2 and "cannot load pipeline definition" in rejected.stderr
    invalid.write_text("invalid syntax !!!\n")
    malformed = cli("pipeline", "plan", str(invalid), "--input", str(inputs))
    assert malformed.returncode == 2 and "cannot load pipeline definition" in malformed.stderr


def test_public_cli_capabilities_and_components_import_without_optional_consumers() -> None:
    program = """
import importlib
import importlib.abc
import pkgutil
import sys
class NoConsumers(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {
            'concept_studio',
            'demo_game_collection',
            'demo_game_tools',
            'iron_petal_unit_pipeline',
            'bellweather_pipeline',
            'stage_gen_legacy',
            'ember_hollow_pipeline',
            'the_grain_pipeline',
        }:
            raise AssertionError('Public surface imported optional consumer: ' + fullname)
sys.meta_path.insert(0, NoConsumers())
import stage_gen.interfaces.cli
import stage_gen.application
import stage_gen.capabilities
import stage_gen.pipeline
import stage_gen.components
for module in pkgutil.iter_modules(stage_gen.components.__path__):
    if module.ispkg and not module.name.startswith('_'):
        importlib.import_module('stage_gen.components.' + module.name)
assert not any(
    name.split('.')[0] in {
        'stage_gen_legacy', 'concept_studio', 'demo_game_tools', 'demo_game_collection',
        'bellweather_pipeline', 'iron_petal_unit_pipeline',
        'ember_hollow_pipeline', 'the_grain_pipeline',
    }
    for name in sys.modules
)
print('public imports have no optional consumers')
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-c", program], check=False, capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr


def test_selected_product_tests_collect_using_only_the_installed_core(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    for key in (
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "FAL_KEY",
        "ELEVENLABS_API_KEY",
        "PYTHONPATH",
    ):
        environment.pop(key, None)
    environment["_STAGE_GEN_DISABLE_DOTENV"] = "1"
    installed = _install_wheel(repository, tmp_path, environment)
    program = """
import importlib.abc
import sys
from pathlib import Path
installed, repository = map(Path, sys.argv[1:])
sys.path[:0] = [str(installed), str(repository)]
attempted = set()
class NoConsumers(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {
            'concept_studio',
            'demo_game_collection',
            'demo_game_tools',
            'iron_petal_unit_pipeline',
            'bellweather_pipeline',
            'stage_gen_legacy',
            'ember_hollow_pipeline',
            'the_grain_pipeline',
        }:
            attempted.add(fullname)
            raise AssertionError('Product collection attempted an optional import: ' + fullname)
sys.meta_path.insert(0, NoConsumers())
from scripts.test_ownership import paths_for
import stage_gen.pipeline
assert Path(stage_gen.pipeline.__file__).is_relative_to(installed)
import pytest
status = pytest.main(['--collect-only', '-q', *paths_for(repository, 'product')])
assert not attempted, sorted(attempted)
raise SystemExit(status)
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-c", program, str(installed), str(repository)],
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "tests collected" in completed.stdout
