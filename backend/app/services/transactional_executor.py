"""
Transactional command execution — implements the Fault-Tolerant Sandboxing model
from Yan, "Fault-Tolerant Sandboxing for AI Coding Agents", arXiv:2512.12806
(2025).

Two layers, exactly as the paper specifies:

  1. Tool-Call Sandboxing Layer — a policy engine P(C) ∈ {SAFE, UNSAFE,
     UNCERTAIN} (paper §4.2):
       SAFE      read-only / low-risk (e.g. `git status`, `ls`)
                 -> execute directly, NO snapshot (latency bypass)
       UNSAFE    destructive (e.g. `rm -rf /`, `mkfs`)
                 -> blocked, NEVER executed
       UNCERTAIN state-modifying (e.g. `pip install`, `sed -i`)
                 -> wrapped in a filesystem transaction

  2. Fault Recovery Framework — transactional snapshot/rollback (paper Eq. 1,
     Algorithm 1):
       S_{t+1} = S_t + ΔC   if execution(C) succeeds   (COMMIT)
       S_{t+1} = S_t        if execution(C) fails       (ROLLBACK)
     Snapshot is a copy-on-write simulation via `shutil` (paper §4.3).

This module is deliberately executor-agnostic: `run()` takes an `executor`
callable so the transaction logic can be unit-tested deterministically and also
wired to the real subprocess runner in executor_service.py.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class Policy(str, Enum):
    SAFE      = "SAFE"
    UNSAFE    = "UNSAFE"
    UNCERTAIN = "UNCERTAIN"


# ── Policy engine (paper §4.2) ─────────────────────────────────────────────────

# SAFE: read-only / low-risk first tokens. These bypass the snapshot (latency).
_SAFE_COMMANDS = frozenset({
    "ls", "cat", "pwd", "echo", "grep", "find", "head", "tail", "wc", "stat",
    "file", "which", "whoami", "id", "date", "env", "printenv", "df", "du",
    "ps", "top", "uname", "hostname", "uptime", "tree", "diff",
})

# Read-only git subcommands (paper lists `git status` as Safe/Whitelisted).
_SAFE_GIT_SUBCOMMANDS = frozenset({
    "status", "log", "diff", "show", "branch", "remote", "config",
    "ls-files", "rev-parse", "describe", "blame", "shortlog", "tag",
})

# UNSAFE: destructive command signatures. Blocked, never executed.
# NOTE: classify() lowercases the command first, so all patterns use lowercase.
# The flag-skip group (-{1,2}[a-z-]+\s+)* tolerates long flags (e.g.
# --no-preserve-root) appearing *between* the -rf token and the / target —
# without it `rm -rf --no-preserve-root /` slips through (found via the NL2Bash
# + SandboxEscapeBench benchmark, benchmarks/b4_sandboxing).
_UNSAFE_PATTERNS = [
    re.compile(r"\brm\s+(-{1,2}[a-z-]+\s+)*-[a-z]*r[a-z]*f?[a-z]*\s+(-{1,2}[a-z-]+\s+)*/(?:\s|$|\*)"),  # rm -rf /
    re.compile(r"\brm\s+(-{1,2}[a-z-]+\s+)*-[a-z]*f[a-z]*r[a-z]*\s+(-{1,2}[a-z-]+\s+)*/(?:\s|$|\*)"),   # rm -fr /
    re.compile(r"--no-preserve-root"),                       # flag exists only to wipe /
    re.compile(r"\bmkfs(\.\w+)?\b"),                          # mkfs / mkfs.ext4
    re.compile(r"\bdd\b.*\bof=/dev/(sd|nvme|vd|hd)\w*"),      # dd of=/dev/sda
    re.compile(r">\s*/dev/(sd|nvme|vd|hd)\w*"),               # > /dev/sda
    re.compile(r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;"),# fork bomb :(){ :|:& };:
    re.compile(r"\bchmod\b.*\b000\b.*/\s*$"),                 # chmod -R 000 /
    re.compile(r"\bshred\b.*\s/(dev|etc|boot|bin|usr|lib)/"), # shred device or system file
    re.compile(r">\s*/etc/(passwd|shadow|sudoers)"),          # clobber critical files
    re.compile(r"\bmv\b[^|;&>\n]*\s/dev/null(?:\s|$)"),       # mv <path> /dev/null (destroy)
    re.compile(r">\s*/proc/sysrq-trigger"),                   # control/crash host kernel
    re.compile(r"(?:-v|--volume)\s+/:/"),                     # docker run -v /:/host (host-root mount)
    re.compile(r"\bunshare\b[^|;&\n]*\b(--map-root-user|sh|bash)\b"),  # new-namespace root/shell
]

# UNSAFE escape primitives (subset of Paper-2 vectors that are flat-out blocked
# rather than sandboxed — direct host-escape attempts).
_UNSAFE_ESCAPE_TOKENS = frozenset({
    "release_agent", "/proc/self/exe", "docker.sock", "/var/run/docker",
    "pivot_root", "init_module", "insmod", "nsenter", "sysrq-trigger",
})


@dataclass
class TxResult:
    """Outcome of a transactional execution (mirrors paper Algorithm 1 returns)."""
    policy:       Policy
    executed:     bool          # did the command actually run?
    exit_code:    Optional[int] # None if blocked
    stdout:       str = ""
    stderr:       str = ""
    committed:    bool = False  # state advanced (success)
    rolled_back:  bool = False  # state restored (failure)
    blocked:      bool = False  # UNSAFE -> never executed
    overhead_ms:  int = 0       # snapshot+restore time (the "sandbox tax")
    runtime_ms:   int = 0       # command execution time


def classify(command: str) -> Policy:
    """
    Policy function P(C) from paper §4.2.

    Order matters: UNSAFE checked first (a destructive command must never be
    mislabelled SAFE), then SAFE (read-only fast path), else UNCERTAIN.
    """
    if not command or not command.strip():
        return Policy.SAFE
    lowered = command.lower()

    # UNSAFE: destructive patterns or direct escape primitives
    for pat in _UNSAFE_PATTERNS:
        if pat.search(lowered):
            return Policy.UNSAFE
    for tok in _UNSAFE_ESCAPE_TOKENS:
        if tok in lowered:
            return Policy.UNSAFE

    # SAFE: every statement is a read-only whitelisted command
    statements = _split_statements(command)
    if statements and all(_is_safe_statement(s) for s in statements):
        return Policy.SAFE

    # Otherwise state-modifying -> transactional
    return Policy.UNCERTAIN


def _split_statements(command: str) -> list[str]:
    # Split on ; && || newline — coarse but enough for classification
    return [s.strip() for s in re.split(r"[;\n]|&&|\|\|", command) if s.strip()]


def _is_safe_statement(stmt: str) -> bool:
    # Reject pipes/redirects that could still write
    if re.search(r">\s*\S", stmt) or "|" in stmt and ">" in stmt:
        return False
    first = stmt.split()[0] if stmt.split() else ""
    # strip env-var prefixes like FOO=bar
    while "=" in first and not first.startswith("/"):
        parts = stmt.split()
        parts = parts[1:]
        if not parts:
            return False
        stmt = " ".join(parts)
        first = parts[0]
    # `git` is safe only for read-only subcommands (status, log, diff, ...)
    if first == "git":
        toks = stmt.split()
        return len(toks) >= 2 and toks[1] in _SAFE_GIT_SUBCOMMANDS
    return first in _SAFE_COMMANDS


# ── Snapshot / rollback (paper §4.3, Algorithm 1) ─────────────────────────────

def _snapshot(workdir: str) -> str:
    """Copy-on-write simulation: full copy of the workspace to a temp dir."""
    snap = tempfile.mkdtemp(prefix="astra-tx-snap-")
    dest = os.path.join(snap, "state")
    shutil.copytree(workdir, dest, dirs_exist_ok=True)
    return snap


def _restore(workdir: str, snap: str) -> None:
    """Restore workspace from snapshot (rollback)."""
    src = os.path.join(snap, "state")
    # Wipe current contents then copy snapshot back
    for entry in os.listdir(workdir):
        p = os.path.join(workdir, entry)
        if os.path.isdir(p) and not os.path.islink(p):
            shutil.rmtree(p, ignore_errors=True)
        else:
            try:
                os.remove(p)
            except OSError:
                pass
    shutil.copytree(src, workdir, dirs_exist_ok=True)


def _discard(snap: str) -> None:
    shutil.rmtree(snap, ignore_errors=True)


# Executor signature: (command, workdir) -> (exit_code, stdout, stderr)
ExecutorFn = Callable[[str, str], tuple[int, str, str]]


def run(command: str, workdir: str, executor: ExecutorFn) -> TxResult:
    """
    Transactional Execution Loop — Algorithm 1 from the paper.

      Classify C via P(C)
      if UNSAFE:  return ERROR (Policy Violation), never execute
      if SAFE:    execute, no snapshot
      else:       snapshot -> execute -> (commit | rollback)
    """
    policy = classify(command)

    if policy is Policy.UNSAFE:
        return TxResult(policy=policy, executed=False, exit_code=None,
                        stderr="Policy Violation: destructive command blocked",
                        blocked=True)

    if policy is Policy.SAFE:
        t0 = time.monotonic()
        code, out, err = executor(command, workdir)
        return TxResult(policy=policy, executed=True, exit_code=code,
                        stdout=out, stderr=err, committed=(code == 0),
                        runtime_ms=int((time.monotonic() - t0) * 1000))

    # UNCERTAIN -> transactional snapshot/execute/commit-or-rollback
    snap_t0 = time.monotonic()
    snap = _snapshot(workdir)
    snapshot_ms = int((time.monotonic() - snap_t0) * 1000)

    run_t0 = time.monotonic()
    code, out, err = executor(command, workdir)
    runtime_ms = int((time.monotonic() - run_t0) * 1000)

    restore_ms = 0
    if code != 0:
        r0 = time.monotonic()
        _restore(workdir, snap)
        restore_ms = int((time.monotonic() - r0) * 1000)
        _discard(snap)
        return TxResult(policy=policy, executed=True, exit_code=code,
                        stdout=out, stderr=(err + "\n[State Rolled Back]").strip(),
                        rolled_back=True,
                        overhead_ms=snapshot_ms + restore_ms, runtime_ms=runtime_ms)

    _discard(snap)
    return TxResult(policy=policy, executed=True, exit_code=code,
                    stdout=out, stderr=err, committed=True,
                    overhead_ms=snapshot_ms, runtime_ms=runtime_ms)
