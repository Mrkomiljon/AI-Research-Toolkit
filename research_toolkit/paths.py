"""Workspace layout and path-traversal protection."""
from __future__ import annotations

import os
from pathlib import Path

WORKSPACE_DIRS = [
    "sources",
    "papers/PDFs",
    "evidence",
    "literature",
    "analysis",
    "manuscript",
    "reviews",
    "progress",
    "workflow",
    "exports",
]


class UnsafePathError(ValueError):
    pass


def safe_join(root: Path, relative: str | os.PathLike[str]) -> Path:
    """Join `relative` under `root`; refuse absolute paths, drive letters and escapes via '..'."""
    rel = str(relative).replace("\\", "/")
    if not rel or rel.startswith("/") or (len(rel) > 1 and rel[1] == ":"):
        raise UnsafePathError(f"absolute path not allowed: {relative!r}")
    if any(part == ".." for part in rel.split("/")):
        raise UnsafePathError(f"path escapes workspace: {relative!r}")
    root_res = root.resolve()
    candidate = (root_res / rel).resolve()
    try:
        candidate.relative_to(root_res)
    except ValueError as exc:
        raise UnsafePathError(f"path escapes workspace: {relative!r}") from exc
    return candidate


def rel_to(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def ensure_workspace_dirs(root: Path) -> None:
    for d in WORKSPACE_DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
    for keep in ("papers/PDFs", "exports"):
        (root / keep / ".gitkeep").touch(exist_ok=True)
