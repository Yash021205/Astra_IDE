"""
Per-workspace file storage + GitHub repo import.

Each workspace gets a directory under WORKSPACE_DATA_ROOT. Supports importing a
public git repo (the "bring a GitHub repo" flow), listing the file tree, and
reading/writing files. All paths are confined to the workspace directory
(path-traversal safe), and imports are restricted to https git hosts.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

WORKSPACE_DATA_ROOT = Path(
    os.getenv("ASTRA_WORKSPACE_DATA", Path(__file__).resolve().parents[2] / "workspace_data")
)
MAX_FILE_BYTES = 1 * 1024 * 1024            # 1 MB per file read/write
# Public repos: strict allowlist of git hosts.
_ALLOWED_GIT = re.compile(r"^https://(github\.com|gitlab\.com|bitbucket\.org)/[\w.\-]+/[\w.\-]+(\.git)?/?$")
# Authenticated clones (token@github.com) are allowed from internal callers only.
_ALLOWED_GIT_AUTH = re.compile(r"^https://[^@]+@(github\.com|gitlab\.com|bitbucket\.org)/[\w.\-]+/[\w.\-]+(\.git)?/?$")
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".next", "dist", "build", "venv", ".venv"}


def _ws_dir(workspace_id: int) -> Path:
    d = WORKSPACE_DATA_ROOT / f"ws-{workspace_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def workspace_dir(workspace_id: int) -> Path:
    """Public accessor for the workspace's on-disk directory (used by the terminal)."""
    return _ws_dir(workspace_id)


def _safe_path(workspace_id: int, rel: str) -> Path:
    """Resolve `rel` inside the workspace dir; reject traversal outside it."""
    base = _ws_dir(workspace_id).resolve()
    target = (base / rel.lstrip("/")).resolve()
    if base != target and base not in target.parents:
        raise ValueError("path escapes workspace")
    return target


@dataclass
class ImportResult:
    ok: bool
    detail: str
    file_count: int = 0


def import_repo(workspace_id: int, git_url: str, branch: str | None = None) -> ImportResult:
    """Shallow-clone a git repo into the workspace (replacing its contents).

    Accepts:
    - Public HTTPS repos (github/gitlab/bitbucket)
    - Authenticated HTTPS URLs (token@host/…) — used internally by the GitHub
      integration for private-repo clones. Never called with user-provided URLs.
    An optional `branch` narrows the clone to that branch.
    """
    git_url = git_url.strip()
    is_public = _ALLOWED_GIT.match(git_url)
    is_auth   = _ALLOWED_GIT_AUTH.match(git_url)
    if not is_public and not is_auth:
        return ImportResult(False, "only https github/gitlab/bitbucket repos are allowed")
    base = _ws_dir(workspace_id)
    # clone into a temp sibling then move contents in (keeps base stable)
    tmp = base.parent / f".clone-{workspace_id}"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd += ["--branch", branch]
        cmd += [git_url, str(tmp)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            # Strip token from error messages before returning
            err = re.sub(r"https://[^@]+@", "https://***@", r.stderr or "")
            return ImportResult(False, f"clone failed: {err[-200:]}")
        # wipe workspace + move cloned files in (drop .git)
        for child in base.iterdir():
            shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink()
        shutil.rmtree(tmp / ".git", ignore_errors=True)
        for child in tmp.iterdir():
            shutil.move(str(child), str(base / child.name))
        n = sum(1 for _ in base.rglob("*") if _.is_file())
        return ImportResult(True, f"imported {git_url.split('@')[-1]}", n)
    except subprocess.TimeoutExpired:
        return ImportResult(False, "clone timed out (repo too large?)")
    except FileNotFoundError:
        # `git` binary not present on the host/container.
        return ImportResult(False, "git is not available on the server")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def list_tree(workspace_id: int, max_entries: int = 2000) -> list[dict]:
    """Flat list of files/dirs (relative paths) for the workspace, skipping noise."""
    base = _ws_dir(workspace_id)
    out: list[dict] = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        rel_root = os.path.relpath(root, base)
        for d in sorted(dirs):
            p = "" if rel_root == "." else rel_root + "/"
            out.append({"path": p + d, "type": "dir"})
        for f in sorted(files):
            p = "" if rel_root == "." else rel_root + "/"
            try:
                size = (Path(root) / f).stat().st_size
            except OSError:
                size = 0
            out.append({"path": p + f, "type": "file", "size": size})
        if len(out) >= max_entries:
            break
    return sorted(out, key=lambda e: e["path"])[:max_entries]


def read_file(workspace_id: int, rel: str) -> str:
    p = _safe_path(workspace_id, rel)
    if not p.is_file():
        raise FileNotFoundError(rel)
    if p.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("file too large to open")
    return p.read_text(encoding="utf-8", errors="replace")


def write_file(workspace_id: int, rel: str, content: str) -> int:
    if len(content.encode("utf-8", errors="replace")) > MAX_FILE_BYTES:
        raise ValueError("file too large to save")
    p = _safe_path(workspace_id, rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p.stat().st_size


def write_bytes_file(workspace_id: int, rel: str, data: bytes) -> int:
    """Write raw bytes (uploaded file) into the workspace. 8 MB cap."""
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("file too large to upload (max 8 MB)")
    p = _safe_path(workspace_id, rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p.stat().st_size


def make_dir(workspace_id: int, rel: str) -> None:
    """Create a folder (and parents) inside the workspace."""
    p = _safe_path(workspace_id, rel)
    p.mkdir(parents=True, exist_ok=True)


def delete_path(workspace_id: int, rel: str) -> None:
    """Delete a file or folder (recursively) inside the workspace."""
    p = _safe_path(workspace_id, rel)
    base = _ws_dir(workspace_id).resolve()
    if p == base:
        raise ValueError("cannot delete the workspace root")
    if p.is_dir():
        shutil.rmtree(p, ignore_errors=True)
    elif p.exists():
        p.unlink()
    else:
        raise FileNotFoundError(rel)


def read_bytes(workspace_id: int, rel: str) -> tuple[bytes, str]:
    """Return (raw bytes, guessed content-type) for a file — used to serve images."""
    import mimetypes
    p = _safe_path(workspace_id, rel)
    if not p.is_file():
        raise FileNotFoundError(rel)
    if p.stat().st_size > 8 * 1024 * 1024:        # 8 MB cap for raw serving
        raise ValueError("file too large")
    ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    return p.read_bytes(), ctype


def search(workspace_id: int, query: str, max_results: int = 200) -> list[dict]:
    """Plain-text search across workspace files (VS Code-style results)."""
    if not query:
        return []
    base = _ws_dir(workspace_id)
    q = query.lower()
    out: list[dict] = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for f in sorted(files):
            fp = Path(root) / f
            try:
                if fp.stat().st_size > MAX_FILE_BYTES:
                    continue
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = str(fp.relative_to(base)).replace("\\", "/")
            for i, line in enumerate(text.splitlines(), 1):
                if q in line.lower():
                    out.append({"path": rel, "line": i, "text": line.strip()[:240]})
                    if len(out) >= max_results:
                        return out
    return out


def copy_workspace_files(src_id: int, dst_id: int) -> int:
    """Copy all files from one workspace dir into another (used by fork)."""
    src = _ws_dir(src_id)
    dst = _ws_dir(dst_id)
    n = 0
    for item in src.rglob("*"):
        if any(part in _SKIP_DIRS for part in item.relative_to(src).parts):
            continue
        target = dst / item.relative_to(src)
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            n += 1
    return n


def delete_workspace_files(workspace_id: int) -> None:
    shutil.rmtree(_ws_dir(workspace_id), ignore_errors=True)
