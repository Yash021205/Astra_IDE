"""
Risk Scorer — maps workload + user context to a sandbox tier.

Tier selection model (from Section 6.4 of the project spec):
  risk < 0.30   →  runc          (low overhead, trusted code)
  risk < 0.70   →  gVisor        (user-space kernel, medium overhead)
  risk >= 0.70  →  Firecracker   (microVM, hardware isolation)

The risk score is a weighted sum of dimensions that historically correlate with
container-escape and abuse:
  - language risk    (shell-class languages enable host-level commands)
  - network access   (allows exfiltration / scanning)
  - filesystem write (allows persistence + binary drop)
  - user trust       (new / low-reputation users get stronger isolation)
  - code pattern     (static keyword scan for obviously dangerous calls)

This is the canonical implementation used for:
  - offline experiments (ablation studies, threshold tuning)
  - the backend service (workspace creation pipeline)
The backend keeps its own duplicate copy to avoid importing the ml package;
both must stay in sync.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

SANDBOX_TIERS = ("runc", "gvisor", "firecracker")


_DEFAULT_DANGEROUS_LANGS = frozenset({"bash", "sh", "shell", "powershell", "zsh"})

_DEFAULT_SUSPICIOUS_KEYWORDS = (
    # Process / shell escape
    "subprocess",
    "os.system",
    "eval(",
    "exec(",
    "spawn(",
    "Runtime.getRuntime",
    # Filesystem
    "/dev/",
    "mount ",
    "chmod 777",
    "rm -rf /",
    # Network / raw access
    "iptables",
    "raw socket",
    "AF_PACKET",
    # Container escape vectors
    "/proc/self/exe",
    "docker.sock",
)


@dataclass
class WorkloadRequest:
    """All inputs needed to score a workload's risk."""

    language: str
    network_access: bool = False
    filesystem_write: bool = True
    user_trust: float = 0.5
    code_snippet: str = ""


@dataclass
class RiskScorer:
    """
    Configurable risk scorer. Default weights are taken from the project spec
    and sum to 1.0; override for ablation experiments.
    """

    weight_language:   float = 0.30
    weight_network:    float = 0.20
    weight_fs_write:   float = 0.20
    weight_user_trust: float = 0.20
    weight_code_scan:  float = 0.10

    threshold_runc_to_gvisor:   float = 0.30
    threshold_gvisor_to_fc:     float = 0.70

    user_trust_low_cutoff: float = 0.5

    dangerous_langs:     frozenset[str] = field(default_factory=lambda: _DEFAULT_DANGEROUS_LANGS)
    suspicious_keywords: tuple[str, ...] = _DEFAULT_SUSPICIOUS_KEYWORDS

    # ── Scoring ──────────────────────────────────────────────────────────────

    def score(self, req: WorkloadRequest) -> float:
        s = 0.0
        if req.language.lower() in self.dangerous_langs:
            s += self.weight_language
        if req.network_access:
            s += self.weight_network
        if req.filesystem_write:
            s += self.weight_fs_write
        if req.user_trust < self.user_trust_low_cutoff:
            s += self.weight_user_trust
        if self._scan_code(req.code_snippet):
            s += self.weight_code_scan
        return min(s, 1.0)

    def select_tier(self, risk_score: float) -> str:
        if risk_score < self.threshold_runc_to_gvisor:
            return "runc"
        if risk_score < self.threshold_gvisor_to_fc:
            return "gvisor"
        return "firecracker"

    def score_and_select(self, req: WorkloadRequest) -> tuple[float, str]:
        s = self.score(req)
        return s, self.select_tier(s)

    # ── Code scan helper ─────────────────────────────────────────────────────

    def _scan_code(self, code: str) -> bool:
        if not code:
            return False
        lowered = code.lower()
        return any(kw in lowered for kw in self.suspicious_keywords)

    # ── Bulk / batch convenience ─────────────────────────────────────────────

    def score_batch(self, requests: Iterable[WorkloadRequest]) -> list[float]:
        return [self.score(r) for r in requests]
