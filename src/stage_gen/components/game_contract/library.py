"""Secure resolution of digest-bound game contracts from an explicit authored library root.

Games resolve exactly the way character profiles do: the request names a relative `ref` and the
digest it expects, the operator names the root on the command line, and the read is confined to
that root by descriptor. The digest is checked against the bytes actually read *before* they are
parsed, so a contract that changed on disk since the request was written fails as a mismatch
rather than quietly directing a run under different rules than the request recorded.

The resolved identity additionally carries the vocabulary digest. That is not redundant with the
contract digest: the contract names keywords, and the vocabulary decides what those keywords
*mean* in a prompt. Editing `warm dusk palette`'s wording changes every image a contract using it
produces while leaving the contract's own bytes untouched, so both digests belong in the identity
and both belong in the run tag.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from gnode import InputProvenance
from stage_gen.components._secure_fs import (
    SecurePathError,
    open_absolute_directory,
    read_relative_regular_file,
)
from stage_gen.components.game_contract.loader import (
    canonical_game_contract_json,
    load_game_contract_bytes,
)
from stage_gen.components.game_contract.models import GameContract, GameContractBinding
from stage_gen.components.game_contract.vocabulary import (
    LoadedGameVocabulary,
    load_game_vocabulary,
)

GAME_LIBRARY_RESOLUTION_VERSION = "game-contract-library-resolution-v1"

#: The one path shape a binding may name, mirroring `library/characters/<id>/profile.toml`. A
#: fixed shape is what lets the resolver check that the directory name and the declared
#: `game_id` agree, which is the cheapest available guard against a copied file that still
#: claims to be the game it was copied from.
_REF_PARTS = ("library", "games")
_REF_FILENAME = "game.toml"


@dataclass(frozen=True, slots=True)
class ResolvedGameContract:
    binding: GameContractBinding
    contract: GameContract
    vocabulary: LoadedGameVocabulary
    source_path: Path
    source_bytes: bytes
    canonical_bytes: bytes

    @property
    def source_sha256(self) -> str:
        return hashlib.sha256(self.source_bytes).hexdigest()

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    @property
    def source_provenance(self) -> InputProvenance:
        return InputProvenance(
            ref=self.binding.ref,
            sha256=self.source_sha256,
            source="content",
            bytes=len(self.source_bytes),
            media_type="application/toml",
        )

    def identity(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "kind": "resolved-game-contract-v1",
            "resolution_version": GAME_LIBRARY_RESOLUTION_VERSION,
            "binding": self.binding.model_dump(mode="json"),
            "game_id": self.contract.game_id,
            "revision": self.contract.revision,
            "projection": self.contract.camera.projection,
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
            "canonical_bytes": len(self.canonical_bytes),
            "vocabulary_sha256": self.vocabulary.sha256,
            "rights_status": self.contract.rights.status,
        }


def resolve_game_contract_binding(
    value: object,
    *,
    game_library_root: str | Path,
    vocabulary: LoadedGameVocabulary | None = None,
) -> ResolvedGameContract:
    """Resolve one exact library binding without following filesystem symlinks."""

    binding = GameContractBinding.model_validate(value)
    parts = PurePosixPath(binding.ref).parts
    if len(parts) != 4 or parts[:2] != _REF_PARTS or parts[3] != _REF_FILENAME:
        raise ValueError(f"game ref must equal library/games/<game_id>/{_REF_FILENAME}")
    loaded_vocabulary = vocabulary or load_game_vocabulary()
    root = Path(game_library_root).absolute()
    try:
        with open_absolute_directory(root, label="game library root") as root_fd:
            source_bytes = read_relative_regular_file(
                root_fd,
                parts,
                label="game contract source",
            )
            if hashlib.sha256(source_bytes).hexdigest() != binding.source_sha256:
                raise ValueError("game contract source_sha256 mismatch")
            contract = load_game_contract_bytes(
                source_bytes,
                source_suffix=".toml",
                vocabulary=loaded_vocabulary,
            )
            if contract.game_id != parts[2]:
                raise ValueError("game contract game_id must match its library directory")
            return ResolvedGameContract(
                binding=binding,
                contract=contract,
                vocabulary=loaded_vocabulary,
                source_path=root.joinpath(*parts),
                source_bytes=source_bytes,
                canonical_bytes=canonical_game_contract_json(contract),
            )
    except SecurePathError as error:
        raise ValueError(str(error)) from error


__all__ = [
    "GAME_LIBRARY_RESOLUTION_VERSION",
    "ResolvedGameContract",
    "resolve_game_contract_binding",
]
