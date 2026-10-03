"""Where things sit in a run folder; the runner writes there and every reader looks there."""

from __future__ import annotations

_SUFFIXES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "json": ".json",
    "annotations": ".json",
    "text/markdown": ".md",
    "text/plain": ".txt",
    "audio/wav": ".wav",
    "audio/mpeg": ".mp3",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/x-matroska": ".mkv",
    "model/gltf-binary": ".glb",
    "file/zip": ".zip",
}


def suffix(kind: str) -> str:
    return _SUFFIXES.get(kind, "")


def safe(path: str) -> str:
    """A step path as one folder name."""

    out = [c if c.isalnum() or c in "._-" else "_" for c in path]
    return "".join(out).strip("_") or "step"


def step_file(path: str, port: str, kind: str, *, key: str | None, index: int, count: int) -> str:
    """``files/<step path>/<port><suffix>``; one file of several is ``<port>/<key or index>``."""

    label = port if count == 1 else f"{port}/{key or index}"
    return f"files/{safe(path)}/{label}{suffix(kind)}"


def output_file(name: str, kind: str, *, key: str | None, index: int, single: bool) -> str:
    """``outputs/<name><suffix>``; an element of a list or collection is ``<name>/<key>``."""

    label = name if single else f"{name}/{key or index}"
    return f"outputs/{label}{suffix(kind)}"


def view_file(digest: str, kind: str) -> str:
    """A file a view shows, kept beside the view so a copied run folder still shows it."""

    return f"views/files/{digest}{suffix(kind)}"


def view_template(digest: str) -> str:
    """A view's HTML template, by the digest of its bytes."""

    return f"views/{digest}.html"


__all__ = ["output_file", "safe", "step_file", "suffix", "view_file", "view_template"]
