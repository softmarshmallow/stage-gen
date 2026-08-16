from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_docs_checker() -> ModuleType:
    path = Path(__file__).parents[2] / "scripts/check_docs.py"
    spec = importlib.util.spec_from_file_location("stage_gen_docs_check", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_repository_documentation_and_publication_contract() -> None:
    repository_root = Path(__file__).parents[2]
    result = _load_docs_checker().run_docs_check(repository_root)
    assert result.failures == ()
    assert result.markdown_count > 0
    assert result.text_count > 0
    assert result.media_count == 1
