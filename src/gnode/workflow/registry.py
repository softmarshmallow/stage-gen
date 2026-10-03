"""Resolve ``uses:``: built-in node types, your project's node types, and workflows.

``gnode/<name>@<major>`` names a standard type; its identity is its declared version, and
``gnode.lock`` guards that the source behind a version never changes silently. A path
starting ``./`` is relative to the project root (the folder holding ``gnode.yaml``), from
whichever workflow file it is written in.
``./nodes/file.py#name`` names a type in your project; unless it declares a version, its
identity is its source: the module, the project modules it imports, and its declared
resources. ``./workflows/file.yaml`` names a workflow used as one step.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from gnode.workflow.document import WorkflowDocument, load_workflow
from gnode.workflow.spec import NodeSpec, SpecError, spec_of
from gnode.workflow.values import FactsReader, FileValue, digest_of

BUILTIN = re.compile(r"^gnode/(?P<name>[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*)@(?P<major>\d+)$")
PROJECT = re.compile(r"^(?P<file>\.{1,2}/[^#]+\.py)#(?P<name>[A-Za-z_][A-Za-z0-9_]*)$")
WORKFLOW = re.compile(r"^(?P<file>\.{1,2}/.+\.ya?ml)$")
PACKAGE = re.compile(r"^[a-z0-9_-]+/[a-z0-9_.]+@\d+$")


class RegistryError(ValueError):
    """A ``uses:`` that names nothing gnode can run."""


@dataclass(frozen=True, slots=True)
class TypeRef:
    """What a step's ``uses:`` names: the node type, and its identity for caching."""

    uses: str
    spec: NodeSpec
    identity: str


@dataclass(frozen=True, slots=True)
class WorkflowRef:
    """A workflow used as a step."""

    uses: str
    document: WorkflowDocument
    base_dir: Path


class Resolver:
    """What the expander asks of the project: node types, project files, route defaults."""

    def node_type(self, uses: str, base_dir: Path) -> TypeRef | WorkflowRef:
        raise NotImplementedError

    def project_file(self, relative: str, base_dir: Path) -> FileValue:
        raise NotImplementedError

    def route_default(self, capability: str) -> str | None:
        del capability
        return None

    def input_file(self, path: str, kind: str) -> FileValue:
        """A file another workflow passes as an input: any readable path, by content."""

        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class BuiltinType:
    major: int
    spec: NodeSpec


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ProjectModules:
    """Import your project's node modules once, and say which project files they read."""

    def __init__(self, root: Path, packages: Iterable[str] = ()) -> None:
        self.root = root.resolve()
        #: Installed packages whose modules count as project source (``sources:``).
        self.packages = tuple(packages)
        self._modules: dict[Path, ModuleType] = {}
        self._package_folders: dict[str, Path | None] = {}

    def load(self, path: Path) -> ModuleType:
        path = path.resolve()
        loaded = self._modules.get(path)
        if loaded is not None:
            return loaded
        if not path.is_relative_to(self.root):
            raise RegistryError(f"{path.name} is outside the project")
        name = "_gnode_project_" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise RegistryError(f"cannot import {path.name}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        added = str(self.root) not in sys.path
        if added:
            sys.path.insert(0, str(self.root))
        try:
            spec.loader.exec_module(module)
        except Exception as error:
            sys.modules.pop(name, None)
            raise RegistryError(
                f"{path.relative_to(self.root).as_posix()} failed to import: "
                f"{type(error).__name__}: {error}"
            ) from error
        finally:
            if added:
                sys.path.remove(str(self.root))
        self._modules[path] = module
        return module

    def source_closure(self, path: Path) -> list[Path]:
        """The module and every project module it imports, transitively."""

        seen: list[Path] = []
        frontier = [path.resolve()]
        while frontier:
            current = frontier.pop()
            if current in seen:
                continue
            seen.append(current)
            tree = ast.parse(current.read_text(encoding="utf-8"), filename=str(current))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    base = node.module or ""
                    if node.level:
                        package = current.parent
                        for _ in range(node.level - 1):
                            package = package.parent
                        prefix = self.label(package).replace("/", ".")
                        base = ".".join(part for part in (prefix, base) if part)
                    names = [base, *(f"{base}.{alias.name}" for alias in node.names)]
                for dotted in names:
                    candidate = self._project_file(dotted)
                    if candidate is not None and candidate not in seen:
                        frontier.append(candidate)
        return sorted(seen)

    def label(self, path: Path) -> str:
        """A source file's stable name: from the project root, or from a package's parent."""

        path = path.resolve()
        if path.is_relative_to(self.root):
            return path.relative_to(self.root).as_posix()
        for name in self.packages:
            folder = self._package_folder(name)
            if folder is not None and path.is_relative_to(folder):
                return path.relative_to(folder.parent).as_posix()
        raise RegistryError(f"{path.name} is outside the project and its sources")

    def _package_folder(self, name: str) -> Path | None:
        if name not in self._package_folders:
            found = importlib.util.find_spec(name)
            locations = None if found is None else found.submodule_search_locations
            self._package_folders[name] = (
                Path(next(iter(locations))).resolve() if locations else None
            )
        return self._package_folders[name]

    def _project_file(self, dotted: str) -> Path | None:
        if not dotted:
            return None
        top = dotted.partition(".")[0]
        bases = [(self.root, dotted)]
        if top in self.packages:
            folder = self._package_folder(top)
            if folder is not None:
                bases.append((folder.parent, dotted))
        for base, name in bases:
            relative = Path(*name.split("."))
            for candidate in (
                base / relative.with_suffix(".py"),
                base / relative / "__init__.py",
            ):
                if candidate.is_file():
                    return candidate.resolve()
        return None


class Registry(Resolver):
    """Everything ``uses:`` can name, with identities, plus project files by content."""

    def __init__(
        self,
        *,
        project_root: Path,
        builtins: Iterable[BuiltinType],
        locks: Mapping[str, str] | None = None,
        route_defaults: Mapping[str, str] | None = None,
        facts_reader: FactsReader | None = None,
        sources: Iterable[str] = (),
    ) -> None:
        self.project_root = project_root.resolve()
        self.builtins: dict[tuple[str, int], NodeSpec] = {}
        for builtin in builtins:
            self.builtins[(builtin.spec.name, builtin.major)] = builtin.spec
        self.locks = dict(locks or {})
        self.route_defaults = dict(route_defaults or {})
        self.modules = ProjectModules(self.project_root, sources)
        self.facts_reader = facts_reader
        self.lock_problems: list[str] = []
        self._files: dict[Path, FileValue] = {}

    # --------------------------------------------------------------- uses

    def node_type(self, uses: str, base_dir: Path) -> TypeRef | WorkflowRef:
        builtin = BUILTIN.fullmatch(uses)
        if builtin is not None:
            key = (builtin["name"], int(builtin["major"]))
            spec = self.builtins.get(key)
            if spec is None:
                raise RegistryError(f"no built-in node type {uses}; see gnode nodes")
            return TypeRef(uses, spec, f"{uses}.{spec.version or 0}")
        project = PROJECT.fullmatch(uses)
        if project is not None:
            return self._project_type(uses, base_dir / project["file"], project["name"])
        workflow = WORKFLOW.fullmatch(uses)
        if workflow is not None:
            path = (base_dir / workflow["file"]).resolve()
            if not path.is_file():
                raise RegistryError(f"{uses}: no workflow file {workflow['file']}")
            return WorkflowRef(uses, load_workflow(path), self.project_root)
        if PACKAGE.fullmatch(uses):
            raise RegistryError(f"{uses}: published node packages are not available yet")
        raise RegistryError(
            f"uses: {uses!r} is gnode/<type>@<major>, ./nodes/<file>.py#<name> "
            "or ./workflows/<file>.yaml"
        )

    def _project_type(self, uses: str, path: Path, attribute: str) -> TypeRef:
        if not path.is_file():
            raise RegistryError(f"{uses}: no file {path.name}")
        module = self.modules.load(path)
        value = getattr(module, attribute, None)
        spec = spec_of(value)
        if spec is None:
            raise RegistryError(f"{uses}: {attribute} is not declared with @node")
        source = self.source_identity(path, spec)
        relative = path.resolve().relative_to(self.project_root).as_posix()
        if spec.version is None:
            return TypeRef(uses, spec, f"source:{source}")
        locked = self.locks.get(f"{relative}#{attribute}@{spec.version}")
        if locked is not None and locked != source:
            self.lock_problems.append(
                f"{uses}: its source changed but version {spec.version} did not; bump the "
                f"version, or confirm no change in behaviour with "
                f"gnode lock --same {relative}#{attribute}"
            )
        return TypeRef(uses, spec, f"{relative}#{attribute}@{spec.version}")

    def source_identity(self, path: Path, spec: NodeSpec) -> str:
        files = {
            self.modules.label(item): _sha256_file(item)
            for item in self.modules.source_closure(path)
        }
        for resource in spec.resources:
            target = (self.project_root / resource).resolve()
            if not target.is_relative_to(self.project_root) or not target.is_file():
                raise SpecError(f"{spec.name}: declared resource {resource} is not a project file")
            files[resource] = _sha256_file(target)
        return digest_of(files)

    # -------------------------------------------------------------- files

    def project_file(self, relative: str, base_dir: Path) -> FileValue:
        path = (base_dir / relative).resolve()
        if not path.is_relative_to(self.project_root):
            raise RegistryError(f"{relative} is outside the project")
        cached = self._files.get(path)
        if cached is not None:
            return cached
        data = path.read_bytes()
        value = FileValue(
            digest=hashlib.sha256(data).hexdigest(),
            kind=kind_of(path),
            name=path.relative_to(self.project_root).as_posix(),
            size=len(data),
            facts_reader=self.facts_reader,
            location=str(path),
        )
        self._files[path] = value
        return value

    def route_default(self, capability: str) -> str | None:
        return self.route_defaults.get(capability)

    def input_file(self, path: str, kind: str) -> FileValue:
        target = Path(path)
        if not target.is_absolute():
            target = self.project_root / target
        target = target.resolve()
        if not target.is_file():
            raise RegistryError(f"no input file {path}")
        cached = self._files.get(target)
        if cached is not None:
            return cached
        data = target.read_bytes()
        found = kind_of(target)
        value = FileValue(
            digest=hashlib.sha256(data).hexdigest(),
            kind=found if found != "file" else kind,
            name=target.name,
            size=len(data),
            facts_reader=self.facts_reader,
            location=str(target),
        )
        self._files[target] = value
        return value


_KINDS = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".json": "json",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
    ".toml": "text/toml",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".zip": "file/zip",
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".html": "text/html",
}


def kind_of(path: Path) -> str:
    return _KINDS.get(path.suffix.lower(), "file")
