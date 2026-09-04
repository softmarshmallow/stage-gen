"""Per-block versions for published runtime manifests (contract rule C-R3).

A runtime manifest is a set of named blocks. Each block carries its own version in the
root ``blocks`` table, so a consumer gates the block it parses rather than the document,
and a producer that changes one block moves one version. The document's own ``kind``
moves only when the set of blocks or the root fields change shape.

A block version is an identity, not a cache key: it says whether a consumer may read
the block. It lives in the recipe that publishes the block (or the component whose
function builds it, once a block is shared), and the identity table reads it from there.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ManifestBlock[C]:
    """One named block: the key it publishes under, its version, and what builds it."""

    key: str
    version: str
    build: Callable[[C], object]


def block_table[C](blocks: Sequence[ManifestBlock[C]] | Mapping[str, str]) -> dict[str, str]:
    """The ``blocks`` table a manifest root carries: key -> version, in publication order."""

    if isinstance(blocks, Mapping):
        return dict(blocks)
    table: dict[str, str] = {}
    for block in blocks:
        if block.key in table:
            raise ValueError(f"manifest block published twice: {block.key}")
        table[block.key] = block.version
    return table


def build_blocks[C](blocks: Sequence[ManifestBlock[C]], context: C) -> dict[str, object]:
    """Build every block in order. Order matters: a closure block reads what came before."""

    return {block.key: block.build(context) for block in blocks}


def present_blocks(versions: Mapping[str, str], manifest: Mapping[str, object]) -> dict[str, str]:
    """The table for a manifest built by hand: every declared block the document carries.

    A declared block that is absent or ``None`` is an optional block this run does not
    publish; it has no entry, and a consumer that wants it reads its absence as absence.
    """

    unknown = [key for key in versions if key not in manifest]
    table = {key: version for key, version in versions.items() if manifest.get(key) is not None}
    if unknown:
        raise ValueError(f"manifest declares block versions it does not publish: {unknown}")
    return table
