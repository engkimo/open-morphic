"""Filesystem tools — pathlib wrappers for LAEE."""

from __future__ import annotations

import glob as globlib
import shutil
from pathlib import Path
from typing import Any


async def fs_read(args: dict[str, Any]) -> str:
    """Read file contents."""
    path = Path(args["path"])
    return path.read_text(encoding=args.get("encoding", "utf-8"))


async def fs_write(args: dict[str, Any]) -> str:
    """Write content to file. Creates parent directories if needed."""
    path = Path(args["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    content = args["content"]
    path.write_text(content, encoding=args.get("encoding", "utf-8"))
    return f"Written {len(content)} bytes to {path}"


async def fs_edit(args: dict[str, Any]) -> str:
    """Replace first occurrence of old string with new string in file."""
    path = Path(args["path"])
    content = path.read_text()
    old = args["old"]
    new = args["new"]
    if old not in content:
        raise ValueError(f"Pattern not found in {path}: {old!r}")
    content = content.replace(old, new, 1)
    path.write_text(content)
    return f"Edited {path}: replaced 1 occurrence"


async def fs_delete(args: dict[str, Any]) -> str:
    """Delete file or directory."""
    path = Path(args["path"])
    recursive = args.get("recursive", False)
    if path.is_dir():
        if recursive:
            shutil.rmtree(path)
        else:
            path.rmdir()
    else:
        path.unlink()
    return f"Deleted {path}"


async def fs_move(args: dict[str, Any]) -> str:
    """Move or rename file/directory."""
    src = Path(args["src"])
    dst = Path(args["dst"])
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return f"Moved {src} -> {dst}"


async def fs_glob(args: dict[str, Any]) -> str:
    """Glob pattern search."""
    pattern = args["pattern"]
    root = args.get("path", ".")
    matches = sorted(globlib.glob(pattern, root_dir=root, recursive=True))
    return "\n".join(matches) if matches else "(no matches)"


async def fs_tree(args: dict[str, Any]) -> str:
    """Display directory tree."""
    root = Path(args.get("path", "."))
    max_depth = args.get("max_depth", 3)
    lines: list[str] = [str(root)]
    _walk(root, "", max_depth, 0, lines)
    return "\n".join(lines)


def _walk(
    directory: Path, prefix: str, max_depth: int, depth: int, lines: list[str]
) -> None:
    if depth >= max_depth or not directory.is_dir():
        return
    entries = sorted(directory.iterdir())
    for i, entry in enumerate(entries):
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{entry.name}")
        if entry.is_dir():
            extension = "    " if is_last else "│   "
            _walk(entry, prefix + extension, max_depth, depth + 1, lines)
