"""Real per-workspace containers, managed through the Docker CLI.

When ENABLE_REAL_CONTAINERS=1 and the Docker socket is available, each workspace
is backed by a genuine container: `Start` runs one (with the workspace files
bind-mounted, CPU/memory limits, and network on/off per its risk profile), the
terminal `docker exec`s a shell INTO it, and the Containers page reads real
`docker stats`/`docker logs`. Everything is best-effort — if Docker isn't
reachable, callers fall back to the in-process behaviour so the app still works.
"""
from __future__ import annotations

import os
import shutil
import subprocess

from app.services import workspace_files

ENABLED = os.getenv("ENABLE_REAL_CONTAINERS", "0") == "1"
# Host path that is bind-mounted to /app/workspace_data inside the backend
# container, so nested per-workspace containers can mount the same files.
WORKSPACE_DATA_HOST = os.getenv("WORKSPACE_DATA_HOST", "")

# Small base images per language (pulled on first start).
_IMAGES = {
    "python": "python:3.12-slim", "javascript": "node:20-slim", "typescript": "node:20-slim",
    "go": "golang:1.22-alpine", "rust": "rust:1-slim", "cpp": "gcc:13", "c": "gcc:13",
    "java": "eclipse-temurin:21-jdk", "bash": "alpine:3.20", "shell": "alpine:3.20",
}


def image_for(language: str) -> str:
    return _IMAGES.get((language or "").lower(), "debian:stable-slim")


def _name(ws_id: int) -> str:
    return f"astra-ws-{ws_id}"


def available() -> bool:
    """Real containers are enabled AND the docker client + socket are present."""
    return ENABLED and shutil.which("docker") is not None and os.path.exists("/var/run/docker.sock")


def _docker(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


_RUNTIMES_CACHE: set[str] | None = None


def _runtimes() -> set[str]:
    """Runtimes Docker knows about (e.g. {'runc', 'runsc', 'kata-fc'})."""
    global _RUNTIMES_CACHE
    if _RUNTIMES_CACHE is None:
        try:
            r = _docker(["info", "--format", "{{range $k,$v := .Runtimes}}{{$k}} {{end}}"], timeout=10)
            _RUNTIMES_CACHE = set(r.stdout.split()) if r.returncode == 0 else {"runc"}
        except Exception:
            _RUNTIMES_CACHE = {"runc"}
    return _RUNTIMES_CACHE


def runtime_for(tier: str) -> str:
    """Map a sandbox tier to a Docker runtime that's actually installed.
    runc → runc; gVisor/Firecracker → runsc (gVisor) if present, else runc.
    (True Firecracker/Kata needs KVM/nested-virt, unavailable on e2 VMs.)"""
    rts = _runtimes()
    if tier in ("gvisor", "firecracker") and "runsc" in rts:
        return "runsc"
    if tier == "firecracker":
        for cand in ("kata-fc", "kata-runtime", "kata"):
            if cand in rts:
                return cand
    return "runc"


def is_running(ws_id: int) -> bool:
    if not available():
        return False
    try:
        r = _docker(["inspect", "-f", "{{.State.Running}}", _name(ws_id)], timeout=10)
        return r.returncode == 0 and r.stdout.strip() == "true"
    except Exception:
        return False


def start(ws) -> bool:
    """Create + start the per-workspace container. Returns True on success."""
    if not available():
        return False
    name = _name(ws.id)
    try:
        _docker(["rm", "-f", name], timeout=30)                  # clear any stale one
        workspace_files.workspace_dir(ws.id)                     # ensure the dir exists
        runtime = runtime_for(ws.sandbox_tier)
        args = [
            "run", "-d", "--name", name, "--label", "astra=1",
            "--label", f"tier={ws.sandbox_tier}", "--runtime", runtime,
            "--memory", f"{int(ws.memory_request)}m",
            "--cpus", str(ws.cpu_request or 0.5),
            "--pids-limit", "256",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--network", "bridge" if ws.network_access else "none",
            "-w", "/workspace",
        ]
        if WORKSPACE_DATA_HOST:
            args += ["-v", f"{os.path.join(WORKSPACE_DATA_HOST, f'ws-{ws.id}')}:/workspace"]
        args += [image_for(ws.language), "sleep", "infinity"]
        r = _docker(args, timeout=240)                           # may pull the image
        return r.returncode == 0
    except Exception:
        return False


def stop(ws_id: int) -> None:
    if available():
        try:
            _docker(["rm", "-f", _name(ws_id)], timeout=30)
        except Exception:
            pass


def exec_argv(ws_id: int) -> list[str]:
    """Command that opens an interactive shell inside the workspace container."""
    return ["docker", "exec", "-i", "-t", _name(ws_id), "/bin/sh"]


def _to_mb(s: str) -> float:
    s = s.strip()
    try:
        if s.endswith("GiB"): return round(float(s[:-3]) * 1024, 1)
        if s.endswith("MiB"): return round(float(s[:-3]), 1)
        if s.endswith("KiB"): return round(float(s[:-3]) / 1024, 1)
        if s.endswith("B"):   return round(float(s[:-1]) / 1024 / 1024, 2)
    except ValueError:
        pass
    return 0.0


def stats(ws_id: int) -> dict | None:
    """Live {cpu_pct, mem_mb, mem_pct} from `docker stats`, or None."""
    if not is_running(ws_id):
        return None
    try:
        r = _docker(["stats", "--no-stream", "--format",
                     "{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}", _name(ws_id)], timeout=15)
        if r.returncode != 0 or "|" not in r.stdout:
            return None
        cpu, mem, memp = r.stdout.strip().split("|")
        return {
            "cpu_pct": float(cpu.strip().rstrip("%") or 0),
            "mem_mb": _to_mb(mem.split("/")[0]),
            "mem_pct": float(memp.strip().rstrip("%") or 0),
        }
    except Exception:
        return None


def logs(ws_id: int, tail: int = 50) -> list[str]:
    if not available():
        return []
    try:
        r = _docker(["logs", "--tail", str(tail), _name(ws_id)], timeout=15)
        out = (r.stdout + r.stderr).strip()
        return out.splitlines() if out else []
    except Exception:
        return []


# ── Port discovery + in-container HTTP proxy (live preview of a dev server) ─────

def list_listening_ports(ws_id: int) -> list[int]:
    """TCP ports something is listening on INSIDE the workspace container, so the
    preview UI can offer real dev-server ports. Best-effort: needs ss or netstat
    in the image (present on most dev images); returns [] otherwise."""
    if not is_running(ws_id):
        return []
    try:
        r = _docker(["exec", _name(ws_id), "sh", "-c",
                     "ss -tlnH 2>/dev/null || netstat -tln 2>/dev/null"], timeout=10)
    except Exception:
        return []
    import re
    ports: set[int] = set()
    for line in (r.stdout or "").splitlines():
        m = re.search(r"[:.](\d{2,5})\s", line + " ")   # port in the local-address column
        if m:
            p = int(m.group(1))
            if 1 <= p <= 65535:
                ports.add(p)
    return sorted(ports)


def fetch_port(ws_id: int, port: int, path: str) -> tuple[bytes, str] | None:
    """HTTP GET a dev server running inside the container at 127.0.0.1:<port>/<path>
    and return (body, content_type), or None if unreachable. Runs the request with
    whatever HTTP client the image already has (curl / wget / python / node), so it
    works even for a `--network none` sandbox. Content type is inferred from the path."""
    if not is_running(ws_id):
        return None
    p = (path or "").lstrip("/")
    url = f"http://127.0.0.1:{int(port)}/{p}"
    name = _name(ws_id)
    pyfetch = (f"import urllib.request,sys;"
               f"sys.stdout.buffer.write(urllib.request.urlopen({url!r},timeout=10).read())")
    nodefetch = (f"const h=require('http');h.get({url!r},r=>{{const d=[];"
                 f"r.on('data',c=>d.push(c));r.on('end',()=>process.stdout.write(Buffer.concat(d)))}})"
                 f".on('error',()=>process.exit(1))")
    attempts = [
        ["curl", "-sS", "-m", "10", url],
        ["wget", "-qO-", "-T", "10", url],
        ["python3", "-c", pyfetch],
        ["python", "-c", pyfetch],
        ["node", "-e", nodefetch],
    ]
    for argv in attempts:
        try:
            r = subprocess.run(["docker", "exec", name, *argv],
                               capture_output=True, timeout=15)   # bytes (no text=True)
        except Exception:
            continue
        if r.returncode == 0 and r.stdout:
            import mimetypes
            ctype = mimetypes.guess_type(p or "index.html")[0] or "text/html; charset=utf-8"
            return r.stdout, ctype
    return None
