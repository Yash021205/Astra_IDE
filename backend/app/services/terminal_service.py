"""
Interactive terminal for a workspace — a real shell process bridged over a
WebSocket to an xterm.js front-end.

In production each workspace runs inside its sandbox tier (runc/gVisor/
Firecracker, see B4); the terminal there is the sandbox's own shell, so the
blast radius is the container. In dev we spawn a shell rooted at the workspace's
on-disk directory (workspace_files.workspace_dir). Two backends:

  * POSIX  — a genuine PTY (pty.openpty) so full-screen TUIs, colours, job
             control and window-resize all work.
  * Windows — a pipe-bridged cmd.exe fallback (no PTY); good enough for the dev
             demo (type commands, see output) without extra native deps.
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

_POSIX = os.name == "posix"

if _POSIX:
    import fcntl
    import pty
    import select
    import struct
    import termios


class TerminalProcess:
    """A shell process with read/write/resize, uniform across platforms."""

    def __init__(self, cwd: Path, shell: str | None = None,
                 argv: list[str] | None = None):
        # `argv`, if given, is the exact command to run (e.g. a `docker exec`
        # into the workspace container). Otherwise a plain login shell.
        self.cwd = str(cwd)
        self._closed = False
        if _POSIX:
            self._start_posix(argv or [shell or os.environ.get("SHELL", "/bin/bash")])
        else:
            self._start_windows(argv or [shell or "cmd.exe"])

    # ── POSIX: real PTY ──────────────────────────────────────────────────────
    def _start_posix(self, argv: list[str]) -> None:
        self._master, slave = pty.openpty()
        env = dict(os.environ, TERM="xterm-256color")
        self._proc = subprocess.Popen(
            argv, stdin=slave, stdout=slave, stderr=slave,
            cwd=self.cwd, env=env, start_new_session=True, close_fds=True)
        os.close(slave)

    # ── Windows: pipe-bridged cmd.exe ────────────────────────────────────────
    def _start_windows(self, argv: list[str]) -> None:
        self._proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, cwd=self.cwd, bufsize=0,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self._q: "queue.Queue[bytes]" = queue.Queue()
        self._reader = threading.Thread(target=self._win_reader, daemon=True)
        self._reader.start()

    def _win_reader(self) -> None:
        fd = self._proc.stdout.fileno()
        while True:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            self._q.put(chunk)

    # ── Uniform API ──────────────────────────────────────────────────────────
    @property
    def alive(self) -> bool:
        return not self._closed and self._proc.poll() is None

    def write(self, data: str) -> None:
        if self._closed:
            return
        raw = data.encode(errors="ignore")
        if _POSIX:
            try:
                os.write(self._master, raw)
            except OSError:
                self.close()
        else:
            try:
                self._proc.stdin.write(raw)
                self._proc.stdin.flush()
            except (OSError, ValueError):
                self.close()

    def resize(self, rows: int, cols: int) -> None:
        if _POSIX and not self._closed:
            try:
                fcntl.ioctl(self._master, termios.TIOCSWINSZ,
                            struct.pack("HHHH", rows, cols, 0, 0))
            except OSError:
                pass  # PTY went away

    def read_blocking(self, timeout: float = 0.2) -> bytes:
        """Return available shell output (<= ~64 KiB) or b'' if none within timeout."""
        if self._closed:
            return b""
        if _POSIX:
            try:
                r, _, _ = select.select([self._master], [], [], timeout)
            except (OSError, ValueError):
                return b""
            if self._master in r:
                try:
                    return os.read(self._master, 65536)
                except OSError:
                    self.close()
                    return b""
            return b""
        else:
            try:
                return self._q.get(timeout=timeout)
            except queue.Empty:
                return b""

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._proc.terminate()
        except Exception:
            pass
        if _POSIX:
            try:
                os.close(self._master)
            except OSError:
                pass
