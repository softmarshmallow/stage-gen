"""Product collection follows real helper imports before loading optional packages."""

# test-owner: product
from __future__ import annotations

from pathlib import Path

from scripts.test_ownership import test_owners as collect_owners


def _write(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_relative_helper_imports_and_cycles_propagate_optional_ownership(tmp_path: Path) -> None:
    _write(tmp_path, "tests/feature/test_indirect.py", "from .helpers import value\n")
    _write(tmp_path, "tests/feature/helpers.py", "from . import cycle\nvalue = 1\n")
    _write(
        tmp_path, "tests/feature/cycle.py", "from . import helpers\nimport bellweather_pipeline\n"
    )
    _write(tmp_path, "tests/test_control.py", "value = 1\n")
    assert collect_owners(tmp_path) == {
        "tests/feature/test_indirect.py": "games",
        "tests/test_control.py": "product",
    }


def test_package_initializer_and_script_helper_dependencies_are_followed(tmp_path: Path) -> None:
    _write(tmp_path, "tests/feature/__init__.py", "import concept_studio\n")
    _write(tmp_path, "tests/feature/test_indirect.py", "value = 1\n")
    _write(tmp_path, "scripts/helper.py", "import bellweather_pipeline\n")
    _write(tmp_path, "tests/test_script.py", "from scripts.helper import value\n")
    assert collect_owners(tmp_path) == {
        "tests/feature/test_indirect.py": "apps",
        "tests/test_script.py": "games",
    }


def test_explicit_product_marker_only_overrides_source_string_hints(tmp_path: Path) -> None:
    _write(tmp_path, "tests/test_hygiene.py", '# test-owner: product\nFORBIDDEN = "godot/games/"\n')
    _write(tmp_path, "tests/test_hidden.py", "# test-owner: product\nfrom .helpers import value\n")
    _write(tmp_path, "tests/helpers.py", "import bellweather_pipeline\nvalue = 1\n")
    _write(tmp_path, "tests/test_docs.py", "# test-owner: games\nvalue = 1\n")
    assert collect_owners(tmp_path) == {
        "tests/test_docs.py": "games",
        "tests/test_hidden.py": "games",
        "tests/test_hygiene.py": "product",
    }


def test_named_import_from_package_follows_submodule_and_live_tests_are_excluded(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "tests/test_indirect.py", "from tests.helpers import optional\n")
    _write(tmp_path, "tests/helpers/optional.py", "import concept_studio\n")
    _write(tmp_path, "tests/live/test_provider.py", "import bellweather_pipeline\n")
    assert collect_owners(tmp_path) == {"tests/test_indirect.py": "apps"}


def test_literal_dynamic_imports_follow_the_same_dependency_graph(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "tests/test_dynamic.py",
        'import importlib\nimportlib.import_module("tests.optional")\n',
    )
    _write(tmp_path, "tests/optional.py", "import bellweather_pipeline\n")
    assert collect_owners(tmp_path) == {"tests/test_dynamic.py": "games"}
