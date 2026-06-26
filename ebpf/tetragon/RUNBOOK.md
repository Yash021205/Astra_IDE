# B2 — eBPF telemetry capture (Tetragon): setup & verify

Captures kernel telemetry from ASTRA workspace pods and exports the JSON event
stream that `ml/telemetry/aggregator.py` consumes (→ scheduler features + the B4
IDS syscall stream).

> **Linux-kernel only** (eBPF). Run on the **GCP VM / WSL2 / college Linux PC**,
> not the Windows dev box. The processing layers (`ml/telemetry/`) + their tests
> run anywhere; this runbook is just for the live capture.

## 1. Install Tetragon on the cluster
```bash
helm repo add cilium https://helm.cilium.io
helm install tetragon cilium/tetragon -n kube-system
kubectl rollout status -n kube-system ds/tetragon
```

## 2. Apply the ASTRA tracing policy
```bash
kubectl apply -f ebpf/tetragon/workspace-tracing-policy.yaml
```

## 3. Stream events (and export for the aggregator)
```bash
# live, human-readable:
kubectl exec -n kube-system ds/tetragon -c tetragon -- \
  tetra getevents -o compact --pods <workspace-pod>

# JSON export to feed ml/telemetry/aggregator.py:
kubectl exec -n kube-system ds/tetragon -c tetragon -- \
  tetra getevents -o json > /tmp/astra-events.jsonl
```

## 4. Process into features + IDS syscall stream (anywhere, incl. Windows)
```python
import json
from ml.telemetry.aggregator import Event, aggregate, syscall_stream
evs = []
for line in open("/tmp/astra-events.jsonl"):
    e = json.loads(line)
    pe = e.get("process_kprobe") or e.get("process_exec")
    if not pe: continue
    p = pe["process"]
    evs.append(Event(ts_ms=..., pid=int(p["pid"]), comm=p["binary"],
                     syscall=pe.get("function_name","")))
windows = aggregate(evs)                 # → scheduler features (state_vector())
seq = syscall_stream(windows)            # → feed ml.anomaly_ids (B4 IDS)
```

## What this delivers
- **Scheduler state inputs (B1):** per-window cpu/disk/net/run-queue/active from
  `WindowFeatures.state_vector()` at 500 ms resolution (report §6.1).
- **First-party syscall corpus (B4 IDS):** `syscall_stream()` is exactly the
  integer-sequence format the LID-DS/ADFA pipeline used — so ASTRA can finally run
  the Paper-3 IDS on its *own* 2025 data (the fix noted in the B4 IDS benchmark).
- **Per-PID Top-K (eHashPipe):** feed per-PID cpu_ns/bytes into `HashPipe.update()`
  for the live top consumers, in bounded memory.
