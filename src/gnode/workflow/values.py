"""The values a plan and a run pass between steps, and how each enters identity.

A file is known by its content (``FileValue``). A repeated step's results are a keyed,
ordered ``Collection``. A step that was left out, skipped or rejected yields ``MISSING``,
which ``??`` and ``gnode/select`` step over; a step that failed yields a ``Failed`` that
skips whatever reads it. While planning, a result that does not exist yet is an
``expr.Pending``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from gnode.workflow.expr import ExpressionError, Pending, Scope, _plain

FactsReader = Callable[["FileValue"], Mapping[str, Any]]


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def digest_of(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class FileValue:
    """One file, known by the SHA-256 of its bytes.

    ``name`` is only for people (an input's path, an output's port); it never enters
    identity. ``content`` is a JSON file's parsed value, so ``outputs.json.title`` reads
    into it. ``facts`` are intrinsic measurements (size, alpha, duration) read on demand.
    """

    digest: str
    kind: str
    name: str
    size: int
    key: str | None = None
    content: Any = field(default=None, compare=False, repr=False)
    facts_reader: FactsReader | None = field(default=None, compare=False, repr=False)
    location: str | None = field(default=None, compare=False, repr=False)

    def expression_plain(self) -> Any:
        return {"file": self.digest}

    def expression_text(self) -> str:
        if isinstance(self.content, str):
            return self.content
        return f"sha256:{self.digest}"

    def expression_facts(self) -> Mapping[str, Any]:
        facts: dict[str, Any] = {"bytes": self.size, "kind": self.kind}
        if self.facts_reader is not None:
            facts.update(self.facts_reader(self))
        return facts

    def expression_stem(self) -> str:
        return PurePosixPath(self.name).stem

    def expression_member(self, name: str) -> Any:
        if isinstance(self.content, Mapping):
            if name not in self.content:
                raise ExpressionError(f"{self.name} has no field {name!r}")
            return self.content[name]
        if name in {"digest", "kind", "key"}:
            return getattr(self, name)
        raise ExpressionError(f"a file has no field {name!r}; use facts(file).{name}")

    def expression_item(self, index: Any) -> Any:
        if isinstance(self.content, list | Mapping):
            return Scope().item(self.content, index)
        raise ExpressionError(f"{self.name} cannot be indexed")

    def expression_len(self) -> int:
        if isinstance(self.content, list | Mapping | str):
            return len(self.content)
        raise ExpressionError(f"len() of a {self.kind} file")

    def with_key(self, key: str | None) -> FileValue:
        return FileValue(
            self.digest,
            self.kind,
            self.name,
            self.size,
            key,
            self.content,
            self.facts_reader,
            self.location,
        )


class _Missing:
    """A result that does not exist: left out, skipped or rejected."""

    _instance: _Missing | None = None

    def __new__(cls) -> _Missing:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "MISSING"

    expression_is_missing = True

    def __bool__(self) -> bool:
        return False

    def expression_plain(self) -> Any:
        return {"missing": True}

    def expression_member(self, name: str) -> Any:
        del name
        return self

    def expression_item(self, index: Any) -> Any:
        del index
        return self


MISSING: Any = _Missing()


@dataclass(frozen=True, slots=True)
class Failed:
    """A failed step's result: whatever reads it is skipped, never run on a stand-in."""

    instance_id: str

    def expression_plain(self) -> Any:
        return {"failed": self.instance_id}

    def expression_member(self, name: str) -> Any:
        del name
        return self

    def expression_item(self, index: Any) -> Any:
        del index
        return self


@dataclass(frozen=True, slots=True)
class Collection:
    """Every instance of a repeat, in ``for_each`` order, each under its key.

    Skipped instances are absent. ``verdicts`` carries each element's verdict when its
    step was judged, for ``accepted()``.
    """

    items: tuple[tuple[str, Any], ...]
    verdicts: Mapping[str, str | None] = field(default_factory=dict)

    def __iter__(self) -> Iterator[tuple[str, Any]]:
        return iter(self.items)

    def keys(self) -> list[str]:
        return [key for key, _ in self.items]

    def values(self) -> list[Any]:
        return [value for _, value in self.items]

    def as_mapping(self) -> dict[str, Any]:
        return dict(self.items)

    def expression_plain(self) -> Any:
        return {"collection": [[key, _plain(value)] for key, value in self.items]}

    def expression_len(self) -> int:
        return len(self.items)

    def expression_item(self, index: Any) -> Any:
        for key, value in self.items:
            if key == index:
                return value
        if isinstance(index, int) and not isinstance(index, bool):
            return self.items[index][1]
        raise ExpressionError(f"no instance {index!r}")

    def expression_member(self, name: str) -> Any:
        """The same field of every element: ``collection.json.title`` per key."""

        scope = Scope()
        items: list[tuple[str, Any]] = []
        for key, value in self.items:
            member = scope.member(value, name)
            if member is MISSING:
                continue
            items.append((key, member))
        return Collection(tuple(items), self.verdicts)

    def expression_accepted(self) -> Any:
        undecided = [key for key, _ in self.items if self.verdicts.get(key, "accept") is None]
        if undecided:
            refs: set[str] = set()
            for _, value in self.items:
                refs |= pending_refs(value)
            return Pending(frozenset(refs), digest_of({"accepted": self.expression_plain()}))
        return Collection(
            tuple(
                (key, value)
                for key, value in self.items
                if self.verdicts.get(key, "accept") == "accept"
            ),
            {key: "accept" for key, _ in self.items if self.verdicts.get(key) == "accept"},
        )


def plain(value: Any) -> Any:
    """A JSON-shaped stand-in for identity: files by digest, pending results by token."""

    return _plain(value)


def contains(value: Any, predicate: Callable[[Any], bool]) -> bool:
    if predicate(value):
        return True
    if isinstance(value, Collection):
        return any(contains(item, predicate) for _, item in value.items)
    if isinstance(value, Mapping):
        return any(contains(item, predicate) for item in value.values())
    if isinstance(value, list | tuple):
        return any(contains(item, predicate) for item in value)
    return False


def contains_pending(value: Any) -> bool:
    return contains(value, lambda item: isinstance(item, Pending))


def contains_failed(value: Any) -> bool:
    return contains(value, lambda item: isinstance(item, Failed))


def pending_refs(value: Any) -> set[str]:
    """Every instance a value is waiting on."""

    found: set[str] = set()

    def visit(item: Any) -> bool:
        if isinstance(item, Pending):
            found.update(item.refs)
        return False

    contains(value, visit)
    return found


__all__ = [
    "MISSING",
    "Collection",
    "Failed",
    "FileValue",
    "canonical_json",
    "contains_failed",
    "contains_pending",
    "digest_of",
    "pending_refs",
    "plain",
]
