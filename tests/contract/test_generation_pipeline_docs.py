from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPOSITORY_ROOT = Path(__file__).parents[2]
PIPELINE_DOCUMENT = REPOSITORY_ROOT / "docs/spec/game/generation-pipeline.md"


def _load_contract_writer() -> ModuleType:
    path = REPOSITORY_ROOT / "scripts/write_pipeline_graph_contract.py"
    spec = importlib.util.spec_from_file_location("stage_gen_pipeline_graph_contract", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_writer = _load_contract_writer()
CONTRACT_KIND = _writer.CONTRACT_KIND
FIXTURE_REF = _writer.FIXTURE_REF
build_graph_contract = _writer.build_graph_contract
document_contract = _writer.document_contract
render = _writer.render


def test_generation_pipeline_document_tracks_the_executable_stage_graphs() -> None:
    # The snapshot is derived by scripts/write_pipeline_graph_contract.py rather than transcribed,
    # so the writer and this check cannot drift. Regenerate with `--write` after any graph change.
    assert document_contract(PIPELINE_DOCUMENT) == build_graph_contract(REPOSITORY_ROOT)


def test_generation_pipeline_contract_declares_its_identity_and_fixture() -> None:
    contract = document_contract(PIPELINE_DOCUMENT)
    assert contract["kind"] == CONTRACT_KIND
    assert contract["fixture_ref"] == FIXTURE_REF
    assert (REPOSITORY_ROOT / contract["fixture_ref"]).is_dir()


def test_generation_pipeline_contract_block_is_rendered_canonically() -> None:
    # Guards the writer's own formatting: a hand-edited block that happens to parse equal must
    # still fail, or the document and the regenerated output would differ byte for byte.
    source = PIPELINE_DOCUMENT.read_text(encoding="utf-8")
    assert render(document_contract(PIPELINE_DOCUMENT)) in source


def test_generation_pipeline_document_is_discoverable_from_game_authorities() -> None:
    required_link = "generation-pipeline.md"
    same_directory_authority = (
        REPOSITORY_ROOT / "docs/spec/game/authored-contract-schema.md"
    ).read_text(encoding="utf-8")
    docs_index = (REPOSITORY_ROOT / "docs/README.md").read_text(encoding="utf-8")
    game_contract = (REPOSITORY_ROOT / "docs/game-contract.md").read_text(encoding="utf-8")
    game_package = (REPOSITORY_ROOT / "docs/game-package.md").read_text(encoding="utf-8")

    assert required_link in same_directory_authority
    assert "spec/game/generation-pipeline.md" in docs_index
    assert "spec/game/generation-pipeline.md" in game_contract
    assert "spec/game/generation-pipeline.md" in game_package
