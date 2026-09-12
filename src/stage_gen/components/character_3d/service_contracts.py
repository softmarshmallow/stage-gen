"""Application-injected services for contained character graph execution."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from gnode import BindingTable


class EpisodeBackendFactory(Protocol):
    def __call__(self, run: object, episode_id: str, *, limits: object, pricing: object) -> object:
        """Create one metered reasoning episode; concrete backend belongs to composition."""
        ...


@dataclass(frozen=True)
class CharacterServices:
    episode_backend_factory: EpisodeBackendFactory
    upstream_executor_factory: Callable[[object], object]
    rig_executor_factory: Callable[[object], object]
    upstream_bindings: Callable[[], BindingTable]
    credential_provider: Callable[[str], str]
