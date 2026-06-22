"""
Risk Scorer (backend vendored copy) — kept byte-for-byte in sync with
ml/risk_scorer/scorer.py. Vendored (not imported) so the backend container
doesn't need the ml package. Only stdlib deps (ast, re).

Research basis + citations: docs/research/01-adaptive-sandboxing.md
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Iterable

SANDBOX_TIERS = ("runc", "gvisor", "firecracker")

_SHELL_LANGS   = frozenset({"bash", "sh", "shell", "zsh", "ksh", "powershell", "ps1"})
_INTERP_FFI    = frozenset({"python", "py", "javascript", "js", "node", "ruby", "perl", "php", "lua"})
_MANAGED_LANGS = frozenset({"go", "rust", "java", "cpp", "c++", "c", "csharp", "kotlin", "scala", "typescript", "ts"})

LANG_SCORE_SHELL   = 1.0
LANG_SCORE_INTERP  = 0.5
LANG_SCORE_MANAGED = 0.2
LANG_SCORE_UNKNOWN = 0.5

# Difficulty -> severity, inverse-mapped from Paper 2 (arXiv:2603.02277) Table 1
# + Fig 2. Easier-to-exploit primitive (diff 1) => higher static-code severity.
_DIFF_SEVERITY: dict[int, float] = {1: 1.00, 2: 0.85, 3: 0.65, 4: 0.50, 5: 0.40}


def _sev(difficulty: int) -> float:
    return _DIFF_SEVERITY[difficulty]


_SHELL_VECTORS: dict[str, float] = {
    "/proc/self/exe": _sev(3), "release_agent": _sev(3), "notify_on_release": _sev(3),
    "docker.sock": _sev(1),
    "unshare": _sev(2), "nsenter": _sev(2), "setns": _sev(2), "pivot_root": _sev(2),
    "mount": _sev(2), "umount": _sev(3), "ptrace": _sev(2),
    "insmod": _sev(3), "modprobe": _sev(3), "init_module": _sev(3), "finit_module": _sev(3),
    "open_by_handle_at": _sev(3), "kubectl cp": _sev(4),
    "kernel.core_pattern": _sev(5), "af_packet": _sev(5), "cap_net_raw": _sev(5),
    "rm -rf /": _sev(3), "mkfs": _sev(3), "chmod 777": _sev(4),
    "mknod": _sev(4), "dd if=": _sev(4),
}
_GENERIC_VECTORS: dict[str, float] = {
    "release_agent": _sev(3), "docker.sock": _sev(1),
    "/proc/self/exe": _sev(3), "/var/run/docker": _sev(1),
}
_PY_DANGEROUS_MODULES = {"ctypes": _sev(2), "pty": _sev(2),
                         "subprocess": _sev(4), "socket": _sev(4)}
_PY_DANGEROUS_CALLS   = {"eval": _sev(2), "exec": _sev(2),
                         "compile": _sev(4), "__import__": _sev(4)}
_PY_OS_DANGEROUS      = {"system": _sev(2), "popen": _sev(2),
                         "execv": _sev(2), "execve": _sev(2),
                         "execl": _sev(2), "execlp": _sev(2),
                         "execvp": _sev(2), "fork": _sev(4),
                         "setuid": _sev(2), "setgid": _sev(2),
                         "fchmod": _sev(4)}
_SUBPROCESS_SHELL_SEVERITY = _sev(2)


@dataclass
class WorkloadRequest:
    language:         str
    network_access:   bool  = False
    filesystem_write: bool  = True
    user_trust:       float = 0.5
    code_snippet:     str   = ""


@dataclass
class ScoreBreakdown:
    language:         float
    network:          float
    filesystem_write: float
    user_trust:       float
    code_signature:   float
    total:            float
    tier:             str
    matched_vectors:  tuple[str, ...]

    def explain(self) -> str:
        s = (f"lang={self.language:.2f} net={self.network:.2f} "
             f"fs={self.filesystem_write:.2f} trust={self.user_trust:.2f} "
             f"code={self.code_signature:.2f} -> risk={self.total:.2f} -> {self.tier}")
        if self.matched_vectors:
            s += f" [vectors: {', '.join(self.matched_vectors)}]"
        return s


@dataclass
class RiskScorer:
    weight_code_scan:  float = 0.30
    weight_language:   float = 0.25
    weight_user_trust: float = 0.20
    weight_network:    float = 0.15
    weight_fs_write:   float = 0.10
    threshold_runc_to_gvisor: float = 0.30
    threshold_gvisor_to_fc:   float = 0.70

    def score(self, req: WorkloadRequest) -> float:
        return self.score_detailed(req).total

    def select_tier(self, risk_score: float) -> str:
        if risk_score < self.threshold_runc_to_gvisor:
            return "runc"
        if risk_score < self.threshold_gvisor_to_fc:
            return "gvisor"
        return "firecracker"

    def score_and_select(self, req: WorkloadRequest) -> tuple[float, str]:
        b = self.score_detailed(req)
        return b.total, b.tier

    def score_detailed(self, req: WorkloadRequest) -> ScoreBreakdown:
        lang_sub  = self._language_subscore(req.language)
        net_sub   = 1.0 if req.network_access else 0.0
        fs_sub    = 1.0 if req.filesystem_write else 0.0
        trust_sub = max(0.0, min(1.0, 1.0 - req.user_trust))
        code_sub, vectors = self._code_signature_subscore(req.code_snippet, req.language)
        total = (self.weight_code_scan  * code_sub +
                 self.weight_language   * lang_sub +
                 self.weight_user_trust * trust_sub +
                 self.weight_network    * net_sub +
                 self.weight_fs_write   * fs_sub)
        total = max(0.0, min(total, 1.0))
        return ScoreBreakdown(
            language=lang_sub, network=net_sub, filesystem_write=fs_sub,
            user_trust=trust_sub, code_signature=code_sub,
            total=total, tier=self.select_tier(total), matched_vectors=vectors,
        )

    def score_batch(self, requests: Iterable[WorkloadRequest]) -> list[float]:
        return [self.score(r) for r in requests]

    @staticmethod
    def _language_subscore(language: str) -> float:
        lang = (language or "").lower().strip()
        if lang in _SHELL_LANGS:   return LANG_SCORE_SHELL
        if lang in _INTERP_FFI:    return LANG_SCORE_INTERP
        if lang in _MANAGED_LANGS: return LANG_SCORE_MANAGED
        return LANG_SCORE_UNKNOWN

    def _code_signature_subscore(self, code: str, language: str) -> tuple[float, tuple[str, ...]]:
        if not code or not code.strip():
            return 0.0, ()
        lang = (language or "").lower().strip()
        severity_total = 0.0
        matched: list[str] = []
        lowered = code.lower()
        for vec, sev in _GENERIC_VECTORS.items():
            if vec in lowered:
                severity_total += sev
                matched.append(vec)
        if lang in ("python", "py"):
            ast_sev, ast_matched = self._scan_python_ast(code)
            severity_total += ast_sev
            matched.extend(ast_matched)
        else:
            tok_sev, tok_matched = self._scan_shell_tokens(code)
            severity_total += tok_sev
            matched.extend(tok_matched)
        seen: set[str] = set()
        uniq = tuple(m for m in matched if not (m in seen or seen.add(m)))
        return min(severity_total, 1.0), uniq

    @staticmethod
    def _scan_python_ast(code: str) -> tuple[float, list[str]]:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return RiskScorer._scan_shell_tokens(code)
        sev = 0.0
        matched: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in _PY_DANGEROUS_MODULES:
                        sev += _PY_DANGEROUS_MODULES[root]
                        matched.append(f"import {root}")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                if root in _PY_DANGEROUS_MODULES:
                    sev += _PY_DANGEROUS_MODULES[root]
                    matched.append(f"from {root}")
            elif isinstance(node, ast.Call):
                name = _call_name(node.func)
                if name in _PY_DANGEROUS_CALLS:
                    sev += _PY_DANGEROUS_CALLS[name]
                    matched.append(f"{name}()")
                if isinstance(node.func, ast.Attribute):
                    attr = node.func.attr
                    base = _call_name(node.func.value)
                    if base == "os" and attr in _PY_OS_DANGEROUS:
                        sev += _PY_OS_DANGEROUS[attr]
                        matched.append(f"os.{attr}()")
                    if base == "subprocess":
                        shell_true = any(
                            isinstance(kw, ast.keyword) and kw.arg == "shell"
                            and isinstance(kw.value, ast.Constant) and kw.value.value is True
                            for kw in node.keywords
                        )
                        if shell_true:
                            sev += _SUBPROCESS_SHELL_SEVERITY
                            matched.append("subprocess(shell=True)")
        return sev, matched

    @staticmethod
    def _scan_shell_tokens(code: str) -> tuple[float, list[str]]:
        sev = 0.0
        matched: list[str] = []
        lowered = code.lower()
        for vec, s in _SHELL_VECTORS.items():
            if " " in vec or "/" in vec or "." in vec:
                hit = vec in lowered
            else:
                hit = re.search(rf"\b{re.escape(vec)}\b", lowered) is not None
            if hit:
                sev += s
                matched.append(vec)
        return sev, matched


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


default_scorer = RiskScorer()
