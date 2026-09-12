"""New private product dependencies require an explicit ownership decision."""

from __future__ import annotations

import ast
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REVIEWED = {
    "stage_gen.components._authored_package": {"read_digest_bound_member", "read_package_member"},
    "stage_gen.components._game_input": {
        "AuthoredContractLoadError",
        "GAME_ID_PATTERN",
        "KEBAB_ID_PATTERN",
        "PACKAGE_ID_PATTERN",
        "SHA256_PATTERN",
        "SNAKE_ID_PATTERN",
        "canonical_contract_json",
        "normalized_text",
        "parse_toml_contract",
        "portable_relative_path",
        "sha256_bytes",
        "unique_values",
    },
    "stage_gen.components._node_kit": {"ProviderCall", "card_prompt", "node_result"},
    "stage_gen.components._secure_fs": {
        "SecurePathError",
        "open_absolute_directory",
        "read_absolute_regular_file",
        "read_relative_regular_file",
    },
    "stage_gen.interfaces.asset_recipes": {"_dispatch_storefront", "_dispatch_universe"},
}


def test_godot_private_product_imports_have_an_explicit_review() -> None:
    unreviewed: list[str] = []
    for path in (REPOSITORY_ROOT / "godot").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("stage_gen")
            ):
                private_module = any(part.startswith("_") for part in node.module.split("."))
                for alias in node.names:
                    if (
                        private_module or alias.name.startswith("_")
                    ) and alias.name not in REVIEWED.get(node.module, set()):
                        unreviewed.append(
                            f"{path.relative_to(REPOSITORY_ROOT)}:{node.lineno}: "
                            f"{node.module}.{alias.name}"
                        )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("stage_gen.") and any(
                        part.startswith("_") for part in alias.name.split(".")
                    ):
                        unreviewed.append(
                            f"{path.relative_to(REPOSITORY_ROOT)}:{node.lineno}: {alias.name}"
                        )
    assert not unreviewed, "Review private dependency ownership before adding:\n" + "\n".join(
        unreviewed
    )


def test_every_reviewed_private_dependency_has_a_documented_decision() -> None:
    document = (REPOSITORY_ROOT / "godot/docs/python-dependencies.md").read_text(encoding="utf-8")
    for module, names in REVIEWED.items():
        assert module in document
        for name in names:
            assert f"`{name}`" in document
