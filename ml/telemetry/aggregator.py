"""
B2 — telemetry aggregator: turn a raw eBPF event stream (Tetragon/libbpf style)
into the two things ASTRA needs:
  * 500 ms-windowed NODE features for the B1 scheduler state (cpu_util, disk_io,
    net_bw, run_queue proxy, active processes) — the report's eBPF state inputs;
  * a per-window SYSCALL-NAME SEQUENCE for the B4 graph IDS (same format the
    LID-DS pipeline consumes) — i.e. B2 is what produces ASTRA's first-party
    syscall corpus.

Pure/testable; the in-kernel capture that produces these events is in
ebpf/tetragon/ (Linux only).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

WINDOW_MS = 500


@dataclass
class Event:
    ts_ms:     float
    pid:       int
    comm:      str
    syscall:   str
    cpu_ns:    float = 0.0      # on-CPU time attributed to this event
    bytes_io:  float = 0.0      # disk bytes
    bytes_net: float = 0.0      # network bytes


@dataclass
class WindowFeatures:
    t_start_ms:   float
    cpu_util:     float         # 0..1 (fraction of core-time used)
    disk_io_kbps: float
    net_bw_mbps:  float
    run_queue:    float         # proxy: mean concurrent active PIDs
    active_pids:  int
    syscalls:     List[str] = field(default_factory=list)  # ordered, for the IDS

    def state_vector(self) -> List[float]:
        """The eBPF-derived slice of the scheduler state (report §6.1)."""
        return [self.cpu_util, self.disk_io_kbps, self.net_bw_mbps,
                self.run_queue, float(self.active_pids)]


def aggregate(events: List[Event], window_ms: int = WINDOW_MS,
              n_cores: int = 4) -> List[WindowFeatures]:
    """Bucket events into fixed windows and compute per-window features."""
    if not events:
        return []
    events = sorted(events, key=lambda e: e.ts_ms)
    t0 = events[0].ts_ms
    out: List[WindowFeatures] = []
    bucket: List[Event] = []
    win_idx = 0

    def _flush(idx: int, evs: List[Event]) -> None:
        if not evs:
            return
        win_s = window_ms / 1000.0
        cpu = sum(e.cpu_ns for e in evs) / (window_ms * 1e6 * max(1, n_cores))
        diskk = sum(e.bytes_io for e in evs) / win_s / 1024.0
        netm = sum(e.bytes_net for e in evs) / win_s / 1e6 * 8.0
        pids = {e.pid for e in evs}
        out.append(WindowFeatures(
            t_start_ms=t0 + idx * window_ms,
            cpu_util=min(1.0, cpu),
            disk_io_kbps=round(diskk, 2),
            net_bw_mbps=round(netm, 4),
            run_queue=round(len(evs) / max(1, len(pids)), 2),
            active_pids=len(pids),
            syscalls=[e.syscall for e in evs if e.syscall],
        ))

    for e in events:
        idx = int((e.ts_ms - t0) // window_ms)
        if idx != win_idx:
            _flush(win_idx, bucket)
            bucket = []
            win_idx = idx
        bucket.append(e)
    _flush(win_idx, bucket)
    return out


def syscall_stream(windows: List[WindowFeatures]) -> List[int]:
    """Flatten windows into a single syscall-ID sequence (vocab built on the fly)
    ready for ml.anomaly_ids embedding (the B4 IDS). Returns integer IDs."""
    vocab: dict = {}
    seq: List[int] = []
    for w in windows:
        for name in w.syscalls:
            seq.append(vocab.setdefault(name, len(vocab) + 1))
    return seq
