"""
B2 — eBPF telemetry processing.

Pure, testable layers under the (Linux-only) eBPF capture:
  hashpipe.py   — HashPipe sketch for per-PID Top-K CPU/memory (eHashPipe)
  aggregator.py — raw events → 500ms scheduler features + syscall stream for IDS

The in-kernel capture (Tetragon TracingPolicy) lives in ebpf/tetragon/.
"""
from ml.telemetry.hashpipe import HashPipe, topk_precision
from ml.telemetry.aggregator import Event, WindowFeatures, aggregate, syscall_stream

__all__ = [
    "HashPipe", "topk_precision",
    "Event", "WindowFeatures", "aggregate", "syscall_stream",
]
