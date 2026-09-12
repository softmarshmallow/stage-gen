"""Independent recipe graph documentation stays in the product's offline gate."""

from __future__ import annotations

from pathlib import Path

from scripts.write_pipeline_graph_contract import (
    UNIVERSE_ADMITTED_REF,
    UNIVERSE_FIXTURE_REF,
    UNIVERSE_GALLERY_CONTRACT_KIND,
    UNIVERSE_SEMANTIC_CONTRACT_KIND,
    build_universe_gallery_graph_contract,
    build_universe_semantic_graph_contract,
    document_contract,
    render,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
UNIVERSE_DOCUMENT = REPOSITORY_ROOT / "docs/spec/universe/generation-v1.md"


def test_universe_document_tracks_both_of_its_phase_graphs() -> None:
    # Universe is the one recipe that seals two graphs, because the size of its
    # gallery is a result of its semantic phase. Each phase carries its own
    # labelled block in the one document that describes both.
    assert document_contract(
        UNIVERSE_DOCUMENT, label="semantic"
    ) == build_universe_semantic_graph_contract(REPOSITORY_ROOT)
    assert document_contract(
        UNIVERSE_DOCUMENT, label="gallery"
    ) == build_universe_gallery_graph_contract(REPOSITORY_ROOT)


def test_universe_contracts_declare_their_identity_and_their_fixtures() -> None:
    semantic = document_contract(UNIVERSE_DOCUMENT, label="semantic")
    gallery = document_contract(UNIVERSE_DOCUMENT, label="gallery")
    assert semantic["kind"] == UNIVERSE_SEMANTIC_CONTRACT_KIND
    assert gallery["kind"] == UNIVERSE_GALLERY_CONTRACT_KIND
    assert semantic["phase"] == "semantic"
    assert gallery["phase"] == "gallery"
    assert semantic["fixture_ref"] == gallery["fixture_ref"] == UNIVERSE_FIXTURE_REF
    assert (REPOSITORY_ROOT / UNIVERSE_FIXTURE_REF).is_dir()
    # The gallery graph is planned offline against a committed admission, so the
    # fan-out has a checked identity without a paid semantic run behind it.
    assert gallery["admitted_ref"] == UNIVERSE_ADMITTED_REF
    assert (REPOSITORY_ROOT / UNIVERSE_ADMITTED_REF).is_file()
    assert gallery["entity_count"] > 0


def test_universe_contract_blocks_are_rendered_canonically() -> None:
    source = UNIVERSE_DOCUMENT.read_text(encoding="utf-8")
    for label in ("semantic", "gallery"):
        assert render(document_contract(UNIVERSE_DOCUMENT, label=label), label=label) in source


def test_universe_document_is_discoverable_from_the_docs_index() -> None:
    docs_index = (REPOSITORY_ROOT / "docs/README.md").read_text(encoding="utf-8")
    taxonomy = (REPOSITORY_ROOT / "docs/spec/universe/taxonomy-v0.md").read_text(encoding="utf-8")
    assert "spec/universe/generation-v1.md" in docs_index
    assert "generation-v1.md" in taxonomy


def test_storefront_document_uses_the_independent_example() -> None:
    from scripts.write_pipeline_graph_contract import (
        STOREFRONT_CONTRACT_KIND,
        STOREFRONT_DOCUMENT,
        STOREFRONT_FIXTURE_REF,
        build_storefront_graph_contract,
    )

    contract = document_contract(STOREFRONT_DOCUMENT)
    assert contract == build_storefront_graph_contract(REPOSITORY_ROOT)
    assert contract["kind"] == STOREFRONT_CONTRACT_KIND
    assert contract["fixture_ref"] == STOREFRONT_FIXTURE_REF
    assert (REPOSITORY_ROOT / STOREFRONT_FIXTURE_REF / "make_inputs.py").is_file()
    assert contract["surface_count"] == 1
    assert contract["operation_counts"] == {
        "local": 6,
        "image_generation": 1,
        "structured_generation": 3,
    }
    assert render(contract) in STOREFRONT_DOCUMENT.read_text(encoding="utf-8")


def test_product_graph_writer_runs_without_game_inputs(tmp_path: Path) -> None:
    import shutil

    from scripts.write_pipeline_graph_contract import (
        STOREFRONT_FIXTURE_REF,
        build_storefront_graph_contract,
    )

    # The writer's only declared storefront source is the independent example author.
    fixture = tmp_path / STOREFRONT_FIXTURE_REF
    fixture.mkdir(parents=True)
    shutil.copyfile(
        REPOSITORY_ROOT / STOREFRONT_FIXTURE_REF / "make_inputs.py",
        fixture / "make_inputs.py",
    )
    assert build_storefront_graph_contract(tmp_path) == build_storefront_graph_contract(
        REPOSITORY_ROOT
    )
    assert not (tmp_path / "godot").exists()
