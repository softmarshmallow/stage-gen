"""Keep repository workspace composition out of the standalone core source archive."""

from __future__ import annotations

import gzip
import io
import os
import re
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


def standalone_pyproject(contents: str) -> str:
    """Remove only workspace ownership; preserve the package and its dev dependencies."""
    excluded_sections = {"tool.uv.workspace", "tool.uv.sources"}
    section = ""
    lines: list[str] = []
    for line in contents.splitlines(keepends=True):
        match = re.fullmatch(r"\[([^\[\]]+)\]\s*", line.strip())
        if match:
            section = match.group(1)
        if section in excluded_sections:
            continue
        if section == "dependency-groups" and re.match(r"(?:games|apps)\s*=", line):
            continue
        lines.append(line)
    return "".join(lines)


class CoreSourceArchiveHook(BuildHookInterface):  # type: ignore[type-arg]
    """Generate sdist-only metadata without mutating the checkout's workspace."""

    def finalize(self, version: str, build_data: dict[str, Any], artifact_path: str) -> None:
        if self.target_name != "sdist":
            return
        artifact = Path(artifact_path)
        descriptor, staged_name = tempfile.mkstemp(dir=artifact.parent, suffix=".tar.gz")
        staged = Path(staged_name)
        try:
            with (
                os.fdopen(descriptor, "wb") as out,
                tarfile.open(artifact, "r:gz") as source,
                gzip.GzipFile(fileobj=out, mode="wb", filename="", mtime=315532800) as compressed,
                tarfile.open(fileobj=compressed, mode="w") as target,
            ):
                for member in source.getmembers():
                    stream = source.extractfile(member) if member.isfile() else None
                    if member.name.endswith("/pyproject.toml"):
                        if stream is None:
                            raise ValueError("source archive pyproject.toml must be a file")
                        content = standalone_pyproject(stream.read().decode("utf-8")).encode()
                        stream.close()
                        member.size = len(content)
                        stream = io.BytesIO(content)
                    target.addfile(member, stream)
                    if stream is not None:
                        stream.close()
            os.replace(staged, artifact)
        finally:
            staged.unlink(missing_ok=True)
