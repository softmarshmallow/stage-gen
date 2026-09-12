"""Identity lookup helpers and inventory for public asset contracts.

Fields and constants remain owned by their capability packages; this inventory
reads them without importing the optional demo workspace. It is not a registry
that caller-defined pipelines must join. The public pipeline envelopes live in
``stage_gen.pipeline``; the complete historical game census belongs to
``stage_gen_legacy.identities`` under ``godot/legacy/python``.
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
    "manifest": "a runtime manifest a host parses",
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
class GraphIdentitySource:
    """The current kind and accepted legacy pairs declared by one graph reader."""

    module: str
    current_attribute: str
    graph_attribute: str

    def resolve(self) -> str:
        identity = getattr(import_module(self.module), self.current_attribute)
        if not isinstance(identity, str):
            raise TypeError(f"{self} is not a string constant")
        return identity

    def resolve_legacy(self) -> tuple[tuple[int, str], ...]:
        graph = getattr(import_module(self.module), self.graph_attribute)
        identities = getattr(graph, "LEGACY_GRAPH_IDENTITIES", None)
        if not isinstance(identities, frozenset):
            raise TypeError(f"{self.legacy_authority} is not a frozen identity set")
        resolved: list[tuple[int, str]] = []
        for item in identities:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], int)
                or isinstance(item[0], bool)
                or item[0] < 1
                or not isinstance(item[1], str)
                or not item[1]
            ):
                raise TypeError(f"{self.legacy_authority} contains invalid graph identity {item!r}")
            resolved.append(item)
        return tuple(sorted(resolved, key=lambda item: (item[1], item[0])))

    @property
    def legacy_authority(self) -> str:
        return f"{self.module}:{self.graph_attribute}.LEGACY_GRAPH_IDENTITIES"

    def __str__(self) -> str:
        return f"{self.module}:{self.current_attribute}"


type CurrentIdentitySource = IdentitySource | GraphIdentitySource


@dataclass(frozen=True, slots=True)
class ContractIdentity:
    identity: str
    family: str
    separator: str
    version: int
    role: IdentityRole
    source: CurrentIdentitySource

    def sibling(self, version: int) -> str:
        return f"{self.family}{self.separator}v{version}"


@dataclass(frozen=True, slots=True)
class AcceptedLegacyGraphIdentity:
    """One graph identity a reader accepts but new plans never publish."""

    schema_version: int
    identity: str
    family: str
    separator: str
    version: int
    source: GraphIdentitySource


def _field(module: str, model: str, field: str = "kind") -> IdentitySource:
    return IdentitySource(f"stage_gen.{module}", model, field)


def _constant(module: str, name: str) -> IdentitySource:
    return IdentitySource(f"stage_gen.{module}", name)


def _graph(module: str, current: str, graph: str) -> GraphIdentitySource:
    return GraphIdentitySource(f"stage_gen.{module}", current, graph)


IDENTITY_SOURCES: tuple[tuple[IdentityRole, CurrentIdentitySource], ...] = (
    ("authored", _field("components.scenario.models", "ScenarioDeclarations")),
    ("authored", _field("components.scenario.models", "ScenarioCatalog")),
    ("authored", _field("components.character_profile.models", "CharacterProfile")),
    ("authored", _field("components.character_profile.models", "CharacterProfileBinding")),
    ("authored", _field("recipes.universe.models", "UniverseSource")),
    ("authored", _field("recipes.storefront.models", "StorefrontSource")),
    ("generated", _field("components.sideview_map_design.design", "PlatformerChunkMapDesign")),
    ("generated", _field("components.scenario.models", "ScenarioProgram")),
    ("generated", _field("components.scenario.models", "ScenarioAdmissionReport")),
    ("generated", _field("recipes.universe.models", "SampleLedger")),
    ("generated", _field("recipes.storefront.models", "DrawLedger")),
    ("generated", _field("recipes.storefront.models", "StorefrontDirection")),
    ("generated", _field("recipes.storefront.models", "StoreListing")),
    (
        "generated",
        _constant("recipes.portrait_motion.pipeline", "PORTRAIT_MOTION_PLAN_KIND"),
    ),
    ("manifest", _constant("recipes.universe.universe_types", "MANIFEST_KIND")),
    (
        "graph",
        _graph(
            "recipes.universe.universe_graph",
            "UNIVERSE_GRAPH_KIND",
            "UniverseGraph",
        ),
    ),
    (
        "graph",
        _graph(
            "recipes.storefront.storefront_graph",
            "STOREFRONT_GRAPH_KIND",
            "StorefrontGraph",
        ),
    ),
    (
        "graph",
        _graph(
            "recipes.portrait_motion.pipeline",
            "PORTRAIT_MOTION_GRAPH_KIND",
            "PortraitMotionGraph",
        ),
    ),
    ("mode", _field("components.painted_terrain.models", "PaintedTerrainGround", "mode")),
    ("namespace", _constant("recipes.universe.universe_graph", "UNIVERSE_CACHE_NAMESPACE")),
    ("namespace", _constant("recipes.storefront.storefront_graph", "STOREFRONT_CACHE_NAMESPACE")),
    ("realization", _constant("components.sound_effect.models", "GENERATED_CLIP_REALIZATION_KIND")),
    ("realization", _constant("components.speech.models", "SPOKEN_LINE_REALIZATION_KIND")),
)

#: Block registries: a manifest's ``blocks`` table, key -> version. A version a component
#: declares (a block a shared family builds) is read from the component; the registry that
#: publishes it only references it.
BLOCK_REGISTRIES: tuple[IdentitySource, ...] = ()

#: Families with no current member: the whole family is retired, at every version. A family
#: with a current member needs no entry here, because every lower version is retired by
#: arithmetic. The reason is the doc's, not the test's; it is what the table prints.
RETIRED_FAMILIES: tuple[tuple[str, str], ...] = ()

#: Strings that are not `<family>-v<n>` shaped but name a retired thing all the same.
RETIRED_STRINGS: tuple[tuple[str, str], ...] = ()


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
    seen: dict[str, CurrentIdentitySource] = {}
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


@cache
def accepted_legacy_graph_identities() -> tuple[AcceptedLegacyGraphIdentity, ...]:
    """Graph identities retained strictly for reading route-free historical plans."""

    current = {entry.identity: entry.source for entry in contract_identities()}
    entries: list[AcceptedLegacyGraphIdentity] = []
    seen: dict[str, GraphIdentitySource] = {}
    for role, source in IDENTITY_SOURCES:
        if role != "graph" or not isinstance(source, GraphIdentitySource):
            continue
        for schema_version, identity in source.resolve_legacy():
            if identity in current:
                raise ValueError(
                    f"{identity} is both current at {current[identity]} and legacy at "
                    f"{source.legacy_authority}"
                )
            if identity in seen:
                raise ValueError(
                    f"{identity} is accepted twice: {seen[identity].legacy_authority} and "
                    f"{source.legacy_authority}"
                )
            seen[identity] = source
            family, separator, version = parse_identity(identity)
            if schema_version != version:
                raise ValueError(
                    f"{identity} encodes v{version} but {source.legacy_authority} "
                    f"pairs it with schema version {schema_version}"
                )
            entries.append(
                AcceptedLegacyGraphIdentity(
                    schema_version=schema_version,
                    identity=identity,
                    family=family,
                    separator=separator,
                    version=version,
                    source=source,
                )
            )
    return tuple(entries)


def current_versions() -> dict[str, frozenset[int]]:
    """Family → the versions with a live authority; the module docstring names the doubled ones."""

    versions: dict[str, set[int]] = {}
    for entry in contract_identities():
        versions.setdefault(entry.family, set()).add(entry.version)
    return {family: frozenset(found) for family, found in versions.items()}
