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
    assert result.media_count == 6


def test_repository_storage_policy_uses_live_enforced_limits() -> None:
    repository_root = Path(__file__).parents[2]
    policy = (repository_root / "docs/repository-storage.md").read_text(encoding="utf-8")

    assert re.search(r"\bapproximately\s+\d+(?:\.\d+)?\s+MiB\b", policy) is None
    for limit in ("audio: 20 MiB", "image: 5 MiB", "video: 25 MiB", "combined: 100 MiB"):
        assert limit in policy
    assert "uv run python scripts/check_docs.py" in policy
    assert (
        "tests/contract/test_packaged_resources.py::"
        "test_repository_media_obeys_git_size_and_location_policy"
    ) in policy


def test_character_profile_workflow_is_discoverable_and_version_accurate() -> None:
    repository_root = Path(__file__).parents[2]
    readme = (repository_root / "README.md").read_text(encoding="utf-8")
    architecture = (repository_root / "ARCHITECTURE.md").read_text(encoding="utf-8")
    library = (repository_root / "docs/character-library.md").read_text(encoding="utf-8")
    docs_index = (repository_root / "docs/README.md").read_text(encoding="utf-8")

    for required in (
        "stage-gen character-profile validate",
        "stage-gen character-profile digest",
        "examples/scrolling-preview/profile-enabled-coast.toml",
        "examples/dialogue-theme/profile-enabled-date.toml",
        "STAGE_GEN_CHARACTER_LIBRARY_ROOT",
        "wire V3/recipe V4",
    ):
        assert required in readme or required in library or required in docs_index
    assert "At committed HEAD it is not a provider-backed" not in architecture
    assert "successful scrolling-preview run also writes manifest schema v2" not in readme
    assert "strict v2 lower_snake_case `dialogue-scene` recipe" not in docs_index


def test_image_repeat_contract_and_preview_fallback_are_scoped() -> None:
    repository_root = Path(__file__).parents[2]
    image_repeat = (repository_root / "docs/image-repeat.md").read_text(encoding="utf-8")
    for required in (
        "one image in, one image proven to repeat on a declared axis out",
        "await service.admit(ImageRepeatAdmissionRequest(...))",
        "await service.repair(ImageRepeatRepairRequest(...))",
        "exactly three unmarked, pixel-identical copies",
        "Legacy preview fallbacks are ineligible",
        "Two-axis tileability is a non-goal",
    ):
        assert required in image_repeat

    legacy_fallback_documents = (
        repository_root / "docs/scene-layers.md",
        repository_root / "docs/spec/asset-contracts.md",
    )

    for document in legacy_fallback_documents:
        contract = document.read_text(encoding="utf-8")
        assert "repeat-x-seam-overlap" in contract
        assert re.search(r"temporary legacy.{0,100}fallback", contract, re.DOTALL)
        assert re.search(r"no\s+verified (?:loop|repeat) artifact", contract)
        assert "sourceWidthPx - 256" in contract
        assert re.search(r"alpha", contract, re.IGNORECASE)
        assert re.search(r"verified\s+repeat\s+(?:unit|artifact)", contract)
        assert "ineligible" in contract


def test_terrain_atlas_documentation_matches_runtime_contract() -> None:
    repository_root = Path(__file__).parents[2]
    contract = (repository_root / "docs/spec/terrain-atlas.md").read_text(encoding="utf-8")
    normalized = " ".join(contract.split())

    for required in (
        "terrain-atlas-3x3-minimal-v1",
        "47 reachable 3x3-minimal",
        "all eight neighbors",
        "Dynamic engine tilemaps require `direct_pass`",
        "Collision comes from occupancy, not alpha",
    ):
        assert required in normalized


def test_game_contract_authorities_are_discoverable_and_match_the_live_models() -> None:
    """The master and executable game contracts remain distinct and discoverable.

    Modelled on the character-profile discoverability test above, and extended with the checks
    that keep the prepared package-root schema from drifting from its live model and exact current
    identities.
    """

    repository_root = Path(__file__).parents[2]
    readme = (repository_root / "README.md").read_text(encoding="utf-8")
    master_doc = (repository_root / "docs/game-contract.md").read_text(encoding="utf-8")
    schema_doc = (repository_root / "docs/spec/game/authored-contract-schema.md").read_text(
        encoding="utf-8"
    )
    sequence_doc = (
        repository_root / "docs/spec/game/dialogue-and-cutscene-sequences.md"
    ).read_text(encoding="utf-8")
    package_doc = (repository_root / "docs/game-package.md").read_text(encoding="utf-8")
    docs_index = (repository_root / "docs/README.md").read_text(encoding="utf-8")
    discoverable_docs = (readme, master_doc, schema_doc, sequence_doc, package_doc, docs_index)

    for required in (
        "stage-gen package validate",
        "stage-gen package digest",
        "stage-gen package plan",
        "library/games/<game_id>/game.toml",
        "game-package-v3",
        "game-contract-v6",
        "prepared-game-runtime-v9",
    ):
        assert any(required in document for document in discoverable_docs)

    for required in (
        "spec/game/authored-contract-schema.md",
        "spec/game/view-and-style-taxonomy.md",
        "spec/game/dialogue-and-cutscene-sequences.md",
        "Visible gameplay requires visual coverage",
        "player `hurt` motion coverage",
        "Sequence control is explicit",
    ):
        assert required in master_doc

    for required in (
        "semantic control-flow graph",
        "orthogonal presentation program",
        "A **cutscene**",
        "control leases",
        "The current prepared sequence and runtime shapes remain valid",
    ):
        assert required in sequence_doc

    from stage_gen.components.game_contract import (
        PREPARED_GAME_CONTRACT_SCHEMA_VERSION,
        PreparedGameContract,
    )

    # Every current package-root field appears in the worked shape. A field added to the model
    # without appearing in the executable-schema authority fails here.
    for field in PreparedGameContract.model_fields:
        assert field in schema_doc
    assert f"schema_version = {PREPARED_GAME_CONTRACT_SCHEMA_VERSION}" in schema_doc
    assert f'kind = "game-contract-v{PREPARED_GAME_CONTRACT_SCHEMA_VERSION}"' in schema_doc
    assert "side_view_2d" in schema_doc
    assert "ui.toml" in schema_doc
    assert "maps/<map_id>.toml" in schema_doc
