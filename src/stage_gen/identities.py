"""The identity table: every persisted identity string, read from the one place that owns it.

A persisted identity is a ``kind`` or ``mode`` word a document carries so that a reader
can refuse what it does not understand: the authored documents, the documents the
pipeline generates, the runtime manifests, the execution graphs, the mode words inside
documents, the cache namespaces, and the audio realization kinds. Each is declared once
in the code, on a pydantic ``Literal`` field or a module constant; this table names that
place and reads the value from it, so the docs can derive from the code instead of
asserting version strings by hand (contract rule C-R5 in ``docs/game-contract.md``).

What is *not* here: a node's ``contract_version``. That is a cache key, not an identity
(C-R1), and the cache-key goldens under ``tests/unit/recipes`` are its evidence. The
per-port ``kind`` labels inside an execution graph are graph vocabulary and stay with
their recipe.

Two families carry two live versions under one name, recorded rather than hidden:
``dialogue-scene`` is both the authored document (v5) and the recipe version (v8) the
plan and bundle stamp; ``scenario-program`` is the scenario component's program (v2)
and, at v1, a port label in the dialogue graph. Renaming either is a persisted change
and waits for the bump that needs it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from importlib import import_module
from typing import Literal, get_args

type IdentityRole = Literal[
    "authored",
    "generated",
    "manifest",
    "block",
    "graph",
    "mode",
    "namespace",
    "recipe",
    "realization",
]

ROLE_MEANING: dict[IdentityRole, str] = {
    "authored": "a document an author writes and the pipeline validates",
    "generated": "a document the pipeline writes and a consumer or a later node reads",
    "manifest": "a runtime manifest a web consumer parses",
    "block": "one named block of a runtime manifest, versioned on its own (C-R3)",
    "graph": "a sealed execution-graph document",
    "mode": "a closed-vocabulary word inside a document that selects a producer",
    "namespace": "a node-cache namespace: one recipe's whole tree of restorable work",
    "recipe": "a recipe version a generated document stamps beside its own kind",
    "realization": "how an authored audio event is realized",
}

_IDENTITY_PATTERN = re.compile(
    r"^(?P<family>[a-z0-9][a-z0-9_/-]*?)(?P<separator>[-_])v(?P<version>\d+)$"
)


@dataclass(frozen=True, slots=True)
class IdentitySource:
    """Where an identity is declared: a module constant, or a pydantic ``Literal`` field."""

    module: str
    attribute: str
    field: str | None = None

    def resolve(self) -> str:
        owner = getattr(import_module(self.module), self.attribute)
        if self.field is None:
            if not isinstance(owner, str):
                raise TypeError(f"{self} is not a string constant")
            return owner
        annotation = owner.model_fields[self.field].annotation
        literal = get_args(annotation)
        if len(literal) != 1 or not isinstance(literal[0], str):
            raise TypeError(f"{self} is not a single-string Literal field")
        return literal[0]

    def __str__(self) -> str:
        suffix = "" if self.field is None else f".{self.field}"
        return f"{self.module}:{self.attribute}{suffix}"


@dataclass(frozen=True, slots=True)
class ContractIdentity:
    identity: str
    family: str
    separator: str
    version: int
    role: IdentityRole
    source: IdentitySource

    def sibling(self, version: int) -> str:
        return f"{self.family}{self.separator}v{version}"


def _field(module: str, model: str, field: str = "kind") -> IdentitySource:
    return IdentitySource(f"stage_gen.{module}", model, field)


def _constant(module: str, name: str) -> IdentitySource:
    return IdentitySource(f"stage_gen.{module}", name)


IDENTITY_SOURCES: tuple[tuple[IdentityRole, IdentitySource], ...] = (
    # Authored documents: what an author writes.
    ("authored", _field("orchestration.game_package", "GamePackageSelector")),
    ("authored", _field("components.game_contract.package", "PreparedGameContract")),
    ("authored", _field("components.platformer_map.prepared", "PreparedGameMap")),
    ("authored", _field("components.platformer_gameplay.models", "GameplayContract")),
    ("authored", _field("components.game_ui.models", "GameUi")),
    ("authored", _field("components.game_fx.models", "GameFx")),
    ("authored", _field("components.game_soundtrack.models", "GameSoundtrack")),
    ("authored", _field("components.game_soundtrack.models", "GameSoundtrackBinding")),
    ("authored", _field("components.game_voices.models", "GameVoices")),
    ("authored", _field("components.platformer_content.models", "PlayerContentCatalog")),
    ("authored", _field("components.platformer_content.models", "MobContentCatalog")),
    ("authored", _field("components.platformer_content.models", "NpcContentCatalog")),
    ("authored", _field("components.platformer_content.models", "PropContentCatalog")),
    ("authored", _field("components.platformer_content.models", "ItemContentCatalog")),
    ("authored", _field("components.platformer_content.models", "ProjectileContentCatalog")),
    ("authored", _field("components.runner_gameplay.models", "RunnerGameplayContract")),
    ("authored", _field("components.runner_track.models", "RunnerTrack")),
    ("authored", _field("components.runner_content.models", "RunnerAvatarCatalog")),
    ("authored", _field("components.runner_content.models", "RunnerBossCatalog")),
    ("authored", _field("components.runner_audio.models", "RunnerAudioContract")),
    ("authored", _field("components.scenario.models", "ScenarioDeclarations")),
    ("authored", _field("components.scenario.models", "ScenarioCatalog")),
    ("authored", _field("components.case.models", "CaseDocument")),
    ("authored", _field("components.case.models", "CaseCatalog")),
    ("authored", _field("components.character_profile.models", "CharacterProfile")),
    ("authored", _field("components.character_profile.models", "CharacterProfileBinding")),
    ("authored", _field("recipes.pointclick_room.models", "PointClickRoom")),
    ("authored", _field("recipes.dialogue_scene.models", "DialogueSceneDocument")),
    ("authored", _field("recipes.universe.models", "UniverseSource")),
    # Generated documents: what the pipeline writes for a consumer or a later node.
    ("generated", _field("components.platformer_map.prepared", "PreparedMapTerrain")),
    ("generated", _field("components.sideview_map_design.design", "PlatformerChunkMapDesign")),
    ("generated", _field("components.scenario.models", "ScenarioProgram")),
    ("generated", _field("components.scenario.models", "ScenarioAdmissionReport")),
    ("generated", _field("components.case.models", "CaseRuntime")),
    ("generated", _field("components.case.models", "CaseAdmissionReport")),
    ("generated", _constant("orchestration.game_package", "RESOLVED_GAME_PACKAGE_KIND")),
    ("generated", _constant("orchestration.game_package", "GAME_PACKAGE_VALIDATION_KIND")),
    ("generated", _field("recipes.pointclick_room.models", "RoomSolvabilityReport")),
    ("generated", _field("recipes.dialogue_scene.models", "DialogueScenePlan")),
    ("generated", _field("recipes.dialogue_scene.models", "IndependentReview")),
    ("generated", _field("recipes.dialogue_scene.models", "DialogueBundle")),
    ("generated", _field("recipes.universe.models", "SampleLedger")),
    # Runtime manifests: what a web consumer parses.
    (
        "manifest",
        _constant("recipes.sideview_platformer.package_types", "PREPARED_RUNTIME_MANIFEST_KIND"),
    ),
    ("manifest", _constant("recipes.sideview_runner.runner_types", "MANIFEST_KIND")),
    ("manifest", _constant("recipes.pointclick_room.room_types", "MANIFEST_KIND")),
    ("manifest", _constant("recipes.universe.universe_types", "MANIFEST_KIND")),
    # Execution graphs.
    ("graph", _field("recipes.sideview_platformer.execution_graph", "ExecutionGraph")),
    ("graph", _field("recipes.sideview_runner.runner_graph", "SideviewRunnerGraph")),
    ("graph", _field("recipes.pointclick_room.room_graph", "PointClickRoomGraph")),
    ("graph", _field("recipes.dialogue_scene.scene_graph", "DialogueSceneGraph")),
    ("graph", _field("recipes.universe.universe_graph", "UniverseGraph")),
    # Mode words.
    ("mode", _field("components.sideview_stage.models", "PreparedMapGround", "mode")),
    ("mode", _field("components.painted_terrain.models", "PaintedTerrainGround", "mode")),
    ("mode", _field("components.platformer_map.prepared", "PreparedMapClimbable", "mode")),
    ("mode", _field("components.platformer_map.prepared", "PreparedMapPortal", "mode")),
    ("mode", _field("components.runner_track.models", "RunnerStructuralGround", "mode")),
    ("mode", _field("components.runner_track.models", "RunnerCamera", "mode")),
    # Cache namespaces.
    ("namespace", _constant("recipes.sideview_platformer.package_graph", "WORLD_CACHE_NAMESPACE")),
    (
        "namespace",
        _constant("recipes.sideview_platformer.package_graph", "CONTENT_CACHE_NAMESPACE"),
    ),
    ("namespace", _constant("recipes.sideview_runner.runner_graph", "RUNNER_CACHE_NAMESPACE")),
    ("namespace", _constant("recipes.pointclick_room.room_graph", "POINTCLICK_CACHE_NAMESPACE")),
    ("namespace", _constant("recipes.dialogue_scene.scene_graph", "DIALOGUE_CACHE_NAMESPACE")),
    ("namespace", _constant("recipes.universe.universe_graph", "UNIVERSE_CACHE_NAMESPACE")),
    # Recipe versions stamped beside a generated document's own kind.
    ("recipe", _field("recipes.dialogue_scene.models", "DialogueScenePlan", "recipe_version")),
    # Blocks a shared component builds for more than one manifest.
    ("block", _constant("components.game_fx.nodes", "FX_MANIFEST_BLOCK_VERSION")),
    # Audio realizations.
    ("realization", _constant("components.sound_effect.models", "GENERATED_CLIP_REALIZATION_KIND")),
    ("realization", _constant("components.speech.models", "SPOKEN_LINE_REALIZATION_KIND")),
    ("realization", _field("components.runner_audio.models", "OscillatorSweepRealization")),
)

#: Block registries: a manifest's ``blocks`` table, key -> version. A version a component
#: declares (a block a shared family builds) is read from the component; the registry that
#: publishes it only references it.
BLOCK_REGISTRIES: tuple[IdentitySource, ...] = (
    _constant(
        "recipes.sideview_platformer.prepared_manifest", "PLATFORMER_MANIFEST_BLOCK_VERSIONS"
    ),
    _constant("recipes.sideview_runner.runner_types", "RUNNER_MANIFEST_BLOCK_VERSIONS"),
)

#: Families with no current member: the whole family is retired, at every version. A family
#: with a current member needs no entry here, because every lower version is retired by
#: arithmetic. The reason is the doc's, not the test's; it is what the table prints.
RETIRED_FAMILIES: tuple[tuple[str, str], ...] = (
    ("game-map-book", "the ordered map book required an index file the library forbids"),
    ("game-map-book-manifest", "retired with the map book"),
    ("game-map-book-binding", "retired with the map book"),
    ("resolved-game-map", "the `game-map-v2` parser was a dead twin of the current map"),
    ("resolved-game-map-book", "retired with the map book"),
    ("game-sequence", "dialogue moved to authored scenarios; both genres walk one program"),
    ("game-sequence-catalog", "retired with the sequence"),
    ("game-soundtrack-manifest", "the soundtrack publishes inside the runtime manifest"),
    (
        "prepared-game-execution-graph",
        "renamed with the node ABI to `sideview-platformer-execution-graph`",
    ),
    ("prepared-game-execution-event", "renamed with the node ABI"),
    ("prepared-game-execution-summary", "renamed with the node ABI"),
    ("prepared-game-execution-projection", "renamed with the node ABI"),
    ("prepared-game-execution-view", "renamed with the node ABI"),
)

#: Strings that are not `<family>-v<n>` shaped but name a retired thing all the same.
RETIRED_STRINGS: tuple[tuple[str, str], ...] = (
    ('"scrolling-preview"', "the recipe id, renamed to `sideview-platformer` with the node ABI"),
    ("@stage-gen/scrolling-preview", "the provenance component, renamed with the recipe"),
    ("manifest V7", "a runtime manifest named by number rather than by kind"),
)


def parse_identity(identity: str) -> tuple[str, str, int]:
    """Split ``<family><sep>v<n>`` into its family, separator and version."""

    match = _IDENTITY_PATTERN.match(identity)
    if match is None:
        raise ValueError(f"{identity!r} is not a versioned identity")
    return match["family"], match["separator"], int(match["version"])


@cache
def contract_identities() -> tuple[ContractIdentity, ...]:
    """Every current identity, resolved from its source, in table order."""

    entries: list[ContractIdentity] = []
    seen: dict[str, IdentitySource] = {}
    for role, source in IDENTITY_SOURCES:
        identity = source.resolve()
        if identity in seen:
            raise ValueError(f"{identity} is declared twice: {seen[identity]} and {source}")
        seen[identity] = source
        family, separator, version = parse_identity(identity)
        entries.append(ContractIdentity(identity, family, separator, version, role, source))
    for registry in BLOCK_REGISTRIES:
        table = getattr(import_module(registry.module), registry.attribute)
        if not isinstance(table, dict):
            raise TypeError(f"{registry} is not a block table")
        for key, identity in table.items():
            if identity in seen:
                continue  # a component's block, referenced here and declared there
            source = IdentitySource(registry.module, f"{registry.attribute}[{key!r}]")
            seen[identity] = source
            family, separator, version = parse_identity(identity)
            entries.append(ContractIdentity(identity, family, separator, version, "block", source))
    return tuple(entries)


def current_versions() -> dict[str, frozenset[int]]:
    """Family → the versions with a live authority; the module docstring names the doubled ones."""

    versions: dict[str, set[int]] = {}
    for entry in contract_identities():
        versions.setdefault(entry.family, set()).add(entry.version)
    return {family: frozenset(found) for family, found in versions.items()}
