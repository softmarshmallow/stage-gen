"""Game-wide gameplay mechanisms composed by versioned game contracts."""

from __future__ import annotations

from typing import Literal

from stage_gen.components.game_contract.spawning import MobPopulationDirection
from stage_gen.contracts.artifacts import PersistedContractModel


class CombatTextPolicy(PersistedContractModel):
    """Whether combat outcomes are presented as transient world-space text."""

    schema_version: Literal[1] = 1
    kind: Literal["combat-text-v1"] = "combat-text-v1"
    enabled: bool = True

    def manifest_projection(self) -> dict[str, object]:
        """Return the stable engine-neutral combat-text mechanism block."""

        return self.model_dump(mode="json", by_alias=False)


class GameplayDirection(PersistedContractModel):
    """Independent gameplay mechanisms authored by a versioned game contract."""

    mob_population: MobPopulationDirection | None = None
    combat_text: CombatTextPolicy | None = None


__all__ = ["CombatTextPolicy", "GameplayDirection"]
