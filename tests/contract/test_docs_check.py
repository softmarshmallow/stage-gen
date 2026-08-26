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


def test_game_contract_authorities_are_discoverable_and_match_the_live_models() -> None:
    """The master and executable game contracts remain distinct and discoverable.

    Modelled on the character-profile discoverability test above, and extended with the checks
    that keep the executable schema from drifting from the models it describes: the documented
    vocabulary sections, the camera projections the recipe accepts, and the one exact current
    manifest version a consumer must require are all read from the live definitions rather than
    restated by hand.
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
    docs_index = (repository_root / "docs/README.md").read_text(encoding="utf-8")
    discoverable_docs = (readme, master_doc, schema_doc, sequence_doc, docs_index)

    for required in (
        "stage-gen game validate",
        "stage-gen game digest",
        "examples/scrolling-preview/game-directed-village.toml",
        "library/games/<game_id>/game.toml",
        "STAGE_GEN_GAME_LIBRARY_ROOT",
        "game-contract-binding-v1",
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
        "The current bundle and runtime shapes remain valid",
    ):
        assert required in sequence_doc

    from stage_gen.components.game_contract import (
        GameContract,
        load_game_vocabulary,
    )
    from stage_gen.recipes.scrolling_preview.game import ACCEPTED_PROJECTIONS
    from stage_gen.recipes.scrolling_preview.village import VILLAGE_MANIFEST_SCHEMA_VERSION

    # Every field of the contract appears in the page's worked example, and every field that
    # carries direction rather than identity additionally has its own section. A field added to
    # the model without a paragraph explaining it fails here rather than shipping undocumented.
    identity_fields = {"schema_version", "kind", "game_id", "revision", "display_name"}
    for field in GameContract.model_fields:
        assert field in schema_doc
        if field not in identity_fields:
            assert f"### `[{field}]`" in schema_doc

    vocabulary = load_game_vocabulary().vocabulary
    for section in type(vocabulary).model_fields:
        if section in {"schema_version", "kind"}:
            continue
        assert f"`{section}`" in schema_doc

    for projection in ACCEPTED_PROJECTIONS:
        assert projection in schema_doc
    assert f'"schema_version": {VILLAGE_MANIFEST_SCHEMA_VERSION}' in schema_doc
