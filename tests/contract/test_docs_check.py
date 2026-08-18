from __future__ import annotations

import importlib.util
import re
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
    assert result.media_count == 3


def test_repository_storage_policy_uses_live_enforced_limits() -> None:
    repository_root = Path(__file__).parents[2]
    policy = (repository_root / "docs/repository-storage.md").read_text(encoding="utf-8")

    assert re.search(r"\bapproximately\s+\d+(?:\.\d+)?\s+MiB\b", policy) is None
    for limit in ("audio: 20 MiB", "image: 5 MiB", "video: 25 MiB", "combined: 50 MiB"):
        assert limit in policy
    assert "uv run python scripts/check_docs.py" in policy
    assert (
        "tests/contract/test_packaged_resources.py::"
        "test_repository_media_obeys_git_size_and_location_policy"
    ) in policy


def test_loop_preview_fallback_is_temporary_and_verified_loop_scoped() -> None:
    repository_root = Path(__file__).parents[2]
    documents = (
        repository_root / "docs/loop-synthesis.md",
        repository_root / "docs/scene-layers.md",
        repository_root / "docs/spec/asset-contracts.md",
    )

    for document in documents:
        contract = document.read_text(encoding="utf-8")
        assert "repeat-x-seam-overlap" in contract
        assert re.search(r"temporary legacy.{0,100}fallback", contract, re.DOTALL)
        assert re.search(r"no\s+verified loop artifact", contract)
        assert "sourceWidthPx - 256" in contract
        assert re.search(r"alpha", contract, re.IGNORECASE)
        assert re.search(r"verified\s+repeat\s+(?:unit|artifact)", contract)
        assert "ineligible" in contract


def test_tileset_documentation_matches_connected_harmonic_runtime() -> None:
    repository_root = Path(__file__).parents[2]
    contract = (repository_root / "docs/spec/tileset.md").read_text(encoding="utf-8")
    normalized = " ".join(contract.split())

    for required in (
        "does not register or render per-role atlas frames",
        "512 x 512 toroidal",
        "luminance-sorted color palette",
        "3/7/19/43",
        "connected-run fill TileSprites",
        "runtime-only 12-pixel side bands",
    ):
        assert required in normalized
    for retired in (
        "register frames against the inset content rectangle",
        "per-channel mean, variance",
        "three mirror-safe warped samples",
        "Cull transition frames",
    ):
        assert retired not in normalized
